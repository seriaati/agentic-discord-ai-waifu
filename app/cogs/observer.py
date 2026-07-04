import time
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger

from app.core.embeds import DefaultEmbed
from app.db.models import Observation, User
from app.services.memory import add_observation, get_or_create_user
from app.types import Interaction  # noqa: TC001

if TYPE_CHECKING:
    from collections.abc import Iterable

    from discord.activity import ActivityTypes

    from app.core.bot import MyBot

SHOW_LIMIT = 15
RATE_LIMIT_SECONDS = 600


def _activity_detail(activity: ActivityTypes) -> str:
    """Rich-presence details/state (e.g. "Competitive - Dust II; In a match"), if published."""
    details: str | None = getattr(activity, "details", None)
    state: str | None = getattr(activity, "state", None)
    parts = [part for part in (details, state) if part]
    return f" ({'; '.join(parts)})" if parts else ""


def _activity_summaries(activities: Iterable[ActivityTypes]) -> set[str]:
    summaries: set[str] = set()
    for activity in activities:
        if isinstance(activity, discord.Spotify):
            summaries.add(
                f"正在聽 Spotify: {activity.title} - {activity.artist} (專輯: {activity.album})"
            )
        elif activity.type is discord.ActivityType.playing and activity.name:
            summaries.add(f"開始玩 {activity.name}{_activity_detail(activity)}")
        elif activity.type is discord.ActivityType.listening and activity.name:
            summaries.add(f"正在聽 {activity.name}{_activity_detail(activity)}")
        elif activity.type is discord.ActivityType.watching and activity.name:
            summaries.add(f"正在看 {activity.name}{_activity_detail(activity)}")
    return summaries


class ObserverCog(commands.Cog):
    observe = app_commands.Group(name="observe", description="管理觀察功能與觀察紀錄")

    def __init__(self, bot: MyBot) -> None:
        self.bot = bot
        self._last_write: dict[int, float] = {}

    async def _record(self, discord_id: int, kind: str, summary: str) -> None:
        now = time.monotonic()
        last = self._last_write.get(discord_id)
        if last is not None and now - last < RATE_LIMIT_SECONDS:
            return

        user = await User.get_or_none(discord_id=discord_id)
        if user is None or not user.observe_opt_in:
            return

        newest = await Observation.filter(user=user).order_by("-created_at").first()
        if newest is not None and newest.summary == summary:
            return

        await add_observation(user, kind, summary)
        self._last_write[discord_id] = now
        logger.debug(f"Recorded {kind} observation for {discord_id}: {summary}")

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member) -> None:
        if after.bot:
            return
        new_summaries = _activity_summaries(after.activities) - _activity_summaries(
            before.activities
        )
        if not new_summaries:
            return
        await self._record(after.id, "presence", min(new_summaries))

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        if member.bot or before.channel == after.channel:
            return
        if after.channel is not None:
            summary = f"加入語音頻道 {after.channel.name}"
        else:
            summary = f"離開語音頻道 {before.channel.name}"  # pyright: ignore[reportOptionalMemberAccess]
        await self._record(member.id, "voice", summary)

    @observe.command(name="on", description="開啟觀察功能 (記錄你的遊戲、音樂與語音動態)")
    async def observe_on(self, i: Interaction) -> None:
        user = await get_or_create_user(i.user.id)
        user.observe_opt_in = True
        await user.save(update_fields=["observe_opt_in"])
        embed = DefaultEmbed(
            title="觀察功能已開啟",
            description="我會開始記錄你的遊戲、Spotify 與語音頻道動態\n"
            "使用 `/observe show` 查看紀錄, `/observe off` 隨時關閉",
        )
        await i.response.send_message(embed=embed, ephemeral=True)

    @observe.command(name="off", description="關閉觀察功能")
    async def observe_off(self, i: Interaction) -> None:
        user = await get_or_create_user(i.user.id)
        user.observe_opt_in = False
        await user.save(update_fields=["observe_opt_in"])
        embed = DefaultEmbed(
            title="觀察功能已關閉",
            description="我不會再記錄你的動態\n已儲存的紀錄可以用 `/observe clear` 刪除",
        )
        await i.response.send_message(embed=embed, ephemeral=True)

    @observe.command(name="show", description="查看關於你的觀察紀錄")
    async def observe_show(self, i: Interaction) -> None:
        observations = (
            await Observation.filter(user__discord_id=i.user.id)
            .order_by("-created_at")
            .limit(SHOW_LIMIT)
        )
        if observations:
            lines = "\n".join(
                f"- {obs.summary} ({discord.utils.format_dt(obs.created_at, 'R')})"
                for obs in observations
            )
            embed = DefaultEmbed(
                title=f"最近的觀察紀錄 ({len(observations)} 筆)", description=lines
            )
        else:
            embed = DefaultEmbed(title="沒有觀察紀錄", description="目前沒有任何關於你的觀察紀錄")
        await i.response.send_message(embed=embed, ephemeral=True)

    @observe.command(name="clear", description="刪除所有關於你的觀察紀錄")
    async def observe_clear(self, i: Interaction) -> None:
        deleted = await Observation.filter(user__discord_id=i.user.id).delete()
        embed = DefaultEmbed(title="觀察紀錄已刪除", description=f"已刪除 {deleted} 筆觀察紀錄")
        await i.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: MyBot) -> None:
    await bot.add_cog(ObserverCog(bot))
