import datetime
import random
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks
from loguru import logger

from app.agent.proactive import decide_proactive_message, generate_time_based_message
from app.core.embeds import DefaultEmbed
from app.db.models import Observation, User
from app.services.memory import get_or_create_user
from app.services.webhook import send_as_persona
from app.types import Interaction  # noqa: TC001
from app.utils.misc import get_utc8_now

if TYPE_CHECKING:
    from app.agent.proactive import TimeTriggerKind
    from app.core.bot import MyBot
    from app.db.models import Persona

LOOP_MINUTES = 15
QUIET_HOURS_START = 23  # UTC+8
QUIET_HOURS_END = 9
OBSERVATION_MAX_AGE = datetime.timedelta(hours=2)
COOLDOWN = datetime.timedelta(hours=6)
USERS_PER_TICK = 3
OBSERVATIONS_PER_USER = 10
DISCORD_MESSAGE_LIMIT = 2000

MINUTES_PER_DAY = 24 * 60
GREETING_WINDOW_MINUTES = 60  # greet within an hour of wake/sleep time
RECENT_CHAT_GRACE = datetime.timedelta(hours=1)  # no greeting if they just chatted
CHECKIN_MIN_IDLE = datetime.timedelta(hours=3)
AFTERNOON_START_HOUR = 12  # UTC+8
AFTERNOON_END_HOUR = 14
AFTERNOON_CHANCE = 0.05  # per tick -> a few afternoons per week
CHECKIN_CHANCE = 0.01  # per tick -> roughly once every couple of days

# Greetings are capped once per day via these date fields instead of COOLDOWN.
GREETING_DATE_FIELDS: dict[str, str] = {
    "morning": "last_morning_greeting",
    "afternoon": "last_afternoon_greeting",
    "night": "last_night_greeting",
}


def _minute_of_day(t: datetime.time) -> int:
    return t.hour * 60 + t.minute


class ProactiveCog(commands.Cog):
    proactive = app_commands.Group(name="proactive", description="管理主動訊息功能")

    def __init__(self, bot: MyBot) -> None:
        self.bot = bot
        self.tick.start()

    async def cog_unload(self) -> None:
        self.tick.cancel()

    @tasks.loop(minutes=LOOP_MINUTES)
    async def tick(self) -> None:
        now = get_utc8_now()
        quiet = now.hour >= QUIET_HOURS_START or now.hour < QUIET_HOURS_END

        # Schedule-anchored greetings run even in quiet hours (they follow the
        # user's own wake/sleep times); everything else respects them.
        await self._time_based_pass(now, quiet=quiet)
        if quiet:
            return

        # Oldest unhandled observation first -> deterministic user order.
        observations = (
            await Observation.filter(
                handled=False,
                created_at__gte=now - OBSERVATION_MAX_AGE,
                user__proactive_opt_in=True,
                user__last_persona_id__isnull=False,
            )
            .order_by("created_at")
            .prefetch_related("user__last_persona")
        )
        candidates: dict[int, User] = {}
        for obs in observations:
            candidates.setdefault(obs.user.id, obs.user)

        selected = [
            user
            for user in candidates.values()
            if user.last_proactive_at is None or now - user.last_proactive_at >= COOLDOWN
        ][:USERS_PER_TICK]

        for user in selected:
            try:
                await self._process_user(user, now)
            except Exception:
                logger.exception(f"Proactive processing failed for user {user.discord_id}")

    @tick.before_loop
    async def before_tick(self) -> None:
        await self.bot.wait_until_ready()

    async def _time_based_pass(self, now: datetime.datetime, *, quiet: bool) -> None:
        users = await User.filter(
            proactive_opt_in=True, last_persona_id__isnull=False
        ).prefetch_related("last_persona")
        for user in users:
            trigger = self._due_time_trigger(user, now, quiet=quiet)
            if trigger is None:
                continue
            kind, mark_date = trigger
            try:
                await self._send_time_based(user, kind, mark_date, now)
            except Exception:
                logger.exception(f"Time-based proactive failed for user {user.discord_id}")

    def _due_time_trigger(
        self, user: User, now: datetime.datetime, *, quiet: bool
    ) -> tuple[TimeTriggerKind, datetime.date | None] | None:
        """Pick the time-based trigger due for `user`, with the date to mark it done."""
        if user.last_chat_at is not None and now - user.last_chat_at < RECENT_CHAT_GRACE:
            return None
        minute = _minute_of_day(now.time())

        if user.wake_time is not None:
            # Modular math so windows crossing midnight key to the wake/sleep
            # moment's date, not today's.
            elapsed = (minute - _minute_of_day(user.wake_time)) % MINUTES_PER_DAY
            if elapsed <= GREETING_WINDOW_MINUTES:
                wake_date = (now - datetime.timedelta(minutes=elapsed)).date()
                if user.last_morning_greeting != wake_date:
                    return "morning", wake_date

        if user.sleep_time is not None:
            remaining = (_minute_of_day(user.sleep_time) - minute) % MINUTES_PER_DAY
            if remaining <= GREETING_WINDOW_MINUTES:
                sleep_date = (now + datetime.timedelta(minutes=remaining)).date()
                if user.last_night_greeting != sleep_date:
                    return "night", sleep_date

        if (
            AFTERNOON_START_HOUR <= now.hour < AFTERNOON_END_HOUR
            and user.last_afternoon_greeting != now.date()
            and random.random() < AFTERNOON_CHANCE
        ):
            return "afternoon", now.date()

        cooldown_ok = user.last_proactive_at is None or now - user.last_proactive_at >= COOLDOWN
        idle_ok = user.last_chat_at is None or now - user.last_chat_at >= CHECKIN_MIN_IDLE
        if not quiet and cooldown_ok and idle_ok and random.random() < CHECKIN_CHANCE:
            return "checkin", None

        return None

    async def _send_time_based(
        self,
        user: User,
        kind: TimeTriggerKind,
        mark_date: datetime.date | None,
        now: datetime.datetime,
    ) -> None:
        persona = user.last_persona
        if persona is None:
            return

        try:
            message = await generate_time_based_message(user, persona, kind)
        finally:
            # Mark greetings done even on SKIP so we don't re-ask the model every tick.
            field = GREETING_DATE_FIELDS.get(kind)
            if field is not None and mark_date is not None:
                setattr(user, field, mark_date)
                await user.save(update_fields=[field])

        if message is None:
            logger.info(f"Time-based agent chose to skip {kind} for user {user.discord_id}")
            return
        await self._deliver(user, persona, message, now)

    async def _process_user(self, user: User, now: datetime.datetime) -> None:
        observations = (
            await Observation.filter(
                user=user, handled=False, created_at__gte=now - OBSERVATION_MAX_AGE
            )
            .order_by("-created_at")
            .limit(OBSERVATIONS_PER_USER)
        )
        if not observations:
            return

        persona = user.last_persona
        if persona is None:
            return

        try:
            message = await decide_proactive_message(user, persona, observations)
        finally:
            await Observation.filter(id__in=[obs.id for obs in observations]).update(handled=True)

        if message is None:
            logger.info(f"Proactive agent chose to skip user {user.discord_id}")
            return
        await self._deliver(user, persona, message, now)

    async def _deliver(
        self, user: User, persona: Persona, message: str, now: datetime.datetime
    ) -> None:
        channel = self.bot.get_channel(persona.channel_id)
        if channel is None or not isinstance(channel, discord.abc.Messageable):
            logger.info(f"Proactive channel {persona.channel_id} unavailable, skipping")
            return

        content = message[:DISCORD_MESSAGE_LIMIT]
        if not await send_as_persona(channel, persona, content):
            await channel.send(content)
        user.last_proactive_at = now
        await user.save(update_fields=["last_proactive_at"])
        logger.info(f"Sent proactive message to user {user.discord_id} in {persona.channel_id}")

    @proactive.command(name="on", description="開啟主動訊息功能")
    async def proactive_on(self, i: Interaction) -> None:
        user = await get_or_create_user(i.user.id)
        user.proactive_opt_in = True
        await user.save(update_fields=["proactive_opt_in"])
        embed = DefaultEmbed(
            title="主動訊息功能已開啟",
            description="我偶爾會在你最後與角色對話的頻道主動找你聊天\n"
            "使用 `/proactive off` 隨時關閉",
        )
        await i.response.send_message(embed=embed, ephemeral=True)

    @proactive.command(name="off", description="關閉主動訊息功能")
    async def proactive_off(self, i: Interaction) -> None:
        user = await get_or_create_user(i.user.id)
        user.proactive_opt_in = False
        await user.save(update_fields=["proactive_opt_in"])
        embed = DefaultEmbed(title="主動訊息功能已關閉", description="我不會再主動傳訊息給你")
        await i.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: MyBot) -> None:
    await bot.add_cog(ProactiveCog(bot))
