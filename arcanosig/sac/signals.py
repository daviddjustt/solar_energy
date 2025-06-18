from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string

from .models import (
    RelatorioInteligencia, 
    TipoRelatorio, 
    RelatorioInteligenciaChangeLog,
)

User = get_user_model()

@receiver(post_save, sender=RelatorioInteligencia)
def enviar_email_para_usuarios_sac(sender, instance, created, **kwargs):
    """
    Envia um e-mail para todos os usuários com a flag is_sac=True
    quando um relatório é adicionado por um usuário com perfil FOCAL.
    O e-mail será personalizado de acordo com o tipo do relatório.
    """
    if created and instance.focal and instance.focal.sac_profile == 'FOCAL':
        # Recupera todos os usuários com is_sac=True
        usuarios_sac = User.objects.filter(is_sac=True)

        # Lista de e-mails dos usuários
        emails = [usuario.email for usuario in usuarios_sac if usuario.email]

        # Envia o e-mail
        if emails:
            # Define o assunto do e-mail conforme o tipo de relatório
            if instance.tipo == TipoRelatorio.FINAL:
                assunto = 'Novo Relatório Final de Inteligência Adicionado'
                template = 'email/novo_relatorio_final.html'
            else:
                assunto = 'Novo Relatório Preliminar de Inteligência Adicionado'
                template = 'email/novo_relatorio_preliminar.html'

            # Obtem os quantitativos não-zero
            quantitativos = instance.get_quantitativos_nao_zero()

            # Renderiza o template de e-mail
            email_content = render_to_string(template, {
                'focal_name': instance.focal.name,
                'tipo_relatorio': instance.get_tipo_display(),
                'numero_ano': instance.numero_ano,
                'quantitativos': quantitativos,
                'tem_quantitativos': bool(quantitativos)
            })

            send_mail(
                subject=assunto,
                message=f'Um novo relatório {instance.get_tipo_display()} foi adicionado.',  # Texto alternativo
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=emails,
                fail_silently=False,
                html_message=email_content,  # Envia o HTML renderizado
            )

receiver(pre_save, sender=RelatorioInteligencia)
def pre_save_relatorio_inteligencia(sender, instance, **kwargs):
    """Armazena o estado original da instância antes da alteração."""
    if instance.pk: # Verifica se a instância já existe (não é uma criação)
        try:
            # Busca a instância original no banco de dados
            original_instance = sender.objects.get(pk=instance.pk)
            # Armazena a instância original temporariamente no objeto atual
            instance._original_instance = original_instance
        except sender.DoesNotExist:
            # Isso pode acontecer se o objeto foi deletado entre a busca e o pre_save,
            # ou em casos raros. Tratamos como se não houvesse original.
            instance._original_instance = None
    else:
        instance._original_instance = None # Não há original para novas instâncias

@receiver(post_save, sender=RelatorioInteligencia)
def post_save_relatorio_inteligencia(sender, instance, created, **kwargs):
    """Cria um log de alteração após a criação ou atualização de um relatório."""
    user = kwargs.get('user', None)
    if user and not isinstance(user, User):
         user = None


    if created:
        # Log de Criação
        RelatorioInteligenciaChangeLog.objects.create(
            relatorio=instance,
            changed_by=user,
            change_type='create',
        )
        print(f"Log: Relatório '{instance}' criado por {user or 'Usuário Desconhecido'}")

    else:
        # Log de Atualização
        original_instance = getattr(instance, '_original_instance', None)

        if original_instance:
            changed_fields = {}
            # Itera sobre os campos do modelo para encontrar o que mudou
            for field in sender._meta.fields:
                field_name = field.name
                if field_name in ['id', 'changed_at', 'created_at']: # Adicione outros campos a ignorar se necessário
                    continue

                old_value = getattr(original_instance, field_name)
                new_value = getattr(instance, field_name)

                # Compara os valores. Trata casos de relacionamentos ForeignKey
                if field.remote_field: # É um relacionamento (ForeignKey, OneToOne)
                    old_value_display = str(old_value) if old_value else ''
                    new_value_display = str(new_value) if new_value else ''
                    if old_value != new_value:
                         changed_fields[field_name] = {
                             'old': old_value_display,
                             'new': new_value_display
                         }
                else: # Campo normal
                    # Converte para string para comparação e armazenamento no TextField
                    old_value_str = str(old_value) if old_value is not None else ''
                    new_value_str = str(new_value) if new_value is not None else ''

                    if old_value_str != new_value_str:
                         changed_fields[field_name] = {
                             'old': old_value_str,
                             'new': new_value_str
                         }

            # Cria um log de alteração para cada campo modificado
            if changed_fields:
                 for field_name, values in changed_fields.items():
                     RelatorioInteligenciaChangeLog.objects.create(
                         relatorio=instance,
                         changed_by=user,
                         change_type='update',
                         field_name=field_name,
                         old_value=values['old'],
                         new_value=values['new']
                     )
                     print(f"Log: Relatório '{instance}' - Campo '{field_name}' alterado por {user or 'Usuário Desconhecido'}")
            else:
                 # Loga que houve um save, mas sem alterações detectadas nos campos principais
                 # Isso pode acontecer se apenas campos como 'changed_at' forem atualizados
                 print(f"Log: Relatório '{instance}' salvo sem alterações detectadas nos campos principais por {user or 'Usuário Desconhecido'}")

        # Limpa a instância original armazenada
        if hasattr(instance, '_original_instance'):
            del instance._original_instance

@receiver(post_delete, sender=RelatorioInteligencia)
def post_delete_relatorio_inteligencia(sender, instance, **kwargs):
    """Cria um log de alteração após a exclusão de um relatório."""
    user = kwargs.get('user', None)
    if user and not isinstance(user, User):
         user = None

    relatorio_pk = instance.pk
    relatorio_str = str(instance) # Captura a representação string antes de deletar

    try:
        RelatorioInteligenciaChangeLog.objects.create(
            # relatorio=instance, # Não vincular diretamente se o FK for CASCADE ou se quiser que o log persista
            relatorio=None, # Defina como None se o FK permitir NULL para logs de exclusão
            changed_by=user,
            change_type='delete',
            # Opcional: Armazenar detalhes do relatório deletado nos campos de valor
            field_name='Relatório Deletado',
            old_value=f"PK: {relatorio_pk}", # Armazena o PK antigo
            new_value=f"Representação: {relatorio_str}" # Armazena a representação string
        )
        print(f"Log: Relatório '{relatorio_str}' (PK: {relatorio_pk}) deletado por {user or 'Usuário Desconhecido'}")

    except Exception as e:
        # Loga qualquer erro na criação do log de exclusão
        print(f"Erro ao criar log de exclusão para Relatório PK {relatorio_pk}: {e}")
