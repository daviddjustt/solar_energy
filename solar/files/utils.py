from django.core.exceptions import ValidationError
import os
import uuid
from django.utils import timezone
from django.utils.text import slugify


def get_document_upload_path(instance, filename):
    # Determine o diretório base com base no tipo da instância do documento.
    # 'instance' será o objeto do modelo (DocumentUser, ProjectDocument, etc.)

    base_path_parts = ['documents'] # Diretório raiz para todos os uploads

    # Verifica se a instância é um DocumentUser (tem um campo 'user')
    if hasattr(instance, 'user') and instance.user:
        base_path_parts.append('users')
        # Usamos o PK do usuário para criar um diretório específico para ele
        base_path_parts.append(str(instance.user.pk))
    # Verifica se a instância é um ProjectDocument (tem um campo 'project')
    # Assumimos que ProjectDocument é outro modelo concreto que herda de Document
    # e tem um ForeignKey para ClientProject.
    elif hasattr(instance, 'project') and instance.project:
        base_path_parts.append('projects')
        # Usamos o codigoCliente do projeto para criar um diretório específico
        base_path_parts.append(instance.project.codigoCliente)
    else:
        # Fallback para outros tipos de documentos ou se o relacionamento ainda não foi definido
        # (embora para DocumentUser e ProjectDocument, user/project deveriam ser obrigatórios)
        base_path_parts.append('unassigned')

    # Adiciona o tipo de documento ao caminho
    document_type_slug = slugify(instance.document_type)
    base_path_parts.append(document_type_slug)

    # Gera um nome de arquivo único para evitar colisões
    name, ext = os.path.splitext(filename)
    unique_filename = f"{slugify(name)}-{uuid.uuid4().hex[:8]}{ext}"

    # Combina todas as partes para formar o caminho final
    return os.path.join(*base_path_parts, unique_filename)

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