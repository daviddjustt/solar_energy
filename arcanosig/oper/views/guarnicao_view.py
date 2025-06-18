from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from arcanosig.oper.models.operacao import Guarnicao # Ajuste o caminho de importação conforme necessário
import uuid

User = get_user_model() # Obtém o modelo de usuário ativo

class GuarnicaoRemoveMembroView(APIView):
        # O método delete agora espera guarnicao_id (int) e membro_id (int)
        def delete(self, request, guarnicao_id: int, membro_id: uuid):
            # Obter a guarnição
            guarnicao = get_object_or_404(Guarnicao, pk=guarnicao_id)

            # Obter o usuário (membro) pelo ID inteiro
            user_to_remove = get_object_or_404(User, pk=membro_id)

            try:
                # Usar o método de negócio do modelo Guarnicao
                success = guarnicao.remover_membro(user_to_remove)

                if success:
                    return Response({"detail": "Membro removido com sucesso."}, status=status.HTTP_204_NO_CONTENT)
                else:
                     # O método remover_membro retorna True em sucesso, então esta parte pode não ser alcançada
                     # se o get_object_or_404 para o usuário for bem-sucedido, mas é bom ter.
                     return Response({"detail": "Associação membro-guarnição não encontrada."}, status=status.HTTP_404_NOT_FOUND)

            except ValidationError as e:
                # Captura a exceção levantada pelo método remover_membro (ex: tentar remover comandante)
                return Response({"detail": e.message}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                # Captura outros erros inesperados
                return Response({"detail": f"Erro interno ao remover membro: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

