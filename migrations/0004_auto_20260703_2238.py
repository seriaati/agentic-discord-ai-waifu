from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields
from tortoise.migrations.constraints import UniqueConstraint


class Migration(migrations.Migration):
    dependencies = [("models", "0003_auto_20260703_2153")]

    initial = False

    operations = [
        # Personas become per-channel; old global rows have no channel to bind to.
        ops.RunSQL('DELETE FROM "persona";', reverse_sql=""),
        ops.AlterField(
            model_name="Persona", name="discord_id", field=fields.BigIntField(db_index=True)
        ),
        ops.AddField(model_name="Persona", name="channel_id", field=fields.BigIntField()),
        ops.AddField(
            model_name="Persona", name="facts", field=fields.TextField(null=True, unique=False)
        ),
        ops.AddField(
            model_name="Persona", name="guild_id", field=fields.BigIntField(db_index=True)
        ),
        ops.AddConstraint(
            model_name="Persona",
            constraint=UniqueConstraint(fields=("discord_id", "channel_id"), name=None),
        ),
    ]
