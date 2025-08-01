#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from configurations import importer


def main():
    # CRUCIAL: Chame importer.install() antes de definir as variáveis de ambiente
    # para que o django-configurations possa interceptar a importação das configurações.
    importer.install()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "solar.config")
    # É uma boa prática definir uma configuração padrão para o manage.py,
    # que pode ser sobrescrita por uma variável de ambiente se necessário.
    os.environ.setdefault("DJANGO_CONFIGURATION", "Local")

    try:
        from configurations.management import execute_from_command_line
    except ImportError:
        # The above import may fail for some other reason. Ensure that the
        # issue is really that Django is missing to avoid masking other
        # exceptions on Python 2.
        try:
            import django # noqa
        except ImportError:
            raise ImportError(
                "Couldn't import Django. Are you sure it's installed and "
                "available on your PYTHONPATH environment variable? Did you "
                "forget to activate a virtual environment?"
            )
        raise
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
