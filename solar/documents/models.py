from django.db import models
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError
from decimal import Decimal
import os
from django.utils import timezone
from solar.files.models import BaseModel, ArquivoMixin

from .utils import (
    CELULAR_REGEX,
    get_document_upload_path, 
    validate_file_size, 
    validate_file_extension, 
)

class AndamentoDoProjeto(models.TextChoices):
    ANALISE_DE_DOCUMENTOS = 'Em análise de documentos'
    EXECUCAO = "Projeto em Execução"
    PAGAMENTOS = 'Pagamento da TRT/ART e pagamento do projeto'
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
        ('PJ', 'Pessoa Jurídica'),
        ('PF', 'Pessoa Física'),
    ]
    FINANCEIRO_CHOICES = [
        ('valor_unico', 'Valor Único'),
        ('mensalidade', 'Mensalidade'),
    ]

    # Informações básicas do projeto
    codigoCliente = models.CharField(
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
    nomeTitular = models.CharField(
        max_length=200,
        verbose_name="Nome do titular do projeto"
    )
    classe = models.CharField(
        max_length=100,
        verbose_name="Classe"
    )
    tipoDocumento = models.CharField(
        max_length=2,
        choices=DOCUMENT_TYPE_CHOICES,
        default='PJ',
        verbose_name="Tipo de cliente"
    )
    VOLTAGEM_CHOICES = [
        ('Monofásico - 127V', 'Monofásico - 127V'),
        ('Monofásico - 220V', 'Monofásico - 220V'),
        ('Bifásico - 127/220V', 'Bifásico - 127/220V'),
        ('Bifásico - 220/380V', 'Bifásico - 220/380V'),
        ('Trifásico - 127/220V', 'Trifásico - 127/220V'),
        ('Trifásico - 220/380V', 'Trifásico - 220/380V'),
    ]
    voltagem = models.CharField(
        max_length=100,
        choices=VOLTAGEM_CHOICES,
        help_text="Voltagem do consumidor"
    )
    email = models.EmailField(
        max_length=255,
        unique=False,
        verbose_name='Email'
    )
    celular_validator = RegexValidator(
        regex=CELULAR_REGEX,
        message='Celular inválido'
    )
    telefone = models.CharField(
        max_length=11,
        validators=[celular_validator],
        verbose_name='Telefone'
    )
    # Endereço
    cep = models.CharField(
        max_length=9,
        validators=[RegexValidator(regex=r'^\d{5}-?\d{3}$', message="CEP deve estar no formato XXXXX-XXX")],
        verbose_name="CEP"
    )
    rua = models.CharField(max_length=200, verbose_name="Logradouro")
    numero = models.CharField(max_length=20, verbose_name="Número")
    bairro = models.CharField(max_length=100, verbose_name="Bairro")
    cidade = models.CharField(max_length=100, verbose_name="Cidade")
    complemento = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name="complementoo"
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
    
    # Status da documentação (será complementoado pelos status dos documentos individuais)
    documetacaoCompleta = models.BooleanField(
        default=False,
        verbose_name="Documentação completa"
    )
    status = models.CharField(
           max_length=43,
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
        help_text='Valor em reais com 2 casas decimais',
        default=0.00,
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
    
    def __str__(self):
        return f"{self.name} - {self.voltagem}"
    
    @property
    def cnpj_or_cpf_do_cliente(self):
        """
        Retorna o valor do campo CNPJ do usuário associado a este projeto.
        """
        if self.user:
            return self.user.cnpj or self.user.cpf
        
    @property
    def documento_tipo(self):
        """Retorna o tipo do documento baseado no tipoDocumento"""
        return 'CPF' if self.tipoDocumento == 'PF' else 'PJ'
    
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

    def _normalize_text_fields(self):
        """Normaliza os campos de texto."""
        if self.name:
            self.name = self.name.upper()
        if self.cnpj:
            self.cnpj = ''.join(filter(str.isdigit, self.cnpj))
        if self.telefone:
            self.telefone = ''.join(filter(str.isdigit, self.telefone))

    def get_required_documents(self):
        """Retorna lista de documentos obrigatórios"""
        base_docs = [
            'documento_cliente',
            'unidade_geradora_fatura',
            'unidades_consumidoras_fatura',
            'lista_material',
            'procuracao_assinada'
            'cartao_cnpj',
            'inscricao_estadual_',
            'contrato_social',
            'Documentação ART',
            'Documentação TRT',
            ]
        return base_docs

    @property
    def is_payment_complete(self):
        """Verifica se o pagamento está completo (boleto + comprovante aprovado)"""
        if self.document_type == 'boleto':
            return self.payment_proofs.filter(status=self.APPROVED).exists()
        elif self.document_type == 'comprovante_de_pagamento':
            return self.status == self.APPROVED and self.related_payment_document is not None
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
    
    def check_documetacaoCompleta(self):
        """Verifica se toda documentação obrigatória foi enviada E APROVADA"""
        required_docs = self.get_required_documents()
        # Agora, consideramos apenas documentos aprovados para a completude
        uploaded_approved_doc_types = set(
            self.documents.filter(status=ProjectDocument.APPROVED)
            .values_list('document_type', flat=True)
        )
        self.documetacaoCompleta = all(doc_type in uploaded_approved_doc_types for doc_type in required_docs)
        self.save(update_fields=['documetacaoCompleta']) # Salva apenas o campo atualizado
 
    def __str__(self):
        return f"{self.codigoCliente} - {self.nomeTitular} (Criado por: {self.created_by_name})"
    
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

    def save(self, *args, **kwargs):
        """Override do save para executar validações"""
        self.full_clean()
        super().save(*args, **kwargs)

class ConsumerUnit(models.Model):
    project = models.ForeignKey(
        ClientProject,
        on_delete=models.CASCADE,
        related_name='consumer_units',
        default=0,
    )
    codigoCliente = models.CharField(
        max_length=50,
        verbose_name="Código único do cliente",
    )
    porcentagem = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Porcentagem (%)"
    )
    priority_level = models.PositiveSmallIntegerField(
        verbose_name="Nível de Prioridade",
        help_text="Um valor inteiro, onde o número mais baixo indica maior prioridade. Deve ser único por projeto.",
        null=True,
        blank=True,
    )
    priodidade_is_porcentagem = models.BooleanField(
        default= True,
        verbose_name="Prioridade baseada em porcentagem",
        help_text="Se marcado, a prioridade será determinada pela porcentagem em vez do nível de prioridade."
    )
    class Meta:
        verbose_name = "Unidade Consumidora"
        verbose_name_plural = "Unidades Consumidoras"
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

    def validate(self):
        super().validate()
        # Garantir unicidade do nível de prioridade dentro do mesmo projeto
        if self.priodidade_is_porcentagem == True:
            self.priority_level = None
        else:
            self.porcentagem = None
                
    def __str__(self):
        return f"UC {self.codigoCliente} - Projeto: {self.project.codigoCliente} (Prioridade: {self.priority_level})"

class ListaDeMateriais(models.Model):
    project = models.ForeignKey(
        ClientProject,
        on_delete=models.CASCADE,
        related_name='material_lists'
    )
    
    # Campos relacionados aos módulos fotovoltáicos 
    quantd_mod_fotovoltaico = models.PositiveIntegerField(
        verbose_name="Quantidade de Módulos Fotovoltaicos",
        blank=True,
        null=True,
    )
    marca_mod_fotovoltaico = models.CharField(
        verbose_name="Marca dos Módulos Fotovoltaicos",
        blank=True,
        null=True,
    )
    potencia_mod_fotovoltaico = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        verbose_name="Potência de cada Módulo Fotovoltaico (W)",
        blank=True,
        null=True,
    )
    modelo_mod_fotovoltaico = models.CharField(
        max_length=100,
        verbose_name="Modelo dos Módulos Fotovoltaicos",
        blank=True,
        null=True,
    )
    
    # Inversores
    quantd_inversores = models.PositiveIntegerField(
        verbose_name="Quantidade de Inversores",
        blank=True,
        null=True,
    )
    marca_inversores = models.CharField(
        verbose_name="Marca dos Inversores",
        blank=True,
        null=True,
    )
    potencia_nominal_inversores = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        verbose_name="Potência nominal dos inversores (kW)",
        blank=True,
        null=True,
    )
    modelo_inversores = models.CharField(
        max_length=100,
        verbose_name="Modelo dos Inversores",
        blank=True,
        null=True,
    )   
    
    @property
    def valor_total(self):
        """Calcula o valor total do material"""
        return self.quantidade * self.valor_unitario
    
    def __str__(self):
        return f"{self.descricao} - {self.quantidade} x R$ {self.valor_unitario:,.2f} = R$ {self.valor_total:,.2f}"

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
        # Documentos adicionais para PJ
        ('cartao_cnpj', 'Cartão CNPJ'),
        ('contrato_social', 'Contrato Social'),
        #Pagamentos
        ('boleto', 'Boleto'),
        ('comprovante_de_pagamento', 'Comprovante de Pagamento'),
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
    # NOVO CAMPO para ligação
    related_payment_document = models.ForeignKey(
        'self', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='payment_proofs',
        help_text="Documento relacionado (boleto para comprovante ou vice-versa)"
    )
    # NOVO CAMPO: Status do documento
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=IN_ANALYSIS, # Documentos recém-enviados começam "Em Análise"
        verbose_name="Status do Documento"
    )
    # `uploaded_at` é fornecido por BaseModel.created_at
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
    
    # ==========================================
    # PROPERTIES E MÉTODOS AUXILIARES
    # ==========================================
    
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