import os
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError

from solar.choices import (
    AndamentoDoProjeto, 
    StatusDocumento, 
    TipoDocumento,
    get_document_upload_path,
    validate_file_size,)

class TimestampMixin(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Criado em")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Última atualização em")

    class Meta:
        abstract = True
class ArquivoMixin(TimestampMixin, models.Model):
    arquivo = models.FileField(upload_to=get_document_upload_path)
    class Meta:
        abstract = True

class Document(ArquivoMixin, models.Model):
    """
    Modelo abstrato base para documentos, fornecendo campos comuns
    como tipo, status, motivo de rejeição e data de aprovação.
    """
    document_type = models.CharField(
        max_length=80,
        choices=TipoDocumento.choices, # Usando a nova classe TipoDocumento
        verbose_name="Tipo do documento"
    )
    status = models.CharField(
        max_length=20,
        choices=StatusDocumento.choices, # Usando a classe StatusDocumento
        default=StatusDocumento.EM_ANALISE,
        verbose_name="Status do Documento"
    )
    rejection_reason = models.TextField(
        blank=True,
        null=True,
        verbose_name="Motivo da rejeição"
    )
    approved_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Data de Aprovação"
    )
    # O campo related_payment_document deve estar presente em ambos
    # DocumentUser e ProjectDocument, então ele pode ser definido aqui.
    related_payment_document = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL, # Alterado para SET_NULL para evitar deleção em cascata indesejada
        null=True,
        blank=True,
        related_name='related_documents', # Nome genérico, subclasses podem sobrescrever
        help_text="Documento relacionado (boleto para comprovante ou vice-versa)"
    )

    class Meta:
        abstract = True # Este modelo não cria uma tabela no banco de dados
        ordering = ['-created_at']
        # Índices podem ser definidos nas subclasses concretas

    def __str__(self):
        return f"{self.get_document_type_display()} ({self.get_status_display()})"

    def clean(self):
        super().clean()
        if self.arquivo:
            try:
                validate_file_size(self.arquivo)
            except ValidationError as e:
                raise ValidationError({'arquivo': e.message})

        # Validação para related_payment_document
        if self.related_payment_document:
            if self.related_payment_document.pk == self.pk:
                raise ValidationError({'related_payment_document': 'Um documento não pode ser relacionado a si mesmo.'})
            # Lógica para garantir que boleto se relaciona com comprovante e vice-versa
            if self.document_type == TipoDocumento.BOLETO and self.related_payment_document.document_type != TipoDocumento.COMPROVANTE_PAGAMENTO:
                raise ValidationError({'related_payment_document': 'Um boleto só pode ser relacionado a um comprovante de pagamento.'})
            if self.document_type == TipoDocumento.COMPROVANTE_PAGAMENTO and self.related_payment_document.document_type != TipoDocumento.BOLETO:
                raise ValidationError({'related_payment_document': 'Um comprovante de pagamento só pode ser relacionado a um boleto.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        # Lógica para approved_at
        if self.status == StatusDocumento.APROVADO and not self.approved_at:
            self.approved_at = timezone.now()
        elif self.status != StatusDocumento.APROVADO and self.approved_at:
            self.approved_at = None # Limpa a data se o status mudar de APROVADO

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        arquivo_path = self.arquivo.path if self.arquivo else None
        arquivo_storage = self.arquivo.storage if self.arquivo else None

        super().delete(*args, **kwargs)

        if arquivo_path:
            try:
                if os.path.isfile(arquivo_path):
                    os.remove(arquivo_path)
                    print(f"✅ Arquivo removido: {arquivo_path}")
                elif arquivo_storage:
                    arquivo_storage.delete(self.arquivo.name)
                    print(f"✅ Arquivo removido do storage: {self.arquivo.name}")
            except Exception as e:
                print(f"⚠️ Erro ao deletar arquivo físico: {e}")

    # ==========================================
    # PROPERTIES E MÉTODOS AUXILIARES
    # ==========================================

    @property
    def is_payment_document(self):
        """Verifica se o documento é relacionado a pagamento"""
        return self.document_type in [TipoDocumento.BOLETO, TipoDocumento.COMPROVANTE_PAGAMENTO]

    @property
    def is_payment_complete(self):
        """Verifica se o pagamento está completo (boleto + comprovante aprovado)"""
        if self.document_type == TipoDocumento.BOLETO:
            # Assumindo que 'payment_proofs' será o related_name na subclasse
            # Ou você pode precisar de um método para acessar isso
            # Por enquanto, deixamos um placeholder ou ajustamos na subclasse
            return False # Será implementado nas subclasses concretas
        elif self.document_type == TipoDocumento.COMPROVANTE_PAGAMENTO:
            return (
                self.status == StatusDocumento.APROVADO and
                self.related_payment_document is not None and
                self.related_payment_document.status == StatusDocumento.APROVADO
            )
        return False

    @property
    def payment_status(self):
        """Status do pagamento para boletos"""
        if self.document_type == TipoDocumento.BOLETO:
            # Será implementado nas subclasses concretas
            return None
        return None

    @property
    def days_since_upload(self):
        """Retorna quantos dias se passaram desde o upload"""
        if self.created_at:
            delta = timezone.now() - self.created_at
            return delta.days
        return 0

    @property
    def is_recent(self):
        """Verifica se o documento foi enviado recentemente (menos de 7 dias)"""
        return self.days_since_upload <= 7
    
class ProjectDocument(Document): # Herda do modelo abstrato Document
    """
    Representa um documento específico que pertence a um projeto.
    """
    project = models.ForeignKey(
        'solar.Projeto', # Referência ao seu modelo Projeto
        on_delete=models.CASCADE,
        related_name='documents', # Nome para acessar documentos a partir de um projeto
        verbose_name="Projeto"
    )
    document_name = models.CharField( # Campo específico para ProjectDocument
        max_length=80,
        verbose_name="Nome opcional para o documento",
        blank=True,
        null=True
    )

    class Meta(Document.Meta): # Herda a Meta de Document, incluindo ordering
        verbose_name = "Documento do Projeto"
        verbose_name_plural = "Documentos do Projeto"
        # Adicionando índices específicos para ProjectDocument
        indexes = [
            models.Index(fields=['project', 'document_type']),
            models.Index(fields=['status']),
        ]
        # Se um projeto só pode ter UM documento de um determinado tipo, adicione esta restrição:
        # constraints = [
        #     models.UniqueConstraint(fields=['project', 'document_type'], name='unique_project_document_type')
        # ]
        # Lembre-se do erro de índice duplicado 'documents_p_project_8b54f0_idx'.
        # Se a UniqueConstraint acima não for a causa, o problema pode ser de migrações antigas.

    def __str__(self):
        return f"{self.get_document_type_display()} - Projeto: {self.project.codigoCliente} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Lógica para atualizar o status de documentação completa do projeto
        try:
            self.project.check_documetacaoCompleta()
        except Exception as e:
            print(f"Erro ao verificar documentação completa do projeto {self.project.codigoCliente}: {e}")

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        # Lógica para revalidar o status de documentação completa do projeto após a exclusão
        try:
            self.project.check_documetacaoCompleta()
        except Exception as e:
            print(f"⚠️ Erro ao verificar documentação completa do projeto {self.project.codigoCliente} após deleção: {e}")

    # Sobrescrevendo as propriedades de pagamento para ProjectDocument
    @property
    def is_payment_complete(self):
        """Verifica se o pagamento está completo (boleto + comprovante aprovado) para ProjectDocument."""
        if self.document_type == TipoDocumento.BOLETO:
            # Verifica se existe um comprovante de pagamento relacionado e aprovado
            return self.related_documents.filter(
                document_type=TipoDocumento.COMPROVANTE_PAGAMENTO,
                status=StatusDocumento.APROVADO
            ).exists()
        elif self.document_type == TipoDocumento.COMPROVANTE_PAGAMENTO:
            # Verifica se o próprio comprovante está aprovado e se o boleto relacionado também está
            return (
                self.status == StatusDocumento.APROVADO and
                self.related_payment_document is not None and
                self.related_payment_document.status == StatusDocumento.APROVADO
            )
        return False

    @property
    def payment_status(self):
        """Status do pagamento para boletos em ProjectDocument."""
        if self.document_type == TipoDocumento.BOLETO:
            if self.related_documents.filter(document_type=TipoDocumento.COMPROVANTE_PAGAMENTO, status=StatusDocumento.APROVADO).exists():
                return 'PAGO'
            elif self.related_documents.filter(document_type=TipoDocumento.COMPROVANTE_PAGAMENTO).exists():
                return 'COMPROVANTE_EM_ANALISE'
            else:
                return 'PENDENTE'
        return None

class DocumentUser(Document): # Herda do modelo abstrato Document
    """
    Representa um documento específico que pertence a um usuário.
    """
    user = models.ForeignKey(
        'users.User', # Referência ao seu modelo User customizado
        on_delete=models.CASCADE,
        related_name='user_documents', # Nome para acessar documentos a partir de um usuário
        verbose_name="Usuário dono do documento"
    )

    class Meta(Document.Meta): # Herda a Meta de Document, incluindo ordering
        verbose_name = "Documento do Usuário"
        verbose_name_plural = "Documentos do Usuário"
        # Adicionando índices específicos para DocumentUser
        indexes = [
            models.Index(fields=['user', 'document_type']),
            models.Index(fields=['status']),
        ]
        # Se um usuário só pode ter UM documento de um determinado tipo, adicione esta restrição:
        # constraints = [
        #     models.UniqueConstraint(fields=['user', 'document_type'], name='unique_user_document_type')
        # ]

    def __str__(self):
        return f"{self.get_document_type_display()} - Usuário: {self.user.email} ({self.get_status_display()})"

    # Sobrescrevendo as propriedades de pagamento para DocumentUser
    @property
    def is_payment_complete(self):
        """Verifica se o pagamento está completo (boleto + comprovante aprovado) para DocumentUser."""
        if self.document_type == TipoDocumento.BOLETO:
            # Verifica se existe um comprovante de pagamento relacionado e aprovado
            return self.related_documents.filter(
                document_type=TipoDocumento.COMPROVANTE_PAGAMENTO,
                status=StatusDocumento.APROVADO
            ).exists()
        elif self.document_type == TipoDocumento.COMPROVANTE_PAGAMENTO:
            # Verifica se o próprio comprovante está aprovado e se o boleto relacionado também está
            return (
                self.status == StatusDocumento.APROVADO and
                self.related_payment_document is not None and
                self.related_payment_document.status == StatusDocumento.APROVADO
            )
        return False

    @property
    def payment_status(self):
        """Status do pagamento para boletos em DocumentUser."""
        if self.document_type == TipoDocumento.BOLETO:
            if self.related_documents.filter(document_type=TipoDocumento.COMPROVANTE_PAGAMENTO, status=StatusDocumento.APROVADO).exists():
                return 'PAGO'
            elif self.related_documents.filter(document_type=TipoDocumento.COMPROVANTE_PAGAMENTO).exists():
                return 'COMPROVANTE_EM_ANALISE'
            else:
                return 'PENDENTE'
        return None
