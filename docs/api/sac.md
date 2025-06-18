# Sistema de Gestão de Relatórios de Inteligência

## Visão Geral

Sistema de gerenciamento de relatórios de inteligência com foco em segurança, auditoria e controle de acesso granular.

## Características Principais

- Controle de acesso multinível
- Classificação de sigilo de relatórios
- Auditoria completa de acessos
- Permissões baseadas em patente
- Rastreamento detalhado de visualizações

## Níveis de Classificação

1. **Público**: Acessível a todos
2. **Restrito**: Acesso limitado
3. **Confidencial**: Acesso controlado
4. **Secreto**: Acesso altamente restrito
5. **Ultra Secreto**: Acesso extremamente limitado

## Requisitos

- Django 4.2+
- Django REST Framework
- django-filter
- django-simple-history

## Instalação

### 1. Adicione ao INSTALLED_APPS

```python
INSTALLED_APPS = [
    ...
    'relatorios_inteligencia',
    'rest_framework',
    'django_filters',
    'simple_history',
]
```

### 2. Realize as migrações

```bash
python manage.py makemigrations relatorios_inteligencia
python manage.py migrate
```

## Segurança

### Controle de Acesso

- Superusuários: Acesso total
- Administradores: Acesso amplo
- Oficiais superiores: Acesso expandido
- Usuários regulares: Acesso limitado

### Auditoria

- Registro de todos os acessos
- Rastreamento de IP
- Log de visualizações
- Metadados detalhados

## Endpoints Principais

### Relatórios

- `GET /api/relatorios/`: Listar relatórios
- `POST /api/relatorios/`: Criar relatório
- `GET /api/relatorios/{id}/`: Detalhe do relatório
- `PUT /api/relatorios/{id}/`: Atualizar relatório

### Logs de Acesso

- `GET /api/logs-acesso/`: Listar logs
- `GET /api/logs-acesso/resumo-acessos/`: Resumo estatístico

## Boas Práticas

- Sempre valide e sanitize entradas
- Utilize autenticação de dois fatores
- Revise regularmente logs de acesso
- Mantenha segredo de credenciais

## Considerações de Segurança

- Relatórios confidenciais têm acesso extremamente restrito
- Cada acesso é minuciosamente registrado
- Permissões são hierárquicas e baseadas em patente

## Contribuição

1. Faça fork do repositório
2. Crie branch de feature
3. Commit suas alterações
4. Abra um Pull Request

## Licença

[Especificar licença]

```

### Configurações Adicionais
```
