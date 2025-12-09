# Observabilidade

Este documento resume como monitorar as integrações do Pipedesk com Google e os webhooks.

## Logging estruturado

- O `logging_config.py` configura um formatter JSON padrão para todos os logs do namespace `pipedesk_drive`.
- Cada registro inclui `timestamp`, `level`, `logger` e `message`, além de quaisquer campos extras anexados via `extra` ou pelos loggers estruturados em `utils/structured_logging.py`.
- Use `StructuredLogger` para logs de domínio (calendário, saúde) e preferir campos consistentes como `action`, `status` e identificadores de entidades.

## Métricas de saúde

### Endpoints

- `GET /health/calendar`: retorna o estado do calendário, conectividade com a API do Google Calendar e métricas da fila de webhooks.
- `GET /health/gmail`: valida escopos e conectividade com a API do Gmail.
- `GET /health`: agrega métricas de calendário, Gmail e fila de webhooks.

### Campos principais

- `active_channels`: canais de webhook ativos e não expirados.
- `last_sync`: último `updated_at` conhecido de `CalendarSyncState`.
- `event_count`: eventos não cancelados armazenados localmente.
- `calendar_api_reachable` / `api_reachable`: resultado do ping leve às APIs do Google.
- `webhook_queue.queue_depth`: total de entradas em `DriveChangeLog`, útil para detectar backlog.
- `webhook_queue.oldest_event_age_seconds`: idade, em segundos, do evento mais antigo na fila.
- `issues`: lista de motivos para status degradado ou indisponível.

### Regras de status

- `healthy`: métricas normais, conectividade OK e fila de webhooks sob controle.
- `degraded`: ausência de canais ativos, falta de sincronização recente, falha de conectividade ou fila muito profunda.
- `unhealthy`: reservado para falhas críticas; as rotas atuais não marcam este estado automaticamente.
