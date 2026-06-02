# Gerado manualmente para adicionar o campo pedido_vistoria ao ClientProject

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        # Voltamos a depender do 0002 para manter a linha reta no app documents
        ('documents', '0002_clientproject_observacoes'), 
    ]

    # ESSA É A MÁGICA: Avisa o Django para injetar este campo antes do app de notificações rodar
    run_before = [
        ('documents', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='clientproject',
            name='pedido_vistoria',
            field=models.BooleanField(default=False, verbose_name='Pedido de Vistoria Ativo?'),
        ),
    ]