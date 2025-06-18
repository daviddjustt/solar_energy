from rest_framework.permissions import BasePermission

class IsSpecialCPFUser(BasePermission):
    """Permissão para usuários com acesso especial via CPF."""
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and 
            request.user.acesso_especial_cpf
        )

class IsOperationsUser(BasePermission):
    """Permissão para usuários de operações."""
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and 
            request.user.is_operacoes
        )

class IsSACUser(BasePermission):
    """Permissão para usuários do SAC."""
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and 
            request.user.is_sac
        )

class IsSpecialOrOperations(BasePermission):
    """Usuários especiais OU de operações."""
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and 
            (request.user.acesso_especial_cpf or request.user.is_operacoes)
        )
