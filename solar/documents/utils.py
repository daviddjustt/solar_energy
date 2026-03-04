import os
import uuid
from django.utils import timezone
from django.utils.text import slugify
from django.core.exceptions import ValidationError

CELULAR_REGEX = r'^\d{11}$'

VOLTAGEM_MAP = {
    '127': 'Monofásico - 127V',
    '220': 'Monofásico - 220V',
    '127/220': 'Bifásico - 127/220V',
    '220/380': 'Bifásico - 220/380V',
    '127/220T': 'Trifásico - 127/220V',
    '220/380T': 'Trifásico - 220/380V',
}
# Versão com os labels exatos
VOLTAGEM_LABELS = [
    'Monofásico - 127V',
    'Monofásico - 220V',
    'Bifásico - 127/220V',
    'Bifásico - 220/380V',
    'Trifásico - 127/220V',
    'Trifásico - 220/380V',
]
VOLTAGEM_CHOICES = [
    ('Monofásico - 127V', 'Monofásico - 127V'),
    ('Monofásico - 220V', 'Monofásico - 220V'),
    ('Bifásico - 127/220V', 'Bifásico - 127/220V'),
    ('Bifásico - 220/380V', 'Bifásico - 220/380V'),
    ('Trifásico - 127/220V', 'Trifásico - 127/220V'),
    ('Trifásico - 220/380V', 'Trifásico - 220/380V'),
]
STATUS_CHOICES = [
        ('IN_ANALYSIS', 'Em Análise'),
        ('APPROVED', 'Aprovado'),
        ('REJECTED', 'Rejeitado'),
    ]
WATS_CHOICES = [
    ('W','Wats'),
    ('kW','KiloWats'),
]
IN_ANALYSIS = 'IN_ANALYSIS'
APPROVED = 'APPROVED'
REJECTED = 'REJECTED'
DOCUMENT_TYPE_CHOICES_PESSOA = [
        ('PJ', 'Pessoa Jurídica'),
        ('PF', 'Pessoa Física'),
    ]
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

def convert_voltage_value_to_label(value):
    """Converte value em label"""
    value_str = str(value).strip()
    return VOLTAGEM_MAP.get(value_str, value_str)

def get_voltage_choices():
    """Retorna as choices para o model"""
    return [(label, label) for label in VOLTAGEM_LABELS]