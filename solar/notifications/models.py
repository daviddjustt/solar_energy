from django.conf import settings
from django.db import models

class Notification(models.Model):
    # Contexto obrigatório do projeto
    project = models.ForeignKey(
        'documents.ClientProject',
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name="Projeto Relacionado"
    )
    
    # Usuários envolvidos no fluxo
    # Quem envia
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_notifications',
        verbose_name="Remetente"
    )
    # Quem recebe
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_notifications',
        verbose_name="Destinatário"
    )
    
    # Conteúdo Abstrato da Notificação
    title = models.CharField(max_length=150, verbose_name="Título")
    message = models.TextField(verbose_name="Conteúdo/Mensagem")
    
    # Categoria para regras de negócio futuras (ex: 'STATUS_PROJETO', 'DOCUMENTO_RECUSADO')
    category = models.CharField(max_length=50, default='GENERAL', verbose_name="Categoria")
    
    # Controle de leitura
    is_read = models.BooleanField(default=False, verbose_name="Lida?")
    read_at = models.DateTimeField(null=True, blank=True, verbose_name="Lida em")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Notificação"
        verbose_name_plural = "Notificações"
        indexes = [
            models.Index(fields=['recipient', 'is_read']),
            models.Index(fields=['project']),
        ]

    def __str__(self):
        return f"De: {self.sender} -> Para: {self.recipient} | {self.title}"