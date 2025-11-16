from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

#
from rest_framework import generics
from rest_framework.exceptions import PermissionDenied
from solar.users.models import User
#
from .serializers import DocumentUser, DocumentUserSerializer

class DocumentUserListCreateView(generics.ListCreateAPIView):
    serializer_class = DocumentUserSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Filtra documentos para o usuário especificado na URL
        user_pk = self.kwargs['user_pk']
        user = get_object_or_404(User, pk=user_pk)
        # Garante que apenas o próprio usuário ou um admin/técnico pode ver seus documentos
        if self.request.user.is_authenticated and (self.request.user == user or self.request.user.is_staff):
            return DocumentUser.objects.filter(user=user)
        raise PermissionDenied("Você não tem permissão para acessar estes documentos.")

    def perform_create(self, serializer):
        # Esta é a parte crucial para injetar o usuário
        user_pk = self.kwargs['user_pk']
        user = get_object_or_404(User, pk=user_pk)

        # Opcional: Validação de permissão para criar documentos para este usuário
        if self.request.user.is_authenticated and (self.request.user == user or self.request.user.is_staff):
            # Injeta o objeto User no contexto do serializer
            serializer.context['user'] = user
            serializer.save() # Chama o método create do serializer
        else:
            raise PermissionDenied("Você não tem permissão para criar documentos para este usuário.")

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

        # Lógica de permissão para atualização:
        # - Apenas admins/superusers podem alterar 'status' ou 'document_type'.
        # - O próprio usuário pode atualizar o 'arquivo' se for o dono do documento.
        # - Outras atualizações podem ser permitidas ou restritas conforme a necessidade.

        if 'status' in serializer.validated_data and not (user_request.is_staff or user_request.is_superuser):
            raise PermissionDenied("Apenas administradores podem alterar o status do documento.")

        if 'document_type' in serializer.validated_data and not (user_request.is_staff or user_request.is_superuser):
            raise PermissionDenied("Apenas administradores podem alterar o tipo do documento.")

        # Se o arquivo está sendo atualizado, verificar permissões
        if 'arquivo' in serializer.validated_data:
            if not (user_request == document.user or user_request.is_staff or user_request.is_superuser):
                raise PermissionDenied("Você não tem permissão para atualizar o arquivo deste documento.")

        serializer.save()

    def perform_destroy(self, instance):
        user_request = self.request.user
        # Permissões: Apenas o próprio usuário ou admins/superusers podem deletar o documento
        if user_request.is_authenticated and (user_request == instance.user or user_request.is_staff or user_request.is_superuser):
            instance.delete() # O método delete do modelo DocumentUser (herdado de Document) lida com a remoção do arquivo físico.
        else:
            raise PermissionDenied("Você não tem permissão para deletar este documento.")