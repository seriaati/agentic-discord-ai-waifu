import datetime

from app.db.models import DiaryEntry, Fact, ImportantDate, Observation, Persona, Reminder, User
from app.utils.misc import get_utc8_now

FACT_LIMIT = 20
OBSERVATION_LIMIT = 10
DIARY_CONTEXT_DAYS = 5
DIARY_RANGE_MAX_DAYS = 31


async def get_or_create_user(discord_id: int) -> User:
    user, _ = await User.get_or_create(discord_id=discord_id)
    return user


async def add_fact(user: User, content: str) -> Fact:
    return await Fact.create(user=user, content=content)


async def save_schedule(
    user: User, wake_time: datetime.time | None, sleep_time: datetime.time | None
) -> None:
    updates: list[str] = []
    if wake_time is not None:
        user.wake_time = wake_time
        updates.append("wake_time")
    if sleep_time is not None:
        user.sleep_time = sleep_time
        updates.append("sleep_time")
    if updates:
        await user.save(update_fields=updates)


async def add_important_date(user: User, label: str, date: datetime.date) -> ImportantDate:
    return await ImportantDate.create(user=user, label=label, date=date)


async def add_reminder(
    user: User, content: str, due_at: datetime.datetime, persona: Persona
) -> Reminder:
    return await Reminder.create(user=user, content=content, due_at=due_at, persona=persona)


async def add_observation(user: User, kind: str, summary: str) -> Observation:
    return await Observation.create(user=user, kind=kind, summary=summary)


async def append_diary(persona: Persona, content: str) -> DiaryEntry:
    """Extend today's diary entry for `persona`, creating it if this is the first write."""
    today = get_utc8_now().date()
    entry = await DiaryEntry.get_or_none(persona=persona, date=today)
    if entry is None:
        return await DiaryEntry.create(persona=persona, date=today, content=content)
    entry.content += f"\n{content}"
    await entry.save()
    return entry


async def get_diary_entries(
    persona: Persona, start: datetime.date, end: datetime.date
) -> list[DiaryEntry]:
    return await DiaryEntry.filter(persona=persona, date__gte=start, date__lte=end).order_by("date")


def _days_until(date: datetime.date, today: datetime.date) -> int:
    for year in (today.year, today.year + 1):
        try:
            occurrence = date.replace(year=year)
        except ValueError:  # Feb 29 on a non-leap year
            occurrence = datetime.date(year, 3, 1)
        if occurrence >= today:
            return (occurrence - today).days
    return 0


async def build_memory_context(user: User, persona: Persona | None = None) -> str:
    facts = await Fact.filter(user=user).order_by("-created_at").limit(FACT_LIMIT)
    dates = await ImportantDate.filter(user=user).order_by("date")
    observations = (
        await Observation.filter(user=user)
        .order_by("handled", "-created_at")
        .limit(OBSERVATION_LIMIT)
    )
    diary_entries: list[DiaryEntry] = []
    if persona is not None:
        diary_entries = (
            await DiaryEntry.filter(persona=persona).order_by("-date").limit(DIARY_CONTEXT_DAYS)
        )[::-1]
    if not (facts or dates or observations or diary_entries or user.wake_time or user.sleep_time):
        return ""

    today = get_utc8_now().date()
    sections: list[str] = []
    if user.wake_time or user.sleep_time:
        parts: list[str] = []
        if user.wake_time:
            parts.append(f"usually wakes up around {user.wake_time:%H:%M}")
        if user.sleep_time:
            parts.append(f"usually goes to sleep around {user.sleep_time:%H:%M}")
        sections.append(f"This user's daily schedule: {', '.join(parts)} (UTC+8).")
    if facts:
        lines = "\n".join(f"- {fact.content}" for fact in facts)
        sections.append(f"Known facts about this user (newest first):\n{lines}")
    if dates:
        lines = "\n".join(
            f"- {entry.label}: {entry.date.isoformat()} (in {_days_until(entry.date, today)} days)"
            for entry in dates
        )
        sections.append(f"Important dates for this user:\n{lines}")
    if observations:
        lines = "\n".join(f"- [{obs.kind}] {obs.summary}" for obs in observations)
        sections.append(f"Recent observations about this user:\n{lines}")
    if diary_entries:
        lines = "\n\n".join(
            f"[{entry.date.isoformat()}]\n{entry.content}" for entry in diary_entries
        )
        sections.append(f"Your recent diary entries about this user:\n{lines}")

    header = (
        "Background memory about this user, for your awareness only. Let it inform "
        "your tone and what you know; do not turn it into advice or reminders, and "
        "never repeat a reminder that already appears in the recent conversation."
    )
    return "\n\n".join([header, *sections])
