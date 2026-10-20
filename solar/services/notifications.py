from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import get_user_model
from solar.notifications.models import Notification

User = get_user_model()

def enviar_notificacao_servico(users, service, mensagem, assunto_email):
    """
    Dispara notificação no sino e e-mail para uma lista de utilizadores.
    """
    if not users:
        return

    # 1. Criar notificações no sino (Bulk Create para otimização)
    notificacoes = [
        Notification(user=user, service=service, message=mensagem)
        for user in users
    ]
    Notification.objects.bulk_create(notificacoes)

    # 2. Enviar E-mails
    emails = [user.email for user in users if user.email]
    if emails:
        # Utilize o seu template de e-mail padrão aqui; isto é uma abstração básica
        send_mail(
            subject=f"[Solar Tech] {assunto_email} - #{service.id}",
            message=f"{mensagem}\n\nAceda ao sistema para ver os detalhes.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=emails,
            fail_silently=True,
        )

def notificar_nova_solicitacao(service):
    """Notifica apenas os externos habilitados quando o cliente cria a solicitação[cite: 1]."""
    externos = User.objects.filter(is_externo=True, tipos_servico=service.tipo)
    mensagem = f"Nova solicitação de {service.tipo.nome} criada. Prazo: {service.tipo.prazo_informativo}."
    enviar_notificacao_servico(externos, service, mensagem, "Nova Solicitação de Serviço")

def notificar_mudanca_status(service):
    """Notifica o cliente e os externos do tipo quando o status ou pagamento muda[cite: 1]."""
    externos = list(User.objects.filter(is_externo=True, tipos_servico=service.tipo))
    envolvidos = externos + [service.solicitante]
    
    mensagem = f"A solicitação #{service.id} mudou para o status: {service.get_status_display()}."
    enviar_notificacao_servico(envolvidos, service, mensagem, "Atualização de Status")

def notificar_pendencia(service, criada_por_cliente):
    """Se o cliente responde, notifica a equipa. Se a equipa abre, notifica o cliente[cite: 1]."""
    if criada_por_cliente:
        destinatarios = User.objects.filter(is_externo=True, tipos_servico=service.tipo)
        mensagem = f"O cliente respondeu a uma pendência na solicitação #{service.id}."
    else:
        destinatarios = [service.solicitante]
        mensagem = f"Nova pendência que requer a sua atenção na solicitação #{service.id}."
        
    enviar_notificacao_servico(destinatarios, service, mensagem, "Aviso de Pendência")
    
def notificar_documento_rejeitado(service, nome_documento):
    """Notifica o cliente sobre um documento/comprovante reprovado[cite: 1]."""
    mensagem = f"O documento '{nome_documento}' da solicitação #{service.id} foi reprovado."
    enviar_notificacao_servico([service.solicitante], service, mensagem, "Documento Reprovado")
    
def notificar_boleto_anexado(service):
    """Notifica o cliente que um boleto foi disponibilizado[cite: 1]."""
    mensagem = f"Um novo boleto foi anexado à sua solicitação #{service.id}."
    enviar_notificacao_servico([service.solicitante], service, mensagem, "Novo Boleto Disponível")