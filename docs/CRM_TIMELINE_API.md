# CRM Timeline API

API para visualização unificada de comunicações (emails e eventos) por entidade de CRM em uma timeline ordenada cronologicamente.

## Visão Geral

O endpoint de Timeline fornece uma visão unificada e cronológica de todas as comunicações (emails e eventos de calendário) associadas a uma entidade do CRM (Company, Lead, Deal). Ele agrega dados dos endpoints `/emails` e `/events` existentes, mesclando-os em uma única lista ordenada por data.

## Endpoint

### GET /api/crm/{entity_type}/{entity_id}/timeline

Retorna uma timeline unificada de emails e eventos associados a uma entidade do CRM.

#### Parâmetros de Path

- `entity_type` (obrigatório): Tipo da entidade CRM
  - Valores aceitos: `company`, `lead`, `deal`
- `entity_id` (obrigatório): UUID da entidade

#### Parâmetros de Query

- `limit` (opcional): Número máximo de resultados (1-100, padrão: 50)
- `offset` (opcional): Número de resultados a pular para paginação (padrão: 0)
- `time_min` (opcional): Filtrar items após esta data (formato flexível)
- `time_max` (opcional): Filtrar items antes desta data (formato flexível)

#### Exemplo de Request

```http
GET /api/crm/company/comp-123/timeline?limit=20&offset=0
```

#### Exemplo de Response

```json
{
  "items": [
    {
      "id": "event_xyz789",
      "source": "calendar",
      "type": "event",
      "subject": "Client Meeting - Q4 Review",
      "snippet": "Quarterly review meeting with client",
      "datetime": "2024-01-16T14:00:00+00:00",
      "participants": ["client@company.com", "sales@ourcompany.com"],
      "matched_contacts": ["client@company.com"],
      "entity_type": "company",
      "entity_id": "comp-123"
    },
    {
      "id": "18b2f3a8d4c5e1f2",
      "source": "gmail",
      "type": "email",
      "subject": "Q4 Sales Discussion",
      "snippet": "Following up on our previous conversation about Q4 targets...",
      "datetime": "2024-01-15T14:30:00Z",
      "participants": ["client@company.com", "sales@ourcompany.com", "manager@ourcompany.com"],
      "matched_contacts": ["client@company.com"],
      "entity_type": "company",
      "entity_id": "comp-123"
    },
    {
      "id": "event_abc123",
      "source": "calendar",
      "type": "event",
      "subject": "Initial Discovery Call",
      "snippet": null,
      "datetime": "2024-01-10T10:00:00+00:00",
      "participants": ["client@company.com", "ceo@company.com"],
      "matched_contacts": ["client@company.com", "ceo@company.com"],
      "entity_type": "company",
      "entity_id": "comp-123"
    }
  ],
  "total": 37,
  "limit": 20,
  "offset": 0
}
```

#### Campos da Response

- `items`: Lista de objetos `TimelineItem` (emails e eventos mesclados)
  - `id`: ID único (Gmail message ID ou Google Calendar event ID)
  - `source`: Origem do item (`gmail` ou `calendar`)
  - `type`: Tipo de comunicação (`email` ou `event`)
  - `subject`: Assunto do email ou título do evento
  - `snippet`: Prévia do email ou descrição do evento (pode ser `null`)
  - `datetime`: Data/hora da comunicação (timestamp do email ou início do evento)
  - `participants`: Lista de endereços de email envolvidos
  - `matched_contacts`: Emails de contatos da entidade que aparecem neste item
  - `entity_type`: Tipo da entidade CRM
  - `entity_id`: ID da entidade CRM
- `total`: Número total de items na timeline (após filtros, antes da paginação)
- `limit`: Limite de resultados aplicado
- `offset`: Deslocamento aplicado

## Características Principais

### 1. Agregação de Múltiplas Fontes

A timeline combina dados de duas fontes:
- **Gmail**: Emails onde os contatos da entidade aparecem como remetente ou destinatário
- **Calendar**: Eventos onde os contatos da entidade aparecem como participantes

### 2. Ordenação Cronológica

Todos os items são ordenados por `datetime` em ordem **decrescente** (mais recentes primeiro):
- Para emails: usa `internal_date`
- Para eventos: usa `start_time`

### 3. Paginação Pós-Merge

A paginação é aplicada **depois** de:
1. Buscar emails do Gmail
2. Buscar eventos do banco de dados
3. Mesclar ambas as listas
4. Ordenar por datetime

Isso garante que a paginação reflita a ordem cronológica real, não a ordem de cada fonte individualmente.

### 4. Reutilização de Lógica

O endpoint reutiliza a mesma estratégia de associação dos endpoints `/emails` e `/events`:
- Mesma lógica de extração de contatos
- Mesmas regras de matching
- Mesmas validações de entidade

## Autorização e Permissões

### Permissão Base: `crm_read_communications`

O acesso ao endpoint requer a permissão `crm_read_communications`:

**Roles com acesso:**
- `admin`
- `superadmin`
- `manager`
- `analyst`
- `new_business`

**Roles sem acesso (403):**
- `client`
- `customer`
- Roles desconhecidas (princípio de menor privilégio)

### Respeito a Permissões de Detalhes

O endpoint respeita as permissões granulares de Gmail e Calendar:

#### Gmail Permissions (`gmail_read_body`)

- **Roles com acesso ao corpo**: `admin`, `manager`, `analyst`, `new_business`
  - Snippet sempre incluído (não é corpo completo)
- **Roles sem acesso**: `client`, `customer`
  - Snippet sempre incluído (snippet não é considerado corpo completo)

#### Calendar Permissions (`calendar_read_details`)

- **Roles com acesso a detalhes**: `admin`, `manager`, `analyst`, `new_business`
  - `snippet` contém a descrição do evento (se disponível)
- **Roles sem acesso**: `client`, `customer`
  - `snippet` é `null` para eventos

### Exemplo de Comportamento por Role

```python
# Admin - vê tudo
GET /api/crm/company/comp-123/timeline
Headers: x-user-role: admin
# Response: snippet inclui descrições de eventos

# Client - acesso negado
GET /api/crm/company/comp-123/timeline
Headers: x-user-role: client
# Response: 403 Forbidden
```

## Logging Estruturado

O endpoint utiliza logging estruturado para auditoria e debugging:

```python
{
  "action": "get_entity_timeline",
  "status": "success",
  "entity_type": "company",
  "entity_id": "comp-123",
  "role": "admin",
  "total_items": 37,
  "contact_count": 3,
  "returned_count": 20,
  "gmail_items": 25,
  "calendar_items": 12
}
```

### Eventos Logados

1. **Authorization**
   - `status: authorized` - Usuário autorizado com sucesso
   - `status: access_denied` - Usuário sem permissão

2. **No Contacts**
   - `status: no_contacts` - Entidade não tem contatos associados

3. **Success**
   - `status: success` - Timeline retornada com sucesso
   - Inclui contagens de items por fonte

4. **Errors**
   - Erros ao buscar emails ou eventos (não interrompem o endpoint)

## Tratamento de Erros

### 400 Bad Request
Tipo de entidade inválido (validado pelo FastAPI/Pydantic).

### 403 Forbidden
Usuário não tem permissão `crm_read_communications`.

```json
{
  "detail": "Access denied: Insufficient permissions to access CRM communications"
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
Erro ao buscar dados. O endpoint é resiliente - se emails falharem, ainda retorna eventos, e vice-versa.

## Casos de Uso

### 1. Visualização de Histórico Completo

```http
GET /api/crm/company/comp-123/timeline?limit=50
```
Exibe as 50 comunicações mais recentes (emails + eventos) com uma empresa.

### 2. Auditoria de Engajamento

```http
GET /api/crm/lead/lead-001/timeline?time_min=2024-01-01&time_max=2024-03-31
```
Lista todas as interações com um lead em Q1 2024.

### 3. Paginação de Grandes Volumes

```http
GET /api/crm/deal/deal-001/timeline?limit=20&offset=0
# Próxima página
GET /api/crm/deal/deal-001/timeline?limit=20&offset=20
```
Navega por grandes volumes de comunicação de forma eficiente.

### 4. Dashboard de Atividades

```http
GET /api/crm/company/comp-123/timeline?limit=10
```
Exibe as 10 interações mais recentes para um widget de "Atividades Recentes".

## Integração com Frontend

### Exemplo React/TypeScript

```typescript
interface TimelineItem {
  id: string;
  source: 'gmail' | 'calendar';
  type: 'email' | 'event';
  subject: string;
  snippet?: string;
  datetime: string;
  participants: string[];
  matched_contacts: string[];
  entity_type: string;
  entity_id: string;
}

interface TimelineResponse {
  items: TimelineItem[];
  total: number;
  limit: number;
  offset: number;
}

async function fetchTimeline(
  entityType: 'company' | 'lead' | 'deal',
  entityId: string,
  limit: number = 20,
  offset: number = 0
): Promise<TimelineResponse> {
  const response = await fetch(
    `/api/crm/${entityType}/${entityId}/timeline?limit=${limit}&offset=${offset}`,
    {
      headers: {
        'x-user-role': getCurrentUserRole()
      }
    }
  );
  
  if (!response.ok) {
    throw new Error(`Failed to fetch timeline: ${response.statusText}`);
  }
  
  return response.json();
}

// Componente de Timeline
function CRMTimeline({ entityType, entityId }: Props) {
  const [timeline, setTimeline] = useState<TimelineResponse | null>(null);
  
  useEffect(() => {
    fetchTimeline(entityType, entityId, 20, 0)
      .then(setTimeline)
      .catch(console.error);
  }, [entityType, entityId]);
  
  return (
    <div className="timeline">
      {timeline?.items.map(item => (
        <TimelineItemCard key={item.id} item={item} />
      ))}
    </div>
  );
}
```

## Comparação com Endpoints Individuais

| Característica | `/emails` | `/events` | `/timeline` |
|----------------|-----------|-----------|-------------|
| **Fonte de dados** | Apenas Gmail | Apenas Calendar | Gmail + Calendar |
| **Ordenação** | Por data do email | Por data do evento | Por datetime unificado |
| **Paginação** | Por fonte | Por fonte | Pós-merge unificado |
| **Tipo de retorno** | `EmailSummaryForCRM` | `EventSummaryForCRM` | `TimelineItem` |
| **Use case** | Análise de emails | Análise de eventos | Visão cronológica completa |

## Diferenças em Relação aos Endpoints Base

### Estrutura de Dados Simplificada

O `TimelineItem` é uma versão simplificada e normalizada que:
- Não inclui todos os campos de `EmailSummaryForCRM` ou `EventSummaryForCRM`
- Usa campos comuns (`subject`, `datetime`, `participants`)
- Adiciona metadados de contexto (`source`, `type`, `entity_type`, `entity_id`)

### Por que um schema separado?

1. **Normalização**: Emails e eventos têm estruturas diferentes - o schema unificado abstrai essas diferenças
2. **Performance**: Menos campos = menos dados transferidos
3. **Simplicidade**: Frontend não precisa lidar com duas estruturas diferentes
4. **Extensibilidade**: Fácil adicionar novas fontes (tasks, notes, etc.) no futuro

## Performance e Considerações

### Volumes Grandes

Para entidades com muitos emails/eventos:
- Use `limit` menor (10-20) para carregamento rápido
- Implemente scroll infinito no frontend
- Considere cache no backend (próxima melhoria)

### Latência

A latência depende de:
- **Gmail API**: Pode ser lenta para grandes volumes
- **Database query**: Geralmente rápida (eventos estão em cache local)
- **Merge e sort**: Operação em memória, rápida

**Recomendação**: Use filtros de data para reduzir o volume de dados processados.

## Próximas Melhorias

1. **Cache**: Implementar cache de timeline para queries frequentes
2. **Streaming**: Retornar items conforme disponíveis (server-sent events)
3. **Filtros Avançados**: 
   - Por tipo (apenas emails ou apenas eventos)
   - Por participante específico
   - Por palavra-chave no subject
4. **Agregações**: 
   - Contagem de comunicações por período
   - Gráficos de engajamento
5. **Webhooks**: Notificar frontend de novos items
6. **Cursor-based pagination**: Melhor performance para grandes datasets

## Exemplos de Integração

### Dashboard de Vendas

```typescript
// Mostrar últimas 5 interações com cada deal
const deals = await fetchActiveDeals();
const timelinesPromises = deals.map(deal => 
  fetchTimeline('deal', deal.id, 5, 0)
);
const timelines = await Promise.all(timelinesPromises);
```

### Relatório de Atividades

```typescript
// Todas as comunicações do último mês
const oneMonthAgo = new Date();
oneMonthAgo.setMonth(oneMonthAgo.getMonth() - 1);

const timeline = await fetchTimeline(
  'company',
  'comp-123',
  100,
  0,
  {
    time_min: oneMonthAgo.toISOString().split('T')[0]
  }
);

// Análise
const emailCount = timeline.items.filter(i => i.type === 'email').length;
const eventCount = timeline.items.filter(i => i.type === 'event').length;
```

### Widget de Últimas Atividades

```typescript
// Componente para sidebar
function RecentActivity({ entityType, entityId }: Props) {
  const { data } = useQuery(
    ['timeline', entityType, entityId],
    () => fetchTimeline(entityType, entityId, 5, 0),
    { staleTime: 60000 } // Cache por 1 minuto
  );
  
  return (
    <Card title="Recent Activity">
      {data?.items.map(item => (
        <ActivityItem 
          key={item.id}
          icon={item.type === 'email' ? <EmailIcon /> : <CalendarIcon />}
          title={item.subject}
          datetime={item.datetime}
        />
      ))}
    </Card>
  );
}
```

## Observações Importantes

1. **Não Modifica Endpoints Existentes**: `/emails` e `/events` continuam funcionando normalmente
2. **Somente Leitura**: Timeline não permite criação ou modificação
3. **Fallback Gracioso**: Retorna lista vazia se não houver contatos (não erro 404)
4. **Resiliência**: Falhas ao buscar emails ou eventos não impedem o retorno dos outros
5. **Backward Compatibility**: Header `x-user-role` opcional (default: acesso completo)

## Referências

- [CRM Communication API](./CRM_COMMUNICATION_API.md) - Documentação dos endpoints base
- [Permission Service](../services/permission_service.py) - Implementação de permissões
- Repositório: `routers/crm_communication.py` - Implementação do endpoint
- Testes: `tests/test_crm_timeline.py` - Suite de testes completa
