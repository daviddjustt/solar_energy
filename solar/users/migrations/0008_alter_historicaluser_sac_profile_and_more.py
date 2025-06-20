# Generated by Django 5.1.7 on 2025-05-15 12:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0007_historicaluser_is_sac_historicaluser_sac_profile_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='historicaluser',
            name='sac_profile',
            field=models.CharField(blank=True, choices=[('SEM_ACESSO', 'Sem Acesso'), ('LEITOR', 'Leitor'), ('ANALISTA', 'Analista'), ('FOCAL', 'Focal')], max_length=10, null=True, verbose_name='Perfil SAC'),
        ),
        migrations.AlterField(
            model_name='user',
            name='sac_profile',
            field=models.CharField(blank=True, choices=[('SEM_ACESSO', 'Sem Acesso'), ('LEITOR', 'Leitor'), ('ANALISTA', 'Analista'), ('FOCAL', 'Focal')], max_length=10, null=True, verbose_name='Perfil SAC'),
        ),
    ]
