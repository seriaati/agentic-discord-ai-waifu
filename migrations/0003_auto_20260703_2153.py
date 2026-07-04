from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields


class Migration(migrations.Migration):
    dependencies = [("models", "0002_auto_20260703_2138")]

    initial = False

    operations = [
        ops.AddField(
            model_name="User",
            name="last_proactive_at",
            field=fields.DatetimeField(null=True, auto_now=False, auto_now_add=False),
        )
    ]
