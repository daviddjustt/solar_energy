# solar/documents/signals.py
from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import ClientProject, AndamentoDoProjeto, ProjectDocument
from solar.users.email import StatusProjetoChangedEmail, DocumentRejectedEmail
import logging

logger = logging.getLogger(__name__)

# Lista de status que devem disparar o e-mail
STATUS_QUE_GERAM_EMAIL = [
    AndamentoDoProjeto.PAGAMENTO_TRT_ART,
    AndamentoDoProjeto.ANALISE_TECNICA,
    AndamentoDoProjeto.APROVADO,
    AndamentoDoProjeto.REPROVADO,
    AndamentoDoProjeto.VISTORIA,
    AndamentoDoProjeto.CONCLUIDO,
]
