# solar/documents/models.py

from django.db import models
from django.conf import settings
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError
from decimal import Decimal
import os
import re
from django.utils import timezone # Importar timezone para usar em approved_at
from solar.users.models import User
def get_document_upload_path(instance, filename):
    """Gera o caminho de upload baseado no projeto e tipo de documento"""
    return f'projects/{instance.project.client_code}/documents/{instance.document_type}/{filename}'

class ClientProject(models.Model):
    DOCUMENT_TYPE_CHOICES = [
        ('PF', 'Pessoa Física'),
        ('PJ', 'Pessoa Jurídica'),
    ]
    VOLTAGE_CHOICES = [
        ('110V', '110V'),
        ('220V', '220V'),
        ('380V', '380V'),
        ('440V', '440V'),
        ('outros', 'Outros'),
    ]
    # Informações básicas do cliente
    
    client_code = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='id'
    )
    project_holder_name = models.CharField(
        max_length=200,
        verbose_name="Nome do titular do projeto"
    )
    project_class = models.CharField(
        max_length=100,
        verbose_name="Classe"
    )
    email = models.EmailField(verbose_name="E-mail")
    client_type = models.CharField(
        max_length=2,
        choices=DOCUMENT_TYPE_CHOICES,
        default='PF',
        verbose_name="Tipo de cliente"
    )
    # Endereço
    cep = models.CharField(
        max_length=9,
        validators=[RegexValidator(regex=r'^\d{5}-?\d{3}$', message="CEP deve estar no formato XXXXX-XXX")],
        verbose_name="CEP"
    )
    street = models.CharField(max_length=200, verbose_name="Logradouro")
    number = models.CharField(max_length=20, verbose_name="Número")
    neighborhood = models.CharField(max_length=100, verbose_name="Bairro")
    city = models.CharField(max_length=100, verbose_name="Cidade")
    complement = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name="Complemento"
    )
    # Campo documento dinâmico
    documento = models.CharField(
        max_length=18,
        verbose_name="Documento",
        help_text="CPF no formato XXX.XXX.XXX-XX ou CNPJ no formato XX.XXX.XXX/XXXX-XX"
    )
    # Contato - MELHORADO: regex mais flexível
    phone = models.CharField(
        max_length=15,
        validators=[RegexValidator(
            regex=r'^\(\d{2}\)\s?\d{4,5}-?\d{4}$',
            message="Telefone deve estar no formato (XX) XXXXX-XXXX ou (XX) XXXX-XXXX"
        )],
        verbose_name="Telefone do titular"
    )
    # ADICIONADO: Localização em formato decimal (principal)
    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=8,
        verbose_name="Latitude",
        help_text="Latitude em formato decimal"
    )
    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=8,
        verbose_name="Longitude",
        help_text="Longitude em formato decimal"
    )
    # Informações técnicas - MELHORADO: choices definidas
    voltage = models.CharField(
        max_length=50,
        choices=VOLTAGE_CHOICES,
        verbose_name="Tensão"
    )
    # Status da documentação (será complementado pelos status dos documentos individuais)
    documentation_complete = models.BooleanField(
        default=False,
        verbose_name="Documentação completa"
    )
    # Metadados
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_projects'
    )

    @property
    def documento_tipo(self):
        """Retorna o tipo do documento baseado no client_type"""
        return 'CPF' if self.client_type == 'PF' else 'CNPJ'

    @property
    def documento_label(self):
        """Retorna o label apropriado para exibição"""
        return f"{self.documento_tipo}: {self.documento}" if self.documento else self.documento_tipo

    def is_documento_valid(self):
        """ADICIONADO: Valida se o documento está no formato correto"""
        if not self.documento:
            return False
        if self.client_type == 'PF':
            # Validação para CPF
            cpf_pattern = r'^\d{3}\.\d{3}\.\d{3}-\d{2}$'
            return bool(re.match(cpf_pattern, self.documento))
        elif self.client_type == 'PJ':
            # Validação para CNPJ
            cnpj_pattern = r'^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$'
            return bool(re.match(cnpj_pattern, self.documento))
        return False

    def clean(self):
        """Validação customizada"""
        super().clean()
        if not self.documento:
            raise ValidationError({
                'documento': f'{self.documento_tipo} é obrigatório.'
            })
        # Validação do documento
        if not self.is_documento_valid():
            if self.client_type == 'PF':
                raise ValidationError({
                    'documento': 'CPF deve estar no formato XXX.XXX.XXX-XX'
                })
            else:
                raise ValidationError({
                    'documento': 'CNPJ deve estar no formato XX.XXX.XXX/XXXX-XX'
                })
        # ADICIONADO: Validação de coordenadas
        if self.latitude and (self.latitude < -90 or self.latitude > 90):
            raise ValidationError({
                'latitude': 'Latitude deve estar entre -90 e 90 graus'
            })
        if self.longitude and (self.longitude < -180 or self.longitude > 180):
            raise ValidationError({
                'longitude': 'Longitude deve estar entre -180 e 180 graus'
            })

    def save(self, *args, **kwargs):
        """Override do save"""
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.client_code} - {self.project_holder_name}"

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Projeto do Cliente"
        verbose_name_plural = "Projetos dos Clientes"

    def get_required_documents(self):
        """Retorna lista de documentos obrigatórios baseado no tipo de cliente"""
        base_docs = [
            'documento_cliente',
            'unidade_geradora_fatura',
            'unidades_consumidoras_fatura',
            'lista_material',
            'procuracao_assinada'
        ]
        if self.client_type == 'PJ':
            base_docs.extend([
                'cartao_cnpj',
                'inscricao_estadual_municipal',
                'contrato_social'
            ])
        return base_docs

    def check_documentation_complete(self):
        """Verifica se toda documentação obrigatória foi enviada E APROVADA"""
        required_docs = self.get_required_documents()
        # Agora, consideramos apenas documentos aprovados para a completude
        uploaded_approved_doc_types = set(
            self.documents.filter(status=ProjectDocument.APPROVED)
            .values_list('document_type', flat=True)
        )
        self.documentation_complete = all(doc_type in uploaded_approved_doc_types for doc_type in required_docs)
        self.save(update_fields=['documentation_complete'])
        return self.documentation_complete

    @property
    def approved_documents_count(self):
        """Retorna o número de documentos com status 'Aprovado'."""
        return self.documents.filter(status=ProjectDocument.APPROVED).count()

    @property
    def in_analysis_documents_count(self):
        """Retorna o número de documentos com status 'Em Análise'."""
        return self.documents.filter(status=ProjectDocument.IN_ANALYSIS).count()

    @property
    def rejected_documents_count(self):
        """Retorna o número de documentos com status 'Rejeitado'."""
        return self.documents.filter(status=ProjectDocument.REJECTED).count()

    @property
    def total_documents_count(self):
        """Retorna o número total de documentos para o projeto."""
        return self.documents.count()


class ConsumerUnit(models.Model):
    project = models.ForeignKey(
        ClientProject,
        on_delete=models.CASCADE,
        related_name='consumer_units'
    )
    client_code = models.CharField(
        max_length=50,
        verbose_name="Código do cliente da unidade"
    )
    percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Porcentagem (%)"
    )
    # ADICIONADO: Campo tensão para unidade (conforme serializer discutido)
    voltage = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Tensão da unidade"
    )

    class Meta:
        verbose_name = "Unidade Consumidora"
        verbose_name_plural = "Unidades Consumidoras"
        # ADICIONADO: Evita duplicação
        unique_together = ['project', 'client_code']

    def __str__(self):
        return f"UC: {self.client_code} - {self.percentage}%"

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

class ArquivoMixin(models.Model):
    """
    Mixin para campos comuns de arquivos.
    Fornece estrutura base para modelos que lidam com upload de arquivos,
    incluindo campos comuns e métodos de validação.
    """
    # Alterado upload_to para usar a função customizada
    arquivo = models.FileField(
        verbose_name=("Arquivo"),
        upload_to=get_document_upload_path, # Usando a função customizada aqui
        help_text=("Arquivo relacionado ao ponto de fiscalização"),
    )

    class Meta:
        abstract = True

class ProjectDocument(BaseModel, ArquivoMixin):
    # Opções de status para o documento
    STATUS_CHOICES = [
        ('IN_ANALYSIS', 'Em Análise'),
        ('APPROVED', 'Aprovado'),
        ('REJECTED', 'Rejeitado'),
    ]

    # Constantes para fácil acesso aos status
    IN_ANALYSIS = 'IN_ANALYSIS'
    APPROVED = 'APPROVED'
    REJECTED = 'REJECTED'

    DOCUMENT_TYPE_CHOICES = [
        # Documentos obrigatórios para PF e PJ
        ('documento_cliente', 'Documento do Cliente'),
        ('unidade_geradora_fatura', 'Unidade Geradora (Fatura)'),
        ('unidades_consumidoras_fatura', 'Unidades Consumidoras (Fatura)'),
        ('lista_material', 'Lista de Material'),
        ('procuracao_assinada', 'Procuração Assinada'),
        # Documentos adicionais para PJ
        ('cartao_cnpj', 'Cartão CNPJ'),
        ('inscricao_estadual_municipal', 'Inscrição Estadual ou Municipal'),
        ('contrato_social', 'Contrato Social'),
        # Outros documentos
        ('outros', 'Outros Documentos'),
    ]
    FILE_TYPE_CHOICES = [
        ('photo', 'Foto'),
        ('pdf', 'PDF'),
        ('other', 'Outro'),
    ]
    project = models.ForeignKey(
        ClientProject,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    document_type = models.CharField(
        max_length=50,
        choices=DOCUMENT_TYPE_CHOICES,
        verbose_name="Tipo do documento"
    )
    file_type = models.CharField(
        max_length=10,
        choices=FILE_TYPE_CHOICES,
        verbose_name="Tipo de arquivo"
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name="Descrição"
    )
    # NOVO CAMPO: Status do documento
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=IN_ANALYSIS, # Documentos recém-enviados começam "Em Análise"
        verbose_name="Status do Documento"
    )
    rejection_reason = models.TextField(
        blank=True,
        null=True,
        verbose_name="Motivo da rejeição"
    )
    # `uploaded_at` é fornecido por BaseModel.created_at
    approved_at = models.DateTimeField(blank=True, null=True, verbose_name="Data de Aprovação")
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_documents',
        verbose_name="Aprovado por"
    )

    class Meta:
        verbose_name = "Documento do Projeto"
        verbose_name_plural = "Documentos do Projeto"
        unique_together = ['project', 'document_type']

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.project.client_code} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        # Se o status mudou para APROVADO, registra a data e o usuário
        if self.pk: # Se o objeto já existe (é uma atualização)
            original = ProjectDocument.objects.get(pk=self.pk)
            if original.status != self.status and self.status == self.APPROVED:
                self.approved_at = timezone.now()
                # Assumindo que você tem acesso ao usuário atual no contexto da requisição
                # ou que o serializer irá passar o usuário.
                # Por enquanto, deixaremos o approved_by para ser definido no serializer/view.
                # Se você quiser que o approved_by seja definido automaticamente no save do model,
                # precisará de um mecanismo para passar o usuário para o model (ex: thread-local storage ou signals).
                # Para uma API REST, é mais comum definir isso no serializer ou view.
            elif original.status != self.status and self.status != self.APPROVED:
                # Se o status mudou de APROVADO para outro (rejeitado ou em análise), limpa a data/usuário de aprovação
                self.approved_at = None
                self.approved_by = None
        elif self.status == self.APPROVED: # Se é um novo documento e já está sendo criado como APROVADO
            self.approved_at = timezone.now()
            # approved_by deve ser definido na view/serializer

        # Se o status não é REJEITADO, limpa o motivo da rejeição
        if self.status != self.REJECTED:
            self.rejection_reason = None

        super().save(*args, **kwargs)
        # Verifica se a documentação do projeto está completa após salvar o documento
        # Isso é importante para atualizar o campo documentation_complete no ClientProject
        self.project.check_documentation_complete()

    def delete(self, *args, **kwargs):
        # Remove o arquivo físico
        if self.arquivo:
            if os.path.isfile(self.arquivo.path):
                os.remove(self.arquivo.path)
        super().delete(*args, **kwargs)
        # Revalida a documentação do projeto após a exclusão
        self.project.check_documentation_complete()

