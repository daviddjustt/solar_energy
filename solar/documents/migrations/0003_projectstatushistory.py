from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        # Ancora  rigidamente na sua última migração segura
        ('documents', '0002_clientproject_observacoes'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProjectStatusHistory',
            fields=[
                # O Django exige a criação manual do ID quando fazemos na mão
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('changed_by_uuid', models.CharField(blank=True, max_length=255, null=True, verbose_name='UUID do Usuário')),
                ('old_status', models.CharField(max_length=100, verbose_name='Status Antigo')),
                ('new_status', models.CharField(max_length=100, verbose_name='Status Novo')),
                ('changed_at', models.DateTimeField(auto_now_add=True, verbose_name='Data e Hora da Mudança')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='status_history', to='documents.clientproject')),
            ],
            options={
                'verbose_name': 'Histórico de Status',
                'verbose_name_plural': 'Históricos de Status',
                'ordering': ['-changed_at'],
            },
        ),
    ]