import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import Throttled, ValidationError

logger = logging.getLogger(__name__)

def custom_exception_handler(exc, context):
    """
    Handler customizado para exceções do DRF
    Formata respostas de erro de forma consistente
    """
    
    # Chamar o exception handler padrão do DRF
    response = exception_handler(exc, context)
    
    # Se não houver resposta, retornar erro 500
    if response is None:
        logger.error(f"Erro não tratado: {exc}", exc_info=True)
        return Response(
            {
                'success': False,
                'error': 'Erro interno do servidor',
                'detail': 'Um erro inesperado ocorreu'
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    # Tratamento customizado para Throttled
    if isinstance(exc, Throttled):
        custom_response_data = {
            'success': False,
            'error': 'Muitas requisições',
            'detail': str(exc.detail),
            'retry_after': exc.wait(),
        }
        response.data = custom_response_data
        response.status_code = status.HTTP_429_TOO_MANY_REQUESTS
        logger.warning(f"Throttling acionado: {context['request'].path}")
        return response
    
    # Tratamento customizado para ValidationError
    if isinstance(exc, ValidationError):
        logger.warning(f"Erro de validação: {exc.detail}")
        custom_response_data = {
            'success': False,
            'error': 'Erro de validação',
            'details': exc.detail
        }
        response.data = custom_response_data
        return response
    
    # Formatar resposta padrão
    if response.status_code >= 500:
        logger.error(f"Erro 5xx: {exc}", exc_info=True)
        custom_response_data = {
            'success': False,
            'error': 'Erro interno do servidor',
            'detail': 'Um erro inesperado ocorreu'
        }
    elif response.status_code >= 400:
        logger.warning(f"Erro 4xx: {exc}")
        custom_response_data = {
            'success': False,
            'error': response.data.get('detail', 'Erro na requisição'),
            'details': response.data
        }
    else:
        return response
    
    response.data = custom_response_data
    return response
