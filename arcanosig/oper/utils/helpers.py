from functools import wraps
from typing import Type, Union

# Django Core

from django.db.models import QuerySet
from django.core.exceptions import ValidationError

# Django REST Framework

from rest_framework.response import Response
from rest_framework import ( 
    status,
    serializers,
)

def handle_validation_error(error: Union[ValidationError, serializers.ValidationError]) -> Response:
    """
    Utilitário para padronizar o tratamento de erros de validação.
    
    Args:
        error: Uma exceção de validação do Django ou DRF.
    
    Returns:
        Response: Uma resposta HTTP 400 com os detalhes do erro.
    """
    # Tratamento para erros do Django
    if hasattr(error, 'message_dict'):
        error_data = error.message_dict
    # Tratamento para erros do DRF
    elif hasattr(error, 'detail'):
        error_data = error.detail
    # Tratamento para erros com mensagens
    elif hasattr(error, 'messages') and error.messages:
        error_data = {'detail': error.messages}
    # Fallback para erro genérico
    else:
        error_data = {'detail': str(error)}
    
    return Response(error_data, status=status.HTTP_400_BAD_REQUEST)

def handle_exceptions(func):
    """
    Decorator para padronizar o tratamento de exceções nas views.
    
    Args:
        func: A função view a ser decorada.
    
    Returns:
        Uma função wrapper que trata as exceções.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (ValidationError, serializers.ValidationError) as e:
            # Trata ValidationError do Django e DRF de forma unificada
            return handle_validation_error(e)
        except Exception as e:
            # Log do erro para monitoramento (implementar logger)
            return Response(
                {
                    "detail": "Erro interno do servidor", 
                    "error_message": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    return wrapper

def optimize_queryset(
    queryset: QuerySet, 
    serializer_class: Type[serializers.ModelSerializer], 
    exclude_fields: list = None
) -> QuerySet:
    """
    Otimiza querysets com prefetch_related e select_related baseado nos campos do serializer.
    
    Args:
        queryset: O queryset a ser otimizado
        serializer_class: A classe do serializer para extrair os campos relacionados
        exclude_fields: Lista de campos para ignorar na otimização
    
    Returns:
        QuerySet otimizado
    """
    # Campos padrão para exclusão
    exclude_fields = exclude_fields or []
    
    # Campos para prefetch e select
    to_prefetch = []
    to_select = []
    
    try:
        # Cria uma instância do serializador sem contexto
        serializer_instance = serializer_class()
    except TypeError:
        # Caso não consiga criar a instância, retorna o queryset original
        return queryset
    
    # Analisa os campos do serializer
    for field_name, field in serializer_instance.fields.items():
        # Ignora campos na lista de exclusão
        if field_name in exclude_fields:
            continue
        
        # Tratamento para campos relacionais
        if isinstance(field, serializers.RelatedField):
            to_prefetch.append(field_name)
        
        # Tratamento para campos de chave primária relacionada
        elif isinstance(field, serializers.PrimaryKeyRelatedField):
            to_select.append(field_name)
        
        # Tratamento para campos aninhados ou com source personalizado
        elif hasattr(field, 'source') and '__' in str(field.source):
            related_field = str(field.source).split('__')[0]
            to_select.append(related_field)
    
    # Aplica otimizações
    try:
        if to_select:
            queryset = queryset.select_related(*to_select)
        
        if to_prefetch:
            queryset = queryset.prefetch_related(*to_prefetch)
    except Exception as e:
        # Tratamento de erro caso a otimização falhe
        print(f"Erro na otimização do queryset: {e}")
    
    return queryset