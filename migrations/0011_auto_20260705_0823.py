from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields


class Migration(migrations.Migration):
    dependencies = [("models", "0010_auto_20260704_2311")]

    initial = False

    operations = [
        ops.AddField(
            model_name="Persona",
            name="diary_enabled",
            field=fields.BooleanField(default=True, db_default=True),
        )
    ]
