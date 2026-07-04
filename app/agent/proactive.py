from typing import TYPE_CHECKING, Literal

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from app.agent.chat import WEB_TOOL_NAMES
from app.core.settings import SETTINGS
from app.services.memory import build_memory_context
from app.utils.misc import get_utc8_now, to_traditional_chinese

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.db.models import Observation, Persona, User

TimeTriggerKind = Literal["morning", "afternoon", "night", "checkin"]

PROACTIVE_INSTRUCTIONS = (
    "You observed the following recent activity from your companion user. "
    "Decide if a short, natural, non-intrusive message is worth sending. "
    "Most of the time it is NOT — reply with exactly SKIP if unsure, if the activity is "
    "mundane, or if you have nothing genuinely relevant to add. Never mention that you are "
    "observing them; speak naturally, e.g. comment on the game they started playing. "
    "If you do send a message, write it in Traditional Chinese and keep it short."
)

TIME_TRIGGER_INSTRUCTIONS: dict[TimeTriggerKind, str] = {
    "morning": (
        "Your companion user should be waking up around now. Send them a short, warm "
        "good-morning message. You may naturally weave in something you know about them "
        "— an upcoming date, yesterday's diary, their plans. Write in Traditional Chinese "
        "and keep it short. Reply with exactly SKIP only if greeting them truly makes no "
        "sense right now."
    ),
    "afternoon": (
        "It is early afternoon. Send your companion user a short, casual midday greeting "
        "— a light hello, hoping their day is going well. Write in Traditional Chinese "
        "and keep it short. Reply with exactly SKIP only if greeting them truly makes no "
        "sense right now."
    ),
    "night": (
        "Your companion user usually goes to sleep around now. Send them a short, warm "
        "good-night message. Write in Traditional Chinese and keep it short. Reply with "
        "exactly SKIP only if greeting them truly makes no sense right now."
    ),
    "checkin": (
        "You have not talked with your companion user in a while and feel like checking "
        "in. Casually ask what they are up to or how their day is going — keep it light "
        "and natural, in Traditional Chinese, and short. Reply with exactly SKIP if "
        "reaching out right now would feel forced or repetitive given what you know."
    ),
}


def _relative_time(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} minutes ago"
    return f"{minutes // 60} hours ago"


async def _build_system_prompt(user: User, persona: Persona | None, instructions: str) -> str:
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
    return system_prompt + instructions


async def _query_or_skip(system_prompt: str, prompt: str) -> str | None:
    """Run a one-shot agent turn; None means the agent chose to stay silent."""
    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=SETTINGS.chat_model,
        strict_mcp_config=True,
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
    # Fuse: the model occasionally drifts into Simplified Chinese; force Traditional.
    return to_traditional_chinese(result)


async def decide_proactive_message(
    user: User, persona: Persona | None, observations: Sequence[Observation]
) -> str | None:
    """Ask the agent whether to proactively message `user`; None means stay silent."""
    system_prompt = await _build_system_prompt(user, persona, PROACTIVE_INSTRUCTIONS)

    now = get_utc8_now()
    prompt = "\n".join(
        f"- [{obs.kind}] {obs.summary} "
        f"({_relative_time(max(int((now - obs.created_at).total_seconds() // 60), 0))})"
        for obs in observations
    )
    return await _query_or_skip(system_prompt, prompt)


async def generate_time_based_message(
    user: User, persona: Persona, kind: TimeTriggerKind
) -> str | None:
    """Generate a greeting/check-in for `user`; None means the agent chose to skip."""
    system_prompt = await _build_system_prompt(user, persona, TIME_TRIGGER_INSTRUCTIONS[kind])
    prompt = f"Current time: {get_utc8_now():%Y-%m-%d %H:%M (%A)} (UTC+8)."
    return await _query_or_skip(system_prompt, prompt)
