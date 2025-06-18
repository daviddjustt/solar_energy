from rest_framework import permissions
from django.utils import timezone
from .models import RelatorioInteligenciaChangeLog


class PermissaoRelatorioInteligencia(permissions.BasePermission):
    """
    Permissão para gerenciamento de relatórios de inteligência.
    - ANALISTA/FOCAL: CRUD apenas em relatórios que criaram dentro de 6 horas.
    - LEITOR: Apenas leitura (sem CRUD).
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated or not request.user.is_sac:
            return False

        # CREATE: Permitido para ANALISTA/FOCAL
        if view.action == 'create':
            return request.user.sac_profile in ['ANALISTA', 'FOCAL']

        # UPDATE/DELETE: Verificação de tempo é feita em has_object_permission
        if view.action in ['update', 'partial_update', 'destroy']:
            return request.user.sac_profile in ['ANALISTA', 'FOCAL']

        # Métodos GET: Permitido para todos os perfis SAC
        return True

    def has_object_permission(self, request, view, obj):
        # GET: Permitido para LEITOR, ANALISTA, FOCAL
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_sac  # Qualquer perfil SAC

        # UPDATE/DELETE: Somente se o usuário é o analista E dentro de 6h
        if view.action in ['update', 'partial_update', 'destroy']:
            is_owner = obj.analista == request.user  # Analista é o criador
            is_recent = (timezone.now() - obj.criado_em).total_seconds() < 21600  # 6h
            return is_owner and is_recent

        return False


class PermissaoAuditarRelatorio(permissions.BasePermission):
    """
    Permissões específicas para auditoria de relatórios.
    Restringe acesso a logs de auditoria.
    """
    def has_permission(self, request, view):
        """
        Permite acesso a logs apenas para usuários com is_sac=True.
        """
        return (
            request.user.is_authenticated and
            request.user.is_sac and
            request.user.sac_profile in ['FOCAL', 'ANALISTA']
        )

    def has_object_permission(self, request, view, obj):
        """
        Verifica permissão para visualizar logs específicos.
        """
        # Apenas focais, analistas ou o analista responsável pelo relatório podem acessar
        return (
            request.user.sac_profile in ['FOCAL', 'ANALISTA'] or
            obj.relatorio.analista == request.user
        )


class PermissaoLeituraPDF(permissions.BasePermission):
    def has_permission(self, request, view):
        # Permite para superusuários
        if request.user.is_superuser:
            return True

        # Permite métodos GET para qualquer usuário SAC (LEITOR, ANALISTA, FOCAL)
        return (
            request.method in permissions.SAFE_METHODS and
            request.user.is_authenticated and
            request.user.is_sac and
            request.user.sac_profile in ['LEITOR', 'ANALISTA', 'FOCAL']
        )

    def has_object_permission(self, request, view, obj):
        # Permite para superusuários
        if request.user.is_superuser:
            # Registra o acesso para auditoria
            if request.method == 'GET' and view.action == 'visualizar_pdf':
                self._registrar_acesso(request, obj)
            return True

        # Registra o acesso no log para qualquer perfil SAC
        if request.method == 'GET' and view.action == 'visualizar_pdf':
            self._registrar_acesso(request, obj)

            # Obtém endereço IP real considerando proxies
            ip = self.get_client_ip(request)

            RelatorioInteligenciaChangeLog.objects.create(
                relatorio=obj,
                usuario=request.user,
                endereco_ip=ip,
                dispositivo=dispositivo,
                navegador=navegador
            )

        # Reutiliza a mesma lógica base para verificar permissões
        return (
            request.method in permissions.SAFE_METHODS and
            request.user.is_authenticated and
            request.user.is_sac and
            request.user.sac_profile in ['LEITOR', 'ANALISTA', 'FOCAL']
        )

    def _registrar_acesso(self, request, obj):
        # Extrai informações do user agent quando disponível
        dispositivo = ''
        navegador = ''
        if hasattr(request, 'user_agent'):
            dispositivo = request.user_agent.device.family if request.user_agent else ''
            navegador = request.user_agent.browser.family if request.user_agent else ''

        # Obtém endereço IP real considerando proxies
        ip = self.get_client_ip(request)

        RelatorioInteligenciaChangeLog.objects.create(
            relatorio=obj,
            usuario=request.user,
            endereco_ip=ip,
            dispositivo=dispositivo,
            navegador=navegador
        )

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

