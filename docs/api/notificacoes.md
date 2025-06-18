
# Sistema de Notificações na Plataforma de Cautelas

Este documento explica o funcionamento e entendimento do sistema de notificações  como são geradas e tratadas durante o fluxo de cautelas.

## Visão Geral

O sistema de notificações foi projetado para manter os usuários informados sobre eventos relacionados às cautelas, como criação, aceite e devolução. A arquitetura segue o padrão Observer, onde eventos no sistema disparam a criação de notificações.

## Componentes Principais

1. **NotificationHub**: Atua como um hub central que responde a eventos do sistema e delega o tratamento para handlers específicos.

2. **NotificacaoService**: Serviço que centraliza a criação e manipulação de notificações.

3. **Modelo Notificacao**: Armazena as notificações com atributos como usuário, título, mensagem, tipo, status de leitura, etc.

## Comportamento das Notificações

As notificações foram configuradas para seguir um comportamento específico:

### 1. Nova Cautela Pendente
- **Quando**: Criada quando uma nova cautela é registrada para um policial
- **Comportamento**: Automaticamente marcada como lida quando o policial confirma o aceite
- **Data de Leitura**: Recebe exatamente a mesma data/hora do aceite

### 2. Item Devolvido
- **Quando**: Criada quando um item específico de cautela é devolvido
- **Comportamento**: Automaticamente marcada como lida no momento da devolução
- **Data de Leitura**: Recebe exatamente a mesma data/hora da devolução do item

### 3. Cautela Devolvida
- **Quando**: Criada quando todos os itens de uma cautela são devolvidos
- **Comportamento**: Automaticamente marcada como lida no momento da devolução completa
- **Data de Leitura**: Recebe exatamente a mesma data/hora da devolução completa

## Fluxo de Dados

1. Um evento ocorre no sistema (ex: aceite de cautela)
2. O serviço responsável emite um evento para o NotificationHub
3. O NotificationHub direciona para o handler apropriado
4. O handler cria a notificação e atualiza o status de notificações relacionadas quando necessário

## Considerações Importantes

- As notificações são meramente informativas e não requerem ação do policial
- O sistema marca automaticamente como lidas as notificações que representam ações já executadas pelo usuário
- A data de leitura sempre corresponde à data da ação que gerou a marcação como lida
