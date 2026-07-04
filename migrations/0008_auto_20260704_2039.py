from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields


class Migration(migrations.Migration):
    dependencies = [("models", "0007_auto_20260704_2020")]

    initial = False

    operations = [
        ops.AddField(
            model_name="User", name="last_afternoon_greeting", field=fields.DateField(null=True)
        ),
        ops.AddField(
            model_name="User",
            name="last_chat_at",
            field=fields.DatetimeField(null=True, auto_now=False, auto_now_add=False),
        ),
        ops.AddField(
            model_name="User", name="last_morning_greeting", field=fields.DateField(null=True)
        ),
        ops.AddField(
            model_name="User", name="last_night_greeting", field=fields.DateField(null=True)
        ),
        ops.AddField(
            model_name="User",
            name="sleep_time",
            field=fields.TimeField(null=True, auto_now=False, auto_now_add=False),
        ),
        ops.AddField(
            model_name="User",
            name="wake_time",
            field=fields.TimeField(null=True, auto_now=False, auto_now_add=False),
        ),
    ]
