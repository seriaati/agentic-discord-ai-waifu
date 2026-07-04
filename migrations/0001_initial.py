from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise import fields


class Migration(migrations.Migration):
    initial = True

    operations = [
        ops.CreateModel(
            name="Persona",
            fields=[
                (
                    "id",
                    fields.IntField(generated=True, primary_key=True, unique=True, db_index=True),
                ),
                ("discord_id", fields.BigIntField(unique=True, db_index=True)),
                ("name", fields.CharField(max_length=80)),
                ("avatar_url", fields.TextField(null=True, unique=False)),
                ("personality", fields.TextField(unique=False)),
                ("created_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ("updated_at", fields.DatetimeField(auto_now=True, auto_now_add=False)),
            ],
            options={"table": "persona", "app": "models", "pk_attr": "id"},
            bases=["Model"],
        )
    ]
