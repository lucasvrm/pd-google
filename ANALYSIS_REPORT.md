# RELATÓRIO DE ANÁLISE: Integração Google Calendar & Meet

## 1. Visão Geral da Arquitetura
O backend `pd-google` é construído utilizando **FastAPI** (Python) e **SQLAlchemy** (PostgreSQL/SQLite), seguindo uma arquitetura de camadas (Routers -> Services -> Models).

*   **Ponto de Entrada:** `main.py` configura o app FastAPI e inclui os routers.
*   **Serviços de Integração:** Localizados em `services/`, isolam a lógica de comunicação com APIs externas.
*   **Autenticação Google:** Centralizada via **Service Account** (Conta de Serviço), utilizando a biblioteca `google-api-python-client`.
*   **Processamento Assíncrono:** Já existe infraestrutura para Webhooks (`routers/webhooks.py` e `services/webhook_service.py`) para receber notificações de mudanças do Google Drive.

## 2. Estado Atual da Integração
*   **Google Drive:** Totalmente implementado. O sistema cria pastas, gerencia hierarquia e escuta mudanças via Webhooks (Push Notifications).
*   **Google Calendar & Meet:** Inexistente. Não há serviços, modelos ou endpoints dedicados.
*   **Infraestrutura de Auth:** O sistema já carrega credenciais de Service Account (`GOOGLE_SERVICE_ACCOUNT_JSON`), mas atualmente solicita apenas escopos do Drive.

## 3. Requisitos de Integração

### 3.1. Google Calendar (Service Account como Organizador)
Conforme definido, a integração utilizará a própria **Service Account** como "dona" dos eventos.
*   **Criação:** A Service Account cria o evento no seu calendário principal (`primary`).
*   **Convites:** A Service Account adiciona o e-mail do usuário (Sales Rep) e do cliente (Lead) como participantes (`attendees`).
*   **Sincronização Bidirecional:**
    *   **Google -> App:** O backend deve registrar um canal de notificação (`events.watch`) no calendário da Service Account. Ao receber um webhook, usa o `syncToken` para buscar apenas o que mudou.
    *   **App -> Google:** Criações/edições locais disparam chamadas imediatas à API do Google.

### 3.2. Google Meet
*   A geração de links do Meet é feita automaticamente ao criar um evento no Calendar, bastando adicionar a propriedade `conferenceData` com `createRequest` na chamada de API.
*   Não é necessário um "serviço" separado para o Meet; ele é um sub-recurso do evento de calendário.

## 4. Estratégia de Autenticação
*   **Credenciais:** Manter o uso da variável `GOOGLE_SERVICE_ACCOUNT_JSON`.
*   **Escopos:** Adicionar `https://www.googleapis.com/auth/calendar` aos escopos de inicialização no `services/google_drive_real.py` (ou criar um novo `GoogleCalendarService`).
*   **Mecanismo:** A Service Account não impersonará usuários (sem Domain-Wide Delegation por enquanto). Ela será a organizadora oficial das reuniões.

## 5. Modelo de Dados (SQL Migration)
Para suportar a sincronização bidirecional, precisamos de duas novas tabelas: uma para espelhar os eventos e outra para gerenciar o estado da sincronização (tokens).

```sql
-- Tabela para controlar o estado da sincronização incremental (Sync Token)
CREATE TABLE calendar_sync_states (
    id SERIAL PRIMARY KEY,
    resource_id VARCHAR(255),       -- ID do recurso retornado pelo Google ao criar o canal
    channel_id VARCHAR(255) UNIQUE, -- Nosso UUID para o canal de webhook
    calendar_id VARCHAR(255) DEFAULT 'primary', -- ID do calendário monitorado
    sync_token VARCHAR(255),        -- Token para buscar apenas alterações incrementais
    expiration TIMESTAMP,           -- Data de expiração do canal (Google exige renovação)
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP
);

-- Tabela para espelhar eventos locais (Cache/Mirror)
CREATE TABLE calendar_events (
    id SERIAL PRIMARY KEY,
    google_event_id VARCHAR(255) UNIQUE NOT NULL, -- ID oficial do evento no Google
    calendar_id VARCHAR(255) DEFAULT 'primary',

    -- Dados principais
    summary VARCHAR(255),           -- Título da reunião
    description TEXT,               -- Descrição/Pauta
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,

    -- Links Importantes
    meet_link VARCHAR(255),         -- Link do Google Meet
    html_link VARCHAR(255),         -- Link para ver no Google Calendar web

    -- Metadados
    status VARCHAR(50),             -- confirmed, tentative, cancelled
    organizer_email VARCHAR(255),   -- Email de quem criou (neste caso, a Service Account)

    -- Participantes (armazenado como JSON para simplificar leitura rápida)
    -- Ex: [{"email": "lead@gmail.com", "responseStatus": "needsAction"}]
    attendees JSONB,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

## 6. Rascunho de Contrato de API

### 6.1. Agendamento (Frontend -> Backend)

#### `POST /calendar/events`
Cria uma reunião, convida participantes e gera link do Meet.

*   **Request Body:**
    ```json
    {
      "summary": "Reunião de Vendas - Cliente X",
      "description": "Apresentação de proposta...",
      "start_time": "2023-10-25T14:00:00Z",
      "end_time": "2023-10-25T15:00:00Z",
      "attendees": ["vendedor@empresa.com", "cliente@gmail.com"],
      "create_meet_link": true
    }
    ```

*   **Response (201 Created):**
    ```json
    {
      "id": 1,
      "google_event_id": "evt_12345...",
      "meet_link": "https://meet.google.com/abc-defg-hij",
      "status": "confirmed"
    }
    ```

#### `GET /calendar/events`
Lista eventos locais (do banco de dados) com filtros opcionais.

*   **Query Params:** `start_date`, `end_date`
*   **Response:** Lista de objetos de evento.

#### `PATCH /calendar/events/{event_id}`
Atualiza horário ou descrição.

*   **Request Body:** Campos parciais (`start_time`, `summary`, etc.)

#### `DELETE /calendar/events/{event_id}`
Cancela a reunião no Google (envia e-mail de cancelamento aos convidados).

### 6.2. Webhooks (Google -> Backend)

#### `POST /webhooks/google-calendar`
Recebe notificações de mudança.

*   **Headers:** `X-Goog-Channel-ID`, `X-Goog-Resource-State`
*   **Ação:**
    1.  Verifica o `X-Goog-Channel-ID` na tabela `calendar_sync_states`.
    2.  Recupera o `sync_token` salvo.
    3.  Chama a API do Google `events().list(syncToken=...)`.
    4.  Atualiza a tabela `calendar_events` (Upsert: cria novos, atualiza existentes, marca deletados).
    5.  Salva o novo `nextSyncToken` no banco.

## 7. Próximos Passos (Plano de Execução)
1.  Rodar a migração SQL no Supabase.
2.  Criar `services/google_calendar_service.py` (cópia adaptada do drive service com novos escopos).
3.  Implementar `routers/calendar.py` com os endpoints CRUD.
4.  Implementar a lógica de Webhook e Sync Incremental.
