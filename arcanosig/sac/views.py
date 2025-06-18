import os
from datetime import timedelta
import uuid

# Django CORE
from django.contrib.auth import authenticate, get_user_model
from django.db.models import Count, Sum
from django.http import FileResponse, Http404
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.conf import settings

# Django REST Framework
from rest_framework import viewsets, status, serializers # Importar serializers aqui
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied

# Modelos da aplicação
from .models import (
    RelatorioInteligencia,
    RelatorioInteligenciaChangeLog,
    RelatorioCompartilhamento,
    CompartilhamentoAcesso
)

# Serializadores
from .serializers import (
    RelatorioInteligenciaSerializer,
    RelatorioInteligenciaListagemSerializador,
    RelatorioListaSerializer,
    CompartilhamentoSerializer,
    AcessoCompartilhamentoSerializer,
    RelatorioCompartilhamentoEspecialSerializer,
)

# Permissões
from .permissions import (
    PermissaoRelatorioInteligencia,
    PermissaoLeituraPDF,
)

# Ultilitarios 
from .utils.pdf_watermark import add_watermark_to_pdf

# Modelo de usuário
User = get_user_model()

class RelatorioInteligenciaViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gerenciar relatórios de inteligência.
    Inclui controle de acesso, logging e geração de PDFs com marca d'água.
    """
    queryset = RelatorioInteligencia.objects.all().select_related('analista', 'focal')
    serializer_class = RelatorioInteligenciaSerializer
    permission_classes = [IsAuthenticated, PermissaoRelatorioInteligencia]

    def get_serializer_class(self):
        """Usa serializer simplificado para listagem."""
        if self.action == 'list':
            return RelatorioInteligenciaListagemSerializador
        return RelatorioInteligenciaSerializer

    def retrieve(self, request, *args, **kwargs):
        """GET /relatorios-inteligencia/{pk}/ - Registra acesso e atualiza contador."""
        relatorio = self.get_object()
        # Log de acesso
        self._criar_log_acesso(relatorio, request, 'access')
        # Atualiza contador
        self._atualizar_contadores(relatorio)
        serializer = self.get_serializer(relatorio)
        return Response(serializer.data)

    def perform_create(self, serializer):
        """POST /relatorios-inteligencia/"""
        serializer.save()

    def perform_update(self, serializer):
        """PUT/PATCH /relatorios-inteligencia/{pk}/"""
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        """DELETE /relatorios-inteligencia/{pk}/"""
        relatorio = self.get_object()
        # Log de exclusão antes de deletar
        self._criar_log_exclusao(relatorio, request)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['get'], url_path='pdf-url')
    def get_pdf_url(self, request, pk=None):
        """GET /relatorios-inteligencia/{pk}/pdf-url/ - Retorna URL do PDF."""
        relatorio = self.get_object()
        if not relatorio.arquivo_pdf:
            return Response(
                {'detail': "Não há PDF associado."},
                status=status.HTTP_404_NOT_FOUND
            )
        # Log de acesso à URL do PDF
        self._criar_log_acesso(relatorio, request, 'access')
        self._atualizar_contadores(relatorio)
        return Response({'pdf_url': relatorio.arquivo_pdf.url})

    @action(detail=True, methods=['get'], url_path='download-pdf')
    def download_pdf(self, request, pk=None):
        """GET /relatorios-inteligencia/{pk}/download-pdf/ - Download do PDF."""
        relatorio = self.get_object()
        if not relatorio.arquivo_pdf:
            return Response(
                {'detail': "Arquivo PDF não encontrado."},
                status=status.HTTP_404_NOT_FOUND
            )
        # Log de download
        self._criar_log_acesso(relatorio, request, 'download')
        # Atualiza contador
        self._atualizar_contadores(relatorio)
        try:
            response = FileResponse(
                relatorio.arquivo_pdf.open('rb'),
                content_type='application/pdf'
            )
            response['Content-Disposition'] = f'attachment; filename="{relatorio.numero_ano}.pdf"'
            return response
        except FileNotFoundError:
            raise Http404("Arquivo não encontrado no sistema de arquivos.")

    @action(
        detail=True,
        methods=['get'],
        url_path='visualizar-pdf',
        permission_classes=[IsAuthenticated, PermissaoLeituraPDF]
    )
    def visualizar_pdf(self, request, pk=None):
        """GET /relatorios-inteligencia/{pk}/visualizar-pdf/ - PDF com marca d'água."""
        relatorio = self.get_object()
        if not relatorio.arquivo_pdf:
            return Response(
                {'detail': "Arquivo PDF não encontrado."},
                status=status.HTTP_404_NOT_FOUND
            )
        # Log de visualização
        self._criar_log_acesso(relatorio, request, 'view_pdf')
        # Atualiza contador
        self._atualizar_contadores(relatorio)
        # Gera PDF com marca d'água
        try:
            pdf_path = relatorio.arquivo_pdf.path
            user_identifier = getattr(request.user, 'cpf', str(request.user.id))
            pdf_buffer = add_watermark_to_pdf(pdf_path, user_identifier)
            return FileResponse(
                pdf_buffer,
                content_type='application/pdf',
                as_attachment=False,
                filename=f"relatorio_{relatorio.numero_ano}_watermark.pdf"
            )
        except Exception as e:
            print(f"[Erro watermark] {e}")
            return Response(
                {'detail': "Erro ao gerar PDF com marca d'água."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'], url_path='estatisticas')
    def estatisticas(self, request):
        """GET /relatorios-inteligencia/estatisticas/ - Estatísticas gerais."""
        stats = {
            'total_relatorios': self.get_queryset().count(),
            'relatorios_por_tipo': dict(
                self.get_queryset().values('tipo').annotate(
                    count=Count('id')
                ).values_list('tipo', 'count')
            ),
            'total_acessos': self.get_queryset().aggregate(
                Sum('quantidade_acessos')
            )['quantidade_acessos__sum'] or 0,
            'relatorios_mais_acessados': RelatorioInteligenciaListagemSerializador(
                self.get_queryset().order_by('-quantidade_acessos')[:5],
                many=True
            ).data
        }
        return Response(stats)

    # AÇÕES DE COMPARTILHAMENTO
    @action(detail=True, methods=['post'], url_path='compartilhar')
    def compartilhar(self, request, pk=None):
        """POST /relatorios-inteligencia/{pk}/compartilhar/ - Cria compartilhamento"""
        relatorio = self.get_object()
        # Verifica se usuário é FOCAL
        if not (hasattr(request.user, 'is_sac') and request.user.is_sac and hasattr(request.user, 'sac_profile') and request.user.sac_profile == 'FOCAL'):
             return Response(
                 {'detail': 'Apenas FOCALs podem compartilhar relatórios'},
                 status=status.HTTP_403_FORBIDDEN
             )
        # Cria compartilhamento
        data = request.data.copy()
        data['relatorio'] = relatorio.id
        serializer = CompartilhamentoSerializer(data=data, context={'request': request})
        if serializer.is_valid():
            compartilhamento = serializer.save()

            # Prepara a resposta, incluindo campos especiais se o tipo for 'especial'
            response_data = {
                'token': compartilhamento.token,
            }
            if compartilhamento.tipo == 'especial':
                response_data['numero_especial'] = compartilhamento.numero_especial
                response_data['senha_especial'] = compartilhamento.senha_especial

            return Response(response_data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'], url_path='compartilhamentos')
    def listar_compartilhamentos(self, request, pk=None):
        """GET /relatorios-inteligencia/{pk}/compartilhamentos/ - Lista compartilhamentos"""
        relatorio = self.get_object()
        if not (hasattr(request.user, 'is_sac') and request.user.is_sac and hasattr(request.user, 'sac_profile') and request.user.sac_profile == 'FOCAL'):
             return Response(
                 {'detail': 'Apenas FOCALs podem ver compartilhamentos'},
                 status=status.HTTP_403_FORBIDDEN
             )
        compartilhamentos = relatorio.compartilhamentos.all()
        serializer = CompartilhamentoSerializer(
            compartilhamentos, many=True, context={'request': request}
        )
        return Response(serializer.data)

    def _criar_log_acesso(self, relatorio, request, tipo_acesso):
        """Método auxiliar para criar logs de acesso."""
        try:
            RelatorioInteligenciaChangeLog.objects.create(
                relatorio=relatorio,
                usuario=request.user,
                endereco_ip=self.get_client_ip(request),
                change_type=tipo_acesso,
                dispositivo=request.META.get('HTTP_USER_AGENT', 'Desconhecido')[:200],
                navegador=request.META.get('HTTP_USER_AGENT', 'Desconhecido')[:200]
            )
        except Exception as e:
            print(f"[Erro log {tipo_acesso}] {e}")

    def _criar_log_exclusao(self, relatorio, request):
        """Método auxiliar para criar log de exclusão."""
        try:
            RelatorioInteligenciaChangeLog.objects.create(
                deleted_report_id=relatorio.id,
                usuario=request.user,
                endereco_ip=self.get_client_ip(request),
                change_type='delete',
                dispositivo=f"DELETE - {request.META.get('HTTP_USER_AGENT', 'Desconhecido')}"[:200],
                navegador="Operação de Exclusão"[:200]
            )
        except Exception as e:
            print(f"[Erro log exclusão] {e}")

    def _atualizar_contadores(self, relatorio):
        """Método auxiliar para atualizar contadores."""
        try:
            relatorio.quantidade_acessos += 1
            relatorio.ultima_visualizacao = timezone.now()
            relatorio.save(update_fields=['quantidade_acessos', 'ultima_visualizacao'])
        except Exception as e:
            print(f"[Erro atualizar contador] {e}")

    def get_client_ip(self, request):
        """Retorna o IP real do cliente."""
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            return xff.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '0.0.0.0')

class RelatorioListaViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet para listagem simplificada de relatórios."""
    queryset = RelatorioInteligencia.objects.all().order_by('-criado_em')
    serializer_class = RelatorioListaSerializer
    permission_classes = [PermissaoLeituraPDF]

    def get_queryset(self):
        """Permite filtrar por parâmetros de query."""
        queryset = super().get_queryset()
        # Filtro por tipo
        tipo = self.request.query_params.get('tipo')
        if tipo:
            queryset = queryset.filter(tipo=tipo)
        # Filtro por ano
        ano = self.request.query_params.get('ano')
        if ano:
            try:
                ano = int(ano)
                queryset = queryset.filter(criado_em__year=ano)
            except ValueError:
                pass
        # Filtro por analista
        analista_id = self.request.query_params.get('analista_id')
        if analista_id:
            queryset = queryset.filter(analista_id=analista_id)
        return queryset

class CompartilhamentoAcessoViewSet(viewsets.GenericViewSet):
    """ViewSet para acessar PDFs via compartilhamento"""
    def get_serializer_class(self):
        """Retorna o serializer apropriado para a ação."""
        if self.action == 'retrieve':
            # Não usamos serializer para a ação retrieve neste ViewSet,
            # apenas retornamos dados básicos. Retornar um Serializer
            # básico é mais seguro do que None para evitar erros internos do DRF.
            return serializers.Serializer
        elif self.action == 'acessar':
            # Serializer usado para a ação POST /compartilhamento/{token}/acessar/
            return AcessoCompartilhamentoSerializer
        # Retorna um serializer base para outras ações não definidas
        return serializers.Serializer

    def retrieve(self, request, pk=None):
        """GET /compartilhamento/{token}/ - Página de acesso"""
        try:
            compartilhamento = RelatorioCompartilhamento.objects.get(token=pk)
            if not compartilhamento.is_valido():
                return Response(
                    {'detail': 'Link expirado ou inativo'},
                    status=status.HTTP_410_GONE
                )
            return Response({
                'tipo': compartilhamento.tipo,
                'relatorio': compartilhamento.relatorio.numero_ano,
                'expira_em': compartilhamento.expira_em,
                'requer_cpf': compartilhamento.tipo == 'cpf'
            })
        except RelatorioCompartilhamento.DoesNotExist:
            return Response(
                {'detail': 'Compartilhamento não encontrado'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
             # Log de erro inesperado na ação retrieve
             self._log_acesso(request, None, False, f"Erro inesperado no retrieve: {str(e)}")
             return Response(
                 {'detail': f'Ocorreu um erro inesperado: {e}'},
                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
             )


    @action(detail=True, methods=['post'], url_path='acessar')
    def acessar(self, request, pk=None):
        """POST /compartilhamento/{token}/acessar/ - Acessa o PDF"""
        compartilhamento = None # Inicializa como None para o log de erro
        try:
            compartilhamento = RelatorioCompartilhamento.objects.get(token=pk)

            # Valida o serializer com os dados da requisição e o contexto
            serializer = self.get_serializer(
                data=request.data,
                context={'compartilhamento': compartilhamento}
            )
            serializer.is_valid(raise_exception=True) # raise_exception=True levanta ValidationError automaticamente

            data = serializer.validated_data

            # Validação específica por tipo
            acesso_permitido = False
            mask_id = None

            if compartilhamento.tipo == 'cpf':
                cpf = data.get('cpf')
                senha = data.get('senha')
                if cpf and senha: # Verifica se os campos existem nos dados validados
                    acesso_permitido = self._validar_acesso_cpf(cpf, senha)
                    mask_id = cpf
            elif compartilhamento.tipo == 'especial':
                 numero_especial = data.get('numero_especial')
                 senha_especial = data.get('senha_especial')
                 if numero_especial and senha_especial: # Verifica se os campos existem
                    acesso_permitido = self._validar_acesso_especial(
                        compartilhamento, numero_especial, senha_especial
                    )
                    mask_id = numero_especial

            if not acesso_permitido:
                self._log_acesso(request, compartilhamento, False, "Credenciais inválidas")
                return Response(
                    {'detail': 'Credenciais inválidas'},
                    status=status.HTTP_401_UNAUTHORIZED
                )

            # Registra acesso bem-sucedido
            compartilhamento.registrar_acesso()
            self._log_acesso(request, compartilhamento, True) # Log de sucesso após validação

            # Gera PDF com máscara
            relatorio = compartilhamento.relatorio
            if not relatorio.arquivo_pdf or not os.path.exists(relatorio.arquivo_pdf.path):
                 self._log_acesso(request, compartilhamento, False, "Erro PDF: Arquivo não encontrado no sistema de arquivos")
                 return Response(
                     {'detail': 'Arquivo PDF do relatório não encontrado'},
                     status=status.HTTP_404_NOT_FOUND
                 )

            try:
                pdf_path = relatorio.arquivo_pdf.path
                # Use mask_id (CPF ou Numero Especial) para a marca d'água
                pdf_buffer = add_watermark_to_pdf(pdf_path, mask_id)
                return FileResponse(
                    pdf_buffer,
                    content_type='application/pdf',
                    as_attachment=False,
                    filename=f"relatorio_{relatorio.numero_ano}_compartilhado.pdf"
                )
            except Exception as e:
                self._log_acesso(request, compartilhamento, False, f"Erro PDF: {str(e)}")
                return Response(
                    {'detail': 'Erro ao gerar PDF'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        except RelatorioCompartilhamento.DoesNotExist:
            # Log de compartilhamento não encontrado
            self._log_acesso(request, None, False, "Compartilhamento não encontrado")
            return Response(
                {'detail': 'Compartilhamento não encontrado'},
                status=status.HTTP_404_NOT_FOUND
            )

        except serializers.ValidationError as e:
             # Log de erro de validação do serializer
             self._log_acesso(request, compartilhamento, False, f"Erro de validação: {str(e.detail)}")
             return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
             # Log de erro inesperado
             self._log_acesso(request, compartilhamento, False, f"Erro inesperado no acesso: {str(e)}")
             return Response(
                 {'detail': f'Ocorreu um erro inesperado: {e}'},
                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
             )


    def _validar_acesso_cpf(self, cpf, senha):
        """Valida acesso via CPF do usuário cadastrado"""
        if not cpf or not senha:
            return False # Garante que ambos os campos foram fornecidos
        cpf_limpo = ''.join(filter(str.isdigit, cpf))
        try:
            # Usar authenticate para verificar se o usuário existe e a senha está correta
            # Note que authenticate geralmente requer um backend de autenticação que lide com CPF
            # Se não tiver um backend customizado, pode ser necessário buscar o usuário e verificar a senha manualmente
            # user = authenticate(request=None, username=cpf_limpo, password=senha) # Exemplo com authenticate
            # return user is not None

            # Alternativa manual se authenticate não estiver configurado para CPF:
            user = User.objects.get(cpf=cpf_limpo)
            return user.check_password(senha)

        except User.DoesNotExist:
            return False
        except Exception as e:
             print(f"[Erro validação CPF] {e}")
             return False


    def _validar_acesso_especial(self, compartilhamento, numero, senha):
        """Valida acesso via credenciais especiais"""
        if not numero or not senha:
            return False # Garante que ambos os campos foram fornecidos
        return (
            compartilhamento.numero_especial == numero and
            compartilhamento.senha_especial == senha
        )

    def _log_acesso(self, request, compartilhamento, sucesso, erro=None):
        """Registra log de acesso ao compartilhamento"""
        try:
            CompartilhamentoAcesso.objects.create(
                compartilhamento=compartilhamento, # Pode ser None se o compartilhamento não foi encontrado
                ip_address=self.get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                sucesso=sucesso,
                erro=erro
            )
        except Exception as e:
             print(f"[Erro ao registrar log de acesso ao compartilhamento] {e}")

    def get_client_ip(self, request):
        """Retorna IP do cliente"""
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            return xff.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '0.0.0.0')

def get_client_ip(request):
    """Retorna IP do cliente"""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')

def _log_acesso_compartilhamento(request, compartilhamento, sucesso, mensagem=""):
    """Registra log de acesso ao compartilhamento (adaptado para uso externo)"""
    try:
        CompartilhamentoAcesso.objects.create(
            compartilhamento=compartilhamento, # Pode ser None se o compartilhamento não foi encontrado
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            sucesso=sucesso,
            erro=mensagem if not sucesso else None # Armazena a mensagem apenas em caso de erro
        )
    except Exception as e:
         print(f"[Erro ao registrar log de acesso ao compartilhamento] {e}")

class CompartilhamentoEspecialAcessoView(APIView):
    """
    View para acesso direto a PDFs de compartilhamentos do tipo 'especial' via token.
    Retorna o PDF com marca d'água usando o numero_especial.
    """
    def get(self, request, token, format=None):
        compartilhamento = None # Inicializa para uso no log
        # Limpa espaços em branco no início/fim do token recebido
        cleaned_token = token.strip()

        try:
            # 1. Buscar o compartilhamento pelo token LIMPO
            try:
                compartilhamento = RelatorioCompartilhamento.objects.get(token=cleaned_token)
            except RelatorioCompartilhamento.DoesNotExist:
                # Loga com o token original ou limpo, dependendo do que faz mais sentido para debug
                _log_acesso_compartilhamento(request, None, False, f"Compartilhamento especial não encontrado para token (limpo): {cleaned_token}")
                return Response(
                    {'detail': 'Link de compartilhamento não encontrado.'},
                    status=status.HTTP_404_NOT_FOUND
                )

            # 2. Verificar se o compartilhamento é do tipo 'especial'
            if compartilhamento.tipo != 'especial':
                _log_acesso_compartilhamento(request, compartilhamento, False, f"Tentativa de acesso especial a compartilhamento tipo: {compartilhamento.tipo}")
                return Response(
                    {'detail': 'Este link não é para acesso especial direto.'},
                    status=status.HTTP_403_FORBIDDEN # Ou HTTP_400_BAD_REQUEST
                )

            # 3. Verificar se o compartilhamento ainda é válido
            if not compartilhamento.is_valido():
                _log_acesso_compartilhamento(request, compartilhamento, False, "Tentativa de acesso especial a link expirado/inativo")
                return Response(
                    {'detail': 'Link expirado ou inativo.'},
                    status=status.HTTP_410_GONE
                )

            # 4. Verificar se o relatório e o arquivo PDF existem
            relatorio = compartilhamento.relatorio
            if not relatorio.arquivo_pdf or not os.path.exists(relatorio.arquivo_pdf.path):
                 _log_acesso_compartilhamento(request, compartilhamento, False, "Erro PDF: Arquivo não encontrado no sistema de arquivos para acesso especial")
                 return Response(
                      {'detail': 'Arquivo PDF do relatório não encontrado.'},
                      status=status.HTTP_404_NOT_FOUND
                  )

            # 5. Registrar acesso bem-sucedido ANTES de servir o arquivo
            # Note: Esta rota não usa credenciais, então o registro aqui é baseado apenas no token válido.
            # Se você quiser registrar o acesso no modelo RelatorioCompartilhamento, chame:
            # compartilhamento.registrar_acesso() # Se este método existir e for apropriado aqui

            # Usar o numero_especial como identificador para a marca d'água
            mask_id = compartilhamento.numero_especial
            _log_acesso_compartilhamento(request, compartilhamento, True, f"Acesso especial bem-sucedido. Mask ID: {mask_id}")

            # 6. Gerar PDF com marca d'água
            try:
                pdf_path = relatorio.arquivo_pdf.path
                pdf_buffer = add_watermark_to_pdf(pdf_path, mask_id)

                # 7. Retornar o PDF como FileResponse
                return FileResponse(
                    pdf_buffer,
                    content_type='application/pdf',
                    as_attachment=False, # Exibe no navegador
                    filename=f"relatorio_{relatorio.numero_ano}_especial.pdf"
                )

            except Exception as e:
                # Log de erro na geração do PDF
                _log_acesso_compartilhamento(request, compartilhamento, False, f"Erro na geração do PDF para acesso especial: {str(e)}")
                print(f"[Erro ao gerar PDF compartilhado especial] {e}") # Log no console do servidor
                return Response(
                    {'detail': 'Erro ao gerar PDF.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        except Exception as e:
            # Log de erro inesperado
            _log_acesso_compartilhamento(request, compartilhamento, False, f"Erro inesperado no acesso especial: {str(e)}")
            print(f"[Erro inesperado na view CompartilhamentoEspecialAcessoView] {e}") # Log no console do servidor
            return Response(
                {'detail': f'Ocorreu um erro inesperado: {e}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class GerarLinkAcessoEspecialView(APIView):
    """
    Endpoint para gerar um link de acesso especial temporário para um relatório.
    Requer autenticação e perfil 'FOCAL'.
    Recebe o UUID do relatório na URL.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, relatorio_uuid, *args, **kwargs):
        # relatorio_uuid é capturado diretamente da URL

        # 1. Validar permissão: Apenas usuários FOCAL podem criar links especiais
        user = request.user
        # Adapte a verificação de perfil conforme a estrutura do seu modelo de usuário
        # Exemplo baseado nos seus models:
        if not (hasattr(user, 'is_sac') and user.is_sac and hasattr(user, 'sac_profile') and user.sac_profile == 'FOCAL'):
             raise PermissionDenied("Você não tem permissão para gerar links de acesso especial.")

        # 2. Buscar o relatório usando o UUID da URL
        # get_object_or_404 lida com DoesNotExist (retorna 404)
        # O sistema de rotas do Django/DRF já valida o formato UUID
        relatorio = get_object_or_404(RelatorioInteligencia, id=relatorio_uuid)

        # 3. Criar o objeto RelatorioCompartilhamento do tipo 'especial'
        # A lógica de geração de token, numero_especial, senha_especial e expiração
        # para o tipo 'especial' já está no método save() do modelo.
        try:
            compartilhamento = RelatorioCompartilhamento.objects.create(
                relatorio=relatorio,
                criado_por=user,
                tipo='especial' # Usando o tipo 'especial' conforme definido no seu modelo
            )
        except Exception as e:
            # Logar o erro e retornar um erro genérico
            print(f"Erro ao criar compartilhamento: {e}") # Substituir por log real
            return Response(
                {"detail": "Ocorreu um erro interno ao gerar o link de acesso especial."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # 4. Serializar a resposta
        output_serializer = RelatorioCompartilhamentoEspecialSerializer(compartilhamento)

        # 5. Retornar a resposta
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)
