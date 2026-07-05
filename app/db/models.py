from tortoise import fields
from tortoise.models import Model

from app.constants import DEFAULT_TIMEZONE


class Persona(Model):
    id = fields.IntField(primary_key=True)
    discord_id = fields.BigIntField(db_index=True)
    guild_id = fields.BigIntField(db_index=True)
    channel_id = fields.BigIntField()
    name = fields.CharField(max_length=80)  # Discord webhook username limit
    avatar_url = fields.TextField(null=True)
    personality = fields.TextField()
    facts = fields.TextField(null=True)
    context_cleared_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        unique_together = (("discord_id", "channel_id"),)


class DiaryEntry(Model):
    id = fields.IntField(primary_key=True)
    persona: fields.ForeignKeyRelation[Persona] = fields.ForeignKeyField(
        "models.Persona", related_name="diary_entries"
    )
    date = fields.DateField()  # the user's local day; set from get_user_now(user).date()
    content = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        unique_together = (("persona", "date"),)


class User(Model):
    id = fields.IntField(primary_key=True)
    discord_id = fields.BigIntField(unique=True, db_index=True)
    last_persona: fields.ForeignKeyNullableRelation[Persona] = fields.ForeignKeyField(
        "models.Persona", related_name=False, null=True, on_delete=fields.OnDelete.SET_NULL
    )
    observe_opt_in = fields.BooleanField(default=False)
    proactive_opt_in = fields.BooleanField(default=False)
    last_proactive_at = fields.DatetimeField(null=True)
    last_chat_at = fields.DatetimeField(null=True)
    timezone = fields.CharField(
        max_length=64, default=DEFAULT_TIMEZONE, db_default=DEFAULT_TIMEZONE
    )  # IANA name
    wake_time = fields.TimeField(null=True)  # user-local wall clock
    sleep_time = fields.TimeField(null=True)  # user-local wall clock
    last_morning_greeting = fields.DateField(null=True)  # date of the wake moment greeted
    last_afternoon_greeting = fields.DateField(null=True)
    last_night_greeting = fields.DateField(null=True)  # date of the sleep moment greeted
    created_at = fields.DatetimeField(auto_now_add=True)


class Fact(Model):
    id = fields.IntField(primary_key=True)
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="facts"
    )
    content = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)


class ImportantDate(Model):
    id = fields.IntField(primary_key=True)
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="important_dates"
    )
    label = fields.CharField(max_length=100)
    date = fields.DateField()
    created_at = fields.DatetimeField(auto_now_add=True)


class Reminder(Model):
    id = fields.IntField(primary_key=True)
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="reminders"
    )
    persona: fields.ForeignKeyRelation[Persona] = fields.ForeignKeyField(
        "models.Persona", related_name="reminders"
    )
    content = fields.TextField()
    due_at = fields.DatetimeField(db_index=True)
    delivered = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)


class Observation(Model):
    id = fields.IntField(primary_key=True)
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User", related_name="observations"
    )
    kind = fields.CharField(max_length=32)  # e.g. "presence", "voice"
    summary = fields.TextField()
    handled = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
