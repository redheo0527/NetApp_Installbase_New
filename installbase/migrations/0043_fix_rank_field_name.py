# Generated manually to fix rank field name if it was already created

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('installbase', '0042_fix_other_ips_null'),
    ]

    operations = [
        # 0041에서 이미 user_rank로 생성되었으므로 추가 작업 불필요
        # 만약 서버에서 rank로 생성되었다면 수동으로 다음 SQL 실행:
        # ALTER TABLE installbase_userprofile RENAME COLUMN rank TO user_rank;
    ]
