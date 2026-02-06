# Generated manually to fix null values in other_ips field

from django.db import migrations, models


def fix_other_ips_null(apps, schema_editor):
    """기존 null 값을 빈 문자열로 변경"""
    InstallBase = apps.get_model('installbase', 'InstallBase')
    InstallBase.objects.filter(other_ips__isnull=True).update(other_ips='')


class Migration(migrations.Migration):

    dependencies = [
        ('installbase', '0041_userprofile'),
    ]

    operations = [
        # 먼저 null 값을 빈 문자열로 변경
        migrations.RunPython(fix_other_ips_null, migrations.RunPython.noop),
        # 그 다음 필드에 null=True 추가 (이미 모델에 추가됨)
        migrations.AlterField(
            model_name='installbase',
            name='other_ips',
            field=models.TextField(blank=True, null=True, verbose_name='그 외 IP'),
        ),
    ]
