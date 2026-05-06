from rest_framework import permissions

class IsAdminOrTechnician(permissions.BasePermission):
    """
    Permite acesso apenas a Administradores ou Técnicos.
    Utiliza as flags booleanas do custom User model.
    """
    def has_permission(self, request, view):
        # Primeiro, garante que há um usuário autenticado
        if not request.user or not request.user.is_authenticated:
            return False
            
        # Verifica as flags do seu modelo de Usuário
        return request.user.is_superuser or request.user.is_admin or request.user.is_tecnico