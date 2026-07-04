from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields


class Migration(migrations.Migration):
    dependencies = [("models", "0006_auto_20260703_2312")]

    initial = False

    operations = [
        # Add nullable first so existing rows can be backfilled from channel_id.
        ops.AddField(
            model_name="Reminder",
            name="persona",
            field=fields.ForeignKeyField(
                "models.Persona",
                source_field="persona_id",
                null=True,
                db_constraint=True,
                to_field="id",
                related_name="reminders",
                on_delete=OnDelete.CASCADE,
            ),
        ),
        ops.RunSQL(
            sql=[
                'UPDATE "reminder" r SET "persona_id" = p."id" '
                'FROM "persona" p, "user" u '
                'WHERE r."user_id" = u."id" AND p."discord_id" = u."discord_id" '
                'AND p."channel_id" = r."channel_id"',
                # Reminders whose persona no longer exists cannot be delivered as anyone.
                'DELETE FROM "reminder" WHERE "persona_id" IS NULL',
            ],
            reverse_sql=[],
        ),
        ops.AlterField(
            model_name="Reminder",
            name="persona",
            field=fields.ForeignKeyField(
                "models.Persona",
                source_field="persona_id",
                db_constraint=True,
                to_field="id",
                related_name="reminders",
                on_delete=OnDelete.CASCADE,
            ),
        ),
        ops.RemoveField(model_name="Reminder", name="channel_id"),
        ops.AddField(
            model_name="User",
            name="last_persona",
            field=fields.ForeignKeyField(
                "models.Persona",
                source_field="last_persona_id",
                null=True,
                db_constraint=True,
                to_field="id",
                related_name=False,
                on_delete=OnDelete.SET_NULL,
            ),
        ),
        ops.RunSQL(
            sql=[
                'UPDATE "user" u SET "last_persona_id" = p."id" '
                'FROM "persona" p '
                'WHERE p."discord_id" = u."discord_id" AND p."channel_id" = u."last_channel_id"'
            ],
            reverse_sql=[],
        ),
        ops.RemoveField(model_name="User", name="last_channel_id"),
    ]
