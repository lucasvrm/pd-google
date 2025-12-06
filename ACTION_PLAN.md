# PLANO DE AÇÃO: Integração Google Calendar & Meet

Este documento detalha o plano de execução para integrar o backend `pd-google` com Google Calendar e Google Meet, permitindo agendamento, geração de links de reunião e sincronização bidirecional.

## Sumário das Fases
*   **Fase 1: Fundação & Modelo de Dados** - Ajustes de infraestrutura, banco de dados e credenciais.
*   **Fase 2: Core Calendar & API** - Implementação dos serviços de calendário e endpoints CRUD básicos.
*   **Fase 3: Sincronização Bidirecional** - Implementação de Webhooks e lógica de Sync Token para manter dados atualizados.
*   **Fase 4: Google Meet & Frontend API** - Geração de links de reunião e refinamento dos contratos para o frontend.
*   **Fase 5: Hardening & Observabilidade** - Tratamento de erros, logs robustos e segurança.

---

## Detalhamento das Fases

### Fase 1: Fundação & Modelo de Dados
**Objetivo:** Preparar o terreno, garantindo que o banco de dados e a infraestrutura de autenticação estejam prontos.

*   **Tarefas:**
    1.  **Migração SQL:** Executar o script SQL (já fornecido na análise) no Supabase para criar `calendar_events` e `calendar_sync_states`.
    2.  **Atualizar Modelos Python:** Criar arquivo `models/calendar.py` (ou adicionar ao `models.py`) mapeando as novas tabelas SQLAlchemy.
    3.  **Configuração de Escopos:** Atualizar a lista de escopos na inicialização das credenciais Google para incluir `https://www.googleapis.com/auth/calendar`.
    4.  **Isolamento do Serviço:** Criar estrutura base de `services/google_calendar_service.py` herdando a lógica de autenticação existente.

*   **Dependências:** Acesso ao banco Supabase.
*   **Critérios de Pronto:** Tabelas criadas no DB, modelos SQLAlchemy refletindo o schema, serviço iniciando sem erros com novos escopos.
*   **Riscos:** Conflitos de dependências (improvável, pois já usa `google-api-python-client`).

### Fase 2: Core Calendar & API
**Objetivo:** Permitir que o backend crie e manipule eventos no Google Calendar.

*   **Tarefas:**
    1.  **Implementar `services/google_calendar_service.py`:**
        *   Método `create_event(data)`: Cria evento no calendário `primary` da Service Account.
        *   Método `list_events(timeMin, timeMax)`: Busca eventos no Google.
        *   Método `update_event(id, data)`: Atualiza evento.
        *   Método `delete_event(id)`: Cancela evento.
    2.  **Criar `routers/calendar.py`:**
        *   Implementar endpoints básicos mapeando para o serviço (ver seção Contrato de API).
    3.  **Persistência Inicial:** Ao criar um evento via API, salvar imediatamente na tabela `calendar_events` (espelhamento otimista).

*   **Dependências:** Fase 1 concluída.
*   **Critérios de Pronto:** É possível criar um evento via Postman/cURL e vê-lo aparecer no calendário da Service Account e no banco de dados local.
*   **Riscos:** Falhas na conversão de timezones (Google exige ISO format preciso).

### Fase 3: Sincronização Bidirecional (Webhooks)
**Objetivo:** Garantir que alterações feitas diretamente no Google Calendar reflitam no sistema.

*   **Tarefas:**
    1.  **Canal de Notificação:** Implementar método `watch_calendar()` no serviço para registrar o webhook no Google (expira em ~7 dias, precisa de renovação).
    2.  **Rota de Webhook:** Criar/ajustar `routers/webhooks.py` para receber notificações do recurso "calendar".
    3.  **Lógica de Sync:**
        *   Ao receber webhook, recuperar `sync_token` do banco.
        *   Chamar `events().list(syncToken=...)` para pegar apenas o delta.
        *   Atualizar tabela `calendar_events` (insert/update/delete lógico).
        *   Salvar novo `nextSyncToken`.
    4.  **Renovação Automática:** Criar endpoint ou script para renovar o canal `watch` antes da expiração.

*   **Dependências:** URL pública (Render) para o Google entregar os webhooks.
*   **Critérios de Pronto:** Alterar o horário de um evento no Google Calendar e ver a mudança refletida no banco de dados do sistema em segundos.
*   **Riscos:** "Loop de sincronização" (App atualiza Google -> Google notifica App -> App tenta atualizar de novo). Solução: verificar se o dado realmente mudou antes de escrever.

### Fase 4: Google Meet & Frontend API
**Objetivo:** Finalizar a integração com Meet e expor a API polida para o frontend.

*   **Tarefas:**
    1.  **Geração de Meet:** Ajustar o payload de criação de evento para incluir `conferenceData` (requer `conferenceDataVersion=1`).
    2.  **Extração de Links:** No processamento da resposta do Google, extrair `hangoutLink` e salvar em `calendar_events.meet_link`.
    3.  **Endpoint de Listagem Otimizado:** O endpoint `GET /calendar/events` deve ler exclusivamente do banco de dados local (para performance), confiando na sincronização da Fase 3.
    4.  **Filtros de API:** Adicionar filtros por data (`start_date`, `end_date`) e status no endpoint de listagem.

*   **Dependências:** Fase 2 e 3 estáveis.
*   **Critérios de Pronto:** Criar evento via API gera automaticamente um link do Meet; Frontend consegue listar eventos rapidamente sem chamar API do Google em tempo real.

### Fase 5: Hardening & Observabilidade
**Objetivo:** Tornar a solução robusta para produção.

*   **Tarefas:**
    1.  **Logs Estruturados:** Adicionar logs JSON em pontos críticos (início de sync, erro de API, webhook recebido). *Nunca logar tokens ou corpos de e-mail sensíveis.*
    2.  **Tratamento de Erros:**
        *   Tratar 404 (evento deletado no Google).
        *   Tratar 410 (Sync Token expirado -> requer sync completo).
        *   Exponential Backoff para falhas de rede.
    3.  **Limpeza de Dados:** Job para arquivar/deletar eventos antigos do banco.
    4.  **Segurança:** Validar cabeçalhos `X-Goog-Channel-Token` para garantir origem dos webhooks.

---

## Contrato de API Refinado

### 1. Criar Evento (com Meet)
*   **Método:** `POST /calendar/events`
*   **Fase:** 2 (Core) -> 4 (Meet)
*   **Body:**
    ```json
    {
      "summary": "Demo Produto",
      "description": "Apresentação para cliente...",
      "start_time": "2023-10-27T10:00:00-03:00",
      "end_time": "2023-10-27T11:00:00-03:00",
      "attendees": ["cliente@email.com"],
      "create_meet": true
    }
    ```
*   **Response:** JSON com `id`, `google_id`, `meet_link`, `status`.

### 2. Listar Eventos
*   **Método:** `GET /calendar/events`
*   **Fase:** 2 (Direto Google) -> 4 (Via DB Local)
*   **Query Params:** `start`, `end` (ISO Dates)
*   **Response:** Array de eventos. A partir da Fase 4, a leitura é 100% do DB local.

### 3. Atualizar Evento
*   **Método:** `PATCH /calendar/events/{id}`
*   **Fase:** 2
*   **Body:** Campos parciais (`start_time`, `summary`, etc.)

### 4. Cancelar Evento
*   **Método:** `DELETE /calendar/events/{id}`
*   **Fase:** 2
*   **Comportamento:** Remove do Google (status `cancelled`). No DB local, pode ser soft-delete ou update de status.

---

## Estratégia Final de Autenticação/Autorização

### Modelo: Service Account "Organizadora"
A decisão estratégica é utilizar a **Service Account (SA)** existente como a "anfitriã" de todas as reuniões geradas pelo sistema.

1.  **Sem OAuth de Usuário:** O usuário final (vendedor) **não** precisa logar com Google. Ele loga no sistema normalmente.
2.  **Convites:** Quando o vendedor agenda uma reunião, o sistema (via SA) cria o evento e **convida** o vendedor e o cliente por e-mail.
3.  **Fluxo:**
    *   Backend autentica com Google usando `GOOGLE_SERVICE_ACCOUNT_JSON`.
    *   Backend cria evento no calendário `primary` da SA.
    *   Backend adiciona `attendees: [{email: 'vendedor@...'}, {email: 'cliente@...'}]`.
    *   Google envia e-mail de convite para ambos com o link do Meet.
4.  **Segurança:**
    *   A chave JSON da SA nunca sai do servidor.
    *   Nenhum token de usuário é armazenado.
    *   O backend atua como autoridade máxima.

### Diretrizes de Segurança e Logs
*   **Logs:** Logar `event_id`, `calendar_id` e status HTTP. Não logar PII (emails, nomes) nos logs de aplicação se possível.
*   **Webhook Secret:** Usar um segredo aleatório no header `X-Goog-Channel-Token` ao registrar o canal e validá-lo no recebimento.
*   **Validação de Input:** Sanitizar inputs de texto (summary, description) para evitar injeção.
