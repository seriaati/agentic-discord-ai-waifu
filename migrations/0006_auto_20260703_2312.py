from tortoise import migrations
from tortoise.migrations import operations as ops
from tortoise.fields.base import OnDelete
from tortoise import fields

class Migration(migrations.Migration):
    dependencies = [('models', '0005_auto_20260703_2249')]

    initial = False

    operations = [
        ops.CreateModel(
            name='DiaryEntry',
            fields=[
                ('id', fields.IntField(generated=True, primary_key=True, unique=True, db_index=True)),
                ('persona', fields.ForeignKeyField('models.Persona', source_field='persona_id', db_constraint=True, to_field='id', related_name='diary_entries', on_delete=OnDelete.CASCADE)),
                ('date', fields.DateField()),
                ('content', fields.TextField(unique=False)),
                ('created_at', fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ('updated_at', fields.DatetimeField(auto_now=True, auto_now_add=False)),
            ],
            options={'table': 'diaryentry', 'app': 'models', 'unique_together': (('persona', 'date'),), 'pk_attr': 'id'},
            bases=['Model'],
        ),
    ]
