import asyncio
import re
import shlex
from typing import TYPE_CHECKING

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, McpServerConfig, ResultMessage

from app.agent.tools import DIARY_TOOL_NAMES, MEMORY_TOOL_NAMES, create_memory_server
from app.core.settings import SETTINGS
from app.services.memory import build_memory_context
from app.utils.misc import get_utc8_now

if TYPE_CHECKING:
    from app.db.models import Persona, User

SYSTEM_PROMPT = (
    "You are a companion chatting with users on a Discord server. "
    "This is most likely a text role-play conversation, not an AI-assistant-style "
    "conversation, unless your persona configuration explicitly says you are an "
    "assistant. Try your very best to satisfy whatever demand or requirement the "
    "user has, as long as it aligns with your given persona - never go out of "
    "character. Keep replies concise and conversational, short enough for a "
    "Discord message. Never prefix your reply with your own name (e.g. `Name:`); "
    "output only the message body.\n\n"
    "You have these tools available to assist the user:\n"
    "- WebSearch: search the web for current information.\n"
    "- WebFetch: fetch and read a specific web page.\n"
)
if SETTINGS.browser_enabled:
    SYSTEM_PROMPT += (
        "- Playwright browser tools (browser_navigate, browser_click, ...): drive a "
        "real headless browser for pages that need JavaScript or interaction; prefer "
        "WebSearch/WebFetch when they suffice.\n"
    )
SYSTEM_PROMPT += "Use tools naturally within the conversation without describing their mechanics."

WEB_TOOL_NAMES = ["WebSearch", "WebFetch"]

# `--isolated` keeps concurrent queries from fighting over one browser profile.
_BROWSER_MCP_COMMAND = shlex.split(SETTINGS.browser_mcp_command)
BROWSER_MCP_SERVERS: dict[str, McpServerConfig] = (
    {
        "playwright": {
            "command": _BROWSER_MCP_COMMAND[0],
            "args": [*_BROWSER_MCP_COMMAND[1:], "--headless", "--isolated"],
        }
    }
    if SETTINGS.browser_enabled
    else {}
)
# "mcp__playwright" (no tool suffix) allows every tool from that server.
BROWSER_TOOL_NAMES = ["mcp__playwright"] if SETTINGS.browser_enabled else []

MEMORY_INSTRUCTIONS = (
    "\n\nWhen the user states a lasting preference or personal fact about themselves, "
    "call the remember_fact tool to save it. When they mention a birthday, anniversary, "
    "or other important date, call the remember_date tool. When they mention their usual "
    "wake-up time or bedtime, call the set_schedule tool. Do not announce that you are "
    "saving memories; just keep chatting naturally. When the user asks to be reminded of "
    "something, call the set_reminder tool with the absolute UTC+8 time, then confirm briefly."
)

DIARY_INSTRUCTIONS = (
    "\n\nYou keep a private diary about you and this user; your recent entries may appear "
    "above. When something noteworthy happens in the conversation — an event in their life, "
    "a strong mood, something you did together — call write_diary to extend today's entry. "
    "Use read_diary to look up older days when the past is relevant. Never announce that you "
    "are writing in or reading your diary."
)


async def _wait_for_browser_server(client: ClaudeSDKClient) -> None:
    """Block until the Playwright MCP server connects, so its tools reach the model.

    The CLI connects MCP servers asynchronously; without this wait the first
    (and, for one-shot replies, only) turn races the connection and the model
    never sees the browser tools. Connection normally takes under a second.
    """
    for _ in range(50):  # ~10s ceiling
        status = await client.get_mcp_status()
        playwright = next((s for s in status["mcpServers"] if s["name"] == "playwright"), None)
        if playwright is None or playwright["status"] != "pending":
            return
        await asyncio.sleep(0.2)


async def generate_reply(
    prompt: str,
    *,
    user: User | None = None,
    persona: Persona | None = None,
    history: str | None = None,
) -> str:
    """Generate a chat reply for a single user message."""
    if history:
        prompt = (
            "Recent messages in this channel (oldest first), in `Name: message` format. "
            "The name prefixes are transcript formatting only.\n"
            f"<history>\n{history}\n</history>\n\n"
            f"The user's new message:\n{prompt}\n\n"
            "Reply with your message content only. Do NOT prefix your reply with your "
            "name or any `Name:` label."
        )

    system_prompt = SYSTEM_PROMPT
    if persona is not None:
        system_prompt += (
            f"\n\nYour name is {persona.name}. Stay in character with the personality "
            f'defined below.\n<persona name="{persona.name}">\n{persona.personality}\n</persona>'
        )
        if persona.facts:
            system_prompt += f"\n\nImportant facts about you:\n{persona.facts}"

    if user is not None:
        memory_context = await build_memory_context(user, persona)
        if memory_context:
            system_prompt += f"\n\n{memory_context}"
        system_prompt += f"\n\nCurrent time: {get_utc8_now():%Y-%m-%d %H:%M} (UTC+8)."
        system_prompt += MEMORY_INSTRUCTIONS
        allowed_tools = [*MEMORY_TOOL_NAMES, *WEB_TOOL_NAMES, *BROWSER_TOOL_NAMES]
        if persona is not None:
            system_prompt += DIARY_INSTRUCTIONS
            allowed_tools += DIARY_TOOL_NAMES
        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            model=SETTINGS.chat_model,
            mcp_servers={"memory": create_memory_server(user, persona), **BROWSER_MCP_SERVERS},
            strict_mcp_config=True,
            tools=WEB_TOOL_NAMES,
            allowed_tools=allowed_tools,
        )
    else:
        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            model=SETTINGS.chat_model,
            mcp_servers=BROWSER_MCP_SERVERS,
            strict_mcp_config=True,
            tools=WEB_TOOL_NAMES,
            allowed_tools=[*WEB_TOOL_NAMES, *BROWSER_TOOL_NAMES],
        )

    result_text = ""
    async with ClaudeSDKClient(options=options) as client:
        if SETTINGS.browser_enabled:
            await _wait_for_browser_server(client)
        await client.query(prompt)
        async for message in client.receive_response():
            if isinstance(message, ResultMessage) and message.result:
                result_text = message.result

    result_text = result_text.strip()
    if persona is not None:
        # Fuse: the model occasionally still echoes the transcript's `Name:` prefix.
        # Match both halfwidth and fullwidth colons.
        result_text = re.sub(rf"^{re.escape(persona.name)}\s*[:：]\s*", "", result_text)  # noqa: RUF001
    return result_text
