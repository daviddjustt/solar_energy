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

class AndamentoDoProjeto(models.TextChoices):
    ANALISE_DE_DOCUMENTOS = 'Em análise de documentos'
    EXECUCAO = "Projeto em Execução"
    # Pagamento do ART e TRT se encaixa aqui ?
    ANALISE_TECNICA = 'Projeto em análise técnica'
    APROVADO = 'Projeto aprovado'
    REPROVADO = 'Projeto reprovado'
    VISTORIA = 'Projeto em vistoria'
    CONCLUIDO = 'Projeto finalizado'

    @classmethod
    def get_display_name(cls, code):
           """Retorna o nome de exibição para o código fornecido."""
           for status in cls:
               if status.name == code:
                   return status.value
           return None
       

class ClientProject(models.Model):
    
    # Choices simples do documento 
    DOCUMENT_TYPE_CHOICES = [
        ('PF', 'Pessoa Física'),
        ('PJ', 'Pessoa Jurídica'),
    ]
    FINANCEIRO_CHOICES = [
        ('valor_unico', 'Valor Único'),
        ('mensalidade', 'Mensalidade'),
    ]

    # Informações básicas do projeto
    client_code = models.CharField(
        max_length=50,
        verbose_name="Código único do cliente",
        )
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_projects',
        verbose_name='Criado por'
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
    voltagem = models.IntegerField(
        verbose_name='voltagem',
        help_text='Voltagem da unidade geradora',
        default=220,
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
        verbose_name="Númeor doo CPF ou CNPJ",
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
    
    #Localização em graus, minutos, segundos
    latGraus = models.SmallIntegerField(
        verbose_name="Latitude (Graus)",
        help_text="Parte inteira da latitude (-90 a 90)"
    )
    latMin = models.SmallIntegerField(
        verbose_name="Latitude (Minutos)",
        help_text="Minutos da latitude (0 a 59)"
    )
    latSeg = models.SmallIntegerField(
        verbose_name="Latitude (Segundos)",
        help_text="Segundos da latitude (0 a 59)"
    )
    longGraus = models.SmallIntegerField(
        verbose_name="Longitude (Graus)",
        help_text="Parte inteira da longitude (-180 a 180)"
    )
    longMin = models.SmallIntegerField(
        verbose_name="Longitude (Minutos)",
        help_text="Minutos da longitude (0 a 59)"
    )
    longSeg = models.SmallIntegerField(
        verbose_name="Longitude (Segundos)",
        help_text="Segundos da longitude (0 a 59)"
    )
    
    # Status da documentação (será complementado pelos status dos documentos individuais)
    documentation_complete = models.BooleanField(
        default=False,
        verbose_name="Documentação completa"
    )
    status = models.CharField(
           max_length=40,
           choices=AndamentoDoProjeto.choices,
           default=AndamentoDoProjeto.ANALISE_DE_DOCUMENTOS,
           verbose_name="Status do Projeto"
    )
    
    # CAMPOS FINANCEIROS
    tipo_financeiro = models.CharField(
        max_length=15,
        choices=FINANCEIRO_CHOICES,
        default='valor_unico',
        verbose_name='Tipo de Financiamento'
    )
    valor_financeiro = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Valor Financeiro',
        help_text='Valor em reais com 2 casas decimais'
    )
    parcelas = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Número de Parcelas',
        help_text='Obrigatório apenas para mensalidade'
    )

    # Metadados
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Propriedades
    @property
    def documento_tipo(self):
        """Retorna o tipo do documento baseado no client_type"""
        return 'CPF' if self.client_type == 'PF' else 'CNPJ'
    @property
    def documento_label(self):
        """Retorna o label apropriado para exibição"""
        return f"{self.documento_tipo}: {self.documento}" if self.documento else self.documento_tipo
    @property
    def decimal_latitude(self):
        """Converte latitude de GMS para decimal"""
        if self.latGraus is None or self.latMin is None or self.latSeg is None:
            return None
        sign = -1 if self.latGraus < 0 else 1
        return Decimal(sign * (abs(self.latGraus) + (self.latMin / 60) + (self.latSeg / 3600))).quantize(Decimal('0.00000001'))
    @property
    def decimal_longitude(self):
        """Converte longitude de GMS para decimal"""
        if self.longGraus is None or self.longMin is None or self.longSeg is None:
            return None
        sign = -1 if self.longGraus < 0 else 1
        return Decimal(sign * (abs(self.longGraus) + (self.longMin / 60) + (self.longSeg / 3600))).quantize(Decimal('0.00000001'))
    @property
    def approved_documents_count(self):
        """Retorna o número de documentos aprovados para o projeto."""
        return self.documents.filter(status=ProjectDocument.APPROVED).count()

    @property
    def in_analysis_documents_count(self):
        """Retorna o número de documentos em análise para o projeto."""
        return self.documents.filter(status=ProjectDocument.IN_ANALYSIS).count()

    @property
    def rejected_documents_count(self):
        """Retorna o número de documentos rejeitados para o projeto."""
        return self.documents.filter(status=ProjectDocument.REJECTED).count()

    @property
    def total_documents_count(self):
        """Retorna o número total de documentos para o projeto."""
        return self.documents.count()
    
    @property
    def created_by_name(self):
        """Retorna o nome do usuário que criou o projeto"""
        return self.created_by.name if self.created_by else "Usuário não identificado"
    
    @property
    def created_by_uuid(self):
        """Retorna o UUID do usuário que criou o projeto"""
        return str(self.created_by.uuid) if self.created_by else None
    
    @property
    def valor_total(self):
        """Calcula o valor total do projeto"""
        if self.tipo_financeiro == 'mensalidade' and self.parcelas:
            return self.valor_financeiro * self.parcelas
        return self.valor_financeiro

    @property
    def resumo_financeiro(self):
        """Retorna um resumo do financiamento"""
        if self.tipo_financeiro == 'valor_unico':
            return f"Valor único: R$ {self.valor_financeiro:,.2f}"
        else:
            total = self.valor_total
            return f"Mensalidade: R$ {self.valor_financeiro:,.2f} x {self.parcelas}x = R$ {total:,.2f}"
    
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
        # ADICIONADO: Validação de coordenadas GMS
        if not (-90 <= self.latGraus <= 90):
            raise ValidationError({
                'latGraus': 'Graus da Latitude devem estar entre -90 e 90.'
            })
        if not (0 <= self.latMin <= 59):
            raise ValidationError({
                'latMin': 'Minutos da Latitude devem estar entre 0 e 59.'
            })
        if not (0 <= self.latSeg <= 59):
            raise ValidationError({
                'latSeg': 'Segundos da Latitude devem estar entre 0 e 59.'
            })

        if not (-180 <= self.longGraus <= 180):
            raise ValidationError({
                'longGraus': 'Graus da Longitude devem estar entre -180 e 180.'
            })
        if not (0 <= self.longMin <= 59):
            raise ValidationError({
                'longMin': 'Minutos da Longitude devem estar entre 0 e 59.'
            })
        if not (0 <= self.longSeg <= 59):
            raise ValidationError({
                'longSeg': 'Segundos da Longitude devem estar entre 0 e 59.'
            })

    def save(self, *args, **kwargs):
        """Override do save"""
        self.full_clean()
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Projeto do Cliente"
        verbose_name_plural = "Projetos dos Clientes"

    # Funções
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

    def get_required_documents(self):
        """Retorna lista de documentos obrigatórios baseado no tipo de cliente"""
        base_docs = [
            'documento_cliente',
            'unidade_geradora_fatura',
            'unidades_consumidoras_fatura',
            'lista_material',
            'procuracao_assinada'
            'cartao_cnpj',
            'inscricao_municipal',
            'inscricao_estadual_',
            'contrato_social',
            'Documentação ART',
            'Documentação TRT',
            ]
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
        self.save(update_fields=['documentation_complete']) # Salva apenas o campo atualizado
 
    def __str__(self):
        return f"{self.client_code} - {self.project_holder_name} (Criado por: {self.created_by_name})"
    
    def clean_money(self):
        """Validação personalizada para campos financeiros"""
        super().clean_money()
        
        # Validar parcelas baseado no tipo financeiro
        if self.tipo_financeiro == 'mensalidade':
            if not self.parcelas:
                raise ValidationError({
                    'parcelas': 'Informe o número de parcelas para mensalidade.'
                })
            elif self.parcelas <= 0:
                raise ValidationError({
                    'parcelas': 'O número de parcelas deve ser maior que zero.'
                })
        else:
            # Se não for mensalidade, limpa o campo parcelas
            self.parcelas = None
        
        # Valor financeiro é obrigatório em ambos os casos
        if self.valor_financeiro is None or self.valor_financeiro <= 0:
            raise ValidationError({
                'valor_financeiro': 'Informe um valor financeiro válido maior que zero.'
            })

    def save(self, *args, **kwargs):
        """Override do save para executar validações"""
        self.full_clean()
        super().save(*args, **kwargs)

class ConsumerUnit(models.Model):
    project = models.ForeignKey(
        ClientProject,
        on_delete=models.CASCADE,
        related_name='consumer_units'
    )
    client_code = models.CharField(
        max_length=50,
        verbose_name="Código único do cliente",
    )
    percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Porcentagem (%)"
    )
    priority_level = models.PositiveSmallIntegerField(
        verbose_name="Nível de Prioridade",
        help_text="Um valor inteiro, onde o número mais baixo indica maior prioridade. Deve ser único por projeto.",
        null=False,
        blank=False,
    )
    class Meta:
        verbose_name = "Unidade Consumidora"
        verbose_name_plural = "Unidades Consumidoras"
        unique_together = ('project', 'priority_level')
        ordering = ['priority_level']
    
    def clean(self):
        super().clean()
        if self.project and self.priority_level is not None:
            # Contar todas as unidades consumidoras para este projeto
            all_units_for_project = ConsumerUnit.objects.filter(project=self.project)

            # Se for uma instância existente (update), exclua-a da contagem para a validação de unicidade
            if self.pk:
                all_units_for_project = all_units_for_project.exclude(pk=self.pk)

            # Calcula o número atual de unidades para o projeto (sem incluir a atual se for update)
            current_count_excluding_self = all_units_for_project.count()

            # O valor máximo de prioridade permitido
            # Se for uma nova unidade, o máximo é (unidades existentes + 1)
            # Se for uma unidade existente, o máximo é (total de unidades já salvas para o projeto)
            max_allowed_priority = current_count_excluding_self
            if not self.pk: # Se for uma nova instância
                max_allowed_priority += 1
            else: # Se for uma instância existente, o número total de unidades é o que já está no banco (incluindo ela mesma)
                max_allowed_priority = ConsumerUnit.objects.filter(project=self.project).count()


            if not (1 <= self.priority_level <= max_allowed_priority):
                raise ValidationError({
                    'priority_level': f"O nível de prioridade deve ser entre 1 e {max_allowed_priority} para este projeto."
                })

            # Verifica a unicidade do priority_level entre as outras unidades do projeto
            if all_units_for_project.filter(priority_level=self.priority_level).exists():
                raise ValidationError({
                    'priority_level': f"Já existe uma unidade consumidora com o nível de prioridade {self.priority_level} para este projeto."
                })

    def __str__(self):
        return f"UC {self.client_code} - Projeto: {self.project.client_code} (Prioridade: {self.priority_level})"

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
        ('pagamento_art', 'Documento que comprove o pagamento da ART'),
        ('pagamento_trt', 'Documento que comprove o pagamento da TRT'), # Adicionado vírgula aqui
        ('inscricao_municipal', 'Documento que comprove o pagamento da inscrição municipal'), # Corrigido "incrição" e adicionado vírgula
        ('inscricao_estadual', 'Documento que comprove o pagamento da inscrição estadual'), # Corrigido "incrição" e adicionado vírgula
        ('comprovante_de_pagamento', 'Boleto ou recibo emitido na compra'),
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
        max_length=80,
        choices=DOCUMENT_TYPE_CHOICES,
        verbose_name="Tipo do documento"
    )
    file_type = models.CharField(
        max_length=10,
        choices=FILE_TYPE_CHOICES,
        verbose_name="Tipo de arquivo"
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
    class Meta:
        verbose_name = "Documento do Projeto"
        verbose_name_plural = "Documentos do Projeto"

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
                # precisará de um mecanismo para passar o usuário para o model (ex: thread-local storage ou signals).
                # Para uma API REST, é mais comum definir isso no serializer ou view.
            elif original.status != self.status and self.status != self.APPROVED:
                # Se o status mudou de APROVADO para outro (rejeitado ou em análise), limpa a data/usuário de aprovação
                self.approved_at = None
        elif self.status == self.APPROVED: # Se é um novo documento e já está sendo criado como APROVADO
            self.approved_at = timezone.now()
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
