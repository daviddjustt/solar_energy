# Gerado manualmente para adicionar o campo de observações

from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        # ATENÇÃO: Coloque aqui o nome exato do arquivo da migração que você me enviou 
        # (exemplo: '0001_initial' ou '0015_alguma_coisa'), sempre sem o ".py"
        ('documents', '0001_initial'), 
    ]

    operations = [
        migrations.AddField(
            model_name='clientproject',
            name='observacoes',
            field=models.TextField(blank=True, null=True, verbose_name='Observações'),
        ),
    ]