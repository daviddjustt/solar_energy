
import logging
import string
import traceback
from io import StringIO, BytesIO
import pandas as pd
from secrets import choice as secure_choice
from datetime import datetime, timedelta

# Django imports
from django.conf import settings
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.utils import timezone
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.contrib.auth.mixins import UserPassesTestMixin 
from django.views.generic import ListView
from django.db.models import Q 

from .models import EmailLog, User, UserChangeLog

logger = logging.getLogger(__name__)

class UserExportService:
    """Serviço para exportação de usuários"""
    
    def export_users(self, queryset):
        """
        Método legado para compatibilidade - redireciona para create_csv_response
        """
        logger.warning("UserExportService.export_users() é um método legado. Use create_csv_response() em seu lugar.")
        return self.create_csv_response(queryset=queryset)
    
    def create_csv_response(self, queryset, filename=None):
        """
        Exporta um queryset de usuários para CSV
        Args:
            queryset: QuerySet de User para exportação
            filename: Nome do arquivo CSV (opcional)
        Returns:
            HttpResponse: Resposta HTTP com arquivo CSV
        """
        logger.info(f"Iniciando exportação de {queryset.count()} usuários para CSV")
        
        if not queryset.exists():
            logger.info("Queryset vazio. Exportando CSV vazio.")
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="usuarios_vazio.csv"'
            response.write(u'\ufeff'.encode('utf-8')) # BOM para Excel
            return response
        
        try:
            # 1) Converter QuerySet para DataFrame
            # Incluindo campos SAC que estão no modelo User
            data = list(queryset.values(
                'email', 'name', 'cpf', 'celular', 'patent',
                'is_admin', 'is_operacoes', 'is_sac', 'sac_profile',
                'is_active', 'created_at', 'updated_at',
            ))
            df = pd.DataFrame(data)
            
            # 2) Formatar os dados
            df = self._format_for_csv(df)
            
            # 3) Exportar para CSV
            buffer = BytesIO()
            df.to_csv(buffer, sep=';', index=False, encoding='utf-8-sig')
            
            # 4) Retornar como resposta HTTP
            buffer.seek(0)
            if not filename:
                timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
                filename = f'usuarios_{timestamp}.csv'
            
            response = HttpResponse(buffer, content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            logger.info(f"Exportação de CSV concluída para o arquivo {filename}")
            return response
            
        except Exception as e:
            logger.error(f"Erro durante a exportação de usuários para CSV: {e}", exc_info=True)
            # Retorna uma resposta de erro simples
            response = HttpResponse("Erro ao gerar o arquivo CSV.", status=500)
            return response
    
    def _format_for_csv(self, df):
        """Formata os dados para CSV"""
        # 0) Formatar ID (UUID) para string se existir
        if 'id' in df.columns:
            df['id'] = df['id'].astype(str)
        
        # 1) Renomear colunas
        df = df.rename(columns={
            'id': 'ID',
            'email': 'E-mail',
            'name': 'Nome',
            'cpf': 'CPF',
            'celular': 'Celular',
            'patent': 'Patente',
            'is_admin': 'É Admin',
            'is_operacoes': 'Acesso Operações',
            'is_sac': 'É SAC',
            'sac_profile': 'Perfil SAC',
            'is_active': 'Ativo',
            'created_at': 'Data de Criação',
            'updated_at': 'Data de Atualização'
        })
        
        # 2) Formatar CPF: XXX.XXX.XXX-XX
        def mask_cpf(cpf):
            if pd.isna(cpf) or not cpf:
                return ''
            s = ''.join(filter(str.isdigit, str(cpf)))
            if len(s) == 11:
                return f"{s[:3]}.{s[3:6]}.{s[6:9]}-{s[9:]}"
            return cpf
        
        if 'CPF' in df.columns:
            df['CPF'] = df['CPF'].apply(mask_cpf)
        
        # 3) Formatar Celular: (XX) XXXXX-XXXX
        def mask_cel(cel):
            if pd.isna(cel) or not cel:
                return ''
            s = ''.join(filter(str.isdigit, str(cel)))
            if len(s) == 11:
                return f"({s[:2]}) {s[2:7]}-{s[7:]}"
            return cel
        
        if 'Celular' in df.columns:
            df['Celular'] = df['Celular'].apply(mask_cel)
        
        # 4) Booleanos para SIM/NÃO
        bool_columns = ['É Admin', 'Acesso Operações', 'É SAC', 'Ativo']
        for col in bool_columns:
            if col in df.columns:
                df[col] = df[col].map({True: 'SIM', False: 'NÃO', pd.NA: 'NÃO', None: 'NÃO'}).fillna('NÃO') # Trata NaN/None
        
        # 5) Formatar datas
        date_columns = ['Data de Criação', 'Data de Atualização']
        for col in date_columns:
            if col in df.columns:
                # Use errors='coerce' para transformar datas inválidas em NaT (Not a Time)
                df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%d/%m/%Y %H:%M').fillna('') # Preenche NaT com string vazia
        
        # 6) Reordenar colunas
        # Garantir que apenas colunas existentes sejam incluídas
        columns_order = [
            'ID', 'E-mail', 'Nome', 'CPF', 'Celular', 'Patente',
            'É Admin', 'Acesso Operações', 'É SAC', 'Perfil SAC',
            'Ativo', 'Data de Criação', 'Data de Atualização'
        ]
        valid_columns = [col for col in columns_order if col in df.columns]
        df = df[valid_columns]
        
        logger.debug("Dados formatados para CSV")
        return df

class EmailService:
    """
    Serviço para envio de e-mails com suporte a templates e logging.
    """
    
    @staticmethod
    def send_welcome_email(user, password=None):
        """
        Envia e-mail de boas-vindas com informações de acesso.
        Args:
            user: Instância do modelo User
            password: Senha temporária gerada (opcional)
        Returns:
            bool: True se o e-mail foi enviado com sucesso, False caso contrário
        """
        log_status = 'FAILED'
        error_message = None
        subject = 'N/A' # Inicializa subject para o log
        
        try:
            logger.info(f"Iniciando envio de e-mail de boas-vindas para {user.email}")
            
            # Gera URL de login dinamicamente baseada no ambiente
            if settings.DEBUG:
                domain = 'localhost:8000'
                protocol = 'http'
            else:
                # Usa o primeiro allowed host ou um default
                domain = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else 'arcanosig.com.br'
                protocol = 'https'
            
            # Garante que o LOGIN_URL começa com '/'
            login_path = getattr(settings, 'LOGIN_URL', '/admin/login/') # Use getattr com default
            if not login_path.startswith('/'):
                login_path = f"/{login_path}"
            
            login_url = f"{protocol}://{domain}{login_path}"
            
            # Contexto completo para o template
            context = {
                'user': user,
                'password': password,
                'site_name': getattr(settings, 'SITE_NAME', 'ArcanoSIG'), # Use getattr com default
                'protocol': protocol,
                'domain': domain,
                'login_url': login_url
            }
            
            # Configura e envia o e-mail
            subject = f'Bem-vindo ao {context["site_name"]}'
            
            # Renderiza o template HTML
            html_content = render_to_string('email/activation_imports.html', context)
            text_content = strip_tags(html_content)
            
            # Cria o e-mail
            msg = EmailMultiAlternatives(
                subject,
                text_content,
                settings.DEFAULT_FROM_EMAIL,
                [user.email]
            )
            msg.attach_alternative(html_content, "text/html")
            
            # Envia o e-mail
            result = msg.send()
            
            if result > 0:
                log_status = 'SUCCESS'
                logger.info(f"✅ E-mail de boas-vindas enviado com sucesso para {user.email}")
                return True
            else:
                log_status = 'FAILED'
                error_message = 'Falha no envio - resultado 0'
                logger.warning(f"❌ Falha no envio de e-mail para {user.email} - resultado: {result}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Erro ao enviar e-mail de boas-vindas para {user.email}: {str(e)}", exc_info=True)
            error_message = str(e)
            log_status = 'FAILED'
            return False
            
        finally:
            # Registra o status de envio no log
            try:
                EmailLog.objects.create(
                    user=user,
                    email_type='ACTIVATION',
                    status=log_status,
                    recipient=user.email,
                    subject=subject, # Usa a variável subject definida acima
                    error_message=error_message
                )
                logger.debug(f"Log de email criado para {user.email} com status {log_status}")
            except Exception as log_e:
                logger.error(f"Erro ao registrar EmailLog para {user.email}: {log_e}", exc_info=True)

class UserImportService:
    """
    Serviço para importação de usuários em massa.
    """
    SUPPORTED_EXTENSIONS = ('.csv', '.xls', '.xlsx')
    
    def __init__(self, file_obj, admin_user=None):
        self.file_obj = file_obj
        self.admin_user = admin_user
        self.password_length = getattr(settings, 'DEFAULT_PASSWORD_LENGTH', 10)
        self.from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        self.email_service = EmailService()
    
    def _generate_random_password(self):
        """Gera uma senha aleatória criptograficamente segura."""
        alphabet = (
            string.ascii_letters.replace('l', '').replace('I', '').replace('O', '')
            + string.digits.replace('0', '')
        )
        return ''.join(secure_choice(alphabet) for _ in range(self.password_length))
    
    def _read_file(self):
        """Lê o arquivo e retorna um DataFrame."""
        name = self.file_obj.name.lower()
        if not name.endswith(self.SUPPORTED_EXTENSIONS):
            raise ValueError(f"Formato '{name}' não suportado. Use: {', '.join(self.SUPPORTED_EXTENSIONS)}.")
        
        try:
            # Reset file pointer to the beginning
            self.file_obj.seek(0)
            reader = pd.read_csv if name.endswith('.csv') else pd.read_excel
            
            # Tenta ler com diferentes engines para Excel
            if name.endswith(('.xlsx', '.xls')):
                try:
                    df = reader(self.file_obj, dtype={'cpf': str, 'celular': str}, engine='openpyxl')
                except ImportError:
                    logger.warning("openpyxl não encontrado. Tentando com xlrd (apenas .xls).")
                    try:
                        self.file_obj.seek(0) # Reset file pointer again for xlrd
                        df = reader(self.file_obj, dtype={'cpf': str, 'celular': str}, engine='xlrd')
                    except ImportError:
                        raise ImportError("Nenhum dos motores de leitura de Excel (openpyxl, xlrd) foi encontrado. Instale um deles (`pip install openpyxl` ou `pip install xlrd<2.0`).")
            else: # CSV
                # Tenta ler CSV com diferentes encodings
                try:
                    df = reader(self.file_obj, dtype={'cpf': str, 'celular': str}, encoding='utf-8')
                except UnicodeDecodeError:
                    logger.warning("Erro de decodificação UTF-8. Tentando com latin-1.")
                    self.file_obj.seek(0) # Reset file pointer
                    df = reader(self.file_obj, dtype={'cpf': str, 'celular': str}, encoding='latin-1')
            
            logger.info(f"Arquivo {self.file_obj.name} lido com sucesso. {len(df)} linhas encontradas.")
            return df
            
        except Exception as e:
            logger.error(f"Erro ao ler o arquivo {self.file_obj.name}: {e}", exc_info=True)
            raise ValueError(f"Erro ao ler o arquivo: {e}")
    
    def _normalize_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normaliza e formata dados."""
        df = df.copy()
        
        # Normaliza nomes de colunas para minúsculas para facilitar o acesso
        df.columns = df.columns.str.lower()
        
        # Normaliza campos de texto
        for col in ('email', 'name', 'patent'):
            if col in df.columns:
                # Converte para string, remove espaços, trata NaN/None como string vazia antes de strip
                df[col] = df[col].astype(str).str.strip().replace('', None) # Trata strings vazias como None
                if col == 'email':
                    df[col] = df[col].str.lower()
                # Manter nome e patente como estão no arquivo ou definir uma política de capitalização se necessário
                # df[col] = df[col].str.upper() # Removido para manter capitalização original ou None
        
        # Normaliza CPF e Celular (apenas dígitos)
        for col in ('cpf', 'celular'):
            if col in df.columns:
                # Converte para string, remove não dígitos, trata NaN/None como string vazia antes de replace
                df[col] = df[col].astype(str).str.replace(r'\D+', '', regex=True).replace('', None) # Remove não dígitos, trata vazio como None
        
        # Normaliza campos booleanos
        for bool_col in ('is_admin', 'is_operacoes', 'is_sac', 'is_active'):
            if bool_col in df.columns:
                # Converte para string, remove espaços, converte para maiúsculas, compara com 'TRUE' ou 'SIM'
                df[bool_col] = (
                    df[bool_col].astype(str)
                    .str.strip().str.upper()
                    .apply(lambda x: x in ('TRUE', 'SIM', '1')) # Considera 'TRUE', 'SIM' ou '1' como True
                )
            else:
                # Adiciona coluna booleana com valor padrão False se não existir
                df[bool_col] = False
                logger.warning(f"Coluna '{bool_col}' não encontrada. Usando valor padrão False.")
        
        # Normaliza campo sac_profile
        if 'sac_profile' in df.columns:
            df['sac_profile'] = df['sac_profile'].astype(str).str.strip().replace('', None)
        else:
            df['sac_profile'] = None # Adiciona coluna com None se não existir
            logger.warning("Coluna 'sac_profile' não encontrada. Usando valor padrão None.")
        
        logger.debug("Dados normalizados: %d linhas processadas", len(df))
        return df
    
    def _validate_columns(self, df: pd.DataFrame):
        """Verifica colunas obrigatórias."""
        # Converte nomes de colunas esperadas para minúsculas para corresponder ao DataFrame normalizado
        required_columns = ['email', 'name', 'cpf', 'celular', 'patent']
        missing = [c for c in required_columns if c not in df.columns]
        
        if missing:
            raise ValueError(f"Colunas obrigatórias ausentes: {', '.join(missing)}")
        
        # Verifica se colunas opcionais esperadas existem, caso contrário adiciona com valor padrão
        optional_bool_cols = ['is_admin', 'is_operacoes', 'is_sac', 'is_active']
        for col in optional_bool_cols:
            if col not in df.columns:
                df[col] = False # Adiciona com False se ausente
        
        if 'sac_profile' not in df.columns:
            df['sac_profile'] = None # Adiciona com None se ausente
    
    def _send_activation_email(self, user, password):
        """
        Envia e-mail de ativação com credenciais para o usuário.
        
        Args:
            user: Instância do modelo User
            password: Senha temporária gerada
            
        Returns:
            bool: True se o e-mail foi enviado com sucesso, False caso contrário
        """
        try:
            logger.info(f"Tentando enviar e-mail de ativação para {user.email}")
            
            # Usa o EmailService para enviar o e-mail de boas-vindas
            email_sent = EmailService.send_welcome_email(user, password)
            
            if email_sent:
                logger.info(f"✅ E-mail de ativação enviado com sucesso para {user.email}")
            else:
                logger.warning(f"❌ Falha no envio de e-mail de ativação para {user.email}")
                
            return email_sent
            
        except AttributeError as ae:
            logger.error(f"❌ Erro de atributo ao enviar e-mail para {user.email}: {ae}")
            return False
        except Exception as e:
            logger.error(f"❌ Erro inesperado ao enviar e-mail para {user.email}: {e}", exc_info=True)
            return False
    
    def _log_user_changes(self, user):
        """Registra a criação do usuário no histórico."""
        if not self.admin_user:
            return
        
        # Campos a serem logados na criação
        fields_to_log = [
            ('email', user.email),
            ('name', user.name),
            ('cpf', user.cpf),
            ('celular', user.celular),
            ('patent', user.patent),
            ('is_admin', user.is_admin),
            ('is_operacoes', user.is_operacoes),
            ('is_sac', user.is_sac),
            ('sac_profile', user.sac_profile),
            ('is_active', user.is_active)
        ]
        
        for field_name, field_value in fields_to_log:
            # Para criação, logamos todos os campos que foram definidos
            # Convertendo valores para string para armazenamento no log
            log_value = str(field_value) if field_value is not None else ''
            if isinstance(field_value, bool):
                 log_value = 'SIM' if field_value else 'NÃO'
            elif field_value is None:
                 log_value = '' # Representa None como string vazia no log
            
            UserChangeLog.objects.create(
                user=user,
                changed_by=self.admin_user,
                field_name=field_name,
                old_value="[IMPORTAÇÃO - CRIADO]", # Marca que foi criação por importação
                new_value=log_value
            )
    
    def import_users(self, send_emails=True):
        """Importa usuários com controle de erros e logging."""
        logger.info("Iniciando importação de usuários de %s por %s (Enviar emails: %s)",
                    self.file_obj.name, self.admin_user, send_emails)
        
        results = [] # Lista de dicionários para usuários importados com sucesso
        errors = [] # Lista de dicionários para erros de linha
        email_errors = [] # Lista de emails com falha no envio
        
        try:
            df = self._read_file()
            df = self._normalize_data(df)
            self._validate_columns(df) # Valida colunas após normalização e adição de defaults
            
            # Pré-verifica e-mails e CPFs existentes para dar feedback mais rápido
            # Filtra apenas valores não nulos antes de consultar o DB
            existing_emails = set(User.objects.filter(email__in=df['email'].dropna().tolist()).values_list('email', flat=True))
            existing_cpfs = set(User.objects.filter(cpf__in=df['cpf'].dropna().tolist()).values_list('cpf', flat=True))
            
            # Processa cada linha individualmente
            for idx, row in df.iterrows():
                # Use .get() com None como default para evitar KeyError se a coluna não existir após normalização
                email = row.get('email')
                cpf = row.get('cpf')
                
                # Use um identificador robusto para a linha no log/erros
                row_identifier = f"Linha {idx+2} (Email: {email or 'N/A'}, CPF: {cpf or 'N/A'})" # +2 para considerar cabeçalho e índice 0
                
                # Validação básica de dados na linha
                if not email:
                    errors.append({'row': idx + 2, 'identifier': row_identifier, 'error': 'E-mail não fornecido.'})
                    logger.warning(f"Erro na {row_identifier}: E-mail não fornecido.")
                    continue
                
                if not cpf:
                    errors.append({'row': idx + 2, 'identifier': row_identifier, 'error': 'CPF não fornecido.'})
                    logger.warning(f"Erro na {row_identifier}: CPF não fornecido.")
                    continue
                
                if not row.get('name'):
                    errors.append({'row': idx + 2, 'identifier': row_identifier, 'error': 'Nome não fornecido.'})
                    logger.warning(f"Erro na {row_identifier}: Nome não fornecido.")
                    continue
                
                if not row.get('patent'):
                    errors.append({'row': idx + 2, 'identifier': row_identifier, 'error': 'Patente não fornecida.'})
                    logger.warning(f"Erro na {row_identifier}: Patente não fornecida.")
                    continue
                
                # Verifica duplicidade antes de tentar criar
                if email in existing_emails:
                    errors.append({'row': idx + 2, 'identifier': row_identifier, 'error': f'E-mail já cadastrado: {email}'})
                    logger.warning(f"Erro na {row_identifier}: E-mail já cadastrado.")
                    continue
                
                if cpf in existing_cpfs:
                    errors.append({'row': idx + 2, 'identifier': row_identifier, 'error': f'CPF já cadastrado: {cpf}'})
                    logger.warning(f"Erro na {row_identifier}: CPF já cadastrado.")
                    continue
                
                try:
                    # Cria cada usuário em uma transação independente
                    with transaction.atomic():
                        # Gerar senha aleatória segura
                        pwd = self._generate_random_password()
                        
                        # Criar o usuário
                        # Use .get() com valor padrão para colunas opcionais
                        user = User.objects.create_user(
                            email=email,
                            name=row.get('name'),
                            cpf=cpf,
                            celular=row.get('celular'), # Celular pode ser None após normalização
                            patent=row.get('patent'),
                            password=pwd,
                            is_admin=row.get('is_admin', False),
                            is_operacoes=row.get('is_operacoes', False),
                            is_sac=row.get('is_sac', False),
                            sac_profile=row.get('sac_profile', None), # sac_profile pode ser None
                            is_active=row.get('is_active', True), # Ativa por padrão, mas permite sobrescrever pelo arquivo
                        )
                        
                        # Validar o modelo completo
                        try:
                            user.full_clean()
                        except ValidationError as ve:
                             # Captura erros de validação do modelo Django
                             error_detail = f"Erro de validação do modelo: {ve}"
                             errors.append({'row': idx + 2, 'identifier': row_identifier, 'error': error_detail, 'trace': traceback.format_exc()})
                             logger.warning(f"Erro de validação do modelo para {row_identifier}: {error_detail}")
                             transaction.set_rollback(True) # Garante que a transação seja revertida
                             continue # Pula para a próxima linha
                        
                        user.save()
                        
                        # Adiciona o email e cpf à lista de existentes para evitar duplicação dentro do mesmo arquivo
                        existing_emails.add(email)
                        existing_cpfs.add(cpf)
                    
                    # Log de alterações fora da transação atômica de criação
                    try:
                        self._log_user_changes(user)
                    except Exception as log_exc:
                        logger.error(f"Erro ao logar alterações para o usuário {user.email}: {log_exc}", exc_info=True)
                        # Continua mesmo se o log falhar
                    
                    # Enviar email com credenciais - Lógica condicional melhorada
                    email_sent = False
                    if send_emails:
                        try:
                            email_sent = self._send_activation_email(user, pwd)
                            if not email_sent:
                                email_errors.append({
                                    'recipient': user.email,
                                    'error': 'Falha no envio do e-mail de ativação'
                                })
                        except AttributeError as ae:
                            logger.error(f"Método _send_activation_email com erro: {ae}")
                            email_errors.append({
                                'recipient': user.email,
                                'error': f'Método de envio de email com erro: {ae}'
                            })
                        except Exception as e:
                            logger.error(f"Erro ao tentar enviar email para {user.email}: {e}")
                            email_errors.append({
                                'recipient': user.email,
                                'error': f'Erro no envio de email: {e}'
                            })
                    
                    # Adicionar ao resultado de sucesso
                    results.append({
                        'email': user.email,
                        'name': user.name,
                        'password': pwd,
                        'email_sent': email_sent # Reporta se o email foi tentado/enviado
                    })
                    
                    logger.info(f"Usuário criado e processado com sucesso: {user.email}")
                    
                except (IntegrityError, Exception) as exc:
                    # Captura erros específicos de DB ou outras exceções não capturadas anteriormente para esta linha
                    trace = traceback.format_exc()
                    error_detail = str(exc)
                    errors.append({'row': idx + 2, 'identifier': row_identifier, 'error': error_detail, 'trace': trace})
                    logger.warning(f"Erro ao processar {row_identifier}: {error_detail}")
                    # A transação atômica já deve ter revertido em caso de IntegrityError
            
            # Log de resultados finais
            logger.info(f"Importação concluída: {len(results)} sucessos, {len(errors)} erros, {len(email_errors)} emails com falha")
            
            # Retorna um dicionário com os resultados detalhados
            return {
                'success': True, # Indica que o processo de importação rodou sem falhas gerais
                'message': f"Importação concluída: {len(results)} usuários importados com sucesso.",
                'imported_users': results,
                'errors': errors,
                'email_errors': email_errors
            }
            
        except Exception as general_exc:
            # Captura erros gerais (ex: erro na leitura do arquivo, validação de colunas)
            logger.exception("Erro geral durante importação de usuários")
            return {
                'success': False, # Indica que houve uma falha geral que impediu o processamento completo
                'message': f"Erro geral durante a import"
            }