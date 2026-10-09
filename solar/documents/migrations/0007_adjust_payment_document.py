# Generated manually to align models with database state

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        # Aponta para a migração que criámos anteriormente
        ('documents', '0006_vistoria_automatica'),
    ]

    operations = [
        # 1. Remove o campo fantasma da tabela de Projetos
        migrations.RemoveField(
            model_name='clientproject',
            name='related_payment_document',
        ),
        
        # 2. Oficializa o campo na tabela correta (Documentos)
        migrations.AddField(
            model_name='projectdocument',
            name='related_payment_document',
            field=models.ForeignKey(
                blank=True, 
                help_text='Boleto relacionado', 
                null=True, 
                on_delete=django.db.models.deletion.CASCADE, 
                related_name='payment_proofs', 
                to='documents.projectdocument'
            ),
        ),
        
        # 3. Atualiza os textos do Enum de Status que foram alterados no código
        migrations.AlterField(
            model_name='clientproject',
            name='status',
            field=models.CharField(
                choices=[
                    ('Em análise de documentos', 'Analise De Documentos'), 
                    ('Projeto em Execução', 'Execucao'), 
                    ('Pagamento da TRT/ART', 'Pagamento Trt Art'), 
                    ('Projeto em análise técnica', 'Analise Tecnica'), 
                    ('Projeto aprovado', 'Aprovado'), 
                    ('Projeto reprovado', 'Reprovado'), 
                    ('Projeto em vistoria', 'Vistoria'), 
                    ('Projeto finalizado', 'Concluido'),
                    ('formulario', 'Formulario'),
                    ('diagrama_unifilar', 'Diagrama Unifilar'),
                    ('dados_geradora','Dados da Geradora'),
                    ('unidades_consumidoras_extra', 'Unidades Consumidoras Extra'),
                    ('memorial', 'Memorial'),
                    ('art_documento', 'Art Documento'),
                    ('documento_de_posse', 'Documento de Posse'),
                ], 
                default='Em análise de documentos', 
                max_length=43, 
                verbose_name='Status do Projeto'
            ),
        ),
    ]