from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger

from app.agent import generate_reply
from app.core.embeds import DefaultEmbed, ErrorEmbed
from app.db.models import Persona
from app.services.memory import get_or_create_user
from app.services.webhook import send_as_persona
from app.types import Interaction  # noqa: TC001
from app.utils.misc import get_utc8_now

if TYPE_CHECKING:
    import datetime

    from app.core.bot import MyBot

DISCORD_MESSAGE_LIMIT = 2000
HISTORY_LIMIT = 20


async def _build_history(
    message: discord.Message, *, after: datetime.datetime | None
) -> str | None:
    """Format the last few channel messages as a transcript, oldest first."""
    try:
        lines = [
            f"{msg.author.display_name}: {msg.content.strip()}"
            async for msg in message.channel.history(
                limit=HISTORY_LIMIT, before=message, after=after, oldest_first=False
            )
            if msg.content.strip()
        ]
    except discord.Forbidden:
        return None
    lines.reverse()
    return "\n".join(lines) or None


class Chat(commands.Cog):
    def __init__(self, bot: MyBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return

        persona = await Persona.get_or_none(
            discord_id=message.author.id, channel_id=message.channel.id
        )
        if persona is None:
            return

        prompt = message.content.strip()
        if not prompt:
            return

        user = await get_or_create_user(message.author.id)
        user.last_persona = persona
        user.last_chat_at = get_utc8_now()
        await user.save(update_fields=["last_persona_id", "last_chat_at"])

        try:
            async with message.channel.typing():
                history = await _build_history(message, after=persona.context_cleared_at)
                reply = await generate_reply(prompt, user=user, persona=persona, history=history)
        except Exception:
            logger.exception("Failed to generate reply")
            await message.reply("抱歉, 我現在沒辦法回應, 請稍後再試一次")
            return

        content = reply[:DISCORD_MESSAGE_LIMIT] or "..."
        if not await send_as_persona(message.channel, persona, content):
            await message.reply(content)

    @app_commands.command(name="clear", description="清除對話脈絡, 角色將看不到此指令之前的訊息")
    @app_commands.guild_only()
    async def clear(self, i: Interaction) -> None:
        persona = await Persona.get_or_none(discord_id=i.user.id, channel_id=i.channel_id)
        if persona is None:
            embed = ErrorEmbed(
                title="這個頻道沒有你的角色", description="請先用 `/waifus` 新增角色並綁定這個頻道"
            )
            await i.response.send_message(embed=embed, ephemeral=True)
            return

        persona.context_cleared_at = get_utc8_now()
        await persona.save(update_fields=["context_cleared_at"])
        embed = DefaultEmbed(
            title="對話脈絡已清除",
            description=f"**{persona.name}** 將不會再看到這之前的訊息\n記憶與日記不受影響",
        )
        await i.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: MyBot) -> None:
    await bot.add_cog(Chat(bot))
