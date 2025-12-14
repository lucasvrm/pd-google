# Next Actions — Guia de Regras e Precedência

Este documento descreve as regras de sugestão de **next_action** (próxima ação) para leads, utilizadas no endpoint `/api/leads/sales-view`. O objetivo é orientar vendedores sobre qual ação tomar com cada lead, baseado em engajamento, timing e estado de qualificação.

---

## Sumário

1. [Visão Geral](#visão-geral)
2. [Lista de Next Actions](#lista-de-next-actions)
3. [Campos Influenciadores](#campos-influenciadores)
4. [Parâmetros de Configuração](#parâmetros-de-configuração)
5. [Detalhamento por Regra](#detalhamento-por-regra)
6. [Precedência Final](#precedência-final)
7. [Exemplos de Retorno](#exemplos-de-retorno)
8. [Como Testar](#como-testar)
9. [Checklist de QA Manual](#checklist-de-qa-manual)

---

## Visão Geral

O serviço `next_action_service.py` analisa os dados de cada lead e suas estatísticas de atividade (`LeadActivityStats`) para sugerir a próxima ação mais urgente. As regras são avaliadas em ordem de **precedência** (1 = mais urgente), e a primeira regra que se aplica define o resultado.

**Formato da resposta:**
```json
{
  "code": "string",       // Identificador técnico da ação
  "label": "string",      // Label em PT-BR para exibição na UI
  "reason": "string"      // Explicação do motivo da sugestão
}
```

---

## Lista de Next Actions

Existem **11 códigos únicos** de next_action. A precedência 12 é um fallback que reutiliza o código `send_follow_up`.

| Precedência | Code | Label (PT-BR) | Descrição |
|:-----------:|------|---------------|-----------|
| 1 | `prepare_for_meeting` | Preparar para reunião | Reunião futura agendada |
| 2 | `post_meeting_follow_up` | Follow-up pós-reunião | Reunião recente sem interação posterior |
| 3 | `call_first_time` | Fazer primeira ligação | Lead sem nenhuma interação |
| 4 | `handoff_to_deal` | Fazer handoff (para deal) | Empresa qualificada sem deal vinculado |
| 5 | `qualify_to_company` | Qualificar para empresa | Alto engajamento sem empresa qualificada |
| 6 | `schedule_meeting` | Agendar reunião | Engajamento médio+ sem reunião agendada |
| 7 | `call_again` | Ligar novamente | Ligação recente dentro da janela de follow-up |
| 8 | `send_value_asset` | Enviar material / valor | Lead engajado sem material de valor recente |
| 9 | `send_follow_up` | Enviar follow-up | Interação stale (5–29 dias) |
| 10 | `reengage_cold_lead` | Reengajar lead frio | Lead frio (30–59 dias sem interação) |
| 11 | `disqualify` | Desqualificar / encerrar | Muito tempo sem interação + baixo engajamento |
| 12 | `send_follow_up` | Enviar follow-up | **Default** (manter relacionamento ativo) |

**Nota:** Os códigos das precedências 9 e 12 são iguais (`send_follow_up`), mas a precedência 9 é acionada por critérios específicos (interação stale 5–29 dias), enquanto a 12 é o comportamento padrão quando nenhuma outra regra se aplica.

---

## Campos Influenciadores

### Do modelo `Lead`

| Campo | Tipo | Uso nas Regras |
|-------|------|----------------|
| `created_at` | datetime | Idade do lead (para `call_first_time`) |
| `qualified_company_id` | string/null | Regras 4, 5, 11 (qualificação) |
| `qualified_master_deal_id` | string/null | Regras 4, 11 (deal vinculado) |
| `disqualified_at` | datetime/null | Regras 4, 11 (lead já encerrado) |
| `last_interaction_at` | datetime/null | Fallback se não existir em stats |

### Do modelo `LeadActivityStats`

| Campo | Tipo | Uso nas Regras |
|-------|------|----------------|
| `engagement_score` | int (0–100) | Regras 5, 6, 8, 11 |
| `last_interaction_at` | datetime/null | Dias desde última interação (regras 9–11) |
| `last_event_at` | datetime/null | Reunião passada ou futura (regras 1, 2, 6) |
| `next_scheduled_event_at` | datetime/null | Reunião futura (regra 1, 6) |
| `last_call_at` | datetime/null | Última ligação (regra 7) – campo opcional |
| `last_value_asset_at` | datetime/null | Último material enviado (regra 8) – campo opcional |

---

## Parâmetros de Configuração

Os thresholds são constantes definidas em `next_action_service.py`:

| Constante | Valor | Descrição |
|-----------|:-----:|-----------|
| `STALE_INTERACTION_DAYS` | 5 | Dias para considerar interação "stale" |
| `HIGH_ENGAGEMENT_SCORE` | 70 | Score mínimo para "alto engajamento" |
| `MEDIUM_ENGAGEMENT_SCORE` | 40 | Score mínimo para "engajamento médio" |
| `NEW_LEAD_MAX_AGE_DAYS` | 14 | Dias máx. para considerar lead "novo" |
| `SCHEDULE_MEETING_ENGAGEMENT_THRESHOLD` | 50 | Score mínimo para sugerir agendar reunião |
| `CALL_AGAIN_WINDOW_DAYS` | 7 | Janela de dias para "ligar novamente" |
| `VALUE_ASSET_STALE_DAYS` | 14 | Dias para material de valor ficar "stale" |
| `POST_MEETING_WINDOW_DAYS` | 3 | Janela de dias após reunião para follow-up |
| `COLD_LEAD_DAYS` | 30 | Dias sem interação para lead "frio" |
| `DISQUALIFY_DAYS` | 60 | Dias sem interação para considerar desqualificação |

---

## Detalhamento por Regra

### Precedência 1: `prepare_for_meeting`

**Critério:** Existe evento futuro agendado (`next_scheduled_event_at > now` OU `last_event_at > now`).

**Motivo retornado:** `"Reunião futura agendada para {data}"`

**Campos utilizados:**
- `LeadActivityStats.next_scheduled_event_at`
- `LeadActivityStats.last_event_at`

---

### Precedência 2: `post_meeting_follow_up`

**Critério:**
1. Evento passado ocorreu nos últimos 3 dias (`last_event_at <= now` e `days_since_meeting <= POST_MEETING_WINDOW_DAYS`)
2. Sem interação posterior ao evento (`last_interaction_at is null` OU `last_interaction_at <= last_event_at`)

**Motivo retornado:** `"Reunião ocorrida há {N} dia(s), sem interação posterior"`

**Campos utilizados:**
- `LeadActivityStats.last_event_at`
- `LeadActivityStats.last_interaction_at` (ou `Lead.last_interaction_at` como fallback)

---

### Precedência 3: `call_first_time`

**Critério:** Nenhuma interação registrada (`last_interaction is None`).

**Motivo retornado:**
- `"Lead novo sem interação"` (se `lead_age_days <= 14`)
- `"Nenhuma interação registrada"` (se mais antigo)

**Campos utilizados:**
- `LeadActivityStats.last_interaction_at`
- `Lead.last_interaction_at` (fallback)
- `Lead.created_at`

---

### Precedência 4: `handoff_to_deal`

**Critério:**
1. Tem empresa qualificada (`qualified_company_id is not null`)
2. Não tem deal vinculado (`qualified_master_deal_id is null`)
3. Não foi desqualificado (`disqualified_at is null`)

**Motivo retornado:** `"Empresa qualificada sem deal vinculado"`

**Campos utilizados:**
- `Lead.qualified_company_id`
- `Lead.qualified_master_deal_id`
- `Lead.disqualified_at`

---

### Precedência 5: `qualify_to_company`

**Critério:**
1. Engajamento alto (`engagement_score >= 70`)
2. Sem empresa qualificada (`qualified_company_id is null`)

**Motivo retornado:** `"Engajamento alto ({score}) sem empresa qualificada"`

**Campos utilizados:**
- `LeadActivityStats.engagement_score`
- `Lead.qualified_company_id`

---

### Precedência 6: `schedule_meeting`

**Critério:**
1. Engajamento médio-alto (`engagement_score >= 50`)
2. Sem reunião futura agendada

**Motivo retornado:** `"Engajamento médio-alto ({score}) sem reunião agendada"`

**Campos utilizados:**
- `LeadActivityStats.engagement_score`
- `LeadActivityStats.next_scheduled_event_at`
- `LeadActivityStats.last_event_at`

---

### Precedência 7: `call_again`

**Critério:**
1. Campo `last_call_at` existe
2. Última ligação foi há no máximo 7 dias

**Motivo retornado:** `"Última ligação há {N} dia(s)"`

**Campos utilizados:**
- `LeadActivityStats.last_call_at` (campo opcional)

**Nota:** Esta regra só se aplica se o campo `last_call_at` estiver disponível no schema do banco.

---

### Precedência 8: `send_value_asset`

**Critério:**
1. Engajamento médio+ (`engagement_score >= 40`)
2. `last_value_asset_at` é null OU há mais de 14 dias

**Motivo retornado:**
- `"Lead engajado sem material de valor enviado"` (se nunca enviou)
- `"Último material enviado há {N} dias"` (se stale)

**Campos utilizados:**
- `LeadActivityStats.engagement_score`
- `LeadActivityStats.last_value_asset_at` (campo opcional)

---

### Precedência 9: `send_follow_up`

**Critério:**
1. Dias sem interação >= 5 e < 30
2. Não se aplica nenhuma das regras anteriores

**Motivo retornado:** `"Última interação há {N} dias"`

**Campos utilizados:**
- `LeadActivityStats.last_interaction_at`

---

### Precedência 10: `reengage_cold_lead`

**Critério:**
1. Dias sem interação >= 30 e < 60
2. Não se aplica nenhuma das regras anteriores

**Motivo retornado:** `"Sem interação há {N} dias"`

**Campos utilizados:**
- `LeadActivityStats.last_interaction_at`

---

### Precedência 11: `disqualify`

**Critério:**
1. Dias sem interação >= 60
2. Engajamento baixo (`engagement_score < 40`)
3. Sem empresa qualificada (`qualified_company_id is null`)
4. Sem deal vinculado (`qualified_master_deal_id is null`)
5. Não desqualificado (`disqualified_at is null`)

**Motivo retornado:** `"Sem interação há {N} dias, engajamento baixo ({score})"`

**Campos utilizados:**
- `LeadActivityStats.last_interaction_at`
- `LeadActivityStats.engagement_score`
- `Lead.qualified_company_id`
- `Lead.qualified_master_deal_id`
- `Lead.disqualified_at`

---

### Precedência 12: `send_follow_up` (default)

**Critério:** Nenhuma das regras anteriores se aplica.

**Motivo retornado:** `"Manter relacionamento ativo"`

---

## Precedência Final

```
1. prepare_for_meeting     → Reunião futura
2. post_meeting_follow_up  → Reunião recente, sem follow-up
3. call_first_time         → Sem interação nenhuma
4. handoff_to_deal         → Empresa OK, falta deal
5. qualify_to_company      → Engajamento alto, falta empresa
6. schedule_meeting        → Engajamento médio+, sem reunião
7. call_again              → Ligou recentemente (se campo existe)
8. send_value_asset        → Falta material de valor (se campo existe)
9. send_follow_up          → Interação stale (5–29 dias)
10. reengage_cold_lead     → Lead frio (30–59 dias)
11. disqualify             → Muito tempo + baixo engajamento
12. send_follow_up         → Default
```

---

## Exemplos de Retorno

### Exemplo 1: Reunião futura agendada
```json
{
  "code": "prepare_for_meeting",
  "label": "Preparar para reunião",
  "reason": "Reunião futura agendada para 2025-12-20"
}
```

### Exemplo 2: Lead novo sem interação
```json
{
  "code": "call_first_time",
  "label": "Fazer primeira ligação",
  "reason": "Lead novo sem interação"
}
```

### Exemplo 3: Empresa qualificada sem deal
```json
{
  "code": "handoff_to_deal",
  "label": "Fazer handoff (para deal)",
  "reason": "Empresa qualificada sem deal vinculado"
}
```

### Exemplo 4: Lead frio (45 dias sem interação)
```json
{
  "code": "reengage_cold_lead",
  "label": "Reengajar lead frio",
  "reason": "Sem interação há 45 dias"
}
```

### Exemplo 5: Desqualificar lead
```json
{
  "code": "disqualify",
  "label": "Desqualificar / encerrar",
  "reason": "Sem interação há 75 dias, engajamento baixo (20)"
}
```

---

## Como Testar

### Ordenação por next_action (mais urgente primeiro)

```bash
curl -X GET "http://localhost:8000/api/leads/sales-view?order_by=next_action"
```

Leads com ações mais urgentes (prepare_for_meeting, post_meeting_follow_up, etc.) aparecem primeiro.

---

### Ordenação por next_action invertida (menos urgente primeiro)

```bash
curl -X GET "http://localhost:8000/api/leads/sales-view?order_by=-next_action"
```

Leads com ações menos urgentes (send_follow_up default, disqualify) aparecem primeiro.

---

### Filtrar leads sem interação há N dias + ordenar por next_action

```bash
curl -X GET "http://localhost:8000/api/leads/sales-view?order_by=next_action&days_without_interaction=14"
```

Retorna leads sem interação há pelo menos 14 dias, ordenados por urgência da next_action.

---

### Combinação com outros filtros

```bash
# Leads do owner específico ordenados por next_action
curl -X GET "http://localhost:8000/api/leads/sales-view?order_by=next_action&owner=<user_id>"

# Leads "hot" ordenados por next_action
curl -X GET "http://localhost:8000/api/leads/sales-view?order_by=next_action&priority=hot"

# Leads com status específico
curl -X GET "http://localhost:8000/api/leads/sales-view?order_by=next_action&status=<status_id>"
```

---

## Checklist de QA Manual

Use este checklist para validar manualmente o comportamento do endpoint:

### Pré-requisitos
- [ ] Ambiente de desenvolvimento/staging configurado
- [ ] Banco de dados com leads de teste (variados cenários)
- [ ] Acesso ao endpoint (autenticação se necessária)

### Validação da Ordenação

- [ ] **Teste 1:** `?order_by=next_action` retorna leads ordenados do mais urgente ao menos urgente
  - Verificar: leads com `prepare_for_meeting` aparecem antes de `call_first_time`
  - Verificar: leads com `call_first_time` aparecem antes de `send_follow_up`

- [ ] **Teste 2:** `?order_by=-next_action` inverte a ordem
  - Verificar: leads com `send_follow_up` (default) aparecem primeiro
  - Verificar: leads com `prepare_for_meeting` aparecem por último

### Validação dos Critérios

- [ ] **Teste 3:** Lead com evento futuro retorna `prepare_for_meeting`
  - Criar/usar lead com `next_scheduled_event_at > now`
  - Verificar `code == "prepare_for_meeting"`

- [ ] **Teste 4:** Lead sem interação retorna `call_first_time`
  - Criar/usar lead com `last_interaction_at = null`
  - Verificar `code == "call_first_time"`

- [ ] **Teste 5:** Lead com empresa sem deal retorna `handoff_to_deal`
  - Lead com `qualified_company_id != null` e `qualified_master_deal_id = null`
  - Verificar `code == "handoff_to_deal"`

- [ ] **Teste 6:** Lead com engagement >= 70 sem empresa retorna `qualify_to_company`
  - Lead com `engagement_score >= 70` e `qualified_company_id = null`
  - Verificar `code == "qualify_to_company"`

- [ ] **Teste 7:** Lead frio (30+ dias) retorna `reengage_cold_lead`
  - Lead com última interação há 30–59 dias
  - Verificar `code == "reengage_cold_lead"`

- [ ] **Teste 8:** Lead muito antigo + baixo engajamento retorna `disqualify`
  - Lead com última interação há 60+ dias, `engagement_score < 40`, sem empresa/deal
  - Verificar `code == "disqualify"`

### Validação de Filtros Combinados

- [ ] **Teste 9:** `?days_without_interaction=14&order_by=next_action`
  - Retorna apenas leads sem interação há 14+ dias
  - Ordenação por urgência funciona corretamente

- [ ] **Teste 10:** `?priority=hot&order_by=next_action`
  - Retorna apenas leads com priority_score >= 70
  - Ordenação por urgência funciona corretamente

### Validação da Resposta

- [ ] **Teste 11:** Cada item retorna `next_action` com estrutura correta
  - Campos: `code`, `label`, `reason`
  - `code` é um dos 11 valores únicos válidos (nota: `send_follow_up` pode vir de precedência 9 ou 12)
  - `label` está em português
  - `reason` explica o motivo

- [ ] **Teste 12:** Paginação funciona corretamente
  - `?page=1&pageSize=10` retorna até 10 items
  - `pagination.total` reflete o total de leads filtrados

---

## Notas de Implementação

### SQL vs Python

O endpoint implementa a ordenação por `next_action` de duas formas:

1. **SQL (CASE):** Para ordenação eficiente no banco, usa um `CASE` que mapeia as condições principais para ranks numéricos (1–12). Isso permite ordenação rápida sem carregar todos os leads em memória. A precedência 12 é o fallback default. **Todos os 12 ranks (1–12) estão implementados no SQL, incluindo rank 7 (call_again) e rank 8 (send_value_asset).**

2. **Python (next_action_service):** Para cada lead retornado, a função `suggest_next_action()` é chamada para calcular o `next_action` exato com o `reason` detalhado.

**Nota sobre códigos duplicados:** O código `send_follow_up` aparece em duas precedências (9 e 12). A precedência 9 é acionada quando há interação stale (5–29 dias), enquanto a 12 é o fallback quando nenhuma outra regra se aplica. O `reason` retornado diferencia os casos.

### Campos para Ranks 7-8

As regras 7 (`call_again`) e 8 (`send_value_asset`) dependem dos seguintes campos no modelo `LeadActivityStats`:

- `last_call_at` (timestamptz) — Se NULL, a condição do rank 7 falha e passa para o próximo rank
- `last_value_asset_at` (timestamptz) — Se NULL e engagement >= 40, dispara rank 8 (lead engajado sem material enviado)

Esses campos são adicionados idempotentemente pela migration `ensure_leads_schema_v3.sql`.

### Constantes Importadas

O arquivo `routers/leads.py` importa as seguintes constantes do `services/next_action_service.py`:

- `CALL_AGAIN_WINDOW_DAYS` (7) — Janela de dias para considerar "ligar novamente"
- `VALUE_ASSET_STALE_DAYS` (14) — Dias para material de valor ficar "stale"
- `COLD_LEAD_DAYS`, `DISQUALIFY_DAYS`, `STALE_INTERACTION_DAYS` — Para outras regras
- `HIGH_ENGAGEMENT_SCORE`, `MEDIUM_ENGAGEMENT_SCORE`, `SCHEDULE_MEETING_ENGAGEMENT_THRESHOLD` — Thresholds de engajamento
- `POST_MEETING_WINDOW_DAYS` — Janela pós-reunião

---

*Última atualização: Sprint 4 — Dezembro 2025*
