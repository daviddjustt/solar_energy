from celery import shared_task
from .models import ClientProject, ConsumerUnit, ProjectDocument

import gspread
from oauth2client.service_account import ServiceAccountCredentials

def append_to_google_sheet(sheet_id, dados):
    """
    Adiciona uma linha de dados ao Google Sheets.

    :param sheet_id: ID da planilha do Google Sheets.
    :param dados: Lista de dados a serem adicionados como uma nova linha.
    """
    # Defina o escopo e carregue as credenciais
    escopo = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    credenciais = ServiceAccountCredentials.from_json_keyfile_name('', escopo)

    # Autentique-se e abra a planilha
    cliente = gspread.authorize(credenciais)
    planilha = cliente.open_by_key(sheet_id)
    aba = planilha.sheet1  # Seleciona a primeira aba

    # Adiciona os dados como uma nova linha
    aba.append_row(dados)

@shared_task
def enviar_dados_para_google_sheets():
    # Obtém todos os projetos
    projetos = ClientProject.objects.all()
    for projeto in projetos:
        # Coleta os dados do projeto
        dados_projeto = [
            projeto.client_code,
            projeto.project_holder_name,
            projeto.project_class,
            projeto.email,
            projeto.get_client_type_display(),
            projeto.cep,
            projeto.street,
            projeto.number,
            projeto.neighborhood,
            projeto.city,
            projeto.complement or '',
            projeto.cpf,
            projeto.phone,
            str(projeto.latitude),
            str(projeto.longitude),
            projeto.voltage,
            'Sim' if projeto.documentation_complete else 'Não',
            projeto.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            projeto.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            projeto.created_by.username
        ]
        # Coleta as unidades consumidoras associadas
        unidades_consumidoras = ConsumerUnit.objects.filter(project=projeto)
        for unidade in unidades_consumidoras:
            dados_unidade = [
                unidade.client_code,
                str(unidade.percentage) if unidade.percentage else ''
            ]
            # Adiciona os dados da unidade consumidora aos dados do projeto
            dados_projeto.extend(dados_unidade)
        # Coleta os documentos do projeto
        documentos = ProjectDocument.objects.filter(project=projeto)
        for documento in documentos:
            dados_documento = [
                documento.get_document_type_display(),
                documento.file.url,
                documento.get_file_type_display(),
                documento.description or '',
                'Sim' if documento.is_approved else 'Não',
                documento.rejection_reason or '',
                documento.uploaded_at.strftime('%Y-%m-%d %H:%M:%S'),
                documento.approved_at.strftime('%Y-%m-%d %H:%M:%S') if documento.approved_at else '',
                documento.approved_by.username if documento.approved_by else ''
            ]
            # Adiciona os dados do documento aos dados do projeto
            dados_projeto.extend(dados_documento)
        # Envia os dados para o Google Sheets
        append_to_google_sheet('SEU_SHEET_ID', dados_projeto)
