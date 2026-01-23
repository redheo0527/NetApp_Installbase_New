# Generated manually to fix rank field name if it was already created

from django.db import migrations


def fix_rank_column_if_exists(apps, schema_editor):
    """만약 rank 컬럼이 이미 존재한다면 user_rank로 변경"""
    from django.db import connection
    try:
        with connection.cursor() as cursor:
            # 컬럼 존재 여부 확인
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='installbase_userprofile' 
                AND column_name='rank';
            """)
            if cursor.fetchone():
                # rank 컬럼이 존재하면 user_rank로 변경
                cursor.execute("ALTER TABLE installbase_userprofile RENAME COLUMN \"rank\" TO user_rank;")
    except Exception as e:
        # 이미 user_rank로 되어 있거나 다른 오류인 경우 무시
        pass


def reverse_fix_rank_column(apps, schema_editor):
    """롤백 시 user_rank를 rank로 변경 (실제로는 사용하지 않음)"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('installbase', '0042_fix_other_ips_null'),
    ]

    operations = [
        migrations.RunPython(fix_rank_column_if_exists, reverse_fix_rank_column),
    ]
