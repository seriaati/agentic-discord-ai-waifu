from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from discord.abc import Messageable

    from app.db.models import Persona

WEBHOOK_NAME = "WaifuHook"

_webhook_cache: dict[int, discord.Webhook] = {}


async def _get_webhook(channel: discord.TextChannel) -> discord.Webhook | None:
    """Get the managed webhook for a channel, creating it if missing."""
    cached = _webhook_cache.get(channel.id)
    if cached is not None:
        return cached

    try:
        webhook = discord.utils.get(await channel.webhooks(), name=WEBHOOK_NAME)
        if webhook is None:
            webhook = await channel.create_webhook(name=WEBHOOK_NAME)
    except discord.Forbidden:
        return None

    _webhook_cache[channel.id] = webhook
    return webhook


async def send_as_persona(channel: Messageable, persona: Persona, content: str) -> bool:
    """Send a message through a channel webhook using the persona's identity.

    Returns False if the channel doesn't support webhooks (e.g. DMs) or the bot
    lacks the Manage Webhooks permission; the caller should fall back to a normal reply.
    """
    thread = discord.utils.MISSING
    target = channel
    if isinstance(channel, discord.Thread):
        thread = channel
        target = channel.parent

    if not isinstance(target, discord.TextChannel):
        return False

    webhook = await _get_webhook(target)
    if webhook is None:
        return False

    await webhook.send(
        content,
        username=persona.name,
        avatar_url=persona.avatar_url or discord.utils.MISSING,
        thread=thread,
    )
    return True
