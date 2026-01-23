# Generated manually

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('installbase', '0040_remove_installbase_warranty_end_date'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('avatar_seed', models.CharField(blank=True, default='', help_text='DiceBear API에서 사용할 시드 값', max_length=100, verbose_name='아바타 시드')),
                ('user_rank', models.CharField(choices=[('researcher', '연구원'), ('senior_researcher', '선임연구원'), ('chief_researcher', '책임연구원'), ('lead_researcher', '수석연구원'), ('team_leader', '팀장'), ('division_head', '사업부장')], db_column='rank', default='researcher', max_length=20, verbose_name='직급')),
                ('is_resigned', models.BooleanField(default=False, verbose_name='퇴사 여부')),
                ('resigned_date', models.DateField(blank=True, null=True, verbose_name='퇴사일')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profile', to=settings.AUTH_USER_MODEL, verbose_name='사용자')),
            ],
            options={
                'verbose_name': '사용자 프로필',
                'verbose_name_plural': '사용자 프로필',
            },
        ),
    ]
