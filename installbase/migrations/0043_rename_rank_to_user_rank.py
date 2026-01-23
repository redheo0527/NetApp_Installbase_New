# Generated manually to fix PostgreSQL rank reserved word issue

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('installbase', '0042_fix_other_ips_null'),
    ]

    operations = [
        migrations.RenameField(
            model_name='userprofile',
            old_name='rank',
            new_name='user_rank',
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='user_rank',
            field=models.CharField(choices=[('researcher', '연구원'), ('senior_researcher', '선임연구원'), ('chief_researcher', '책임연구원'), ('lead_researcher', '수석연구원'), ('team_leader', '팀장'), ('division_head', '사업부장')], db_column='rank', default='researcher', max_length=20, verbose_name='직급'),
        ),
    ]
