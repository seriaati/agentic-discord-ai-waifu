from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields


class Migration(migrations.Migration):
    dependencies = [("models", "0009_auto_20260704_2108")]

    initial = False

    operations = [
        ops.AddField(
            model_name="User",
            name="timezone",
            field=fields.CharField(default="Asia/Taipei", db_default="Asia/Taipei", max_length=64),
        )
    ]
