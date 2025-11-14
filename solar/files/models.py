import os
from django.db import models
from django.utils import timezone
from solar.documents.utils import get_document_upload_path, validate_file_size
from solar.documents.models import ClientProject
from django.core.exceptions import ValidationError
from django.core.exceptions import ValidationError
import os
import uuid
from django.utils import timezone
from django.utils.text import slugify

from solar.files.utils import ( 
    DOCUMENT_TYPE_CHOICES, 
    STATUS_CHOICES, 
    IN_ANALYSIS, 
    APPROVED, 
    REJECTED,
)


def get_document_upload_path(instance, filename):
    """
    Gera o caminho de upload organizado e seguro para documentos.
    
    Estrutura: projects/{codigoCliente}/documents/{document_type}/{YYYY}/{MM}/{DD}/{uuid}_{filename}
    
    Exemplo:
    projects/CLI-001/documents/boleto/2025/10/29/a1b2c3d4-e5f6-7890-abcd-ef1234567890_fatura.pdf
    """
    # 1. Extrair extensão do arquivo
    ext = os.path.splitext(filename)[1].lower()  # .pdf, .jpg, etc
    
    # 2. Slugify do nome do arquivo (remove caracteres especiais)
    basename = os.path.splitext(filename)[0]
    slugified_name = slugify(basename)
    
    # 3. Limitar tamanho do nome (máximo 50 caracteres)
    if len(slugified_name) > 50:
        slugified_name = slugified_name[:50]
    
    # 4. Gerar UUID único para evitar conflitos
    unique_id = uuid.uuid4().hex[:8]  # 8 primeiros caracteres do UUID
    
    # 5. Criar nome final do arquivo
    final_filename = f"{unique_id}_{slugified_name}{ext}"
    
    # 6. Obter data atual para organização por data
    now = timezone.now()
    year = now.strftime('%Y')
    month = now.strftime('%m')
    day = now.strftime('%d')
    
    # 7. Construir caminho completo
    path = os.path.join(
        'projects',
        instance.project.codigoCliente,
        'documents',
        instance.document_type,
        year,
        month,
        day,
        final_filename
    )
    
    return path

def validate_file_size(file):
    """
    Valida o tamanho do arquivo (máximo 10 MB para LGPD e performance).
    """
    max_size_mb = 10
    if file.size > max_size_mb * 1024 * 1024:
        raise ValidationError(
            f'O arquivo não pode ter mais de {max_size_mb} MB. '
            f'Tamanho atual: {file.size / (1024 * 1024):.2f} MB'
        )

def validate_file_extension(file):
    """
    Valida a extensão do arquivo (apenas tipos permitidos).
    """
    allowed_extensions = [
        '.pdf', '.jpg', '.jpeg', '.png', 
        '.doc', '.docx', '.xls', '.xlsx'
    ]
    
    ext = os.path.splitext(file.name)[1].lower()
    
    if ext not in allowed_extensions:
        raise ValidationError(
            f'Tipo de arquivo não permitido: {ext}. '
            f'Formatos aceitos: {", ".join(allowed_extensions)}'
        )


class ArquivoMixin(models.Model):
    """
    Mixin para campos comuns de arquivos.
    Fornece estrutura base para modelos que lidam com upload de arquivos,
    incluindo campos comuns e métodos de validação.
    """
    arquivo = models.FileField(
        verbose_name="Arquivo",
        upload_to=get_document_upload_path,
        validators=[validate_file_size, validate_file_extension],
        help_text=(
            "Arquivo do documento. "
            "Máximo 10 MB. Formatos: PDF, JPG, PNG, DOC, DOCX, XLS, XLSX"
        ),
    )
    
    class Meta:
        abstract = True

class BaseModel(models.Model):
    """
    Modelo base que fornece campos de auditoria para todos os modelos do sistema.
    Todos os modelos devem herdar desta classe para ter consistência na
    rastreabilidade de criação e atualização.
    """
    created_at = models.DateTimeField(
        verbose_name=("Data de Criação"),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        verbose_name=("Data de Atualização"),
        auto_now=True
    )
    class Meta:
        abstract = True
        
class Document(BaseModel, ArquivoMixin):
    document_type = models.CharField(
        max_length=80,
        choices=DOCUMENT_TYPE_CHOICES,
        verbose_name="Tipo do documento"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=IN_ANALYSIS, # Documentos recém-enviados começam "Em Análise"
        verbose_name="Status do Documento"
    )
    # `uploaded_at` é fornecido por BaseModel.created_at
    approved_at = models.DateTimeField(blank=True, null=True, verbose_name="Data de Aprovação")
    
    class Meta:
        abstract = True
        verbose_name = "Documento"
        verbose_name_plural = "Documentos"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'document_type']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.project.codigoCliente} ({self.get_status_display()})"
    
    def clean(self):
        """
        Validação customizada do modelo.
        """
        super().clean()
        
        # Validar tamanho do arquivo
        if self.arquivo:
            try:
                validate_file_size(self.arquivo)
            except ValidationError as e:
                raise ValidationError({'arquivo': e.message})
        
    def save(self, *args, **kwargs):
        """
        Override do save com lógica de negócio.
        """
        # Executar validações
        self.full_clean()

        if self.status == self.APPROVED:
                self.approved_at = timezone.now()
        
        # Salvar o objeto
        super().save(*args, **kwargs)
        
        # Atualizar documentação completa do projeto
        try:
            self.project.check_documetacaoCompleta()
        except Exception as e:
            # Log do erro mas não impede o salvamento
            print(f"Erro ao verificar documentação completa: {e}")
    
    def delete(self, *args, **kwargs):
        """
        Override do delete para remover arquivo físico (LGPD).
        """
        # Guardar referência ao arquivo antes de deletar
        arquivo_path = self.arquivo.path if self.arquivo else None
        arquivo_storage = self.arquivo.storage if self.arquivo else None
        
        # Deletar o registro do banco
        super().delete(*args, **kwargs)
        
        # Tentar remover o arquivo físico
        if arquivo_path:
            try:
                # Se estiver usando Railway volume ou filesystem local
                if os.path.isfile(arquivo_path):
                    os.remove(arquivo_path)
                    print(f"✅ Arquivo removido: {arquivo_path}")
                
                # Se estiver usando S3/R2 ou outro storage
                elif arquivo_storage:
                    arquivo_storage.delete(arquivo_path)
                    print(f"✅ Arquivo removido do storage: {arquivo_path}")
            
            except Exception as e:
                # Log do erro mas não impede a deleção do registro
                print(f"⚠️ Erro ao deletar arquivo físico: {e}")
        
        # Revalidar documentação do projeto
        try:
            self.project.check_documetacaoCompleta()
        except Exception as e:
            print(f"⚠️ Erro ao verificar documentação completa após deleção: {e}")
    
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
    
class DocumentUser(Document):
    user = models.ForeignKey("users.User", 
        verbose_name= ("Relação com usuário"), 
        on_delete=models.CASCADE)
    
    class Meta:
        abstract = True
        verbose_name = "Documento do Usuário"
        verbose_name_plural = "Documentos dos Usuários"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'document_type']),
            models.Index(fields=['status']),
        ]
    @property
    def is_payment_document(self):
        """Verifica se o documento é relacionado a pagamento"""
        return self.document_type in ['boleto', 'comprovante_de_pagamento']
    
    @property
    def is_payment_complete(self):
        """Verifica se o pagamento está completo (boleto + comprovante aprovado)"""
        if self.document_type == 'boleto':
            return self.payment_proofs.filter(status=self.APPROVED).exists()
        elif self.document_type == 'comprovante_de_pagamento':
            return (
                self.status == self.APPROVED and 
                self.related_payment_document is not None
            )
        return False
    
    @property
    def payment_status(self):
        """Status do pagamento para boletos"""
        if self.document_type == 'boleto':
            if self.payment_proofs.filter(status=self.APPROVED).exists():
                return 'PAGO'
            elif self.payment_proofs.exists():
                return 'COMPROVANTE_EM_ANALISE'
            else:
                return 'PENDENTE'
        return None
    
class DocumentProject(Document):
    project = models.ForeignKey(
        ClientProject,
        verbose_name="Relação com Projeto",
        on_delete=models.CASCADE,
        related_name="documents"
    )
    class Meta:
        abstract = True
        verbose_name = "Documento do Projeto"
        verbose_name_plural = "Documentos dos Projeto"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'document_type']),
            models.Index(fields=['status']),
        ]
    
    