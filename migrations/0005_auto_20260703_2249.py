from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0004_auto_20260703_2238')]

    initial = False

    operations = [
        ops.CreateModel(
            name='Reminder',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('user', fields.ForeignKeyField('models.User', source_field='user_id', db_constraint=True, to_field='id', related_name='reminders', on_delete=OnDelete.CASCADE)),
                ('channel_id', fields.BigIntField()),
                ('content', fields.TextField(unique=False)),
                ('due_at', fields.DatetimeField(db_index=True, auto_now=False, auto_now_add=False)),
                ('delivered', fields.BooleanField(default=False)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={'table': 'reminder', 'app': 'models', 'pk_attr': 'id'},
            bases=['Model'],
        ),
    ]
