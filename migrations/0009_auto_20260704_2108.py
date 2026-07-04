from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields


class Migration(migrations.Migration):
    dependencies = [("models", "0008_auto_20260704_2039")]

    initial = False

    operations = [
        ops.AddField(
            model_name="Persona",
            name="context_cleared_at",
            field=fields.DatetimeField(null=True, auto_now=False, auto_now_add=False),
        )
    ]
