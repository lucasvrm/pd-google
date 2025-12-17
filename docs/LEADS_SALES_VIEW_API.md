# Sales View API (/api/leads/sales-view)

Este documento descreve o contrato atual do endpoint de leitura de leads agregados usado na visão comercial.

## Método e rota
- **GET** `/api/leads/sales-view`
- Retorna lista paginada de leads com campos normalizados (tags, owner, contatos, prioridade e próxima ação).
- **Importante:** Por padrão, leads com `deleted_at` **ou** `qualified_at` preenchido são automaticamente excluídos dos resultados. Isso garante que apenas leads ativos apareçam na visão comercial.

## Parâmetros de query
- `page` (int, padrão `1`, >= 1): página solicitada.
- `pageSize` (int, padrão `20`, 1-100): tamanho de página (camelCase aceito).
- `page_size` (int, opcional, 1-100): alias em snake_case; se informado, substitui `pageSize`.
- `owner`, `ownerIds`, `owners`, `owner_id`, `owner_user_id` (string CSV): filtros equivalentes de owner; todos são combinados. O valor especial `me` é resolvido para o usuário autenticado (headers `Authorization` ou `x-user-id`).
- `status` (string CSV): filtro por status.
- `origin` (string CSV): filtro por origens.
- `priority` (string CSV): filtro por buckets de prioridade (ex.: `hot,warm,cold`).
- `min_priority_score` (int, opcional): filtra por score mínimo.
- `has_recent_interaction` (bool, opcional): filtra leads com interação recente.
- `next_action` (string CSV, opcional): filtra pelas próximas ações calculadas no backend.
  - Aceita lista separada por vírgula (`prepare_for_meeting,call_again`), com trim e deduplicação automáticos.
  - Aplica lógica de OR (IN) diretamente no SQL, reutilizando o mesmo CASE de ranking usado em `order_by=next_action`.
- `includeQualified` (bool, opcional, padrão `false`): quando `true`, inclui leads qualificados e/ou soft-deleted na resposta. Útil para auditoria e debug. Alias: `include_qualified` (snake_case).
- `order_by` (string, padrão `priority`): campo de ordenação. Valores suportados:
  - `priority`: ordena por score de prioridade (maior primeiro por padrão)
  - `last_interaction`: ordena por data da última interação (mais recente primeiro por padrão)
  - `created_at`: ordena por data de criação (mais recente primeiro por padrão)
  - `status`: ordena por `LeadStatus.sort_order` (menor = mais urgente por padrão). Dentro do mesmo status, leads são ordenados por `created_at` (mais recente primeiro) como tie-breaker para ordenação determinística.
  - `owner`: ordena por nome do responsável (User.name) em ordem alfabética
  - `next_action`: ordena por urgência da próxima ação sugerida, usando ranking:
     1. `prepare_for_meeting` - Reunião futura agendada
     2. `post_meeting_follow_up` - Follow-up pós-reunião (meeting recente sem interação posterior)
     3. `call_first_time` - Nenhuma interação registrada
     4. `handoff_to_deal` - Empresa qualificada sem deal vinculado
     5. `qualify_to_company` - Alto engajamento sem empresa qualificada
     6. `schedule_meeting` - Engajamento médio+ sem reunião agendada
     7. `call_again` - Ligação recente que precisa de follow-up (requer campo last_call_at)
     8. `send_value_asset` - Lead engajado sem material de valor recente (requer campo last_value_asset_at)
     9. `send_follow_up` - Interação stale (>=5 dias, <30 dias)
    10. `reengage_cold_lead` - Lead frio (>=30 dias sem interação)
    11. `disqualify` - Muito tempo sem interação, baixo engajamento, sem empresa/deal
    12. `send_follow_up` - Manter relacionamento ativo (default)
  - Prefixe com `-` para ordem decrescente (ex.: `-priority`, `-status`)
- `filters` (string, opcional): JSON serializado usado para filtros adicionais externos.

## Resposta de sucesso
Estrutura geral:
```json
{
  "data": [LeadSalesViewItem],
  "pagination": {
    "total": number,
    "per_page": number,
    "page": number
  }
}
```

Exemplo real:
```json
{
  "data": [
    {
      "id": "lead1",
      "legal_name": "Big Deal",
      "trade_name": "Big Deal Trade",
      "lead_status_id": "new",
      "lead_origin_id": "inbound",
      "owner_user_id": "user1",
      "owner": { "id": "user1", "name": "Test User" },
      "priority_score": 50,
      "priority_bucket": "warm",
      "last_interaction_at": "2025-12-11T22:55:13.252756Z",
      "qualified_master_deal_id": null,
      "address_city": null,
      "address_state": null,
      "tags": [ { "id": "tag1", "name": "Urgente", "color": "#ff0000" } ],
      "primary_contact": { "id": "contact1", "name": "João Silva", "role": "CEO" },
      "priority_description": "Prioridade média",
      "next_action": {
        "code": "call_first_time",
        "label": "Fazer primeira ligação",
        "reason": "Lead novo sem interação"
      }
    }
  ],
  "pagination": { "total": 1, "per_page": 10, "page": 1 }
}
```

### Possíveis valores de next_action

| Código | Label | Descrição |
|--------|-------|-----------|
| `prepare_for_meeting` | "Preparar para reunião" | Reunião futura agendada |
| `post_meeting_follow_up` | "Follow-up pós-reunião" | Reunião ocorreu recentemente sem interação posterior |
| `call_first_time` | "Fazer primeira ligação" | Lead sem nenhuma interação |
| `handoff_to_deal` | "Fazer handoff (para deal)" | Empresa qualificada mas sem deal vinculado |
| `qualify_to_company` | "Qualificar para empresa" | Alto engajamento sem empresa qualificada |
| `schedule_meeting` | "Agendar reunião" | Engajamento médio+ sem reunião agendada |
| `call_again` | "Ligar novamente" | Ligação recente dentro da janela de follow-up |
| `send_value_asset` | "Enviar material / valor" | Lead engajado sem material de valor recente |
| `send_follow_up` | "Enviar follow-up" | Interação stale ou manter relacionamento ativo |
| `reengage_cold_lead` | "Reengajar lead frio" | Lead muito tempo sem interação (>=30 dias) |
| `disqualify` | "Desqualificar / encerrar" | Lead muito antigo, baixo engajamento, sem qualificação |
```

## primary_contact
O campo `primary_contact` é preenchido a partir da tabela `lead_contacts`:
- **Prioridade 1:** Contato com `is_primary=true`
- **Prioridade 2 (fallback):** Primeiro contato vinculado (ordenado por `added_at`)
- **Sem contatos:** Retorna `null`

Estrutura do objeto:
```json
{
  "id": "uuid-do-contato",
  "name": "Nome do Contato",
  "role": "Cargo (opcional)"
}
```

## Erros
Todos os erros seguem a convenção global de `/api`:

### Validação de parâmetros
- **Status:** 422
- **Body:**
```json
{
  "error": "Validation error",
  "code": "validation_error",
  "details": [ { "loc": ["query", "page"], "msg": "Input should be greater than or equal to 1", "type": "greater_than_equal" } ]
}
```

### Falha interna da Sales View
- **Status:** 500
- **Body:**
```json
{
  "error": "sales_view_error",
  "code": "sales_view_error",
  "message": "Failed to build sales view"
}
```

## Notas adicionais
- Os campos complexos já chegam normalizados pelo backend: `tags` como objetos `{id,name,color}`, `owner` como objeto simples, `primary_contact` com `id`/`name`/`role`, `priority_description` derivada do bucket e `next_action` com `code`/`label`/`reason`.
- Métricas e logs estruturados do endpoint estão descritos em [`docs/SALES_VIEW_OBSERVABILITY.md`](./SALES_VIEW_OBSERVABILITY.md).
- **Documentação completa de Next Actions:** Para detalhamento de regras, precedência, campos influenciadores e checklist de QA, consulte [`docs/backend/next_actions.md`](./backend/next_actions.md).
- **Filtragem de Leads Ativos:** Por padrão, leads com `deleted_at` **ou** `qualified_at` preenchido são automaticamente excluídos da resposta. Isso garante que apenas leads ativos (não qualificados e não deletados) apareçam na visão comercial. Para incluir leads qualificados/deletados (útil para auditoria/debug), use o parâmetro `includeQualified=true`. Consulte [`SOFT_DELETE_IMPLEMENTATION.md`](../SOFT_DELETE_IMPLEMENTATION.md) para mais detalhes.
