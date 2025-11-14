from django.core.exceptions import ValidationError
import os
import uuid
from django.utils import timezone
from django.utils.text import slugify

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