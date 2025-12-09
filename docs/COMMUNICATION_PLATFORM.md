# Plataforma de Comunicação

**Visão agregadora dos sistemas de comunicação integrados: Calendar, Gmail e CRM**

---

## 1. Visão Geral

A Plataforma de Comunicação consolida múltiplas fontes de dados de comunicação em uma visão única e integrada, proporcionando uma perspectiva 360° de todas as interações com Companies, Leads e Deals.

### Integração com Google Calendar/Meet

A plataforma integra-se diretamente com o Google Calendar, permitindo:

- **Criação de eventos** com geração automática de links do Google Meet
- **Sincronização bidirecional** via webhooks do Google Calendar
- **Gestão completa de participantes (attendees)** com status de resposta
- **Espelho local (mirror)** dos eventos para consultas rápidas sem latência da API do Google
- **Atualizações em tempo real** de mudanças feitas diretamente no Google Calendar

Os eventos são armazenados localmente na tabela `calendar_events` e mantidos sincronizados automaticamente através de webhooks do Google, garantindo que qualquer mudança feita no Google Calendar seja refletida imediatamente na plataforma.

### Integração com Gmail

A plataforma fornece acesso de leitura ao Gmail, possibilitando:

- **Leitura de emails** com suporte a busca avançada usando a sintaxe nativa do Gmail
- **Gestão de threads (conversas)** para visualizar contexto completo de comunicações
- **Gerenciamento de labels** para organização e filtragem
- **Acesso a metadados de anexos** (lista de anexos com nome, tipo MIME e tamanho)
- **Filtros avançados** por data, remetente, destinatário e palavras-chave

A integração é somente leitura (read-only), utilizando o scope `gmail.readonly` para garantir que nenhuma modificação acidental seja feita aos emails.

### Camada CRM

A camada CRM é a peça central que conecta as comunicações às entidades de negócio. Ela fornece três grupos principais de endpoints:

#### 1. Emails por Entidade
**Endpoint:** `/api/crm/{entity_type}/{entity_id}/emails`

Retorna emails associados a uma entidade (Company/Lead/Deal) através de matching de emails de contato. O sistema:
- Extrai automaticamente todos os emails de contato da entidade e entidades relacionadas
- Busca no Gmail por mensagens que contenham qualquer um desses emails
- Retorna lista paginada com snippets e metadados

#### 2. Eventos por Entidade
**Endpoint:** `/api/crm/{entity_type}/{entity_id}/events`

Retorna eventos de calendário associados a uma entidade. O sistema:
- Busca na tabela local `calendar_events` por eventos com participantes que correspondam aos contatos
- Filtra por status (confirmed, tentative, cancelled)
- Suporta filtros temporais para análise de períodos específicos

#### 3. Timeline Unificada
**Endpoint:** `/api/crm/{entity_type}/{entity_id}/timeline`

Combina emails e eventos em uma única timeline cronológica:
- Mescla dados de ambas as fontes (Gmail + Calendar)
- Ordena por datetime (mais recentes primeiro)
- Normaliza estrutura de dados para facilitar renderização no frontend
- Aplica paginação **pós-merge** para resultados consistentes

### Caso de Uso: Visão 360° de Entidades

A principal aplicação da Plataforma de Comunicação é fornecer uma **visão completa e contextualizada** de todas as interações com clientes:

#### Para Companies
- Histórico completo de emails trocados com todos os contatos da empresa
- Todas as reuniões realizadas ou agendadas com participantes da empresa
- Timeline unificada mostrando fluxo de comunicação ao longo do tempo

#### Para Leads
- Comunicações durante o processo de qualificação
- Reuniões de discovery e apresentação
- Inclui automaticamente emails da Company qualificada (se `qualified_company_id` estiver definido)

#### Para Deals
- Histórico de negociação via email
- Reuniões de propostas e follow-ups
- Inclui automaticamente comunicações da Company associada

Esta visão 360° permite que times de vendas, CS (Customer Success) e liderança tenham contexto completo antes de qualquer interação, melhorando a qualidade do atendimento e eficácia das conversas.

---

## 2. Arquitetura Lógica

### Fluxo de Dados

A arquitetura segue um fluxo claro e desacoplado:

```
┌─────────────────┐
│  Google APIs    │
│                 │
│  • Calendar API │
│  • Gmail API    │
└────────┬────────┘
         │
         │ (1) Service Account Auth
         │     (read-only scopes)
         ▼
┌─────────────────────────┐
│   Backend Services      │
│                         │
│  • GmailService         │
│    └─ list/search/get   │
│                         │
│  • CalendarService      │
│    └─ CRUD + webhooks   │
│                         │
│  • WebhookService       │
│    └─ sync Calendar     │
└───────────┬─────────────┘
            │
            │ (2) Data aggregation
            │     + business logic
            ▼
┌──────────────────────────┐
│   Camada CRM             │
│                          │
│  • CRMContactService     │
│    └─ extract contacts   │
│                          │
│  • CRM Routers           │
│    └─ /emails            │
│    └─ /events            │
│    └─ /timeline          │
│                          │
│  • PermissionService     │
│    └─ role-based access  │
└───────────┬──────────────┘
            │
            │ (3) REST API
            │     (JSON responses)
            ▼
┌──────────────────────────┐
│   Frontend               │
│                          │
│  • Dashboard widgets     │
│  • Timeline components   │
│  • Entity detail pages   │
│  • Search & filters      │
└──────────────────────────┘
```

### Descrição dos Componentes

#### (1) Google APIs → Backend Services

**Autenticação:**
- Utiliza Google Service Account com credenciais JSON
- Scopes necessários:
  - `https://www.googleapis.com/auth/calendar` (Calendar)
  - `https://www.googleapis.com/auth/gmail.readonly` (Gmail)

**Gmail Service:**
- Encapsula a API do Gmail para operações de leitura
- Suporta busca avançada com query syntax do Gmail
- Retorna dados formatados em schemas padronizados (Pydantic)

**Calendar Service:**
- Gerencia eventos no Google Calendar
- Cria eventos com opção de gerar Meet links
- Sincroniza mudanças via webhooks do Google (push notifications)

**Webhook Service:**
- Recebe notificações de mudanças no Google Calendar
- Atualiza tabela local `calendar_events` automaticamente
- Mantém espelho sincronizado para queries rápidas

#### (2) Camada CRM → Agregação de Dados

**CRM Contact Service:**
- Extrai emails de contato das entidades (Company/Lead/Deal)
- Considera entidades relacionadas (ex: Lead → Company)
- Normaliza e deduplica lista de emails

**CRM Routers:**
- Validam entity_type e entity_id
- Aplicam filtros temporais e paginação
- Chamam Gmail/Calendar services com queries específicas
- Mesclam resultados no caso da timeline

**Permission Service:**
- Controla acesso baseado em roles (admin, manager, analyst, etc.)
- Filtra campos sensíveis conforme permissões
- Aplica princípio de menor privilégio

#### (3) Frontend → Apresentação

O frontend consome os endpoints REST e:
- Renderiza widgets de "Atividades Recentes"
- Monta timelines visuais com ícones de email/evento
- Implementa paginação infinita ou tradicional
- Aplica filtros de data e tipo de comunicação

### Pontos Importantes

- **Resiliência:** Se Gmail falhar, endpoints de CRM ainda retornam eventos do Calendar (e vice-versa)
- **Performance:** Calendar events vêm do banco local (rápido), emails vêm da API do Gmail (pode ter latência)
- **Consistência:** Webhooks mantêm dados do Calendar sincronizados em tempo real
- **Segurança:** Permissões aplicadas em todas as camadas (service + router)

---

## 3. Endpoints Principais

### Calendar API

Gerenciamento completo de eventos e integração com Google Meet.

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/api/calendar/events` | GET | Lista eventos com filtros (data, status, paginação) |
| `/api/calendar/events` | POST | Cria novo evento (com opção de gerar Meet link) |
| `/api/calendar/events/{id}` | GET | Obtém detalhes completos de um evento |
| `/api/calendar/events/{id}` | PATCH | Atualiza evento (título, horário, participantes) |
| `/api/calendar/events/{id}` | DELETE | Cancela evento (soft delete, status='cancelled') |
| `/health/calendar` | GET | Verifica saúde da integração Calendar + webhooks |

**Documentação completa:** [CALENDAR_API.md](../CALENDAR_API.md)

### Gmail API

Acesso de leitura a emails, threads e labels.

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/api/gmail/messages` | GET | Lista emails com busca avançada e filtros |
| `/api/gmail/messages/{id}` | GET | Obtém detalhes completos de um email (incluindo corpo) |
| `/api/gmail/threads` | GET | Lista threads (conversas) |
| `/api/gmail/threads/{id}` | GET | Obtém thread completa com todas as mensagens |
| `/api/gmail/labels` | GET | Lista todas as labels do Gmail |
| `/health/gmail` | GET | Verifica saúde da integração Gmail |

**Documentação completa:** [GMAIL_API.md](../GMAIL_API.md)

### CRM Communication API

Agregação de emails e eventos por entidade de CRM.

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/api/crm/{entity_type}/{entity_id}/emails` | GET | Lista emails associados à entidade |
| `/api/crm/{entity_type}/{entity_id}/events` | GET | Lista eventos associados à entidade |

**Valores de `entity_type`:** `company`, `lead`, `deal`

**Documentação completa:** [CRM_COMMUNICATION_API.md](./CRM_COMMUNICATION_API.md)

### CRM Timeline API

Timeline unificada de comunicações por entidade.

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/api/crm/{entity_type}/{entity_id}/timeline` | GET | Timeline unificada (emails + eventos) ordenada cronologicamente |

**Documentação completa:** [CRM_TIMELINE_API.md](./CRM_TIMELINE_API.md)

### Health & Monitoring

Endpoints para monitoramento e observabilidade.

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/health` | GET | Status agregado de todos os serviços |
| `/health/calendar` | GET | Status específico do Calendar (webhooks, sync) |
| `/health/gmail` | GET | Status específico do Gmail (auth, API) |

**Documentação completa:** [HEALTH_API.md](./HEALTH_API.md)

---

## 4. Permissões e Privacidade

A Plataforma de Comunicação implementa um sistema robusto de controle de acesso baseado em **roles** (papéis de usuário). O role é informado através do header HTTP `x-user-role`.

### Matriz de Roles e Permissões

| Role | Gmail (body) | Gmail (metadata) | Calendar (details) | CRM Communications | Descrição |
|------|--------------|------------------|--------------------|--------------------|-----------|
| `admin` | ✅ Sim | ✅ Sim | ✅ Sim | ✅ Sim | Acesso total a todas as funcionalidades |
| `superadmin` | ✅ Sim | ✅ Sim | ✅ Sim | ✅ Sim | Acesso total (equivalente a admin) |
| `manager` | ✅ Sim | ✅ Sim | ✅ Sim | ✅ Sim | Gerentes têm acesso completo |
| `analyst` | ✅ Sim | ✅ Sim | ✅ Sim | ✅ Sim | Analistas têm acesso completo |
| `new_business` | ✅ Sim | ✅ Sim | ✅ Sim | ✅ Sim | Time comercial tem acesso completo |
| `client` | ❌ Não | ✅ Sim | ❌ Não | ❌ Não (403) | Clientes têm acesso muito limitado |
| `customer` | ❌ Não | ✅ Sim | ❌ Não | ❌ Não (403) | Similar a client |
| `default` | ❌ Não | ✅ Sim | ❌ Não | ❌ Não (403) | Role desconhecida = menor privilégio |
| (sem role) | ❌ Não | ✅ Sim | ✅ Sim* | ✅ Sim* | Compatibilidade com versões antigas |

_*Nota: Para backward compatibility, ausência de role mantém acesso para Calendar e CRM, mas restringe Gmail body._

### Explicação por Funcionalidade

#### Gmail - Corpo de Email (`gmail_read_body`)

**Quem vê o corpo completo (plain_text_body, html_body):**
- Roles com acesso total: `admin`, `superadmin`, `manager`, `analyst`, `new_business`

**Quem vê apenas metadata (subject, snippet, from, to):**
- Roles restritos: `client`, `customer`, roles desconhecidas, sem role

**Justificativa:** O corpo do email pode conter informações sensíveis de negócio, estratégias de vendas ou detalhes confidenciais que não devem ser expostos para clientes externos.

#### Gmail - Metadados (`gmail_read_metadata`)

**Todos os roles** podem ver:
- Subject (assunto)
- Snippet (prévia de 100-200 caracteres)
- From/To/CC (remetente e destinatários)
- Data (internal_date)
- Labels
- Se tem anexos (has_attachments)

**Justificativa:** Metadados fornecem contexto suficiente para entender comunicações sem expor conteúdo completo.

#### Calendar - Detalhes (`calendar_read_details`)

**Quem vê detalhes completos (description, attendees, meet_link):**
- Roles com acesso: `admin`, `superadmin`, `manager`, `analyst`, `new_business`
- Sem role (backward compatibility)

**Quem vê apenas informações básicas (summary, start_time, end_time):**
- Roles restritos: `client`, `customer`, roles desconhecidas

**Justificativa:** Descrições de eventos e listas de participantes podem conter informações estratégicas internas. Links de Meet devem ser controlados para evitar acesso não autorizado a reuniões.

#### CRM Communications (`crm_read_communications`)

**Quem pode acessar `/api/crm/.../emails`, `/events`, `/timeline`:**
- Roles com acesso: `admin`, `superadmin`, `manager`, `analyst`, `new_business`
- Sem role (backward compatibility)

**Quem recebe 403 Forbidden:**
- Roles sem acesso: `client`, `customer`, roles desconhecidas

**Justificativa:** Endpoints CRM agregam dados sensíveis de negócio e relações entre entidades. Acesso deve ser restrito a usuários internos da organização.

### Implementação Técnica

As permissões são implementadas no `PermissionService` (`services/permission_service.py`) através de três classes:

```python
class GmailPermissions:
    gmail_read_metadata: bool  # Ver subject, snippet, from/to
    gmail_read_body: bool      # Ver corpo completo do email

class CalendarPermissions:
    calendar_read_details: bool  # Ver description, attendees, meet_link

class CRMPermissions:
    crm_read_communications: bool  # Acessar endpoints CRM
```

### Exemplo de Uso no Frontend

```typescript
// Enviar role no header
const response = await fetch('/api/crm/company/comp-123/timeline', {
  headers: {
    'x-user-role': getCurrentUserRole() // 'admin', 'analyst', etc.
  }
});

// Response será filtrado conforme permissões do role
```

### Princípio de Menor Privilégio

O sistema adota o **princípio de menor privilégio (least privilege)**:
- Roles desconhecidas ou não mapeadas recebem o mínimo de acesso possível
- Na dúvida, o sistema **nega acesso** em vez de conceder
- Logs estruturados registram tentativas de acesso negado para auditoria

---

## 5. Health & Observabilidade

A Plataforma de Comunicação fornece endpoints dedicados para monitoramento da saúde dos serviços e facilita integração com ferramentas de observabilidade.

### Endpoints de Health Check

#### `/health` - Status Agregado

Retorna status consolidado de todos os serviços da plataforma.

**Exemplo de Response:**
```json
{
  "overall_status": "healthy",
  "timestamp": "2025-12-09T01:22:31.816Z",
  "services": {
    "calendar": {
      "status": "healthy",
      "active_channels": 2,
      "last_sync": "2025-12-09T01:20:00.000Z"
    },
    "gmail": {
      "status": "healthy",
      "auth_ok": true,
      "api_reachable": true
    }
  }
}
```

**Status possíveis:**
- `healthy`: Todos os serviços operacionais
- `degraded`: Pelo menos um serviço degradado, nenhum unhealthy
- `unhealthy`: Pelo menos um serviço não operacional

#### `/health/calendar` - Status do Calendar

Monitora integração com Google Calendar e status dos webhooks.

**Exemplo de Response:**
```json
{
  "service": "calendar",
  "status": "healthy",
  "timestamp": "2025-12-09T01:22:31.816Z",
  "active_channels": 2,
  "last_sync": "2025-12-09T01:20:00.000Z",
  "event_count": 150,
  "oldest_event": "2025-06-01T10:00:00.000Z",
  "newest_event": "2025-12-31T18:00:00.000Z"
}
```

**Critérios de Health:**
- `healthy`: Webhooks ativos e sync recente
- `degraded`: Sem webhooks ativos ou sem sync recente
- `unhealthy`: Falhas críticas na API do Calendar

#### `/health/gmail` - Status do Gmail

Verifica autenticação e conectividade com Gmail API.

**Exemplo de Response:**
```json
{
  "service": "gmail",
  "status": "healthy",
  "timestamp": "2025-12-09T01:22:31.816Z",
  "auth_ok": true,
  "api_reachable": true,
  "configured_scopes": [
    "https://www.googleapis.com/auth/gmail.readonly"
  ]
}
```

**Critérios de Health:**
- `healthy`: Auth OK e API acessível
- `degraded`: Auth OK mas API com problemas
- `unhealthy`: Auth falhou ou não configurado

### Uso em Monitoramento e Alertas

#### Kubernetes Probes

```yaml
# Liveness Probe - verifica se aplicação está viva
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3

# Readiness Probe - verifica se pode receber tráfego
readinessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 5
  timeoutSeconds: 3
  successThreshold: 1
  failureThreshold: 2
```

#### Load Balancer Health Checks

**AWS Application Load Balancer:**
```
Health Check Path: /health
Interval: 30 seconds
Timeout: 5 seconds
Healthy threshold: 2
Unhealthy threshold: 3
```

**Google Cloud Load Balancer:**
```yaml
healthCheck:
  type: HTTP
  requestPath: /health
  port: 8000
  checkIntervalSec: 30
  timeoutSec: 5
```

#### Prometheus Monitoring

```yaml
# Scrape health endpoints
scrape_configs:
  - job_name: 'communication-platform-health'
    metrics_path: '/health'
    scrape_interval: 30s
    static_configs:
      - targets: ['backend:8000']
```

#### Datadog Integration

```python
import requests
from datadog import statsd

response = requests.get('http://localhost:8000/health')
data = response.json()

# Map status to numeric values
status_map = {'healthy': 0, 'degraded': 1, 'unhealthy': 2}
statsd.gauge('platform.health.overall', 
             status_map.get(data['overall_status'], 2))

# Service-specific metrics
for service, details in data['services'].items():
    statsd.gauge(f'platform.health.{service}', 
                 status_map.get(details['status'], 2))
```

### Logs Estruturados

A plataforma utiliza **logging estruturado em JSON** para facilitar análise e agregação.

#### Características dos Logs

**Formato JSON:**
```json
{
  "timestamp": "2025-12-09T10:30:45.123Z",
  "level": "INFO",
  "action": "get_entity_timeline",
  "status": "success",
  "entity_type": "company",
  "entity_id": "comp-123",
  "role": "admin",
  "total_items": 37,
  "gmail_items": 25,
  "calendar_items": 12,
  "duration_ms": 245
}
```

**Masking de Emails:**
Emails sensíveis são automaticamente mascarados nos logs:
```json
{
  "action": "search_emails",
  "from_email": "john***@example.com",
  "to_email": "jane***@company.com"
}
```

**Eventos Logados:**

1. **Autenticação e Autorização:**
   ```json
   {
     "action": "authorization_check",
     "role": "analyst",
     "permission": "crm_read_communications",
     "granted": true
   }
   ```

2. **Operações de API:**
   ```json
   {
     "action": "gmail_list_messages",
     "query": "is:unread",
     "result_count": 15,
     "duration_ms": 320
   }
   ```

3. **Erros e Exceções:**
   ```json
   {
     "level": "ERROR",
     "action": "calendar_create_event",
     "error": "Google Calendar API quota exceeded",
     "status_code": 429
   }
   ```

4. **Health Checks:**
   ```json
   {
     "action": "health_check",
     "service": "calendar",
     "status": "healthy",
     "active_channels": 2
   }
   ```

#### Agregação de Logs

**ELK Stack (Elasticsearch, Logstash, Kibana):**
```conf
# Logstash filter
filter {
  json {
    source => "message"
  }
  if [action] == "authorization_check" and [granted] == false {
    mutate {
      add_tag => [ "access_denied" ]
    }
  }
}
```

**Splunk:**
```
sourcetype=communication_platform_logs
| stats count by action, status
| where status="error"
```

### Recomendações de Observabilidade

1. **Polling de Health Checks:**
   - Frequência: 30-60 segundos para monitoramento geral
   - Timeout: 5 segundos máximo
   - Não pollar mais frequente que 5 segundos

2. **Alertas Recomendados:**
   - **Critical:** `overall_status=unhealthy` por >5 minutos
   - **Warning:** `overall_status=degraded` por >15 minutos
   - **Info:** Mudanças de status de serviços individuais

3. **Métricas Chave:**
   - Taxa de requisições por endpoint
   - Latência (p50, p95, p99) de cada serviço
   - Taxa de erros (4xx, 5xx)
   - Número de webhooks ativos do Calendar
   - Quota usage do Gmail API

4. **Dashboards:**
   - Overview: Status geral + gráfico de disponibilidade
   - Gmail: Métricas de API + autenticação
   - Calendar: Webhooks ativos + eventos sincronizados
   - CRM: Requests por entity_type + tempo de resposta

---

## 6. Exemplos de Uso pelo Frontend

Esta seção apresenta fluxos práticos de como o frontend deve consumir a Plataforma de Comunicação para construir funcionalidades de alto valor.

### Exemplo 1: Montar Timeline de um Deal

**Objetivo:** Exibir todas as comunicações (emails + reuniões) relacionadas a um Deal em ordem cronológica.

**Fluxo:**

```typescript
// 1. Definir configurações
const dealId = 'deal-001';
const pageSize = 20;

// 2. Buscar timeline unificada
async function loadDealTimeline(offset = 0) {
  const response = await fetch(
    `/api/crm/deal/${dealId}/timeline?limit=${pageSize}&offset=${offset}`,
    {
      headers: {
        'x-user-role': getCurrentUserRole()
      }
    }
  );
  
  if (!response.ok) {
    throw new Error(`Failed to load timeline: ${response.statusText}`);
  }
  
  return await response.json();
}

// 3. Renderizar items
async function renderTimeline() {
  const data = await loadDealTimeline(0);
  
  // data.items contém lista unificada de emails e eventos
  // já ordenada cronologicamente (mais recentes primeiro)
  
  data.items.forEach(item => {
    if (item.type === 'email') {
      renderEmailCard({
        id: item.id,
        subject: item.subject,
        snippet: item.snippet,
        datetime: item.datetime,
        participants: item.participants,
        icon: 'email'
      });
    } else if (item.type === 'event') {
      renderEventCard({
        id: item.id,
        subject: item.subject,  // título do evento
        snippet: item.snippet,  // descrição (se tiver permissão)
        datetime: item.datetime, // start_time do evento
        participants: item.participants,
        icon: 'calendar'
      });
    }
  });
  
  // 4. Implementar paginação
  if (data.total > pageSize) {
    renderPaginationControls({
      currentPage: 0,
      totalItems: data.total,
      pageSize: pageSize,
      onPageChange: (page) => {
        loadDealTimeline(page * pageSize)
          .then(renderTimeline);
      }
    });
  }
}
```

**Response Esperada:**
```json
{
  "items": [
    {
      "id": "18b2f3a8d4c5e1f2",
      "source": "gmail",
      "type": "email",
      "subject": "Proposta Comercial Q4",
      "snippet": "Segue em anexo a proposta comercial...",
      "datetime": "2024-01-16T10:30:00Z",
      "participants": ["sales@company.com", "client@example.com"],
      "matched_contacts": ["client@example.com"],
      "entity_type": "deal",
      "entity_id": "deal-001"
    },
    {
      "id": "evt_abc123",
      "source": "calendar",
      "type": "event",
      "subject": "Reunião de Proposta",
      "snippet": "Apresentação da proposta comercial Q4",
      "datetime": "2024-01-15T14:00:00Z",
      "participants": ["sales@company.com", "client@example.com", "manager@company.com"],
      "matched_contacts": ["client@example.com"],
      "entity_type": "deal",
      "entity_id": "deal-001"
    }
  ],
  "total": 37,
  "limit": 20,
  "offset": 0
}
```

### Exemplo 2: Listar Últimas Comunicações de uma Company

**Objetivo:** Widget de "Atividades Recentes" mostrando as 10 comunicações mais recentes com uma empresa.

**Fluxo:**

```typescript
// 1. Component React com React Query
import { useQuery } from 'react-query';

interface RecentActivityProps {
  companyId: string;
}

function RecentActivityWidget({ companyId }: RecentActivityProps) {
  // 2. Fetch últimas 10 comunicações
  const { data, isLoading, error } = useQuery(
    ['company-activity', companyId],
    async () => {
      const response = await fetch(
        `/api/crm/company/${companyId}/timeline?limit=10&offset=0`,
        {
          headers: {
            'x-user-role': getCurrentUserRole()
          }
        }
      );
      
      if (!response.ok) {
        throw new Error('Failed to fetch activity');
      }
      
      return response.json();
    },
    {
      staleTime: 60000, // Cache por 1 minuto
      refetchInterval: 300000 // Refetch a cada 5 minutos
    }
  );
  
  // 3. Renderizar
  if (isLoading) return <Spinner />;
  if (error) return <ErrorMessage error={error} />;
  
  return (
    <Card title="Atividades Recentes">
      {data.items.map(item => (
        <ActivityItem
          key={item.id}
          icon={item.type === 'email' ? <EmailIcon /> : <CalendarIcon />}
          title={item.subject}
          datetime={new Date(item.datetime).toLocaleString('pt-BR')}
          participants={item.participants}
          onClick={() => openActivityDetail(item)}
        />
      ))}
      
      {data.total > 10 && (
        <Link to={`/company/${companyId}/communications`}>
          Ver todas ({data.total})
        </Link>
      )}
    </Card>
  );
}
```

**Alternativa: Buscar Emails e Eventos Separadamente**

Se você precisar exibir emails e eventos em seções distintas:

```typescript
async function loadCompanyCommunications(companyId: string) {
  // Buscar em paralelo
  const [emailsResponse, eventsResponse] = await Promise.all([
    fetch(`/api/crm/company/${companyId}/emails?limit=10&offset=0`, {
      headers: { 'x-user-role': getCurrentUserRole() }
    }),
    fetch(`/api/crm/company/${companyId}/events?limit=10&offset=0`, {
      headers: { 'x-user-role': getCurrentUserRole() }
    })
  ]);
  
  const emails = await emailsResponse.json();
  const events = await eventsResponse.json();
  
  return { emails, events };
}

// Renderizar em duas seções
function CommunicationsSplit({ companyId }: Props) {
  const [data, setData] = useState(null);
  
  useEffect(() => {
    loadCompanyCommunications(companyId).then(setData);
  }, [companyId]);
  
  return (
    <>
      <EmailSection items={data?.emails.emails || []} />
      <EventsSection items={data?.events.events || []} />
    </>
  );
}
```

### Exemplo 3: Usar Paginação e Filtros de Data nos Endpoints CRM

**Objetivo:** Implementar busca com filtros temporais e paginação eficiente.

**Fluxo:**

```typescript
// 1. Interface de filtros
interface CommunicationFilters {
  entityType: 'company' | 'lead' | 'deal';
  entityId: string;
  timeMin?: string;  // YYYY-MM-DD
  timeMax?: string;  // YYYY-MM-DD
  limit?: number;
  offset?: number;
}

// 2. Função de busca com filtros
async function searchCommunications(filters: CommunicationFilters) {
  // Construir query string
  const params = new URLSearchParams();
  if (filters.timeMin) params.append('time_min', filters.timeMin);
  if (filters.timeMax) params.append('time_max', filters.timeMax);
  params.append('limit', String(filters.limit || 50));
  params.append('offset', String(filters.offset || 0));
  
  const response = await fetch(
    `/api/crm/${filters.entityType}/${filters.entityId}/timeline?${params}`,
    {
      headers: {
        'x-user-role': getCurrentUserRole()
      }
    }
  );
  
  return await response.json();
}

// 3. Component com filtros e paginação
function CommunicationBrowser({ entityType, entityId }: Props) {
  const [filters, setFilters] = useState({
    entityType,
    entityId,
    timeMin: undefined,
    timeMax: undefined,
    limit: 20,
    offset: 0
  });
  
  const [timeline, setTimeline] = useState(null);
  
  // Buscar quando filtros mudarem
  useEffect(() => {
    searchCommunications(filters).then(setTimeline);
  }, [filters]);
  
  // Handlers
  const handleDateFilter = (start: Date, end: Date) => {
    setFilters({
      ...filters,
      timeMin: start.toISOString().split('T')[0],
      timeMax: end.toISOString().split('T')[0],
      offset: 0 // Reset para primeira página
    });
  };
  
  const handlePageChange = (newPage: number) => {
    setFilters({
      ...filters,
      offset: newPage * filters.limit
    });
  };
  
  const handleClearFilters = () => {
    setFilters({
      ...filters,
      timeMin: undefined,
      timeMax: undefined,
      offset: 0
    });
  };
  
  // Render
  return (
    <div>
      {/* Filtros */}
      <FilterBar>
        <DateRangePicker
          onChange={handleDateFilter}
          value={[filters.timeMin, filters.timeMax]}
        />
        <Button onClick={handleClearFilters}>
          Limpar Filtros
        </Button>
      </FilterBar>
      
      {/* Timeline */}
      <Timeline items={timeline?.items || []} />
      
      {/* Paginação */}
      <Pagination
        currentPage={Math.floor(filters.offset / filters.limit)}
        totalItems={timeline?.total || 0}
        pageSize={filters.limit}
        onPageChange={handlePageChange}
      />
    </div>
  );
}
```

**Exemplo de Requests com Filtros:**

```bash
# Comunicações de janeiro de 2024
GET /api/crm/company/comp-123/timeline?time_min=2024-01-01&time_max=2024-02-01&limit=50&offset=0

# Segunda página (items 50-99)
GET /api/crm/company/comp-123/timeline?time_min=2024-01-01&time_max=2024-02-01&limit=50&offset=50

# Apenas emails (usar endpoint específico)
GET /api/crm/company/comp-123/emails?time_min=2024-01-01&time_max=2024-02-01&limit=50&offset=0

# Apenas eventos confirmados
GET /api/crm/company/comp-123/events?status=confirmed&limit=50&offset=0
```

### Boas Práticas para Frontend

1. **Sempre enviar `x-user-role` header**
   ```typescript
   headers: {
     'x-user-role': getCurrentUserRole()
   }
   ```

2. **Implementar cache apropriado**
   ```typescript
   // React Query
   const { data } = useQuery(
     ['timeline', entityId],
     fetchTimeline,
     { staleTime: 60000 } // 1 minuto
   );
   ```

3. **Tratar permissões no UI**
   ```typescript
   // Esconder corpo de email se role não tem permissão
   if (userRole === 'client' || userRole === 'customer') {
     // Mostrar apenas snippet
     return <EmailSnippet snippet={item.snippet} />;
   } else {
     // Mostrar corpo completo
     return <EmailBody body={emailDetails.plain_text_body} />;
   }
   ```

4. **Implementar scroll infinito para grandes volumes**
   ```typescript
   const { data, fetchNextPage, hasNextPage } = useInfiniteQuery(
     ['timeline', entityId],
     ({ pageParam = 0 }) => fetchTimeline(entityId, pageParam),
     {
       getNextPageParam: (lastPage, pages) => {
         const currentOffset = pages.length * pageSize;
         return currentOffset < lastPage.total 
           ? currentOffset 
           : undefined;
       }
     }
   );
   ```

5. **Sanitizar HTML ao renderizar email bodies**
   ```typescript
   import DOMPurify from 'dompurify';
   
   function EmailBodyRenderer({ htmlBody }: Props) {
     const sanitized = DOMPurify.sanitize(htmlBody);
     return <div dangerouslySetInnerHTML={{ __html: sanitized }} />;
   }
   ```

---

## Referências

### Documentação Detalhada

- [CALENDAR_API.md](../CALENDAR_API.md) - API completa do Google Calendar/Meet
- [GMAIL_API.md](../GMAIL_API.md) - API completa do Gmail
- [CRM_COMMUNICATION_API.md](./CRM_COMMUNICATION_API.md) - Endpoints de comunicação por entidade
- [CRM_TIMELINE_API.md](./CRM_TIMELINE_API.md) - Endpoint de timeline unificada
- [HEALTH_API.md](./HEALTH_API.md) - Endpoints de health check e observabilidade

### Arquivos de Código

- `services/permission_service.py` - Implementação de controle de acesso
- `services/google_gmail_service.py` - Integração com Gmail API
- `services/google_calendar_service.py` - Integração com Calendar API
- `services/crm_contact_service.py` - Extração de contatos CRM
- `routers/crm_communication.py` - Endpoints CRM

### Outros Recursos

- [README.md](../README.md) - Visão geral do projeto
- [ARCHITECTURE_DIAGRAM.md](../ARCHITECTURE_DIAGRAM.md) - Diagramas de arquitetura
- [DOCUMENTATION_INDEX.md](../DOCUMENTATION_INDEX.md) - Índice de toda documentação

---

**Última atualização:** 2025-12-09  
**Versão:** 1.0  
**Mantido por:** Backend Development Team
