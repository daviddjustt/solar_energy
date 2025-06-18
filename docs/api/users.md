# Sistema de Autenticação USERS

## Visão Geral
Este sistema utiliza Django REST Framework com Djoser e Simple JWT para autenticação. O modelo de usuário é personalizado para policiais militares, com campos específicos como patente, matrícula e CPF.

## Endpoints Principais

### Autenticação JWT
| Método | Endpoint                     | Descrição                          |
|--------|------------------------------|------------------------------------|
| POST   | `/api/v1/auth/jwt/create/`    | Cria tokens JWT (access + refresh) |
| POST   | `/api/v1/auth/jwt/refresh/`   | Atualiza token de acesso           |
| POST   | `/api/v1/auth/jwt/verify/`    | Verifica validade do token         |
| POST   | `/api/v1/auth/token/blacklist/` | Invalida token refresh            |

### Gerenciamento de Usuários
| Método | Endpoint                     | Descrição                          |
|--------|------------------------------|------------------------------------|
| POST   | `/api/v1/auth/users/`         | Cria novo usuário                  |
| GET    | `/api/v1/auth/users/me/`      | Retorna dados do usuário logado    |
| PUT    | `/api/v1/auth/users/me/`      | Atualiza dados do usuário logado   |
| DELETE | `/api/v1/auth/users/me/`      | Remove conta do usuário logado     |

### Fluxos Especiais
| Método | Endpoint                                | Descrição                          |
|--------|-----------------------------------------|------------------------------------|
| POST   | `/api/v1/auth/users/activation/`        | Ativa conta com token recebido     |
| POST   | `/api/v1/auth/users/reset_password/`    | Solicita reset de senha            |
| POST   | `/api/v1/auth/users/set_password/`      | Define nova senha                  |

## Regras de Negócio Importantes

### Criação de Usuário
- Campos obrigatórios: `email`, `name`, `cpf`, `celular`, `password`
- Todos os usuários são criados como inativos (`is_active=False`)
- Patente padrão: Soldado
- Nível de acesso SAC padrão: Sem Acesso

### Fluxo Completo de Ativação de Conta
1. **Cadastro:** Usuário se cadastra (conta criada inativa)
2. **Confirmação por Email:** Recebe email de ativação com link/token
3. **Auto-Ativação:** Usuário clica no link e ativa sua conta
4. **Desativação Automática:** Um signal (`post_activation_set_inactive`) é acionado imediatamente após a ativação, definindo novamente `is_active=False`
5. **Aprovação Manual:** Administrador deve revisar e aprovar manualmente cada usuário através do painel admin
6. **Notificação de Aprovação:** Quando o administrador altera o status para `is_active=True`, um signal (`send_activation_email_on_manual_approval`) envia automaticamente um email de boas-vindas ao usuário, informando que sua conta foi ativada

### Email de Notificação de Ativação
- Quando um administrador ativa uma conta de usuário, o sistema envia automaticamente um email de notificação
- O email contém:
  - Confirmação de ativação da conta
  - Link para acessar o sistema
  - Informações de boas-vindas
- Templates personalizados são usados para apresentar uma comunicação profissional e adequada ao contexto


### Atualização de Dados
- Usuários comuns só podem alterar:
  - `celular`
  - `photo`
- Campos bloqueados para edição direta:
  - `email`
  - `name`
  - `cpf`
  - `patent`
  - Qualquer campo de permissão/acesso

### Hierarquia e Permissões
- **Superusuários**: Matrícula começa com "ADMIN-", patente Coronel, acesso FOCAL
- **Acessos SAC**:
  - NO_ACCESS: Sem acesso ao módulo
  - BASIC: Acesso básico
  - ANALISTA: Permissões intermediárias
  - FOCAL: Máximo nível de acesso

## Modelo de Dados do Usuário
```python
{
    "id": "UUID",
    "email": "string",
    "name": "string (uppercase)",
    "cpf": "string (11 dígitos)",
    "celular": "string (11 dígitos)",
    "photo": "URL ou null",
    "patent": "SOLDADO|CABO|...|CORONEL",
    "is_active": "boolean",
    "sac_access_level": "NO_ACCESS|BASIC|ANALISTA|FOCAL",
    "is_cpi": "boolean",
    "is_operacoes": "boolean"
}
```

## Boas Práticas de Uso
1. Sempre normalize dados antes de enviar:
   - Nomes em maiúsculas
   - CPF/celular apenas dígitos
2. Para operações sensíveis (reset de senha), use os endpoints dedicados
3. Administradores devem usar o painel Django para ativar contas e definir permissões
4. Teste sempre com usuários não-admin primeiro para validar restrições
