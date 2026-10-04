# Generated manually

from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        # Aponta para a última migração que temos registada no seu sistema
        ('documents', '0005_energisaproject'),
    ]

    operations = [
        migrations.AddField(
            model_name='clientproject',
            name='vistoria_automatica',
            field=models.BooleanField(default=False, verbose_name='Vistoria Automática'),
        ),
    ]