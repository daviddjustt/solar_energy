from django.apps import AppConfig

class DocumentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'solar.documents' # ou apenas 'documents', dependendo da sua configuração

    def ready(self):
        # Importa os signals quando o app é carregado
        import solar.documents.signals