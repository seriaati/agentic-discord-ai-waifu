import datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks
from loguru import logger

from app.agent.proactive import decide_proactive_message
from app.core.embeds import DefaultEmbed
from app.db.models import Observation, User
from app.services.memory import get_or_create_user
from app.services.webhook import send_as_persona
from app.types import Interaction  # noqa: TC001
from app.utils.misc import get_utc8_now

if TYPE_CHECKING:
    from app.core.bot import MyBot

LOOP_MINUTES = 15
QUIET_HOURS_START = 23  # UTC+8
QUIET_HOURS_END = 9
OBSERVATION_MAX_AGE = datetime.timedelta(hours=2)
COOLDOWN = datetime.timedelta(hours=6)
USERS_PER_TICK = 3
OBSERVATIONS_PER_USER = 10
DISCORD_MESSAGE_LIMIT = 2000


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
        if now.hour >= QUIET_HOURS_START or now.hour < QUIET_HOURS_END:
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
