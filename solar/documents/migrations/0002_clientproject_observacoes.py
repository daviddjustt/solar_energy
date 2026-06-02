# Gerado manualmente para adicionar observações e pedido de vistoria ao ClientProject

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        # Mantém a dependência original apontando para o início do app
        ('documents', '0001_initial'), 
    ]

    operations = [
        # Operação 1: Campo de Observações
        migrations.AddField(
            model_name='clientproject',
            name='observacoes',
            field=models.TextField(blank=True, null=True, verbose_name='Observações'),
        ),
        # Operação 2: Novo campo pedido_vistoria unificado aqui
        migrations.AddField(
            model_name='clientproject',
            name='pedido_vistoria',
            field=models.BooleanField(default=False, verbose_name='Pedido de Vistoria Ativo?'),
        ),
    ]