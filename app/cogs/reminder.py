from typing import TYPE_CHECKING

import discord
from discord.ext import commands, tasks
from loguru import logger

from app.db.models import Persona, Reminder
from app.services.webhook import send_as_persona
from app.utils.misc import get_utc8_now

if TYPE_CHECKING:
    from app.core.bot import MyBot

LOOP_SECONDS = 30
DISCORD_MESSAGE_LIMIT = 2000


class ReminderCog(commands.Cog):
    def __init__(self, bot: MyBot) -> None:
        self.bot = bot
        self.tick.start()

    async def cog_unload(self) -> None:
        self.tick.cancel()

    @tasks.loop(seconds=LOOP_SECONDS)
    async def tick(self) -> None:
        due = (
            await Reminder.filter(delivered=False, due_at__lte=get_utc8_now())
            .order_by("due_at")
            .prefetch_related("user")
        )
        for reminder in due:
            try:
                await self._deliver(reminder)
            except Exception:
                logger.exception(f"Failed to deliver reminder {reminder.id}")
            finally:
                # Mark delivered even on failure so a broken reminder can't retry forever.
                reminder.delivered = True
                await reminder.save(update_fields=["delivered"])

    @tick.before_loop
    async def before_tick(self) -> None:
        await self.bot.wait_until_ready()

    async def _deliver(self, reminder: Reminder) -> None:
        channel = self.bot.get_channel(reminder.channel_id)
        if channel is None or not isinstance(channel, discord.abc.Messageable):
            logger.info(f"Reminder channel {reminder.channel_id} unavailable, skipping")
            return

        content = f"<@{reminder.user.discord_id}> ⏰ {reminder.content}"[:DISCORD_MESSAGE_LIMIT]
        persona = await Persona.get_or_none(
            discord_id=reminder.user.discord_id, channel_id=reminder.channel_id
        )
        if persona is None or not await send_as_persona(channel, persona, content):
            await channel.send(content)
        logger.info(f"Delivered reminder {reminder.id} to user {reminder.user.discord_id}")


async def setup(bot: MyBot) -> None:
    await bot.add_cog(ReminderCog(bot))
