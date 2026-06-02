# Gerado manualmente para adicionar o campo pedido_vistoria ao ClientProject

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        # Substitua '0002_add_observacoes' pelo nome EXATO do arquivo anterior 
        # que adicionou o campo de observações, sem a extensão .py
        ('documents', '0002_add_observacoes'), 
    ]

    operations = [
        migrations.AddField(
            model_name='clientproject',
            name='pedido_vistoria',
            field=models.BooleanField(default=False, verbose_name='Pedido de Vistoria Ativo?'),
        ),
    ]