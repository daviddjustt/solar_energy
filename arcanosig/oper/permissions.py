from rest_framework.permissions import BasePermission
from arcanosig.oper.models import Guarnicao, Veiculo


class IsAdminOrOperationsOrGuarnicaoMember(BasePermission):
    """
    Permite se:
    - user.is_admin, is_superuser ou is_operacoes
    - ou, o recurso (objeto ou dados de criação) pertence a uma guarnição da qual o user é membro
    """

    def _is_admin(self, user):
        return bool(
            user.is_superuser or
            getattr(user, 'is_admin', False) or
            getattr(user, 'is_operacoes', False)
        )

    def _is_member(self, guarnicao, user):
        if not guarnicao or not user.is_authenticated:
            return False
        # assume related_name='membros'
        return guarnicao.membros.filter(id=user.id).exists() or guarnicao.comandante_id == user.id

    def _get_guarnicao_from_obj(self, obj):
        """
        Tenta extrair a guarnição associada a um objeto qualquer.
        """
        # se o próprio obj for Guarnicao
        if isinstance(obj, Guarnicao):
            return obj
        # se obj tiver atributo direto
        if hasattr(obj, 'guarnicao') and isinstance(obj.guarnicao, Guarnicao):
            return obj.guarnicao
        # se obj for Veiculo ou tiver veiculo
        veiculo = getattr(obj, 'veiculo', None)
        if isinstance(obj, Veiculo):
            veiculo = obj
        if veiculo and hasattr(veiculo, 'guarnicao_associada'):
            return getattr(veiculo, 'guarnicao_associada')
        return None

    def _get_guarnicao_from_request(self, request):
        """
        Tenta obter guarnição do payload de criação:
        - busca guarnicao diretamente
        - ou via veiculo → guarnicao_associada
        """
        data = request.data
        # primeiro, se vier o id da guarnição
        gu_id = data.get('guarnicao')
        if gu_id:
            return Guarnicao.objects.filter(id=gu_id).first()
        # senão, se vier veiculo, busca guarnicao_associada
        ve_id = data.get('veiculo')
        if ve_id:
            veh = Veiculo.objects.filter(id=ve_id).first()
            return getattr(veh, 'guarnicao_associada', None)
        return None

    def has_permission(self, request, view):
        # sempre exigir autenticação
        user = request.user
        if not user.is_authenticated:
            return False

        # superusers / admins / operações têm via livre
        if self._is_admin(user):
            return True

        # no create, validar se o payload pertence a uma guarnição do usuário
        if getattr(view, 'action', None) == 'create':
            gu = self._get_guarnicao_from_request(request)
            return self._is_member(gu, user)

        # para list/retrieve/ações custom, deixamos passar para has_object_permission
        return True

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user.is_authenticated:
            return False

        # admins continuam livres
        if self._is_admin(user):
            return True

        # senão, extrair guarnição do objeto e checar
        gu = self._get_guarnicao_from_obj(obj)
        return self._is_member(gu, user)
