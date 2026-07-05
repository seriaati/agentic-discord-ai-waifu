import datetime
from typing import TYPE_CHECKING, Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from app.services.memory import (
    DIARY_RANGE_MAX_DAYS,
    add_fact,
    add_important_date,
    add_reminder,
    append_diary,
    get_diary_entries,
    save_schedule,
)
from app.utils.misc import get_user_now, get_user_tz

if TYPE_CHECKING:
    from claude_agent_sdk.types import McpSdkServerConfig

    from app.db.models import Persona, User

MEMORY_TOOL_NAMES = [
    "mcp__memory__remember_fact",
    "mcp__memory__remember_date",
    "mcp__memory__set_reminder",
    "mcp__memory__set_schedule",
]

DIARY_TOOL_NAMES = ["mcp__memory__write_diary", "mcp__memory__read_diary"]


def create_memory_server(user: User, persona: Persona | None = None) -> McpSdkServerConfig:
    """Build an in-process MCP server whose tools save memories for `user`.

    When `persona` is given and its diary is enabled, diary tools scoped to that
    persona are included too.
    """

    @tool(
        "remember_fact",
        "Save a lasting fact or preference about the user you are talking to.",
        {"content": str},
    )
    async def remember_fact(args: dict[str, Any]) -> dict[str, Any]:
        await add_fact(user, args["content"])
        return {"content": [{"type": "text", "text": "Fact saved."}]}

    @tool(
        "remember_date",
        "Save an important date (birthday, anniversary, ...) for the user you are talking to. "
        "`date` must be ISO-8601 (YYYY-MM-DD).",
        {"label": str, "date": str},
    )
    async def remember_date(args: dict[str, Any]) -> dict[str, Any]:
        try:
            date = datetime.date.fromisoformat(args["date"])
        except ValueError:
            return {
                "content": [{"type": "text", "text": "Invalid date, use YYYY-MM-DD."}],
                "is_error": True,
            }
        await add_important_date(user, args["label"], date)
        return {"content": [{"type": "text", "text": "Date saved."}]}

    @tool(
        "set_reminder",
        "Set a reminder to deliver to the user at a specific time. "
        "`due_at` must be ISO-8601 (YYYY-MM-DD HH:MM) in the user's local timezone; compute "
        "it from the current time given in your instructions. `content` is the reminder message.",
        {"content": str, "due_at": str},
    )
    async def set_reminder(args: dict[str, Any]) -> dict[str, Any]:
        try:
            due_at = datetime.datetime.fromisoformat(args["due_at"])
        except ValueError:
            return {
                "content": [{"type": "text", "text": "Invalid time, use YYYY-MM-DD HH:MM."}],
                "is_error": True,
            }
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=get_user_tz(user))
        if due_at <= get_user_now(user):
            return {
                "content": [{"type": "text", "text": "That time is in the past."}],
                "is_error": True,
            }
        if persona is None:
            return {
                "content": [{"type": "text", "text": "No persona to deliver the reminder to."}],
                "is_error": True,
            }
        await add_reminder(user, args["content"], due_at, persona)
        return {"content": [{"type": "text", "text": f"Reminder set for {due_at:%Y-%m-%d %H:%M}."}]}

    @tool(
        "set_schedule",
        "Save the user's usual wake-up time and/or bedtime when you learn them. "
        "Times must be HH:MM (24-hour) in the user's local timezone; pass an empty "
        "string for one you do not know. Knowing these lets you greet the user good "
        "morning and good night at the right moments.",
        {"wake_time": str, "sleep_time": str},
    )
    async def set_schedule(args: dict[str, Any]) -> dict[str, Any]:
        # TIMETZ needs a concrete offset; readers only use the wall-clock hour/minute.
        local_tz = datetime.timezone(get_user_now(user).utcoffset() or datetime.timedelta())
        times: dict[str, datetime.time | None] = {}
        for key in ("wake_time", "sleep_time"):
            raw = str(args.get(key) or "").strip()
            if not raw:
                times[key] = None
                continue
            try:
                times[key] = datetime.time.fromisoformat(raw).replace(tzinfo=local_tz)
            except ValueError:
                return {
                    "content": [{"type": "text", "text": "Invalid time, use HH:MM."}],
                    "is_error": True,
                }
        if times["wake_time"] is None and times["sleep_time"] is None:
            return {
                "content": [{"type": "text", "text": "Provide at least one time."}],
                "is_error": True,
            }
        await save_schedule(user, times["wake_time"], times["sleep_time"])
        return {"content": [{"type": "text", "text": "Schedule saved."}]}

    tools = [remember_fact, remember_date, set_reminder, set_schedule]
    if persona is not None and persona.diary_enabled:
        tools += _create_diary_tools(user, persona)
    return create_sdk_mcp_server(name="memory", version="1.0.0", tools=tools)


def _create_diary_tools(user: User, persona: Persona) -> list:
    """Build diary tools scoped to `persona`; `user` anchors the local diary day."""

    @tool(
        "write_diary",
        "Append to today's entry in your private diary about you and this user. "
        "Record noteworthy things as they happen — events, their mood, what you did "
        "together. Write in your own voice, past tense, a sentence or two per call; "
        "do not log routine small talk.",
        {"content": str},
    )
    async def write_diary(args: dict[str, Any]) -> dict[str, Any]:
        await append_diary(persona, args["content"], get_user_now(user).date())
        return {"content": [{"type": "text", "text": "Diary updated."}]}

    @tool(
        "read_diary",
        "Read your past diary entries about you and this user for a date range. "
        "`start` and `end` must be ISO-8601 (YYYY-MM-DD); pass the same date for "
        f"both to read a single day. At most {DIARY_RANGE_MAX_DAYS} days per call.",
        {"start": str, "end": str},
    )
    async def read_diary(args: dict[str, Any]) -> dict[str, Any]:
        try:
            start = datetime.date.fromisoformat(args["start"])
            end = datetime.date.fromisoformat(args["end"])
        except ValueError:
            return {
                "content": [{"type": "text", "text": "Invalid date, use YYYY-MM-DD."}],
                "is_error": True,
            }
        if start > end:
            start, end = end, start
        if (end - start).days >= DIARY_RANGE_MAX_DAYS:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Range too large, at most {DIARY_RANGE_MAX_DAYS} days.",
                    }
                ],
                "is_error": True,
            }
        entries = await get_diary_entries(persona, start, end)
        if not entries:
            text = "No diary entries in that range."
        else:
            text = "\n\n".join(f"[{entry.date.isoformat()}]\n{entry.content}" for entry in entries)
        return {"content": [{"type": "text", "text": text}]}

    return [write_diary, read_diary]
