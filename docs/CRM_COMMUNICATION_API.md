# CRM Communication API

API para agregação de dados de comunicação (emails e eventos) por entidade de CRM.

## Visão Geral

Esta API fornece endpoints dedicados para visualizar emails e eventos de calendário associados a entidades do CRM (Company, Lead, Deal). Ela atua como uma camada de agregação sobre as APIs existentes de Gmail e Calendar, organizando os dados por contexto de negócio.

## Endpoints

### 1. GET /api/crm/{entity_type}/{entity_id}/emails

Retorna emails associados a uma entidade do CRM.

#### Parâmetros de Path

- `entity_type` (obrigatório): Tipo da entidade CRM
  - Valores aceitos: `company`, `lead`, `deal`
- `entity_id` (obrigatório): UUID da entidade

#### Parâmetros de Query

- `limit` (opcional): Número máximo de resultados (1-100, padrão: 50)
- `offset` (opcional): Número de resultados a pular para paginação (padrão: 0)
- `time_min` (opcional): Filtrar emails após esta data (formato: YYYY-MM-DD)
- `time_max` (opcional): Filtrar emails antes desta data (formato: YYYY-MM-DD)

#### Exemplo de Request

```http
GET /api/crm/company/comp-123/emails?limit=20&offset=0
```

#### Exemplo de Response

```json
{
  "emails": [
    {
      "id": "18b2f3a8d4c5e1f2",
      "thread_id": "18b2f3a8d4c5e1f2",
      "subject": "Q4 Sales Discussion",
      "from_email": "client@company.com",
      "to_email": "sales@ourcompany.com",
      "cc_email": "manager@ourcompany.com",
      "snippet": "Following up on our previous conversation about Q4 targets...",
      "internal_date": "2024-01-15T14:30:00Z",
      "has_attachments": true,
      "matched_contacts": ["client@company.com"]
    }
  ],
  "total": 25,
  "limit": 20,
  "offset": 0
}
```

#### Campos da Response

- `emails`: Lista de objetos `EmailSummaryForCRM`
  - `id`: ID da mensagem no Gmail
  - `thread_id`: ID da thread (conversa)
  - `subject`: Assunto do email
  - `from_email`: Endereço do remetente
  - `to_email`: Endereços dos destinatários
  - `cc_email`: Endereços em cópia (CC)
  - `snippet`: Prévia do conteúdo
  - `internal_date`: Data/hora do email
  - `has_attachments`: Indica se há anexos
  - `matched_contacts`: Lista de emails de contatos da entidade que aparecem neste email
- `total`: Número total de emails encontrados
- `limit`: Limite de resultados aplicado
- `offset`: Deslocamento aplicado

### 2. GET /api/crm/{entity_type}/{entity_id}/events

Retorna eventos de calendário associados a uma entidade do CRM.

#### Parâmetros de Path

- `entity_type` (obrigatório): Tipo da entidade CRM
  - Valores aceitos: `company`, `lead`, `deal`
- `entity_id` (obrigatório): UUID da entidade

#### Parâmetros de Query

- `limit` (opcional): Número máximo de resultados (1-100, padrão: 50)
- `offset` (opcional): Número de resultados a pular para paginação (padrão: 0)
- `time_min` (opcional): Filtrar eventos iniciando após este datetime (formato ISO)
- `time_max` (opcional): Filtrar eventos terminando antes deste datetime (formato ISO)
- `status` (opcional): Filtrar por status do evento
  - Valores aceitos: `confirmed`, `tentative`, `cancelled`

#### Exemplo de Request

```http
GET /api/crm/lead/lead-001/events?limit=10&offset=0&status=confirmed
```

#### Exemplo de Response

```json
{
  "events": [
    {
      "id": 42,
      "google_event_id": "evt_abc123xyz",
      "summary": "Client Meeting - Q4 Review",
      "description": "Quarterly review meeting with client",
      "start_time": "2024-01-15T14:00:00+00:00",
      "end_time": "2024-01-15T15:00:00+00:00",
      "meet_link": "https://meet.google.com/abc-defg-hij",
      "html_link": "https://calendar.google.com/event?eid=abc123",
      "status": "confirmed",
      "organizer_email": "sales@ourcompany.com",
      "matched_contacts": ["client@company.com"]
    }
  ],
  "total": 12,
  "limit": 10,
  "offset": 0
}
```

#### Campos da Response

- `events`: Lista de objetos `EventSummaryForCRM`
  - `id`: ID interno do evento no banco de dados
  - `google_event_id`: ID do evento no Google Calendar
  - `summary`: Título do evento
  - `description`: Descrição do evento
  - `start_time`: Data/hora de início
  - `end_time`: Data/hora de término
  - `meet_link`: Link do Google Meet (se disponível)
  - `html_link`: Link para visualizar no Google Calendar
  - `status`: Status do evento (confirmed, tentative, cancelled)
  - `organizer_email`: Email do organizador
  - `matched_contacts`: Lista de emails de contatos da entidade que são participantes
- `total`: Número total de eventos encontrados
- `limit`: Limite de resultados aplicado
- `offset`: Deslocamento aplicado

## Estratégia de Associação

A API utiliza uma estratégia baseada em emails de contato para associar comunicações às entidades do CRM.

### Como Funciona

1. **Extração de Emails de Contato**
   - Para cada entidade (Company/Lead/Deal), o sistema extrai todos os emails de contato relevantes
   - Fontes de emails:
     - Campo `email` direto da entidade (se existir)
     - Tabela `contacts` relacionada à entidade (se existir)
     - Emails de entidades relacionadas (ex: Lead → Company qualificada)

2. **Busca de Emails**
   - Constrói uma query do Gmail para encontrar mensagens contendo os emails de contato
   - Busca em todos os campos: `from`, `to`, `cc`, `bcc`
   - Retorna apenas emails onde pelo menos um contato aparece

3. **Busca de Eventos**
   - Consulta a tabela local `calendar_events` (espelho do Google Calendar)
   - Filtra eventos onde os emails de contato aparecem na lista de participantes (`attendees`)
   - Retorna eventos ordenados por data de início (mais recentes primeiro)

### Exemplo de Associação

Para uma Company com ID `comp-123`:

1. Sistema busca emails associados:
   - Email direto da company: `contact@company.com`
   - Emails da tabela contacts: `ceo@company.com`, `cfo@company.com`

2. Para emails:
   - Busca no Gmail: `from:contact@company.com OR to:contact@company.com OR from:ceo@company.com OR to:ceo@company.com OR from:cfo@company.com OR to:cfo@company.com`
   - Retorna todos os emails que contenham qualquer um desses contatos

3. Para eventos:
   - Consulta `calendar_events` onde `attendees` (JSON) contém qualquer dos emails
   - Retorna eventos com os contatos como participantes

### Entidades Relacionadas

A estratégia considera relacionamentos entre entidades:

- **Lead**: Inclui emails da Company qualificada (se `qualified_company_id` estiver definido)
- **Deal**: Inclui emails da Company associada (se `company_id` estiver definido)
- **Company**: Apenas emails diretos e da tabela de contatos

## Paginação

Ambos os endpoints suportam paginação via parâmetros `limit` e `offset`:

- `limit`: Controla quantos resultados retornar (máximo 100)
- `offset`: Controla quantos resultados pular

Exemplo de paginação:
```
Página 1: ?limit=50&offset=0
Página 2: ?limit=50&offset=50
Página 3: ?limit=50&offset=100
```

O campo `total` na response indica o número total de resultados encontrados, permitindo calcular o número de páginas.

## Tratamento de Erros

### 400 Bad Request
Tipo de entidade inválido.
```json
{
  "detail": "Invalid entity_type. Must be one of: company, lead, deal"
}
```

### 404 Not Found
Entidade não encontrada no banco de dados.
```json
{
  "detail": "Company with id comp-999 not found"
}
```

### 500 Internal Server Error
Erro ao buscar dados do Gmail ou Calendar.
```json
{
  "detail": "Failed to retrieve emails: <error details>"
}
```

## Observações Importantes

1. **Sem Modificação das APIs Brutas**: Esta API não altera o contrato dos endpoints `/api/gmail/*` e `/api/calendar/*`. Ela funciona como uma camada de agregação adicional.

2. **Performance**: A busca de emails utiliza a API do Gmail, que pode ter latência dependendo do volume de dados. Para grandes volumes, considere usar os parâmetros de paginação e filtros de data.

3. **Cache de Eventos**: Os eventos vêm da tabela local `calendar_events`, que é sincronizada via webhooks. Eventos muito recentes podem levar alguns segundos para aparecer.

4. **Extensibilidade**: A estratégia de associação foi projetada para ser facilmente estendida:
   - Pode-se adicionar mais fontes de emails
   - Pode-se implementar lógica mais sofisticada de matching
   - Pode-se adicionar filtros adicionais

5. **Fallback Gracioso**: Se não houver emails de contato associados à entidade, a API retorna uma lista vazia (não um erro), facilitando a integração com o frontend.

## Casos de Uso

### 1. Visualização de Histórico de Comunicação
```http
GET /api/crm/company/comp-123/emails?limit=20
GET /api/crm/company/comp-123/events?limit=20
```
Exibe as comunicações mais recentes com uma empresa.

### 2. Busca Temporal
```http
GET /api/crm/lead/lead-001/emails?time_min=2024-01-01&time_max=2024-03-31
```
Encontra todas as comunicações em um período específico.

### 3. Pipeline de Vendas
```http
GET /api/crm/deal/deal-001/events?status=confirmed
```
Lista apenas reuniões confirmadas relacionadas a um deal.

### 4. Paginação de Grandes Volumes
```http
GET /api/crm/company/comp-123/emails?limit=50&offset=100
```
Navega por grandes volumes de comunicação.

## Integração com Frontend

O frontend pode usar estes endpoints para:

1. **Dashboard de Entidade**: Exibir seção de "Comunicações Recentes" na página de uma Company/Lead/Deal
2. **Timeline**: Construir uma timeline combinada de emails e eventos
3. **Busca Contextual**: Permitir busca de comunicações específicas dentro do contexto de uma entidade
4. **Análise de Engajamento**: Visualizar frequência e padrões de comunicação com clientes

### Exemplo de Implementação (React/TypeScript)

```typescript
async function fetchEntityCommunications(
  entityType: 'company' | 'lead' | 'deal',
  entityId: string,
  limit: number = 20,
  offset: number = 0
) {
  const [emails, events] = await Promise.all([
    fetch(`/api/crm/${entityType}/${entityId}/emails?limit=${limit}&offset=${offset}`),
    fetch(`/api/crm/${entityType}/${entityId}/events?limit=${limit}&offset=${offset}`)
  ]);
  
  return {
    emails: await emails.json(),
    events: await events.json()
  };
}
```

## Próximas Melhorias Sugeridas

1. **Cache**: Implementar cache para queries frequentes
2. **Busca Full-Text**: Adicionar busca por conteúdo de emails
3. **Filtros Avançados**: Permitir filtrar por remetente específico, assunto, etc.
4. **Agregações**: Adicionar endpoints para estatísticas (ex: número de emails por mês)
5. **Webhooks**: Notificar o frontend quando novos emails/eventos são associados
6. **Permissões**: Integrar com `PermissionService` para controle de acesso baseado em roles
