import os
import uuid
import re

from django.core.exceptions import ValidationError
from django.utils.text import slugify
from django.utils import timezone
from django.core.validators import RegexValidator 
from django.db import models

class CelularRegex:
    """Classe para a constante de regex de celular."""
    REGEX = r'^\d{11}$'
    MESSAGE = 'Celular inválido. Formato esperado: DDNNNNNNNNN (ex: 11987654321).'

class MaxImageSize:
    """Classe para a constante de tamanho máximo de imagem."""
    MB = 10

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

class StatusDocumento(models.TextChoices):
    EM_ANALISE = 'IN_ANALYSIS', 'Em Análise'
    APROVADO = 'APPROVED', 'Aprovado'
    REJEITADO = 'REJECTED', 'Rejeitado'

    @classmethod
    def get_display_name(cls, code):
        """Retorna o nome de exibição para o código fornecido."""
        for status in cls:
            if status.name == code:
                return status.value
        return None
    
class TipoDocumento(models.TextChoices):
    # Documentos gerais de projeto
    DOCUMENTO_CLIENTE = 'documento_cliente', 'Documento do Cliente (CPF/CNPJ)'
    FATURA_UNIDADE_GERADORA = 'unidade_geradora_fatura', 'Fatura da Unidade Geradora'
    FATURA_UNIDADES_CONSUMIDORAS = 'unidades_consumidoras_fatura', 'Fatura das Unidades Consumidoras'
    LISTA_MATERIAL = 'lista_material', 'Lista de Materiais'
    PROCURACAO_ASSINADA = 'procuracao_assinada', 'Procuração Assinada'
    CARTAO_CNPJ = 'cartao_cnpj', 'Cartão CNPJ'
    INSCRICAO_ESTADUAL = 'inscricao_estadual_', 'Inscrição Estadual' # Mantendo o underscore para compatibilidade
    CONTRATO_SOCIAL = 'contrato_social', 'Contrato Social'
    DOCUMENTACAO_ART = 'documentacao_art', 'Documentação ART'
    DOCUMENTACAO_TRT = 'documentacao_trt', 'Documentação TRT'

    BOLETO = 'boleto', 'Boleto de Pagamento'
    COMPROVANTE_PAGAMENTO = 'comprovante_de_pagamento', 'Comprovante de Pagamento'

    PESSOA_FISICA = 'PF', 'Pessoa Física'
    PESSOA_JURIDICA = 'PJ', 'Pessoa Jurídica'

    @classmethod
    def get_display_name(cls, code):
        """Retorna o nome de exibição para o código fornecido."""
        for doc_type in cls:
            if doc_type.name == code:
                return doc_type.value
        return None

class VoltagemSistema(models.TextChoices):
    MONOFASICO_127 = 'Monofásico - 127V', 'Monofásico - 127V'
    MONOFASICO_220 = 'Monofásico - 220V', 'Monofásico - 220V'
    BIFASICO_127_220 = 'Bifásico - 127/220V', 'Bifásico - 127/220V'
    BIFASICO_220_380 = 'Bifásico - 220/380V', 'Bifásico - 220/380V'
    TRIFASICO_127_220 = 'Trifásico - 127/220V', 'Trifásico - 127/220V'
    TRIFASICO_220_380 = 'Trifásico - 220/380V', 'Trifásico - 220/380V'

    @classmethod
    def get_display_name(cls, code):
        for choice in cls:
            if choice.name == code:
                return choice.value
        return None

class UnidadePotencia(models.TextChoices):
    WATS = 'W', 'Wats'
    KILOWATS = 'kW', 'KiloWats'

    @classmethod
    def get_display_name(cls, code):
        for choice in cls:
            if choice.name == code:
                return choice.value
        return None
    
class FileType(models.TextChoices):
    PHOTO = 'photo', 'Foto'
    PDF = 'pdf', 'PDF'
    DOCUMENT = 'document', 'Documento' # Adicionado para agrupar .doc, .docx, .xls, .xlsx
    OTHER = 'other', 'Outro'

    @classmethod
    def get_display_name(cls, code):
        for choice in cls:
            if choice.name == code:
                return choice.label # Usar .label para o nome de exibição
        return None

class FileValidationSettings:
    MAX_FILE_SIZE_MB = 10

    # Mapeia os tipos de arquivo (FileType) para suas extensões permitidas
    ALLOWED_EXTENSIONS_MAP = {
        FileType.PHOTO: ['.jpg', '.jpeg', '.png'],
        FileType.PDF: ['.pdf'],
        FileType.DOCUMENT: ['.doc', '.docx', '.xls', '.xlsx'],
        # FileType.OTHER pode não ter extensões específicas ou ser mais flexível
    }

    @classmethod
    def get_all_allowed_extensions(cls):
        """Retorna uma lista plana de todas as extensões permitidas."""
        all_extensions = []
        for extensions_list in cls.ALLOWED_EXTENSIONS_MAP.values():
            all_extensions.extend(extensions_list)
        return all_extensions
    

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
    Valida o tamanho do arquivo (máximo definido em FileValidationSettings).
    """
    max_size_mb = FileType.MAX_FILE_SIZE_MB
    if file.size > max_size_mb * 1024 * 1024:
        raise ValidationError(
            f'O arquivo não pode ter mais de {max_size_mb} MB. '
            f'Tamanho atual: {file.size / (1024 * 1024):.2f} MB'
        )

def validate_file_extension(file):
    """
    Valida a extensão do arquivo, permitindo apenas as extensões definidas
    em FileValidationSettings.
    """
    allowed_extensions = FileValidationSettings.get_all_allowed_extensions()

    ext = os.path.splitext(file.name)[1].lower()

    if ext not in allowed_extensions:
        raise ValidationError(
            f'Tipo de arquivo não permitido: {ext}. '
            f'Formatos aceitos: {", ".join(allowed_extensions)}'
        )


def convert_voltage_value_to_label(value):
    """
    Converte um valor de voltagem (string do banco) para seu label de exibição.
    Utiliza a classe Voltagem.
    """
    value_str = str(value).strip()
    return VoltagemSistema.get_label_from_value(value_str)

def get_voltage_choices():
    """
    Retorna as choices para o campo de voltagem do modelo,
    utilizando a classe Voltagem.
    """
    return VoltagemSistema.choices