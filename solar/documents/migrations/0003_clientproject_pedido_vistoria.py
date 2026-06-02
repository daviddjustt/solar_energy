# Gerado manualmente para adicionar o campo pedido_vistoria ao ClientProject

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0001_initial'), 
    ]

    operations = [
        migrations.AddField(
            model_name='clientproject',
            name='pedido_vistoria',
            field=models.BooleanField(default=False, verbose_name='Pedido de Vistoria Ativo?'),
        ),
    ]