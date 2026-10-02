from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        # Ancora na última migração manual que indicou
        ('documents', '0004_projectprotocol'),
    ]

    operations = [
        migrations.CreateModel(
            name='EnergisaProject',
            fields=[
                # O Django usa o parent_link como Chave Primária para ligar ao modelo Pai
                ('clientproject_ptr', models.OneToOneField(
                    auto_created=True, 
                    on_delete=django.db.models.deletion.CASCADE, 
                    parent_link=True, 
                    primary_key=True, 
                    serialize=False, 
                    to='documents.clientproject'
                )),
                ('tensao_tipo', models.CharField(choices=[('individual', 'Individual'), ('coletivo', 'Coletivo')], default='individual', max_length=15, verbose_name='Tipo de Tensão')),
                ('tensao_imagem', models.ImageField(blank=True, help_text='Opcional. Apenas aplicável se a tensão for Coletiva.', null=True, upload_to='projetos/energisa/tensao/', verbose_name='Imagem da Tensão (Coletivo)')),
                ('cabo_mm2', models.FloatField(verbose_name='Cabo (mm²)')),
                ('isolacao_volts', models.IntegerField(choices=[(750, '750 Volts'), (1000, '1000 Volts')], verbose_name='Isolação do Cabo (V)')),
                ('cabos_por_fase', models.IntegerField(verbose_name='Cabos por Fase')),
                ('disjuntor_amperes', models.FloatField(verbose_name='Disjuntor (A)')),
                ('dps_ka', models.FloatField(verbose_name='Dispositivo de Proteção contra Surtos - DPS (kA)')),
                ('tipo_ramal', models.CharField(choices=[('aereo', 'Aéreo'), ('subterraneo', 'Subterrâneo')], max_length=15, verbose_name='Tipo de Ramal')),
            ],
            options={
                'verbose_name': 'Projeto Energisa',
                'verbose_name_plural': 'Projetos Energisa',
            },
            # Esta linha indica explicitamente que esta tabela herda de ClientProject
            bases=('documents.clientproject',),
        ),
    ]