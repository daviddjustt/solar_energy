from django.db import migrations
from decimal import Decimal

def populate_service_types(apps, schema_editor):
    ServiceType = apps.get_model('services', 'ServiceType')
    
    # Valores extraídos exatamente da tabela de referência
    tipos_servico = [
        {
            'codigo': 'ligacao_nova',
            'nome': 'Ligação nova',
            'valor': Decimal('20.00'),
            'prazo_informativo': '1 dia útil',
            'ativo': True
        },
        {
            'codigo': 'alteracao_carga_fase',
            'nome': 'Alteração de carga e fase',
            'valor': Decimal('20.00'),
            'prazo_informativo': '1 dia útil',
            'ativo': True
        },
        {
            'codigo': 'alteracao_carga',
            'nome': 'Alteração de carga',
            'valor': Decimal('20.00'),
            'prazo_informativo': '1 dia útil',
            'ativo': True
        },
        {
            'codigo': 'troca_titularidade',
            'nome': 'Troca de titularidade',
            'valor': Decimal('20.00'),
            'prazo_informativo': '1 dia útil',
            'ativo': True
        },
        {
            'codigo': 'consulta_carga',
            'nome': 'Consulta de carga, tensão e transformador',
            'valor': Decimal('20.00'),
            'prazo_informativo': '1 dia útil',
            'ativo': True
        },
        {
            'codigo': 'lista_compensacao',
            'nome': 'Alteração na lista de compensação',
            'valor': Decimal('250.00'),
            'prazo_informativo': '30 dias',
            'ativo': True
        },
    ]
    
    # Usamos update_or_create para não duplicar caso a migração seja corrida novamente
    for tipo in tipos_servico:
        ServiceType.objects.update_or_create(
            codigo=tipo['codigo'],
            defaults=tipo
        )

def reverse_populate(apps, schema_editor):
    """Permite reverter (fazer rollback) da migração, apagando estes registos."""
    ServiceType = apps.get_model('services', 'ServiceType')
    codigos = [
        'ligacao_nova', 'alteracao_carga_fase', 'alteracao_carga', 
        'troca_titularidade', 'consulta_carga', 'lista_compensacao'
    ]
    ServiceType.objects.filter(codigo__in=codigos).delete()


class Migration(migrations.Migration):

    dependencies = [
        # ATENÇÃO: Verifique se o nome bate com a sua migração anterior na pasta migrations
        ('services', '0007_alter_serviceunit_options_and_more'), 
    ]

    operations = [
        migrations.RunPython(populate_service_types, reverse_populate),
    ]