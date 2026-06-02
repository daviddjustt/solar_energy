# solar/notifications/migrations/0001_initial.py
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    # Dependências: garante que as tabelas de Projetos e Usuários já existam no banco
    # antes da tabela de notificações ser criada.
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('documents', '0001_initial'), 
    ]

    operations = [
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),                ('title', models.CharField(max_length=150, verbose_name='Título')),
                ('message', models.TextField(verbose_name='Conteúdo/Mensagem')),
                ('category', models.CharField(default='GENERAL', max_length=50, verbose_name='Categoria')),
                ('is_read', models.BooleanField(default=False, verbose_name='Lida?')),
                ('read_at', models.DateTimeField(blank=True, null=True, verbose_name='Lida em')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                
                # Chave Estrangeira para o Projeto
                ('project', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, 
                    related_name='notifications', 
                    to='documents.clientproject', 
                    verbose_name='Projeto Relacionado'
                )),
                
                # Chave Estrangeira para o Remetente (pode ser nulo se for o sistema)
                ('sender', models.ForeignKey(
                    blank=True, 
                    null=True, 
                    on_delete=django.db.models.deletion.SET_NULL, 
                    related_name='sent_notifications', 
                    to=settings.AUTH_USER_MODEL, 
                    verbose_name='Remetente'
                )),
                
                # Chave Estrangeira para o Destinatário
                ('recipient', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, 
                    related_name='received_notifications', 
                    to=settings.AUTH_USER_MODEL, 
                    verbose_name='Destinatário'
                )),
            ],
            options={
                'verbose_name': 'Notificação',
                'verbose_name_plural': 'Notificações',
                'ordering': ['-created_at'],
            },
        ),
        
        # Adicionando os índices de performance que definimos no Model
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['recipient', 'is_read'], name='notif_recipient_is_read_idx'),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['project'], name='notif_project_idx'),
        ),
    ]