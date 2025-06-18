from django.db import models
from django.utils.translation import gettext_lazy as _


class OperacaoStatus(models.TextChoices):
    """Choices para status de operações"""
    AGENDADA = 'agendada', _('Agendada')
    ATIVA = 'ativa', _('Ativa')
    ENCERRADA = 'encerrada', _('Encerrada')
    CANCELADA = 'cancelada', _('Cancelada')


class TipoEquipamento(models.TextChoices):
    """Choices para tipos de equipamentos"""
    PISTOLA = 'pistola', _('Pistola')
    FUZIL = 'fuzil', _('Fuzil')
    CARABINA = 'carabina', _('Carabina')
    MUNICAO = 'municao', _('Munição')
    TABLET = 'tablet', _('Tablet')
    RADIO = 'radio', _('Rádio')
    OUTROS = 'outros', _('Outros')
    COLETE_REFLEXIVO = 'colete_reflexivo', _('Colete Reflexivo')
    CAPACETE = 'capacete', _('Capacete')
    EXPAGIDOR = 'expagidor', _('Expagidor (Gás de Pimenta)')


class StatusEquipamento(models.TextChoices):
    """Choices para status do equipamento"""
    EM_CONDICOES = 'em_condicoes', _('Em Condições')
    DANIFICADO = 'danificado', _('Danificado')
    INOPERANTE = 'inoperante', _('Inoperante')
    EXTRAVIADO = 'extraviado', _('Extraviado')


class StatusAceite(models.TextChoices):
    """Choices para status do aceite de cautela"""
    PENDENTE = 'pendente', _('Pendente')
    CONFIRMADO = 'confirmado', _('Confirmado')
    INVALIDADO = 'invalidado', _('Invalidado')


class ModeloVeiculo(models.TextChoices):
    """Choices para modelos de veículos"""
    L200 = 'l200', _('L200')
    RANGER = 'ranger', _('Ranger')
    TUCSON = 'tucson', _('Tucson')
    HILUX = 'hilux', _('Hilux')
    DUSTER = 'duster', _('Duster')
    OUTROS = 'outros', _('Outros')


class TipoNotificacao(models.TextChoices):
    """Choices para tipos de notificação"""
    CAUTELA_PENDENTE = 'cautela_pendente', _('Cautela Pendente')
    DEVOLUCAO_PENDENTE = 'devolucao_pendente', _('Devolução Pendente')
    DEVOLUCAO_CONFIRMADA = 'devolucao_confirmada', _('Devolução Confirmada')
    EQUIPAMENTO_DANIFICADO = 'equipamento_danificado', _('Equipamento Danificado')
