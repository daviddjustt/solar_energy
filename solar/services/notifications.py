from django.db import transaction
from django.contrib.auth import get_user_model
from solar.notifications.models import Notification
from solar.notifications.services import _enviar_payload_websocket, _enviar_email_template

User = get_user_model()

def enviar_notificacao_servico(users, service, mensagem, assunto, categoria, template_name, context=None):
    if not users:
        return

    notificacoes = []
    emails_destino = []
    
    # 1. Cria a notificação de sistema/WebSocket e separa os e-mails
    for user in users:
        notificacoes.append(
            Notification(
                recipient=user,
                title=assunto,
                message=mensagem,
                category=categoria,
                service=service
            )
        )
        if user.email:
            emails_destino.append(user.email)

    Notification.objects.bulk_create(notificacoes)

    # 2. Dispara tudo apenas após o commit no banco ser concluído
    def disparar_alertas():
        for notif in notificacoes:
            try:
                _enviar_payload_websocket(notif)
            except Exception:
                pass
        
        # Resolve o R2: Os e-mails agora são devidamente disparados
        if emails_destino and template_name:
            for email in emails_destino:
                try:
                    _enviar_email_template(
                        email_destino=email,
                        subject=assunto,
                        template_name=template_name,
                        context=context or {'mensagem': mensagem, 'servico': service}
                    )
                except Exception as e:
                    # Log real em vez de falha silenciosa
                    print(f"Erro ao disparar e-mail para {email}: {e}")

    transaction.on_commit(disparar_alertas)

# --- FUNÇÕES DE DISPARO ---

def notificar_nova_solicitacao(service):
    externos = list(User.objects.filter(is_externo=True, tipos_servico=service.tipo))
    admins = list(User.objects.filter(is_superuser=True) | User.objects.filter(is_admin=True))
    
    envolvidos = list(set(externos + admins))
    
    enviar_notificacao_servico(
        users=envolvidos,
        service=service,
        mensagem=f"Nova solicitação de {service.tipo.nome} criada. Prazo: {service.tipo.prazo_informativo}.",
        assunto=f"Nova Solicitação: {service.tipo.nome}",
        categoria="SERVICO_NOVO",
        template_name="email/services/nova_solicitacao.html"
    )

def notificar_mudanca_status(service):
    externos = list(User.objects.filter(is_externo=True, tipos_servico=service.tipo))
    envolvidos = list(set(externos + [service.solicitante]))
    
    enviar_notificacao_servico(
        users=envolvidos,
        service=service,
        mensagem=f"A solicitação #{service.id} mudou para o status: {service.get_status_display()}.",
        assunto=f"Atualização de Status - #{service.id}",
        categoria="SERVICO_STATUS",
        template_name="email/services/status_alterado.html"
    )

def notificar_pendencia(service, titulo):
    enviar_notificacao_servico(
        users=[service.solicitante],
        service=service,
        mensagem=f"Nova pendência na sua solicitação #{service.id}: {titulo}.",
        assunto="Ação Necessária: Pendência em Aberto",
        categoria="SERVICO_PENDENCIA",
        template_name="email/services/pendencia.html",
        context={'servico': service, 'titulo': titulo, 'mensagem': f"A pendência '{titulo}' foi aberta."}
    )

def notificar_documento_rejeitado_servico(service, nome_doc, motivo):
    enviar_notificacao_servico(
        users=[service.solicitante],
        service=service,
        mensagem=f"O documento '{nome_doc}' foi rejeitado. Motivo: {motivo}.",
        assunto="Documento Rejeitado - Ação Necessária",
        categoria="SERVICO_REJEICAO",
        template_name="email/services/documento_rejeitado.html",
        context={'servico': service, 'nome_doc': nome_doc, 'motivo': motivo}
    )

def notificar_boleto_anexado_servico(service):
    enviar_notificacao_servico(
        users=[service.solicitante],
        service=service,
        mensagem=f"Um novo boleto foi disponibilizado para a solicitação #{service.id}.",
        assunto="Boleto Disponível para Pagamento",
        categoria="SERVICO_BOLETO",
        template_name="email/services/boleto_disponivel.html"
    )

def notificar_comprovante_anexado_servico(service):
    # P1-10: Notifica externos do tipo e também os administradores
    externos = list(User.objects.filter(is_externo=True, tipos_servico=service.tipo))
    admins = list(User.objects.filter(is_superuser=True) | User.objects.filter(is_admin=True))
    
    envolvidos = list(set(externos + admins))
    
    enviar_notificacao_servico(
        users=envolvidos,
        service=service,
        mensagem=f"O cliente anexou um comprovante de pagamento para a solicitação #{service.id}.",
        assunto="Comprovante de Pagamento Recebido",
        categoria="SERVICO_COMPROVANTE",
        template_name="email/services/comprovante_recebido.html"
    )

def notificar_documento_reenviado_servico(service, nome_doc):
    # Regra nova originada no R4
    externos = list(User.objects.filter(is_externo=True, tipos_servico=service.tipo))
    admins = list(User.objects.filter(is_superuser=True) | User.objects.filter(is_admin=True))
    
    envolvidos = list(set(externos + admins))
    
    enviar_notificacao_servico(
        users=envolvidos,
        service=service,
        mensagem=f"O cliente reenviou o documento '{nome_doc}' para análise.",
        assunto=f"Documento Reenviado - #{service.id}",
        categoria="SERVICO_REENVIO",
        template_name="email/services/documento_reenviado.html",
        context={'servico': service, 'nome_doc': nome_doc}
    )