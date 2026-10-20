# solar/services/notifications.py
from django.db import transaction
from django.contrib.auth import get_user_model
from solar.notifications.models import Notification
from solar.notifications.services import _enviar_payload_websocket, _enviar_email_template

User = get_user_model()

def enviar_notificacao_servico(users, service, mensagem, assunto, categoria):
    if not users:
        return

    notificacoes = []
    for user in users:
        # Usamos recipient e title, que são os campos reais do modelo[cite: 4]
        notificacao = Notification(
            recipient=user,
            title=assunto,
            message=mensagem,
            category=categoria,
            service=service
        )
        notificacoes.append(notificacao)

    Notification.objects.bulk_create(notificacoes)

    # Disparar e-mail e push em transaction.on_commit[cite: 4]
    def disparar_alertas():
        for notif in notificacoes:
            try:
                _enviar_payload_websocket(notif)
            except Exception:
                pass
            
            if notif.recipient.email:
                try:
                    # Ajuste o template_name consoante o que já usa em _enviar_email_template
                    _enviar_email_template(
                        email_destino=notif.recipient.email,
                        subject=assunto,
                        template_name='notificacao_padrao', 
                        context={'mensagem': mensagem, 'servico_id': service.id}
                    )
                except Exception:
                    pass

    transaction.on_commit(disparar_alertas)

def notificar_nova_solicitacao(service):
    externos = User.objects.filter(is_externo=True, tipos_servico=service.tipo)
    mensagem = f"Nova solicitação de {service.tipo.nome} criada. Prazo: {service.tipo.prazo_informativo}."
    enviar_notificacao_servico(externos, service, mensagem, "Nova Solicitação", "SERVICO_NOVO")

def notificar_mudanca_status(service):
    externos = list(User.objects.filter(is_externo=True, tipos_servico=service.tipo))
    envolvidos = externos + [service.solicitante]
    mensagem = f"A solicitação #{service.id} mudou para o status: {service.get_status_display()}."
    enviar_notificacao_servico(envolvidos, service, mensagem, "Atualização de Status", "SERVICO_STATUS")