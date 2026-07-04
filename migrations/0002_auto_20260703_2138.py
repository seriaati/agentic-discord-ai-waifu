from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields


class Migration(migrations.Migration):
    dependencies = [("models", "0001_initial")]

    initial = False

    operations = [
        ops.CreateModel(
            name="User",
            fields=[
                (
                    "id",
                    fields.IntField(generated=True, primary_key=True, unique=True, db_index=True),
                ),
                ("discord_id", fields.BigIntField(unique=True, db_index=True)),
                ("last_channel_id", fields.BigIntField(null=True)),
                ("observe_opt_in", fields.BooleanField(default=False)),
                ("proactive_opt_in", fields.BooleanField(default=False)),
                ("created_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={"table": "user", "app": "models", "pk_attr": "id"},
            bases=["Model"],
        ),
        ops.CreateModel(
            name="Fact",
            fields=[
                (
                    "id",
                    fields.IntField(generated=True, primary_key=True, unique=True, db_index=True),
                ),
                (
                    "user",
                    fields.ForeignKeyField(
                        "models.User",
                        source_field="user_id",
                        db_constraint=True,
                        to_field="id",
                        related_name="facts",
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ("content", fields.TextField(unique=False)),
                ("created_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={"table": "fact", "app": "models", "pk_attr": "id"},
            bases=["Model"],
        ),
        ops.CreateModel(
            name="ImportantDate",
            fields=[
                (
                    "id",
                    fields.IntField(generated=True, primary_key=True, unique=True, db_index=True),
                ),
                (
                    "user",
                    fields.ForeignKeyField(
                        "models.User",
                        source_field="user_id",
                        db_constraint=True,
                        to_field="id",
                        related_name="important_dates",
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ("label", fields.CharField(max_length=100)),
                ("date", fields.DateField()),
                ("created_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={"table": "importantdate", "app": "models", "pk_attr": "id"},
            bases=["Model"],
        ),
        ops.CreateModel(
            name="Observation",
            fields=[
                (
                    "id",
                    fields.IntField(generated=True, primary_key=True, unique=True, db_index=True),
                ),
                (
                    "user",
                    fields.ForeignKeyField(
                        "models.User",
                        source_field="user_id",
                        db_constraint=True,
                        to_field="id",
                        related_name="observations",
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
                ("kind", fields.CharField(max_length=32)),
                ("summary", fields.TextField(unique=False)),
                ("handled", fields.BooleanField(default=False)),
                ("created_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={"table": "observation", "app": "models", "pk_attr": "id"},
            bases=["Model"],
        ),
    ]
