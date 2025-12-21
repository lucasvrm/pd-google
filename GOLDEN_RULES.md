# GOLDEN_RULES.md — Backend (pd-google / FastAPI + Python 3.12)

Regras para escrever prompts de **GitHub Copilot Agent Session** focados no backend `pd-google` (Python 3.12 + FastAPI + SQLAlchemy + PostgreSQL/Supabase). Mantém o mesmo espírito do frontend, mas com testes e riscos orientados a serviços e dados.

## 0) Princípio central
Prompt bom = **menos texto, mais decisões executáveis**:
- objetivo claro
- guardrails explícitos
- tarefas em ordem (curtas)
- critérios de aceite verificáveis
- testes + checklist
- formato de entrega padronizado

---

## 1) Sempre declarar BE no topo
Todo prompt deve começar assim:

```md
## 📍 BACKEND
Repo: `owner/pd-google`
```

Proibido misturar FE e BE no mesmo prompt. Se envolver ambos, **separe em prompts distintos**.

---

## 2) Primeira tarefa obrigatória (sempre)
A primeira seção do prompt deve obrigar:

```md
### ⚠️ Primeira tarefa obrigatória
1) Ler e seguir 100%: `AGENTS.md` e `GOLDEN_RULES.md` (raiz do repo).
2) Confirmar arquivos-alvo e pontos de reuso antes de codar.
```

---

## 3) Guardrails (hard constraints) — default
Liste explicitamente o que **não pode mudar** (salvo pedido explícito do usuário):

- ❌ Não alterar **contratos de API** (endpoints, verbos, payloads, shape de request/response)
- ❌ Não alterar **lógica de negócio** (regras, validações, cálculos)
- ❌ Não adicionar **libs novas** (a menos que o usuário peça)
- ❌ Não fazer “refactor por refactor”
- ❌ Não usar workarounds de dados no cliente (consertar na origem: queries/serviços)
- ✅ Mudanças **localizadas**, com reuso do que já existe

Se o pedido exigir mudança de API, ver regra 6.

---

## 4) Regra de complexidade (evitar prompts grandes)
Inclua **Complexidade estimada** (0–100) e obedeça:
- Se **> 85**, dividir em múltiplos prompts por responsabilidade/risco.

Heurística rápida:
- muitos arquivos, refactor estrutural, ou mudanças cruzando vários serviços = alta complexidade
- prefira 1 prompt por “unidade revisável” (um PR pequeno e seguro)

---

## 5) Estrutura do corpo do prompt (curta e executável)
Use a sequência:

1) **Resumo (2–4 bullets)**
2) **Mudanças solicitadas (4–8 itens, em ordem)**  
   - subtarefas curtas, citar arquivos-alvo e reuso (“reusar schema X do módulo Y”)
3) **Critérios de aceite (asserts verificáveis)**
4) **Testes + checklist**

Se virar ensaio, está grande demais.

---

## 6) API: quando (e como) pode mudar
Default: **não mudar contrato**.

Se (e somente se) o prompt exigir mudança de API, deve ser:
- ✅ **Aditiva** (backwards compatible)
- ✅ Campos novos opcionais / endpoints novos versionados
- ❌ Nunca remover/renomear campos existentes
- ❌ Nunca mudar tipo de campo (ex.: `string` → `number`)

---

## 7) Testes e validação (obrigatório)
Todo prompt deve exigir:
- rodar lint/typecheck/tests
- adicionar/ajustar testes quando houver mudança de comportamento/contrato
- checklist manual mínimo (fluxo principal + 1–2 edge cases)

Templates (ajuste conforme serviço):

```sh
pytest -v
flake8 .
mypy .
```

Se houver tasks de ETL/streaming, inclua testes/validações específicas de dados.

---

## 8) Evitar screenshots locais
Não exigir screenshots locais: ambientes do agente podem não renderizar ou ter dependências externas. Validar por testes, logs e inspeção de código/JSON.

---

## 9) Formato de entrega do agente (obrigatório)
O prompt deve obrigar o agente a encerrar com:

- Resumo do que foi feito (5–10 bullets)
- Lista de arquivos alterados/criados/removidos
- Comandos executados + resultados
- Riscos/edge cases + rollback simples
- ROADMAP final (solicitado vs implementado)

Template curto de ROADMAP final:

```md
### 📝 ROADMAP Final

| Item | Status | Observações |
|---|---|---|
| 1 | ✅ | ... |
| 2 | ⚠️ | adaptado: ... |
| 3 | ❌ | fora do escopo: ... |

Legenda: ✅ feito / ⚠️ adaptado / ❌ não feito
```

---

## 10) Esqueleto único (copiar/colar)
Todo prompt deve ser um único bloco Markdown seguindo esta ordem:

```md
# 🎯 Prompt para Agent Session — <título curto>

## 📍 BACKEND
Repo: `owner/pd-google`
Área/Rota: <...>
Escopo: <...>
Fora de escopo: <...>

## Guardrails (hard constraints)
- ...

### ⚠️ Primeira tarefa obrigatória
1) Ler `AGENTS.md` e `GOLDEN_RULES.md` e seguir 100%.
2) Confirmar arquivos-alvo e reuso.

## Resumo
- ...
- ...

## Mudanças solicitadas (ordem)
1) ...
2) ...
3) ...

## Critérios de aceite
1) ...
2) ...

## Testes
- Ajustar/remover:
- Criar/atualizar:
- Comandos:

## Checklist manual
- ...

## Formato de entrega do agente
- (itens obrigatórios + ROADMAP final)
```

---

## 11) Atualização do documento
Atualize este arquivo quando novas “lições aprendidas” surgirem (incident/review) e mantenha-o curto.

---

## 12) Prevenir Erro 310 (hooks sempre no topo do componente)

Embora o backend Python não use hooks de React, mantenha esta regra para consistência entre repositórios (útil para trechos de UI compartilhados ou referências cruzadas). Se precisar editar componentes React/TypeScript (ex.: dashboards ou scripts de UI), siga rigorosamente:

**Regra obrigatória:** toda a ordem de escrita do componente deve evitar hooks após condicionais/returns.

✅ **FAÇA (sempre nesta ordem):**
1. Imports
2. Hooks de dados (useQuery, useMutation, custom hooks)
3. `useMemo`
4. `useCallback`
5. `useState`
6. `useEffect` (se houver)
7. Condicionais e *early returns*
8. Funções normais (handlers sem `useCallback`)
9. Variáveis derivadas
10. JSX `return`

❌ **NÃO FAÇA (gera Erro #310):**

```tsx
// Hook depois de condicional
if (!lead) return <div>Loading</div>
const data = useMemo(() => ...) // ← ERRO #310

// Hook dentro de condicional
if (someCondition) {
  const [state, setState] = useState() // ← ERRO #310
}

// Hook dentro de função/callback
const handleClick = () => {
  const data = useMemo(() => ...) // ← ERRO #310
}
```

✅ **FAÇA:**

```tsx
// Hooks primeiro
const data = useMemo(() => ...)
const [state, setState] = useState()

// Depois condicionais/returns
if (!lead) return <div>Loading</div>

// Depois funções normais
const handleClick = () => {
  // usar state, data, etc.
}
```

🔍 **Como encontrar o problema:**
- Procure por `useCallback`, `useMemo`, `useState`, `useEffect`.
- Verifique se algum aparece **depois** de `if (...) return ...` ou dentro de condicionais/funções.
- Mova **todos** os hooks para o topo do componente.

📝 **Checklist de correção:**
- [ ] Todos os `useState` no topo.
- [ ] Todos os `useMemo` no topo.
- [ ] Todos os `useCallback` no topo.
- [ ] Todos os `useEffect` no topo.
- [ ] Hooks de biblioteca (`useQuery`, etc.) no topo.
- [ ] Nenhum hook depois de `if (...)` ou `return`.
- [ ] Nenhum hook dentro de condicionais.
- [ ] Nenhum hook dentro de funções/callbacks.
