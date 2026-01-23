# Generated manually to fix rank field name if it was already created

from django.db import migrations, models


def noop(apps, schema_editor):
    """아무 작업도 하지 않음"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('installbase', '0042_fix_other_ips_null'),
    ]

    operations = [
        # 만약 rank 컬럼이 이미 존재한다면 user_rank로 변경
        migrations.RunSQL(
            sql="ALTER TABLE installbase_userprofile RENAME COLUMN rank TO user_rank;",
            reverse_sql="ALTER TABLE installbase_userprofile RENAME COLUMN user_rank TO rank;",
        ),
        # 또는 필드가 아직 없다면 그냥 넘어감
        migrations.RunPython(noop, noop),
    ]
