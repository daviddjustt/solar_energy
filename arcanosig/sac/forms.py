from django import forms
from .models import RelatorioInteligencia

class RelatorioInteligenciaForm(forms.ModelForm):
    """
    Formulário para criar/atualizar instâncias de RelatorioInteligencia.
    Exclui campos gerados automaticamente ou definidos na view.
    """
    class Meta:
        model = RelatorioInteligencia
        fields = [
            'tipo',
            'analista',
            'arquivo_pdf',
            'qtd_homicidio',
            'qtd_tentativa_homicidio',
            'qtd_latrocinio',
            'qtd_tentativa_latrocinio',
            'qtd_feminicidio',
            'qtd_tentativa_feminicidio',
            'qtd_morte_intervencao',
            'qtd_mandado_prisao',
            'qtd_encontro_cadaver',
            'qtd_apreensao_drogas',
            'qtd_apreensao_armas',
            'qtd_ocorrencia_repercussao',
            'qtd_outras_intercorrencias',
        ]
