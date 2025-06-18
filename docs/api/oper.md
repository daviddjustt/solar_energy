# Módulo de Operações (oper)

Este módulo gerencia operações policiais, guarnições e seus membros no sistema solarAPI.

## Visão Geral

O módulo de operações permite criar e gerenciar operações policiais, organizadas em guarnições com comandantes e membros. Foi projetado para atender às necessidades específicas de controle e organização de operações da Polícia Militar.

## Modelos

### Operacao

Representa uma operação policial com período definido.

**Campos principais:**
- `name`: Nome da operação
- `description`: Descrição detalhada da operação
- `start_date`: Data de início
- `end_date`: Data de término
- `is_active`: Status de atividade da operação

**Regras de negócio:**
- Data de início não pode ser posterior à data de término
- Novas operações não podem começar no passado
- Operações podem ser ativadas/desativadas

### Guarnicao

Representa uma equipe/guarnição dentro de uma operação.

**Campos principais:**
- `name`: Nome da guarnição
- `operacao`: Operação à qual pertence
- `comandante`: Policial responsável pela guarnição
- `membros`: Policiais que compõem a guarnição

**Regras de negócio:**
- Cada guarnição pertence a uma única operação
- Só é possível modificar guarnições em operações ativas
- O comandante deve ser um policial militar ativo
- O comandante deve ser membro da guarnição

### GuarnicaoMembro

Associação entre policiais e guarnições.

**Campos principais:**
- `guarnicao`: Guarnição
- `user`: Usuário (policial militar)

**Regras de negócio:**
- Apenas policiais militares ativos podem ser membros
- Um policial pode participar de várias guarnições
- Não é possível adicionar membros em operações inativas

## API Endpoints

### Operações

| Método | Endpoint | Descrição | Permissão |
|--------|----------|-----------|-----------|
| GET | `/api/v1/oper/operacoes/` | Listar operações | Usuário autenticado |
| POST | `/api/v1/oper/operacoes/` | Criar operação | Admin |
| GET | `/api/v1/oper/operacoes/{id}/` | Detalhes da operação | Usuário autenticado |
| PUT/PATCH | `/api/v1/oper/operacoes/{id}/` | Atualizar operação | Admin |
| DELETE | `/api/v1/oper/operacoes/{id}/` | Excluir operação | Admin |
| POST | `/api/v1/oper/operacoes/{id}/ativar/` | Ativar operação | Admin |
| POST | `/api/v1/oper/operacoes/{id}/desativar/` | Desativar operação | Admin |

### Guarnições

| Método | Endpoint | Descrição | Permissão |
|--------|----------|-----------|-----------|
| GET | `/api/v1/oper/guarnicoes/` | Listar guarnições | Usuário autenticado |
| POST | `/api/v1/oper/guarnicoes/` | Criar guarnição | Admin |
| GET | `/api/v1/oper/guarnicoes/{id}/` | Detalhes da guarnição | Usuário autenticado |
| PUT/PATCH | `/api/v1/oper/guarnicoes/{id}/` | Atualizar guarnição | Admin |
| DELETE | `/api/v1/oper/guarnicoes/{id}/` | Excluir guarnição | Admin |
| POST | `/api/v1/oper/guarnicoes/{id}/adicionar_membro/` | Adicionar membro | Admin |
| POST | `/api/v1/oper/guarnicoes/{id}/remover_membro/` | Remover membro | Admin |

### Membros de Guarnição

| Método | Endpoint | Descrição | Permissão |
|--------|----------|-----------|-----------|
| GET | `/api/v1/oper/membros/` | Listar membros | Usuário autenticado |
| POST | `/api/v1/oper/membros/` | Criar associação | Admin |
| DELETE | `/api/v1/oper/membros/{id}/` | Remover associação | Admin |

## Exemplos de Uso

### Criar uma Operação

```json
POST /api/v1/oper/operacoes/
{
  "name": "OPERAÇÃO FRONTEIRA",
  "description": "Operação de fiscalização na fronteira oeste",
  "start_date": "2025-04-10",
  "end_date": "2025-05-10",
  "is_active": true
}
```

### Criar uma Guarnição com Membros

```json
POST /api/v1/oper/guarnicoes/
{
  "name": "EQUIPE ALFA",
  "operacao": "550e8400-e29b-41d4-a716-446655440000",
  "comandante": "7c0cd13a-e29b-41d4-a716-446655440001",
  "membros_ids": [
    "7c0cd13a-e29b-41d4-a716-446655440001",
    "550e8400-e29b-41d4-a716-446655440002",
    "550e8400-e29b-41d4-a716-446655440003"
  ]
}
```

### Adicionar Membro a uma Guarnição

```json
POST /api/v1/oper/guarnicoes/{id}/adicionar_membro/
{
  "user": "550e8400-e29b-41d4-a716-446655440004"
}
```

## Filtros Disponíveis

- Operações: `is_active`
- Guarnições: `operacao`, `comandante`
- Membros: `guarnicao`, `user`
