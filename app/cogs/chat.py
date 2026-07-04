from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from loguru import logger

from app.agent import generate_reply
from app.db.models import Persona
from app.services.memory import get_or_create_user
from app.services.webhook import send_as_persona

if TYPE_CHECKING:
    from app.core.bot import MyBot

DISCORD_MESSAGE_LIMIT = 2000
HISTORY_LIMIT = 20


async def _build_history(message: discord.Message) -> str | None:
    """Format the last few channel messages as a transcript, oldest first."""
    try:
        lines = [
            f"{msg.author.display_name}: {msg.content.strip()}"
            async for msg in message.channel.history(limit=HISTORY_LIMIT, before=message)
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
        user.last_channel_id = message.channel.id
        await user.save(update_fields=["last_channel_id"])

        try:
            history = await _build_history(message)
            reply = await generate_reply(prompt, user=user, persona=persona, history=history)
        except Exception:
            logger.exception("Failed to generate reply")
            await message.reply("抱歉, 我現在沒辦法回應, 請稍後再試一次")
            return

        content = reply[:DISCORD_MESSAGE_LIMIT] or "..."
        if not await send_as_persona(message.channel, persona, content):
            await message.reply(content)


async def setup(bot: MyBot) -> None:
    await bot.add_cog(Chat(bot))
