# Generated by Django 5.1.7 on 2025-05-23 13:24

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0008_alter_historicaluser_sac_profile_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserExport',
            fields=[
            ],
            options={
                'verbose_name': 'Exportação de Usuários',
                'verbose_name_plural': 'Exportações de Usuários',
                'proxy': True,
                'indexes': [],
                'constraints': [],
            },
            bases=('users.user',),
        ),
        migrations.DeleteModel(
            name='HistoricalUser',
        ),
    ]
