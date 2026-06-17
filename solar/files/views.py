import os
import zipfile
from io import BytesIO

from django.shortcuts import get_object_or_404
from django.http import FileResponse
from django.conf import settings

from rest_framework import status, permissions, generics, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated

from solar.users.models import User
from .serializers import DocumentUser, DocumentUserSerializer

# =====================================================================
# IMPORTAÇÃO DOS NOVOS SERVIÇOS ADAPTADOS (Camada 4)
# =====================================================================
from solar.notifications.services import (
    notify_user_boleto_added,
    notify_user_comprovante_added
)

class DocumentUserDownloadView(APIView):
    """
    Permite baixar um documento específico de um usuário.
    URL: /api/v1/users/<uuid:user_pk>/documents/<int:document_pk>/download/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, user_pk, document_pk):
        user = get_object_or_404(User, uuid=user_pk)
        document = get_object_or_404(DocumentUser, pk=document_pk, user=user)

        # Lógica de Permissão:
        # Apenas o próprio usuário, superusuários, administradores ou técnicos podem baixar.
        if not (request.user.is_superuser or request.user.is_admin or request.user.is_tecnico or request.user == user):
            raise PermissionDenied("Você não tem permissão para baixar este documento.")

        # Assumindo que 'arquivo' é um FileField/ImageField no seu modelo DocumentUser
        if not document.arquivo:
            raise("O documento não possui um arquivo anexado.")

        file_path = document.arquivo.path

        if not os.path.exists(file_path):
            raise("Arquivo não encontrado no servidor.")

        response = FileResponse(open(file_path, 'rb'), content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
        return response

class DocumentUserDownloadAllView(APIView):
    """
    Compacta e baixa todos os documentos de um usuário em um arquivo ZIP.
    URL: /api/v1/users/<uuid:user_pk>/documents/download-all/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, user_pk):
        user = get_object_or_404(User, uuid=user_pk)
        documents = DocumentUser.objects.filter(user=user)

        # Lógica de Permissão:
        # Apenas o próprio usuário, superusuários, administradores ou técnicos podem baixar todos os documentos.
        if not (request.user.is_superuser or request.user.is_admin or request.user.is_tecnico or request.user == user):
            raise PermissionDenied("Você não tem permissão para baixar todos os documentos deste usuário.")

        if not documents.exists():
            return Response({"detail": "Nenhum documento encontrado para este usuário."}, status=status.HTTP_404_NOT_FOUND)

        buffer = BytesIO()
        with zipfile.ZipFile(buffer, 'w') as zip_file:
            for doc in documents:
                if doc.arquivo and os.path.exists(doc.arquivo.path):
                    # Adiciona o arquivo ao ZIP. O segundo argumento é o nome dentro do ZIP.
                    # Usamos doc.document_type para evitar nomes duplicados se houver vários arquivos com o mesmo nome base
                    file_name_in_zip = f"{doc.document_type}_{os.path.basename(doc.arquivo.path)}"
                    zip_file.write(doc.arquivo.path, file_name_in_zip)

        buffer.seek(0)
        response = FileResponse(buffer, content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{user.name}_documents.zip"'
        return response

class DocumentUserListCreateView(generics.ListCreateAPIView):
    serializer_class = DocumentUserSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Filtra documentos para o usuário especificado na URL
        user_pk = self.kwargs['user_pk']
        user = get_object_or_404(User, pk=user_pk)
        # Garante que apenas o próprio usuário ou um admin/técnico pode ver seus documentos
        if self.request.user.is_authenticated and (self.request.user == user or self.request.user.is_staff):
            return DocumentUser.objects.filter(user=user).order_by('created_at')
        raise PermissionDenied("Você não tem permissão para acessar estes documentos.")

    def perform_create(self, serializer):
        user_pk = self.kwargs.get('user_pk')
        target_user = get_object_or_404(User, uuid=user_pk)
        
        # Salva o documento vinculando-o ao usuário alvo
        documento = serializer.save(user=target_user)
        
        tipo_doc = documento.document_type.upper() if documento.document_type else ""
        user_request = self.request.user

        # 1. Se o Admin criou inserindo um BOLETO direto no usuário
        if tipo_doc == 'BOLETO' and (user_request.is_admin or user_request.is_staff or user_request.is_superuser):
            notify_user_boleto_added(target_user, documento)
            
        # 2. Se o Cliente criou enviando um COMPROVANTE no seu próprio perfil
        elif tipo_doc == 'COMPROVANTE' and user_request == target_user:
            notify_user_comprovante_added(target_user, documento, user_request)


class DocumentUserRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    """
    API endpoint para recuperar, atualizar e deletar um documento de usuário específico.
    - GET: Recupera os detalhes de um documento.
    - PUT/PATCH: Atualiza um documento (incluindo o arquivo, se enviado).
    - DELETE: Remove um documento e seu arquivo físico.
    """
    serializer_class = DocumentUserSerializer
    permission_classes = [IsAuthenticated]
    # Usa 'document_pk' da URL para encontrar o documento
    lookup_url_kwarg = 'document_pk'

    def get_queryset(self):
        # Garante que o queryset é filtrado pelo usuário correto
        user_pk = self.kwargs['user_pk']
        user = get_object_or_404(User, pk=user_pk)

        # Permissões: Apenas o próprio usuário ou admins/superusers podem acessar o documento
        if self.request.user.is_authenticated and (self.request.user == user or self.request.user.is_staff or self.request.user.is_superuser):
            return DocumentUser.objects.filter(user=user)
        raise PermissionDenied("Você não tem permissão para acessar este documento.")

    def perform_update(self, serializer):
        document = self.get_object()
        user_request = self.request.user

        # Validação de Segurança para alteração de arquivos
        if 'arquivo' in serializer.validated_data:
            if not (user_request == document.user or user_request.is_admin or user_request.is_staff or user_request.is_superuser):
                raise PermissionDenied("Você não tem permissão para atualizar o arquivo deste documento.")

        # 1. Salvamos a atualização de forma limpa
        documento_atualizado = serializer.save()

        # 2. Gatilhos de Notificação usando a Camada 4 limpa (apenas se alterou o arquivo físico)
        if 'arquivo' in serializer.validated_data:
            tipo_doc = documento_atualizado.document_type.upper() if documento_atualizado.document_type else ""
            
            # Admin atualizou o boleto do usuário
            if tipo_doc == 'BOLETO' and (user_request.is_admin or user_request.is_staff or user_request.is_superuser):
                notify_user_boleto_added(document.user, documento_atualizado)
                
            # Cliente re-enviou o comprovante dele
            elif tipo_doc == 'COMPROVANTE' and user_request == document.user:
                notify_user_comprovante_added(document.user, documento_atualizado, user_request)
                
    def perform_destroy(self, instance):
        user_request = self.request.user
        if user_request.is_authenticated and (user_request == instance.user or user_request.is_staff or user_request.is_superuser):
            instance.delete()
        else:
            raise PermissionDenied("Você não tem permissão para deletar este documento.")