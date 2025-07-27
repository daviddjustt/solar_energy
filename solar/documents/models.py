from django.db import models
from django.conf import settings
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError
import os


def get_document_upload_path(instance, filename):
    """Gera o caminho de upload baseado no projeto e tipo de documento"""
    return f'projects/{instance.project.client_code}/documents/{instance.document_type}/{filename}'


class ClientProject(models.Model):
    DOCUMENT_TYPE_CHOICES = [
        ('PF', 'Pessoa Física'),
        ('PJ', 'Pessoa Jurídica'),
        # Podemos acrescentar mais tipos
    ]
    
    # Informações básicas do cliente
    client_code = models.CharField(max_length=50, verbose_name="Código do cliente")
    project_holder_name = models.CharField(max_length=200, verbose_name="Nome do titular do projeto")
    project_class = models.CharField(max_length=100, verbose_name="Classe")
    email = models.EmailField(verbose_name="E-mail")
    client_type = models.CharField(max_length=2, choices=DOCUMENT_TYPE_CHOICES, default='PF', verbose_name="Tipo de cliente")
    
    # Endereço
    cep = models.CharField(max_length=9, verbose_name="CEP")
    street = models.CharField(max_length=200, verbose_name="Logradouro")
    number = models.CharField(max_length=20, verbose_name="Número")
    neighborhood = models.CharField(max_length=100, verbose_name="Bairro")
    city = models.CharField(max_length=100, verbose_name="Cidade")
    complement = models.CharField(max_length=200, blank=True, null=True, verbose_name="Complemento")
    
    # Campo documento dinâmico
    documento = models.CharField(
        max_length=18, 
        verbose_name="Documento", 
        help_text="CPF no formato XXX.XXX.XXX-XX ou CNPJ no formato XX.XXX.XXX/XXXX-XX"
    )
    
    # Contato
    phone_validator = RegexValidator(regex=r'^\(\d{2}\)\s\d{4,5}-\d{4}$', message="Celular deve estar no formato (XX) XXXXX-XXXX")
    phone = models.CharField(max_length=15, validators=[phone_validator], verbose_name="Celular do titular")

    # Localização da usina
    latitude = models.DecimalField(max_digits=10, decimal_places=8, verbose_name="Latitude")
    longitude = models.DecimalField(max_digits=11, decimal_places=8, verbose_name="Longitude")
    
    # Informações técnicas
    voltage = models.CharField(max_length=50, verbose_name="Tensão")
    
    # Status da documentação
    documentation_complete = models.BooleanField(default=False, verbose_name="Documentação completa")
    
    # Metadados
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_projects')

    @property
    def documento_tipo(self):
        """Retorna o tipo do documento baseado no client_type"""
        return 'CPF' if self.client_type == 'PF' else 'CNPJ'

    @property
    def documento_label(self):
        """Retorna o label apropriado para exibição"""
        return f"{self.documento_tipo}: {self.documento}" if self.documento else self.documento_tipo

    def clean(self):
        """Validação customizada para o campo documento baseado no tipo de cliente"""
        super().clean()
        
        if not self.documento:
            raise ValidationError({
                'documento': f'{self.documento_tipo} é obrigatório.'
            })
        
        if self.client_type == 'PF':
            # Validação para CPF
            cpf_pattern = r'^\d{3}\.\d{3}\.\d{3}-\d{2}$'
            if not RegexValidator(regex=cpf_pattern).regex.match(self.documento):
                raise ValidationError({
                    'documento': 'CPF deve estar no formato XXX.XXX.XXX-XX'
                })
        
        elif self.client_type == 'PJ':
            # Validação para CNPJ
            cnpj_pattern = r'^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$'
            if not RegexValidator(regex=cnpj_pattern).regex.match(self.documento):
                raise ValidationError({
                    'documento': 'CNPJ deve estar no formato XX.XXX.XXX/XXXX-XX'
                })

    def save(self, *args, **kwargs):
        """Override do save para executar validação antes de salvar"""
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
        """Verifica se toda documentação obrigatória foi enviada"""
        required_docs = self.get_required_documents()
        uploaded_doc_types = set(self.documents.values_list('document_type', flat=True))
        
        self.documentation_complete = all(doc_type in uploaded_doc_types for doc_type in required_docs)
        self.save(update_fields=['documentation_complete'])
        return self.documentation_complete


class ConsumerUnit(models.Model):
    project = models.ForeignKey(ClientProject, on_delete=models.CASCADE, related_name='consumer_units')
    client_code = models.CharField(max_length=50, verbose_name="Código do cliente da unidade")
    percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        blank=True, 
        null=True, 
        verbose_name="Porcentagem (%)"
    )
    
    class Meta:
        verbose_name = "Unidade Consumidora"
        verbose_name_plural = "Unidades Consumidoras"

    def __str__(self):
        return f"UC: {self.client_code} - {self.percentage}%"


class ProjectDocument(models.Model):
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
    
    project = models.ForeignKey(ClientProject, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPE_CHOICES, verbose_name="Tipo do documento")
    file = models.FileField(upload_to=get_document_upload_path, verbose_name="Arquivo")
    file_type = models.CharField(max_length=10, choices=FILE_TYPE_CHOICES, verbose_name="Tipo de arquivo")
    description = models.TextField(blank=True, null=True, verbose_name="Descrição")
    is_approved = models.BooleanField(default=False, verbose_name="Aprovado")
    rejection_reason = models.TextField(blank=True, null=True, verbose_name="Motivo da rejeição")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_documents')

    class Meta:
        verbose_name = "Documento do Projeto"
        verbose_name_plural = "Documentos do Projeto"
        unique_together = ['project', 'document_type']

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.project.client_code}"

    def save(self, *args, **kwargs):
        # Detecta automaticamente o tipo de arquivo
        if self.file:
            file_extension = os.path.splitext(self.file.name)[1].lower()
            if file_extension == '.pdf':
                self.file_type = 'pdf'
            elif file_extension in ['.jpg', '.jpeg', '.png', '.gif']:
                self.file_type = 'photo'
            else:
                self.file_type = 'other'
        
        super().save(*args, **kwargs)
        
        # Verifica se a documentação do projeto está completa
        self.project.check_documentation_complete()

    def delete(self, *args, **kwargs):
        # Remove o arquivo físico
        if self.file:
            if os.path.isfile(self.file.path):
                os.remove(self.file.path)
        
        super().delete(*args, **kwargs)
        
        # Revalida a documentação do projeto
        self.project.check_documentation_complete()
