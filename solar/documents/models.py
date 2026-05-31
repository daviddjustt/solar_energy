from django.db import models
from django.core.validators import RegexValidator, FileExtensionValidator
from django.core.exceptions import ValidationError
from decimal import Decimal
import os
from django.utils import timezone

from solar.files.models import BaseModel, ArquivoMixin

from .utils import (
    CELULAR_REGEX, VOLTAGEM_CHOICES, DOCUMENT_TYPE_CHOICES_PESSOA,
    DOCUMENT_TYPE_CHOICES, IN_ANALYSIS, WATS_CHOICES,
    APPROVED, REJECTED, get_document_upload_path,
    validate_file_size, validate_file_extension,
)

class AndamentoDoProjeto(models.TextChoices):
    ANALISE_DE_DOCUMENTOS = 'Em análise de documentos'
    EXECUCAO = "Projeto em Execução"
    PAGAMENTO_TRT_ART = 'Pagamento da TRT/ART'
    ANALISE_TECNICA = 'Projeto em análise técnica'
    APROVADO = 'Projeto aprovado'
    REPROVADO = 'Projeto reprovado'
    VISTORIA = 'Projeto em vistoria'
    CONCLUIDO = 'Projeto finalizado'

    @classmethod
    def get_display_name(cls, code):
           for status in cls:
               if status.name == code:
                   return status.value
           return None

class ClientProject(models.Model):
    codigoCliente = models.CharField(max_length=50, verbose_name="Código único do cliente")
    created_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_projects', verbose_name='Criado por'
    )
    nomeTitular = models.CharField(max_length=200, verbose_name="Nome do titular do projeto")
    classe = models.CharField(max_length=100, verbose_name="Classe")
    tipoDocumento = models.CharField(
        max_length=2, choices=DOCUMENT_TYPE_CHOICES_PESSOA, default='PJ', verbose_name="Tipo de cliente"
    )
    documento = models.CharField(
        max_length=18, verbose_name='Documento do Cliente (CPF/CNPJ)', null=True, blank=True
    )
    voltagem = models.CharField(max_length=100, choices=VOLTAGEM_CHOICES, help_text="Voltagem do consumidor")
    email = models.EmailField(max_length=255, unique=False, verbose_name='Email')
    telefone = models.CharField(
        max_length=11, validators=[RegexValidator(regex=CELULAR_REGEX, message='Celular inválido')], verbose_name='Telefone'
    )
    cep = models.CharField(
        max_length=9, validators=[RegexValidator(regex=r'^\d{5}-?\d{3}$', message="CEP deve estar no formato XXXXX-XXX")], verbose_name="CEP"
    )
    rua = models.CharField(max_length=200, verbose_name="Logradouro")
    numero = models.CharField(max_length=20, verbose_name="Número")
    bairro = models.CharField(max_length=100, verbose_name="Bairro")
    cidade = models.CharField(max_length=100, verbose_name="Cidade")
    complemento = models.CharField(max_length=200, blank=True, null=True, verbose_name="complementoo")
    latGraus = models.SmallIntegerField(verbose_name="Latitude (Graus)", help_text="Parte inteira da latitude (-90 a 90)")
    latMin = models.SmallIntegerField(verbose_name="Latitude (Minutos)", help_text="Minutos da latitude (0 a 59)")
    latSeg = models.SmallIntegerField(verbose_name="Latitude (Segundos)", help_text="Segundos da latitude (0 a 59)")
    longGraus = models.SmallIntegerField(verbose_name="Longitude (Graus)", help_text="Parte inteira da longitude (-180 a 180)")
    longMin = models.SmallIntegerField(verbose_name="Longitude (Minutos)", help_text="Minutos da longitude (0 a 59)")
    longSeg = models.SmallIntegerField(verbose_name="Longitude (Segundos)", help_text="Segundos da longitude (0 a 59)")
    documetacaoCompleta = models.BooleanField(default=False, verbose_name="Documentação completa")
    status = models.CharField(
           max_length=43, choices=AndamentoDoProjeto.choices, default=AndamentoDoProjeto.ANALISE_DE_DOCUMENTOS, verbose_name="Status do Projeto"
    )
    observacoes = models.TextField(blank=True, null=True, verbose_name="Observações")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def cnpj_or_cpf_do_cliente(self):
        if self.created_by:
            return self.created_by.cnpj_or_cpf_do_cliente
        return None

    @property
    def documento_tipo(self):
        return 'CPF' if self.tipoDocumento == 'PF' else 'PJ'

    @property
    def documento_label(self):
        return f"{self.documento_tipo}: {self.documento}" if self.documento else self.documento_tipo

    @property
    def decimal_latitude(self):
        if self.latGraus is None or self.latMin is None or self.latSeg is None:
            return None
        sign = -1 if self.latGraus < 0 else 1
        return Decimal(sign * (abs(self.latGraus) + (self.latMin / 60) + (self.latSeg / 3600))).quantize(Decimal('0.00000001'))

    @property
    def decimal_longitude(self):
        if self.longGraus is None or self.longMin is None or self.longSeg is None:
            return None
        sign = -1 if self.longGraus < 0 else 1
        return Decimal(sign * (abs(self.longGraus) + (self.longMin / 60) + (self.longSeg / 3600))).quantize(Decimal('0.00000001'))

    @property
    def approved_documents_count(self):
        return self.documents.filter(status=ProjectDocument.STATUS_APPROVED).count()

    @property
    def in_analysis_documents_count(self):
        return self.documents.filter(status=ProjectDocument.STATUS_IN_ANALYSIS).count()

    @property
    def rejected_documents_count(self):
        return self.documents.filter(status=ProjectDocument.STATUS_REJECTED).count()

    @property
    def total_documents_count(self):
        return self.documents.count()

    @property
    def created_by_name(self):
        return self.created_by.name if self.created_by else "Usuário não identificado"

    @property
    def created_by_uuid(self):
        return str(self.created_by.uuid) if self.created_by else None

    def clean(self):
        super().clean()
        if not (-90 <= self.latGraus <= 90): raise ValidationError({'latGraus': 'Entre -90 e 90.'})
        if not (0 <= self.latMin <= 59): raise ValidationError({'latMin': 'Entre 0 e 59.'})
        if not (0 <= self.latSeg <= 59): raise ValidationError({'latSeg': 'Entre 0 e 59.'})
        if not (-180 <= self.longGraus <= 180): raise ValidationError({'longGraus': 'Entre -180 e 180.'})
        if not (0 <= self.longMin <= 59): raise ValidationError({'longMin': 'Entre 0 e 59.'})
        if not (0 <= self.longSeg <= 59): raise ValidationError({'longSeg': 'Entre 0 e 59.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Projeto do Cliente"
        verbose_name_plural = "Projetos dos Clientes"

    def _normalize_text_fields(self):
        if self.nomeTitular:
            self.nomeTitular = self.nomeTitular.upper()
        if self.documento:
            self.documento = ''.join(filter(str.isdigit, self.documento))
        if self.telefone:
            self.telefone = ''.join(filter(str.isdigit, self.telefone))

    def get_required_documents(self):
        return [
            'documento_cliente',
            'unidade_geradora_fatura',
            'unidades_consumidoras_fatura',
            'lista_material',
            'procuracao_assinada',
            'cartao_cnpj',
            'inscricao_estadual',
            'contrato_social',
            'pagamento_art',
            'pagamento_trt',
        ]

    def check_documetacaoCompleta(self):
        required_docs = self.get_required_documents()
        uploaded_approved_doc_types = set(
            self.documents.filter(status=ProjectDocument.STATUS_APPROVED).values_list('document_type', flat=True)
        )
        self.documetacaoCompleta = all(doc_type in uploaded_approved_doc_types for doc_type in required_docs)
        self.save(update_fields=['documetacaoCompleta'])

    def __str__(self):
        return f"{self.codigoCliente} - {self.nomeTitular} (Criado por: {self.created_by_name})"

class ConsumerUnit(models.Model):
    project = models.ForeignKey(
        ClientProject, 
        on_delete=models.CASCADE, 
        related_name='consumer_units',
        null=True,   # Mude o default=0 para null=True
        blank=True
    )
    codigoCliente = models.CharField(max_length=50, verbose_name="Código único do cliente")
    porcentagem = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True, verbose_name="Porcentagem (%)")
    priority_level = models.PositiveSmallIntegerField(
        verbose_name="Nível de Prioridade", help_text="Um valor inteiro...", null=True, blank=True
    )
    prioridade_is_porcentagem = models.BooleanField(
        default= True, verbose_name="Prioridade baseada em porcentagem", help_text="Se marcado..."
    )

    class Meta:
        verbose_name = "Unidade Consumidora"
        verbose_name_plural = "Unidades Consumidoras"
        ordering = ['priority_level']

    def clean(self):
        super().clean()
        if self.project and self.priority_level is not None:
            all_units_for_project = ConsumerUnit.objects.filter(project=self.project)
            if self.pk:
                all_units_for_project = all_units_for_project.exclude(pk=self.pk)
            current_count_excluding_self = all_units_for_project.count()
            max_allowed_priority = current_count_excluding_self
            if not self.pk:
                max_allowed_priority += 1
            else:
                max_allowed_priority = ConsumerUnit.objects.filter(project=self.project).count()
            if not (1 <= self.priority_level <= max_allowed_priority):
                raise ValidationError({'priority_level': f"O nível de prioridade deve ser entre 1 e {max_allowed_priority} para este projeto."})

        # Validacao consertada
        if self.prioridade_is_porcentagem:
            self.priority_level = None
        else:
            self.porcentagem = None

    def __str__(self):
        return f"UC {self.codigoCliente} - Projeto: {self.project.codigoCliente} (Prioridade: {self.priority_level})"

class ListaDeMateriais(models.Model):
    project = models.ForeignKey(ClientProject, on_delete=models.CASCADE, related_name='material_lists', null=True, blank=True)
    tipo = models.CharField(verbose_name="Tipo do Inversor ou Módulo", max_length=50, blank=True, null=True)
    marca = models.CharField(verbose_name="Marca dos Módulos Fotovoltaicos", max_length=100, blank=True, null=True)
    quantidade = models.PositiveIntegerField(verbose_name="Número de módulos", blank=True, null=True)
    modelo = models.CharField(max_length=100, verbose_name="Modelo dos módulos", blank=True, null=True)
    potencia = models.DecimalField(
        max_digits=20, decimal_places=10, verbose_name="Potência de cada Módulo Fotovoltaico (W)", blank=True, null=True
    )
    unidade_de_medida = models.CharField(
        max_length=100, choices=WATS_CHOICES, help_text="Unidade de medida", default="wats"
    )
    

class ProjectDocument(BaseModel, ArquivoMixin):
    STATUS_CHOICES = [
        ('IN_ANALYSIS', 'Em Análise'),
        ('APPROVED', 'Aprovado'),
        ('REJECTED', 'Rejeitado'),
    ]
    STATUS_IN_ANALYSIS = 'IN_ANALYSIS'
    STATUS_APPROVED = 'APPROVED'
    STATUS_REJECTED = 'REJECTED'

    project = models.ForeignKey(
        ClientProject, 
        on_delete=models.CASCADE, 
        related_name='documents',
        null=True,   # Essencial para destravar
        blank=True
    )
    document_name = models.CharField(max_length=80, verbose_name="Nome opcional", blank=True, null=True)
    document_type = models.CharField(max_length=80, choices=DOCUMENT_TYPE_CHOICES, verbose_name="Tipo do documento")
    related_payment_document = models.ForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True, related_name='payment_proofs', help_text="Boleto relacionado"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=IN_ANALYSIS, verbose_name="Status")
    rejection_reason = models.TextField(blank=True,null=True,verbose_name="Motivo da rejeição")
    approved_at = models.DateTimeField(blank=True, null=True, verbose_name="Data de Aprovação")

    class Meta:
        verbose_name = "Documento do Projeto"
        verbose_name_plural = "Documentos do Projeto"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'document_type']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.project.codigoCliente} ({self.get_status_display()})"

    def clean(self):
        super().clean()
        if self.arquivo:
            try:
                validate_file_size(self.arquivo)
            except ValidationError as e:
                raise ValidationError({'arquivo': e.message})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        try:
            self.project.check_documetacaoCompleta()
        except Exception as e:
            pass

    def delete(self, *args, **kwargs):
        arquivo_path = self.arquivo.path if self.arquivo else None
        arquivo_storage = self.arquivo.storage if self.arquivo else None
        super().delete(*args, **kwargs)

        if arquivo_path:
            try:
                if os.path.isfile(arquivo_path):
                    os.remove(arquivo_path)
                elif arquivo_storage:
                    arquivo_storage.delete(arquivo_path)
            except Exception as e:
                pass

        try:
            self.project.check_documetacaoCompleta()
        except Exception as e:
            pass

    @property
    def is_payment_document(self):
        return self.document_type in ['boleto', 'comprovante_de_pagamento']

    @property
    def is_payment_complete(self):
        if self.document_type == 'boleto':
            return self.payment_proofs.filter(status=self.STATUS_APPROVED).exists()
        elif self.document_type == 'comprovante_de_pagamento':
            return self.status == self.STATUS_APPROVED and self.related_payment_document is not None
        return False

    @property
    def payment_status(self):
        if self.document_type == 'boleto':
            if self.payment_proofs.filter(status=self.STATUS_APPROVED).exists():
                return 'PAGO'
            elif self.payment_proofs.exists():
                return 'COMPROVANTE_EM_ANALISE'
            else:
                return 'PENDENTE'
        return None

    @property
    def days_since_upload(self):
        if self.created_at:
            delta = timezone.now() - self.created_at
            return delta.days
        return 0

    @property
    def is_recent(self):
        return self.days_since_upload <= 7