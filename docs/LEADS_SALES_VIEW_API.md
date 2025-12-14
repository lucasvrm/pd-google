# Sales View API (/api/leads/sales-view)

Este documento descreve o contrato atual do endpoint de leitura de leads agregados usado na visão comercial.

## Método e rota
- **GET** `/api/leads/sales-view`
- Retorna lista paginada de leads com campos normalizados (tags, owner, contatos, prioridade e próxima ação).

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
- `order_by` (string, padrão `priority`): campo de ordenação. Valores suportados:
  - `priority`: ordena por score de prioridade (maior primeiro por padrão)
  - `last_interaction`: ordena por data da última interação (mais recente primeiro por padrão)
  - `created_at`: ordena por data de criação (mais recente primeiro por padrão)
  - `status`: ordena por `LeadStatus.sort_order` (menor = mais urgente por padrão)
  - `owner`: ordena por nome do responsável (User.name) em ordem alfabética
  - `next_action`: ordena por urgência da próxima ação sugerida, usando ranking:
    1. `prepare_for_meeting` (reunião futura agendada)
    2. `call_first_time` (nenhuma interação registrada)
    3. `qualify_to_company` (alto engajamento sem empresa qualificada)
    4. `send_follow_up` (interação antiga/stale)
    5. `send_follow_up` (manter relacionamento ativo)
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
