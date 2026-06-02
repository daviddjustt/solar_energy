# Gerado manualmente para criar a tabela ProjectProtocol

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        # Ancora na última migração manual que fizemos
        ('documents', '0003_projectstatushistory'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProjectProtocol',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero_protocolo', models.CharField(blank=True, max_length=100, null=True, verbose_name='Número do Protocolo')),
                ('data_limite', models.DateField(blank=True, null=True, verbose_name='Data Limite')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Data de Criação')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Última Atualização')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='protocolos', to='documents.clientproject', verbose_name='Projeto')),
            ],
            options={
                'verbose_name': 'Protocolo do Projeto',
                'verbose_name_plural': 'Protocolos dos Projetos',
                'ordering': ['-created_at'],
            },
        ),
    ]