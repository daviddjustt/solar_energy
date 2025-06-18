from rest_framework import serializers
from django.utils import timezone
from django.contrib.auth import get_user_model
from .models import (
    RelatorioInteligencia,
    RelatorioInteligenciaChangeLog,
    TipoRelatorio,
    TipoOcorrencia,
    RelatorioCompartilhamento,
    CompartilhamentoAcesso,
)

User = get_user_model()

class UsuarioBreveSserializador(serializers.ModelSerializer):
    """
    Serializador para informações básicas de usuário.
    Minimiza exposure de dados sensíveis.
    """
    patent_display = serializers.CharField(source='get_patent_display', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'name', 'patent', 'patent_display']

class RelatorioInteligenciaChangeLogSerializador(serializers.ModelSerializer):
    """
    Serializador para logs de acesso a relatórios.
    Implementa auditoria detalhada.
    """
    usuario = UsuarioBreveSserializador(read_only=True)
    changed_by = UsuarioBreveSserializador(read_only=True)

    class Meta:
        model = RelatorioInteligenciaChangeLog
        fields = [
            'id',
            'usuario',
            'changed_by',
            'changed_at',  # Campo correto do modelo
            'endereco_ip',
            'dispositivo',
            'navegador',
            'duracao_visualizacao',
            'change_type'
        ]
        read_only_fields = '__all__'

class RelatorioInteligenciaSerializer(serializers.ModelSerializer):
    """
    Serializador principal para relatórios de inteligência.
    Implementa validações complexas e controle de acesso.
    """
    analista = UsuarioBreveSserializador(read_only=True)
    focal = UsuarioBreveSserializador(read_only=True)
    logs_acesso = serializers.SerializerMethodField(
        method_name='obter_ultimos_logs_acesso'
    )
    tipo_display = serializers.CharField(source='get_tipo_display', read_only=True)
    quantitativos = serializers.SerializerMethodField(read_only=True)
    arquivo_pdf_url = serializers.CharField(source='arquivo_pdf.url', read_only=True)

    class Meta:
        model = RelatorioInteligencia
        fields = [
            'id',
            'numero',
            'numero_ano',
            'tipo',
            'tipo_display',
            'analista',
            'focal',
            'arquivo_pdf',
            'arquivo_pdf_url',
            'criado_em',
            'atualizado_em',
            'quantidade_acessos',
            'ultima_visualizacao',
            'logs_acesso',
            'quantitativos',
            # Campos de quantitativo
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
            'qtd_outras_intercorrencias'
        ]
        read_only_fields = [
            'id',
            'numero_ano',
            'criado_em',
            'atualizado_em',
            'quantidade_acessos',
            'ultima_visualizacao',
            'logs_acesso',
            'tipo_display',
            'quantitativos',
            'arquivo_pdf_url'
        ]

    def obter_ultimos_logs_acesso(self, obj):
        """
        Recupera os últimos logs de acesso para o relatório.
        Filtra apenas logs relacionados a acesso/visualização.
        """
        try:
            # Usa o relacionamento correto 'change_logs' e filtra por tipos de acesso
            logs = obj.change_logs.filter(
                change_type__in=['access', 'view_pdf', 'download']
            ).order_by('-changed_at')[:10]

            return RelatorioInteligenciaChangeLogSerializador(logs, many=True).data
        except Exception as e:
            # Log do erro para debug
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Erro ao obter logs de acesso: {e}")
            return []
        
    def validate(self, dados):
        """
        Validação complexa do relatório com regras de negócio.
        """
        usuario_atual = self.context.get('request').user if self.context.get('request') else None

        # Verifica se o usuário tem permissão para criar relatórios
        if usuario_atual and hasattr(usuario_atual, 'is_sac') and hasattr(usuario_atual, 'sac_profile'):
            if not usuario_atual.is_sac or usuario_atual.sac_profile not in ['FOCAL', 'ANALISTA']:
                raise serializers.ValidationError({
                    'permissao': 'Você não tem permissão para criar relatórios.'
                })

        usuario_atual = self.context['request'].user
        # Verifica se o usuário tem permissão para criar relatórios
        if not usuario_atual.is_sac or usuario_atual.sac_profile != 'FOCAL':
            raise serializers.ValidationError({
                'permissao': 'Você não tem permissão para criar relatórios.'
            })
        return dados


    def validate_numero(self, value):
        """Validação do número sequencial"""
        try:
            numero = int(value)
        except (TypeError, ValueError):
            raise serializers.ValidationError("O campo número deve ser um valor inteiro")

        if numero < 1:
            raise serializers.ValidationError("O número deve ser maior que zero")

        # Verificar se já existe um relatório com este número para o mesmo tipo e ano
        request = self.context.get('request')
        if request and hasattr(request, 'data'):
            tipo = request.data.get('tipo', TipoRelatorio.PRELIMINAR)
            ano_atual = timezone.now().year

            queryset = RelatorioInteligencia.objects.filter(
                tipo=tipo,
                numero=numero,
                criado_em__year=ano_atual
            )

            # Se estamos editando, excluir o próprio registro
            if self.instance:
                queryset = queryset.exclude(id=self.instance.id)

            if queryset.exists():
                tipo_display = dict(TipoRelatorio.choices).get(tipo, tipo)
                raise serializers.ValidationError(
                    f"Já existe um relatório {tipo_display} com este número para o ano atual"
                )

        return numero

    def validate_tipo(self, value):
        """Validação do tipo de relatório"""
        if value not in [choice[0] for choice in TipoRelatorio.choices]:
            raise serializers.ValidationError("Tipo de relatório inválido")
        return value

    def create(self, dados_validados):
        """
        Personaliza a criação do relatório.
        Define focal e analista baseado no usuário atual.
        """
        usuario_atual = self.context['request'].user

        # Define o focal como o usuário atual se for focal
        if hasattr(usuario_atual, 'sac_profile') and usuario_atual.sac_profile == 'FOCAL':
            dados_validados['focal'] = usuario_atual

        # Define o analista como o usuário atual se for analista
        if hasattr(usuario_atual, 'sac_profile') and usuario_atual.sac_profile == 'ANALISTA':
            dados_validados['analista'] = usuario_atual
            return RelatorioInteligencia.objects.create(**dados_validados)

        # Define o analista como o usuário atual
        dados_validados['analista'] = self.context['request'].user
        # Cria o relatório
        relatorio = RelatorioInteligencia.objects.create(**dados_validados)
        return relatorio

    def get_quantitativos(self, obj):
        """Retorna os quantitativos não-zero formatados."""
        return obj.get_quantitativos_nao_zero()

class RelatorioInteligenciaListagemSerializador(serializers.ModelSerializer):
    """
    Serializador otimizado para listagem de relatórios.
    Reduz payload para melhor performance.
    """
    analista = UsuarioBreveSserializador(read_only=True)
    focal = UsuarioBreveSserializador(read_only=True)
    tipo_display = serializers.CharField(source='get_tipo_display', read_only=True)
    total_quantitativos = serializers.SerializerMethodField()

    class Meta:
        model = RelatorioInteligencia
        fields = [
            'id',
            'numero',
            'numero_ano',
            'tipo',
            'tipo_display',
            'analista',
            'focal',
            'criado_em',
            'quantidade_acessos',
            'ultima_visualizacao',
            'total_quantitativos'
        ]

    def get_total_quantitativos(self, obj):
        """Retorna o total de quantitativos para exibição rápida"""
        campos_quantitativo = [
            obj.qtd_homicidio, obj.qtd_tentativa_homicidio, obj.qtd_latrocinio,
            obj.qtd_tentativa_latrocinio, obj.qtd_feminicidio, obj.qtd_tentativa_feminicidio,
            obj.qtd_morte_intervencao, obj.qtd_mandado_prisao, obj.qtd_encontro_cadaver,
            obj.qtd_apreensao_drogas, obj.qtd_apreensao_armas, obj.qtd_ocorrencia_repercussao,
            obj.qtd_outras_intercorrencias
        ]
        return sum(campos_quantitativo)

class RelatorioListaSerializer(serializers.ModelSerializer):
    """
    Serializador muito simples para listagem básica (apenas ID e identificação).
    """
    class Meta:
        model = RelatorioInteligencia
        fields = ['id', 'numero_ano', 'tipo', 'criado_em', 'atualizado_em']

class RelatorioBuscaSerializador(serializers.Serializer):
    """
    Serializador específico para busca avançada de relatórios.
    Permite filtros complexos.
    """
    analista_id = serializers.UUIDField(required=False)
    focal_id = serializers.UUIDField(required=False)
    tipo = serializers.ChoiceField(choices=TipoRelatorio.choices, required=False)
    data_inicial = serializers.DateTimeField(required=False)
    data_final = serializers.DateTimeField(required=False)
    numero = serializers.IntegerField(required=False, min_value=1)
    ano = serializers.IntegerField(required=False, min_value=2020)

class CompartilhamentoSerializer(serializers.ModelSerializer):
    """
    Serializer para o modelo RelatorioCompartilhamento.
    Gerencia criação e exibição de compartilhamentos de relatórios.
    """
    relatorio_info = serializers.SerializerMethodField(read_only=True)
    criado_por_info = serializers.SerializerMethodField(read_only=True)
    tipo_display = serializers.CharField(source='get_tipo_display', read_only=True)
    status_validade = serializers.SerializerMethodField(read_only=True)
    link_acesso = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = RelatorioCompartilhamento
        fields = [
            'id',
            'relatorio',
            'relatorio_info',
            'criado_por',
            'criado_por_info',
            'tipo',
            'tipo_display',
            'token',
            'numero_especial',
            'senha_especial', 
            'criado_em',
            'expira_em',
            'ativo',
            'acessos',
            'ultimo_acesso',
            'status_validade',
            'link_acesso'
        ]
        read_only_fields = [
            'id',
            'token',
            'numero_especial',
            'senha_especial',
            'criado_em',
            'acessos',
            'ultimo_acesso',
            'relatorio_info',
            'criado_por_info',
            'tipo_display',
            'status_validade',
            'link_acesso'
        ]
        extra_kwargs = {
            'criado_por': {'write_only': True}
        }

    def get_relatorio_info(self, obj):
        """Retorna informações básicas do relatório compartilhado"""
        return {
            'id': str(obj.relatorio.id),
            'numero_ano': obj.relatorio.numero_ano,
            'tipo': obj.relatorio.tipo,
            'criado_em': obj.relatorio.criado_em
        }

    def get_criado_por_info(self, obj):
        """Retorna informações do usuário que criou o compartilhamento"""
        if obj.criado_por:
            return {
                'id': obj.criado_por.id,
                'name': obj.criado_por.name,
                'patent_display': getattr(obj.criado_por, 'get_patent_display', lambda: 'N/A')()
            }
        return None

    def get_status_validade(self, obj):
        """Retorna status de validade do compartilhamento"""
        return {
            'valido': obj.is_valido(),
            'expirado': obj.expira_em and obj.expira_em < timezone.now() if obj.expira_em else False,
            'ativo': obj.ativo
        }

    def get_link_acesso(self, obj):
        """Gera link de acesso ao compartilhamento"""
        request = self.context.get('request')
        if request:
            base_url = request.build_absolute_uri('/').rstrip('/')
            return f"{base_url}/api/compartilhamento/{obj.token}/"
        return None

    def validate(self, attrs):
        """Validações gerais do compartilhamento"""
        # Verifica se o usuário atual é FOCAL
        request = self.context.get('request')
        if request and request.user:
            if not (hasattr(request.user, 'is_sac') and 
                   hasattr(request.user, 'sac_profile') and
                   request.user.is_sac and 
                   request.user.sac_profile == 'FOCAL'):
                raise serializers.ValidationError({
                    'permissao': 'Apenas usuários com perfil FOCAL podem criar compartilhamentos.'
                })
            
            # Define automaticamente o criador
            attrs['criado_por'] = request.user
        
        return attrs

    def validate_tipo(self, value):
        """Valida o tipo de compartilhamento"""
        tipos_validos = ['cpf', 'especial']
        if value not in tipos_validos:
            raise serializers.ValidationError(f"Tipo deve ser um dos seguintes: {', '.join(tipos_validos)}")
        return value

    def create(self, validated_data):
        """Personaliza a criação do compartilhamento"""
        # O método save() do modelo já cuida da geração do token e credenciais especiais
        return super().create(validated_data)

class AcessoCompartilhamentoSerializer(serializers.Serializer):
    """
    Serializer para validar os dados de acesso a um link de compartilhamento.
    Valida CPF/Senha ou Numero/Senha Especial dependendo do tipo de compartilhamento.
    """
    numero_especial = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    senha_especial = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, data):
        """
        Validação customizada para garantir que os campos corretos são fornecidos
        dependendo do tipo de compartilhamento.
        """
        compartilhamento = self.context.get('compartilhamento')
        if not compartilhamento:
             raise serializers.ValidationError("Contexto de compartilhamento não fornecido.")

        elif compartilhamento.tipo == 'especial':
            numero_especial = data.get('numero_especial')
            senha_especial = data.get('senha_especial')
            if not numero_especial or not senha_especial:
                raise serializers.ValidationError("Número especial e senha especial são obrigatórios para este tipo de compartilhamento.")
            # A validação real das credenciais especiais acontece na view.

        else:
             raise serializers.ValidationError("Tipo de compartilhamento inválido.")

        return data

class CompartilhamentoAcessoSerializer(serializers.ModelSerializer):
    """
    Serializer para logs de acesso aos compartilhamentos.
    Usado para auditoria e controle de acessos.
    """
    compartilhamento_info = serializers.SerializerMethodField(read_only=True)
    sucesso_display = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = CompartilhamentoAcesso
        fields = [
            'id',
            'compartilhamento',
            'compartilhamento_info',
            'ip_address',
            'user_agent',
            'sucesso',
            'sucesso_display',
            'erro',
            'acessado_em'
        ]
        read_only_fields = '__all__'

    def get_compartilhamento_info(self, obj):
        """Retorna informações básicas do compartilhamento"""
        return {
            'token': obj.compartilhamento.token[:8] + '...',  # Mostra apenas os primeiros 8 caracteres
            'tipo': obj.compartilhamento.tipo,
            'relatorio_numero': obj.compartilhamento.relatorio.numero_ano
        }

    def get_sucesso_display(self, obj):
        """Retorna status de sucesso formatado"""
        return "SUCESSO" if obj.sucesso else "FALHA"

class GerarLinkAcessoInputSerializer(serializers.Serializer):
    """Serializer para validar o UUID do relatório na entrada."""
    relatorio_uuid = serializers.UUIDField()

class GerarLinkAcessoOutputSerializer(serializers.ModelSerializer):
    """Serializer para formatar a resposta ao gerar o link especial."""
    tipo_display = serializers.CharField(source='get_tipo_display', read_only=True)

    class Meta:
        model = RelatorioCompartilhamento
        fields = ['token', 'numero_especial', 'senha_especial', 'expira_em', 'tipo_display']

class RelatorioCompartilhamentoEspecialSerializer(serializers.ModelSerializer):
    """Serializer para formatar a resposta ao gerar o link especial."""
    tipo_display = serializers.CharField(source='get_tipo_display', read_only=True)

    class Meta:
        model = RelatorioCompartilhamento
        fields = ['token', 'numero_especial', 'senha_especial', 'expira_em', 'tipo_display']

