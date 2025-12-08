# Arquitetura da Integração Google Calendar - Visão Geral

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│                    FRONTEND (pipedesk-koa / Vercel)                         │
│                                                                             │
└────────────────────────────┬────────────────────────────────────────────────┘
                             │
                             │ REST API (HTTPS)
                             │
┌────────────────────────────▼────────────────────────────────────────────────┐
│                                                                             │
│                     BACKEND (pd-google / Render)                            │
│                          FastAPI + Python                                   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      Routers (Endpoints)                            │   │
│  │                                                                     │   │
│  │  📍 POST   /calendar/events          → Criar evento + Meet         │   │
│  │  📍 GET    /calendar/events          → Listar eventos (DB local)   │   │
│  │  📍 PATCH  /calendar/events/{id}     → Atualizar evento            │   │
│  │  📍 DELETE /calendar/events/{id}     → Cancelar evento             │   │
│  │  📍 POST   /calendar/watch           → Registrar webhook           │   │
│  │  📍 POST   /webhooks/google-drive    → Receber notificações        │   │
│  │                                                                     │   │
│  └───────────────────┬─────────────────────────────────────────────────┘   │
│                      │                                                      │
│  ┌───────────────────▼─────────────────────────────────────────────────┐   │
│  │                     Services (Lógica de Negócio)                    │   │
│  │                                                                     │   │
│  │  🔧 GoogleCalendarService                                           │   │
│  │     ├─ create_event()      → Cria evento no Google                 │   │
│  │     ├─ list_events()       → Lista eventos (com sync token)        │   │
│  │     ├─ get_event()         → Busca evento específico               │   │
│  │     ├─ update_event()      → Atualiza evento                       │   │
│  │     ├─ delete_event()      → Deleta evento                         │   │
│  │     ├─ watch_events()      → Registra canal de notificação         │   │
│  │     └─ stop_channel()      → Para canal                            │   │
│  │                                                                     │   │
│  │  🔧 GoogleAuthService                                               │   │
│  │     └─ Service Account Authentication                              │   │
│  │                                                                     │   │
│  │  🔧 SchedulerService                                                │   │
│  │     ├─ renew_channels_job()      (a cada 6h)                       │   │
│  │     └─ reconcile_drive_state()   (a cada 1h)                       │   │
│  │                                                                     │   │
│  └───────────────────┬─────────────────────────────────────────────────┘   │
│                      │                                                      │
│  ┌───────────────────▼─────────────────────────────────────────────────┐   │
│  │                  Database (PostgreSQL / Supabase)                   │   │
│  │                                                                     │   │
│  │  📦 calendar_events                                                 │   │
│  │     ├─ id (PK)                                                      │   │
│  │     ├─ google_event_id (UNIQUE)                                     │   │
│  │     ├─ summary, description                                         │   │
│  │     ├─ start_time, end_time                                         │   │
│  │     ├─ meet_link, html_link                                         │   │
│  │     ├─ status (confirmed/cancelled)                                 │   │
│  │     ├─ organizer_email                                              │   │
│  │     └─ attendees (JSON)                                             │   │
│  │                                                                     │   │
│  │  📦 calendar_sync_states                                            │   │
│  │     ├─ id (PK)                                                      │   │
│  │     ├─ channel_id (UNIQUE)                                          │   │
│  │     ├─ resource_id                                                  │   │
│  │     ├─ sync_token (para sync incremental)                           │   │
│  │     ├─ expiration                                                   │   │
│  │     └─ active                                                       │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└────────────────────┬──────────────────────────┬─────────────────────────────┘
                     │                          │
                     │ Google API               │ Webhooks (Push Notifications)
                     │ (Service Account)        │
                     │                          │
┌────────────────────▼──────────────────────────▼─────────────────────────────┐
│                                                                             │
│                        GOOGLE WORKSPACE                                     │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     Google Calendar API                             │   │
│  │                                                                     │   │
│  │  • Service Account é "organizadora" de todos os eventos            │   │
│  │  • Cria eventos no calendário 'primary'                            │   │
│  │  • Adiciona participantes como 'attendees'                         │   │
│  │  • Gera links do Google Meet automaticamente                       │   │
│  │  • Envia notificações via webhook quando há mudanças              │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘


═══════════════════════════════════════════════════════════════════════════════
                        FLUXOS PRINCIPAIS
═══════════════════════════════════════════════════════════════════════════════

🔄 FLUXO 1: Criar Evento (Frontend → Google)
──────────────────────────────────────────────

1. Frontend envia POST /calendar/events
   {
     "summary": "Reunião Cliente X",
     "start_time": "2025-12-10T14:00:00Z",
     "end_time": "2025-12-10T15:00:00Z",
     "attendees": ["cliente@email.com"],
     "create_meet_link": true
   }

2. Router recebe e valida

3. GoogleCalendarService.create_event()
   ├─ Prepara payload com conferenceData
   └─ Chama Google Calendar API

4. Google Calendar:
   ├─ Cria evento
   ├─ Gera link do Meet
   └─ Retorna dados completos

5. Backend:
   ├─ Salva em calendar_events (DB)
   └─ Retorna response com meet_link

6. Frontend exibe sucesso + link do Meet


🔄 FLUXO 2: Sincronização (Google → Backend)
─────────────────────────────────────────────

1. Evento modificado no Google Calendar
   (usuário altera horário diretamente no Google)

2. Google envia webhook:
   POST /webhooks/google-drive
   Headers:
     X-Goog-Channel-ID: uuid-do-canal
     X-Goog-Resource-State: change

3. Backend identifica canal (calendar_sync_states)

4. handle_calendar_webhook():
   └─ sync_calendar_events()

5. sync_calendar_events():
   ├─ Recupera sync_token do DB
   ├─ Chama Google API com syncToken
   ├─ Recebe apenas eventos modificados (delta)
   ├─ Atualiza calendar_events no DB
   └─ Salva novo sync_token

6. DB atualizado com mudanças do Google


🔄 FLUXO 3: Renovação de Canal (Automático)
───────────────────────────────────────────

1. Scheduler roda a cada 6 horas

2. renew_channels_job():
   └─ Busca canais expirando em < 24h

3. Para cada canal:
   ├─ stop_channel() no Google
   ├─ watch_events() para criar novo canal
   └─ Atualiza calendar_sync_states no DB

4. Canal renovado automaticamente
   (Google requer renovação ~7 dias)


🔄 FLUXO 4: Listar Eventos (Performance Otimizada)
──────────────────────────────────────────────────

1. Frontend pede GET /calendar/events?time_min=...&time_max=...

2. Router lê DIRETO do DB local (calendar_events)
   (não chama Google API → muito mais rápido)

3. Filtra por:
   ├─ status != 'cancelled'
   ├─ start_time >= time_min
   └─ end_time <= time_max

4. Retorna lista de eventos

5. Frontend exibe calendário


═══════════════════════════════════════════════════════════════════════════════
                            CONFIGURAÇÃO
═══════════════════════════════════════════════════════════════════════════════

📋 Variáveis de Ambiente Necessárias:
──────────────────────────────────────

GOOGLE_SERVICE_ACCOUNT_JSON      (JSON da Service Account)
WEBHOOK_BASE_URL                 (URL pública: https://pd-google.onrender.com)
WEBHOOK_SECRET                   (Secret para validar webhooks)
DATABASE_URL                     (PostgreSQL do Supabase)
CORS_ORIGINS                     (URLs do frontend)


📋 Escopos OAuth Necessários:
─────────────────────────────

https://www.googleapis.com/auth/calendar
https://www.googleapis.com/auth/drive


═══════════════════════════════════════════════════════════════════════════════
                          STATUS ATUAL
═══════════════════════════════════════════════════════════════════════════════

✅ Código:           100% implementado (Fases 1-4)
✅ Testes:           5/5 passando
✅ Modelos:          CalendarEvent + CalendarSyncState prontos
✅ Endpoints:        5 endpoints REST funcionais
✅ Sincronização:    Bidirecional implementada
✅ Meet:             Links gerados automaticamente
✅ Scheduler:        Renovação automática configurada

⚠️  Migração SQL:    Criada mas não executada em produção
⚠️  Hardening:       Parcialmente implementado (60%)
⚠️  Observabilidade: Básica (falta métricas/alertas)

❌ Sync Inicial:     Não implementado (ao criar canal watch)
❌ Rate Limiting:    Não implementado
❌ Cleanup Job:      Não implementado


═══════════════════════════════════════════════════════════════════════════════
                        PRÓXIMOS PASSOS
═══════════════════════════════════════════════════════════════════════════════

🎯 CRÍTICO (antes de deploy):
  1. Executar migrations/calendar_tables.sql no Supabase
  2. Configurar WEBHOOK_BASE_URL e WEBHOOK_SECRET
  3. Teste end-to-end com Google Calendar real
  4. Adicionar sync inicial ao criar canal (5 linhas)
  5. Validação restritiva de webhook token (403)

🔧 IMPORTANTE (hardening):
  6. Retry logic com exponential backoff
  7. Logs estruturados JSON
  8. Job de limpeza de eventos antigos

📊 DESEJÁVEL (observabilidade):
  9. Health check /health/calendar
 10. Métricas Prometheus

```

---

**Legenda:**
- ✅ = Implementado e funcional
- ⚠️ = Parcialmente implementado
- ❌ = Não implementado
- 📍 = Endpoint REST
- 🔧 = Serviço/Componente
- 📦 = Tabela no banco de dados
- 🔄 = Fluxo de dados
