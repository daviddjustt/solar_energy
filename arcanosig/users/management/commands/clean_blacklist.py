from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

class Command(BaseCommand):
    help = 'Limpa tokens expirados da blacklist'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Executa sem excluir, apenas mostra o que seria excluído',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry-run', False)
        now = timezone.now()

        # Obter contagens antes da limpeza
        total_outst = OutstandingToken.objects.count()
        expired_outst = OutstandingToken.objects.filter(expires_at__lt=now).count()
        total_blacklisted = BlacklistedToken.objects.count()

        self.stdout.write(f"Tokens totais: {total_outst}")
        self.stdout.write(f"Tokens expirados: {expired_outst}")
        self.stdout.write(f"Tokens na blacklist: {total_blacklisted}")

        if dry_run:
            self.stdout.write(self.style.WARNING(f"Modo de simulação: {expired_outst} tokens seriam removidos"))
            return

        try:
            with transaction.atomic():
                # Primeiro, exclua os BlacklistedToken relacionados a tokens expirados
                # Isso resolve a restrição de chave estrangeira
                deleted_bl = BlacklistedToken.objects.filter(
                    token__expires_at__lt=now
                ).delete()[0]

                # Agora é seguro excluir os OutstandingToken expirados
                deleted_ot = OutstandingToken.objects.filter(
                    expires_at__lt=now
                ).delete()[0]

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Removidos com sucesso: {deleted_bl} blacklisted tokens e {deleted_ot} outstanding tokens expirados"
                    )
                )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Erro ao limpar tokens: {str(e)}")
            )
