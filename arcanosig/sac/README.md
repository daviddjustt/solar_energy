# 🛡️ Sistema de Gestão de Relatórios de Inteligência e Usuários SAC

Este projeto é um sistema robusto construído com Django e Django REST Framework para gerenciar relatórios de inteligência e usuários com perfis específicos (SAC - Serviço de Análise Criminal). Ele oferece funcionalidades de CRUD para relatórios, controle de acesso baseado em perfis e tempo, auditoria detalhada de acessos e alterações, e notificações por e-mail.

# ✨ Funcionalidades Principais

### Gerenciamento de Usuários Personalizado 👮‍♂️: 
Modelo de usuário estendido com campos como CPF, celular, patente, e perfis específicos (is_sac, sac_profile, is_operacoes).

### Controle de Acesso Granular 🔑:
Permissões baseadas em perfis de usuário **(LEITOR, ANALISTA, FOCAL)** e regras de tempo para edição/exclusão de relatórios.

### Gestão de Relatórios de Inteligência 📊: 
CRUD completo para relatórios, com campos para quantitativos de ocorrências, anexos PDF e informações de autoria (Analista/Focal).

### Auditoria Detalhada:
*   Registro de histórico de alterações em modelos (`User`, `RelatorioInteligencia`) 📜
*   Logs de acesso a relatórios e visualizações de PDF, incluindo IP, dispositivo e navegador. 🕵️‍♀️
*   Log de envio de e-mails. 📧

### Notificações por E-mail 📬: 
Envio automático de e-mails para usuários SAC quando novos relatórios são criados.

### Serializadores Otimizados 📦: 
Serializadores dedicados para diferentes propósitos (detalhe, listagem, busca) para melhor performance e controle de dados. 

### Validações Robustas ✅: 
Validações customizadas para campos como CPF, tamanho de imagem e unicidade de relatórios.

Configure as variáveis de ambiente (e-mail, SITEURL, SITENAME, etc.) no seu arquivo .env ou configurações do Django. ⚙️

# 🚀 Uso da API
A API para gerenciamento de relatórios está disponível no endpoint **/relatorios-inteligencia/**.

## Endpoints
    GET /relatorios-inteligencia/: Lista todos os relatórios de inteligência (serializador otimizado para listagem).
    POST /relatorios-inteligencia/: Cria um novo relatório de inteligência (requer perfil FOCAL).
    GET /relatorios-inteligencia/{id}/: Recupera detalhes de um relatório específico.
    PUT /relatorios-inteligencia/{id}/: Atualiza um relatório (requer perfil ANALISTA ou FOCAL e estar dentro do prazo de 6 horas).
    PATCH /relatorios-inteligencia/{id}/: Atualiza parcialmente um relatório (requer perfil ANALISTA ou FOCAL e estar dentro do prazo de 6 horas).
    DELETE /relatorios-inteligencia/{id}/: Exclui um relatório (requer perfil ANALISTA ou FOCAL e estar dentro do prazo de 6 horas).

## Autenticação
Todos os endpoints requerem autenticação. Utilize tokens de autenticação ou outro método configurado no seu projeto Django REST Framework. 🔒

# 🔑 Permissões
As permissões são controladas pelas classes:

### PermissaoRelatorioInteligencia:

*   **CREATE:** Apenas `ANALISTA` e `FOCAL`.
*   **UPDATE/DELETE:** Apenas `ANALISTA` e `FOCAL` **nos relatórios que criaram e dentro de 6 horas** da criação.
*   **READ (List/Retrieve):** Todos os usuários `is_sac=True`.

### PermissaoAuditarRelatorio: 
Controla o acesso aos logs de auditoria (detalhes não especificados no snippet, mas a classe existe).

### PermissaoLeituraPDF: 
Permite a leitura de PDFs para usuários is_sac=True e superusuários. Registra o acesso.

### Níveis de Acesso e Permissões por Perfil SAC
Os usuários com is_sac=True possuem diferentes níveis de acesso e permissões com base no seu sac_profile:

### Perfil LEITOR:
*   Pode **LER** (listar e visualizar detalhes) todos os relatórios de inteligência. 📖
*   Pode **VISUALIZAR** os arquivos PDF dos relatórios. 📄
*   **NÃO** pode criar, atualizar ou excluir relatórios. ❌

### Perfil ANALISTA:
*   Pode **LER** (listar e visualizar detalhes) todos os relatórios de inteligência. 📖
*   Pode **VISUALIZAR** os arquivos PDF dos relatórios. 📄
*   Pode **CRIAR** novos relatórios de inteligência. ✨
*   Pode **ATUALIZAR** e **EXCLUIR** *apenas* os relatórios que ele próprio criou, dentro de um prazo de 6 horas após a criação. ✏️🗑️⏰

### Perfil FOCAL:
*   Pode **LER** (listar e visualizar detalhes) todos os relatórios de inteligência. 📖
*   Pode **VISUALIZAR** os arquivos PDF dos relatórios. 📄
*   Pode **CRIAR** novos relatórios de inteligência. ✨
*   Pode **ATUALIZAR** e **EXCLUIR** *apenas* os relatórios que ele próprio criou, dentro de um prazo de 6 horas após a criação. ✏️🗑️⏰
*   É o perfil responsável por disparar o sinal de envio de e-mail após a criação de um relatório. 📬

## 📬 Sinais

### enviar_email_para_usuarios_sac: 
Disparado após a criação de um RelatorioInteligencia por um FOCAL. Notifica todos os usuários is_sac=True via e-mail.

### log_pdf_access: 
Disparado no início de cada requisição. Monitora e registra acessos a URLs contendo visualizar_pdf em um logger separado para fins de auditoria de segurança.

## 📄 Modelos

### User: 
Modelo de usuário customizado.

### RelatorioInteligencia: 
Representa um relatório de inteligência, contendo dados como tipo, número, ano, analista, focal, arquivo PDF, quantitativos de ocorrências, etc.

### : 
Registra cada visualização de um relatório, incluindo usuário, data/hora, IP, dispositivo e navegador.

### EmailLog: 
Mantém um registro de todos os e-mails enviados pelo sistema.

### UserChangeLog: 
Registra alterações feitas nos dados dos usuários.

### UserImport (Proxy): 
Modelo utilizado para funcionalidades de importação de usuários.

# 📦 Serializadores

### UsuarioBreveSserializador: 
Informações mínimas do usuário (id, nome, patente) para evitar exposição de dados sensíveis.

### RelatorioInteligenciaChangeLogSerializador: 
Serializa dados de logs de acesso a relatórios.

### RelatorioInteligenciaSerializer: 
Serializador completo para RelatorioInteligencia, usado para criação, atualização e visualização detalhada. Inclui validações e campos aninhados/calculados.

### RelatorioInteligenciaListagemSerializador: 
Serializador simplificado para listagem de relatórios.

### RelatorioBuscaSerializador: 
Utilizado para validar parâmetros de busca avançada.

## Auditoria
O sistema implementa várias camadas de auditoria:

### Histórico de Modelos: 
HistoricalRecords rastreia alterações nos modelos User e RelatorioInteligencia.

### Logs de Acesso a Relatórios: 
RelatorioInteligenciaChangeLog registra quem acessou qual relatório e quando.

### Logs de E-mail: 
EmailLog armazena detalhes de e-mails enviados.

### Logs de Alteração de Usuário: 
UserChangeLog registra alterações específicas em campos de usuário.

### Log de Acesso a PDF: 
O sinal request_started registra acessos diretos aos arquivos PDF mascarados em um arquivo de log separado.

# 📝 Guia de Mensagens de Commit
Para manter um histórico de commits limpo e informativo, siga o padrão Conventional Commits:

    feat: Adiciona nova funcionalidade

    fix: Corrige um bug

    docs: Altera a documentação

    style: Formata código, sem mudanças funcionais

    refactor: Refatora código, sem mudanças funcionais

    perf: Melhora de performance

    test: Adiciona ou corrige testes

    chore: Tarefas de manutenção, configuração, etc.

    feat: Implementa criação de relatórios de inteligência

Adiciona o endpoint POST /relatorios-inteligencia/ para permitir a criação de novos relatórios pelos usuários FOCAL. Inclui validações de dados e atribuição automática do analista.

Use emojis relevantes no início da linha de assunto para maior clareza visual. ✨🐛📚💄🔨🚀✅
