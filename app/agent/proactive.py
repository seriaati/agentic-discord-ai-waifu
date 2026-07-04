from typing import TYPE_CHECKING

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from app.agent.chat import WEB_TOOL_NAMES
from app.core.settings import SETTINGS
from app.services.memory import build_memory_context
from app.utils.misc import get_utc8_now

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.db.models import Observation, Persona, User

PROACTIVE_INSTRUCTIONS = (
    "You observed the following recent activity from your companion user. "
    "Decide if a short, natural, non-intrusive message is worth sending. "
    "Most of the time it is NOT — reply with exactly SKIP if unsure, if the activity is "
    "mundane, or if you have nothing genuinely relevant to add. Never mention that you are "
    "observing them; speak naturally, e.g. comment on the game they started playing. "
    "If you do send a message, write it in Traditional Chinese and keep it short."
)


def _relative_time(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} minutes ago"
    return f"{minutes // 60} hours ago"


async def decide_proactive_message(
    user: User, persona: Persona | None, observations: Sequence[Observation]
) -> str | None:
    """Ask the agent whether to proactively message `user`; None means stay silent."""
    system_prompt = ""
    if persona is not None:
        system_prompt += (
            f"Your name is {persona.name}. Stay in character with this personality:\n"
            f"{persona.personality}\n\n"
        )
        if persona.facts:
            system_prompt += f"Important facts about you:\n{persona.facts}\n\n"
    memory_context = await build_memory_context(user, persona)
    if memory_context:
        system_prompt += f"{memory_context}\n\n"
    system_prompt += PROACTIVE_INSTRUCTIONS

    now = get_utc8_now()
    prompt = "\n".join(
        f"- [{obs.kind}] {obs.summary} "
        f"({_relative_time(max(int((now - obs.created_at).total_seconds() // 60), 0))})"
        for obs in observations
    )

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=SETTINGS.chat_model,
        tools=WEB_TOOL_NAMES,
        allowed_tools=WEB_TOOL_NAMES,
    )
    result = ""
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, ResultMessage) and message.result:
            result = message.result

    result = result.strip()
    if not result or result.startswith("SKIP"):
        return None
    return result
