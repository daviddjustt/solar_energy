from django.db import models
from decimal import Decimal
from django.db import models
from django.conf import settings

from solar.documents.models import BaseModel, ArquivoMixin 

class ServiceType(BaseModel):
    codigo = models.SlugField("Código", max_length=50, unique=True)
    nome = models.CharField("Serviço", max_length=100)
    valor = models.DecimalField("Valor", max_digits=10, decimal_places=2)
    prazo_informativo = models.CharField("Prazo (informativo)", max_length=50)
    ativo = models.BooleanField("Ativo", default=True)

    class Meta:
        verbose_name = "Tipo de Serviço"
        verbose_name_plural = "Tipos de Serviço"

    def __str__(self):
        return self.nome

class ServiceRequest(BaseModel):
    
    class StatusChoices(models.TextChoices):
        ANALISE = 'ANALISE_DOCUMENTOS', 'Análise de Documentos'
        REALIZANDO = 'REALIZANDO_SERVICO', 'Realizando Serviço'
        PENDENCIAS = 'PENDENCIAS', 'Pendências'
        CONCLUIDO = 'CONCLUIDO', 'Concluído'
        REPROVADO = 'REPROVADO', 'Reprovado'

    class PaymentStatusChoices(models.TextChoices):
        PENDENTE = 'PENDENTE', 'Pendente'
        COMPROVANTE_EM_ANALISE = 'COMPROVANTE_EM_ANALISE', 'Comprovante em Análise'
        PAGO = 'PAGO', 'Pago'

    class RateioChoices(models.TextChoices):
        PORCENTAGEM = 'PORCENTAGEM', 'Porcentagem'
        PRIORIDADE = 'PRIORIDADE', 'Prioridade'
        
    # VOLTAGEM_CHOICES (Importe ou recrie as opções usadas em projetos)
    class TensaoChoices(models.TextChoices):
        MONO_127 = 'MONO_127', 'Monofásico 127V'
        MONO_220 = 'MONO_220', 'Monofásico 220V'
        BI_127_220 = 'BI_127_220', 'Bifásico 127/220V'
        BI_220_380 = 'BI_220_380', 'Bifásico 220/380V'
        TRI_127_220 = 'TRI_127_220', 'Trifásico 127/220V'
        TRI_220_380 = 'TRI_220_380', 'Trifásico 220/380V'

    # Identificação
    tipo = models.ForeignKey(ServiceType, on_delete=models.PROTECT, related_name='solicitacoes')
    solicitante = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='solicitacoes_servicos')
    tipo_pessoa = models.CharField("Tipo de Pessoa", max_length=2, choices=[('PF', 'Física'), ('PJ', 'Jurídica')])
    nome_razao_social = models.CharField("Nome / Razão Social", max_length=255)
    documento = models.CharField("CPF/CNPJ", max_length=20)
    endereco = models.TextField("Endereço")
    unidade_consumidora = models.CharField("Unidade Consumidora", max_length=50, blank=True, null=True)
    telefone_contato = models.CharField("Telefone de Contato", max_length=20, blank=True, null=True)
    ponto_referencia_1 = models.CharField("Ponto de Referência 1", max_length=255, blank=True, null=True)
    ponto_referencia_2 = models.CharField("Ponto de Referência 2", max_length=255, blank=True, null=True)
    necessita_obra_rede = models.BooleanField("Necessita obra na rede?", default=False)
    observacoes = models.TextField("Observações Iniciais", blank=True, null=True)

    # Fluxo
    status = models.CharField("Status", max_length=30, choices=StatusChoices.choices, default=StatusChoices.ANALISE)
    executor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='servicos_executados')
    motivo_reprova = models.TextField("Motivo da Reprovação", blank=True, null=True)

    # Financeiro
    valor_cobrado = models.DecimalField("Valor Cobrado", max_digits=10, decimal_places=2)
    payment_status = models.CharField("Status do Pagamento", max_length=30, choices=PaymentStatusChoices.choices, default=PaymentStatusChoices.PENDENTE)

    # Resultado (Conclusão)
    protocolo = models.CharField("Protocolo", max_length=100, blank=True, null=True)
    uc_resultado = models.CharField("UC Resultado", max_length=50, blank=True, null=True)
    prazo_concessionaria = models.DateField("Prazo da Concessionária", blank=True, null=True)
    nota = models.TextField("Nota/Observação Final", blank=True, null=True)
    
    # Específicos de Consulta
    carga = models.DecimalField("Carga (kW)", max_digits=10, decimal_places=2, blank=True, null=True)
    tensao_nominal = models.CharField("Tensão Nominal", max_length=20, choices=TensaoChoices.choices, blank=True, null=True)
    potencia_transformador = models.DecimalField("Potência do Transformador (kVA)", max_digits=10, decimal_places=2, blank=True, null=True)

    # Específicos de Compensação
    modalidade_rateio = models.CharField("Modalidade de Rateio", max_length=20, choices=RateioChoices.choices, blank=True, null=True)
    geracao_mensal_estimada = models.DecimalField("Geração Mensal Estimada (kWh)", max_digits=10, decimal_places=2, blank=True, null=True)
    consumo_mensal_geradora = models.DecimalField("Consumo Mensal da Geradora (kWh)", max_digits=10, decimal_places=2, blank=True, null=True)
    uc_acumula_excedente = models.CharField("UC Acumula Excedente", max_length=50, blank=True, null=True, help_text="Vazio indica a unidade de maior consumo.")

    class Meta:
        verbose_name = "Solicitação de Serviço"
        verbose_name_plural = "Solicitações de Serviços"
        ordering = ['-created_at'] # Assumindo que o BaseModel tem created_at

    def __str__(self):
        return f"Serviço #{self.id} - {self.tipo.nome} ({self.status})"

class ServicePendency(BaseModel):
    class StatusChoices(models.TextChoices):
        ABERTA = 'ABERTA', 'Aberta'
        RESPONDIDA = 'RESPONDIDA', 'Respondida'
        RESOLVIDA = 'RESOLVIDA', 'Resolvida'

    service = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name='pendencias')
    titulo = models.CharField("Título (Nome do documento pedido)", max_length=255)
    observacao = models.TextField("Observação")
    criada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.ABERTA)

class ServiceAttachment(BaseModel, ArquivoMixin): # Assumindo que junta com o ArquivoMixin posteriormente
    class CategoriaChoices(models.TextChoices):
        SOLICITACAO = 'SOLICITACAO', 'Solicitação'
        PENDENCIA_EQUIPE = 'PENDENCIA_EQUIPE', 'Pendência da Equipe'
        PENDENCIA_CLIENTE = 'PENDENCIA_CLIENTE', 'Pendência do Cliente'
        OBSERVACAO = 'OBSERVACAO', 'Observação'
        RESULTADO = 'RESULTADO', 'Resultado'
        BOLETO = 'BOLETO', 'Boleto'
        COMPROVANTE = 'COMPROVANTE_PAGAMENTO', 'Comprovante de Pagamento'

    class StatusChoices(models.TextChoices):
        IN_ANALYSIS = 'IN_ANALYSIS', 'Em Análise'
        APPROVED = 'APPROVED', 'Aprovado'
        REJECTED = 'REJECTED', 'Rejeitado'

    service = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name='anexos')
    categoria = models.CharField(max_length=30, choices=CategoriaChoices.choices)
    document_type = models.CharField(max_length=50) # Deve validar contra as novas opções de DOCUMENT_TYPE_CHOICES
    document_name = models.CharField(max_length=255, blank=True, null=True)
    enviado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    pendencia = models.ForeignKey(ServicePendency, on_delete=models.CASCADE, null=True, blank=True, related_name='anexos')
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.IN_ANALYSIS)
    rejection_reason = models.TextField("Motivo da Rejeição", blank=True, null=True)
    
    # Ligação exclusiva para comprovante → boleto
    related_payment_document = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)

class ServiceUnit(BaseModel):
    class PapelChoices(models.TextChoices):
        GERADORA = 'GERADORA', 'Geradora'
        BENEFICIARIA = 'BENEFICIARIA', 'Beneficiária'
        TRANSFERENCIA = 'TRANSFERENCIA', 'Transferência (Troca de Titularidade)'

    service = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name='unidades')
    papel = models.CharField(max_length=20, choices=PapelChoices.choices)
    ordem = models.PositiveIntegerField(default=0)
    uc_antiga = models.CharField(max_length=50, blank=True, null=True)
    uc_nova = models.CharField(max_length=50, blank=True, null=True)
    porcentagem = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    prioridade = models.PositiveIntegerField(blank=True, null=True)
    fatura = models.ForeignKey(ServiceAttachment, on_delete=models.SET_NULL, null=True, blank=True)

class ServiceObservation(BaseModel):
    service = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name='observacoes_livres')
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    texto = models.TextField()

class ServiceStatusHistory(BaseModel):
    service = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name='historico_status')
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    old_status = models.CharField(max_length=30)
    new_status = models.CharField(max_length=30)
    changed_at = models.DateTimeField(auto_now_add=True)