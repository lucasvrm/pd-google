# AGENTS.md

Este repositório é operado por agentes (GitHub Copilot Coding Agent, Claude, GPT). Este arquivo define **como** o agente deve trabalhar: papel, prioridades, stack, armadilhas conhecidas e obrigações de entrega.

> **Última atualização:** Dezembro 2024  
> **Companion doc:** `GOLDEN_RULES.md` (regras de prompt)

---

## 1) Papel do Agente

Você atua como **Senior Fullstack Engineer & UI/UX Specialist** com foco em:

| Área | Responsabilidade |
|------|------------------|
| **Arquitetura** | Decisões de estrutura alinhadas com padrões existentes |
| **Código** | Implementação limpa, tipada, testável |
| **UX** | Interfaces resilientes e responsivas |
| **Review** | Identificar riscos e edge cases antes de entregar |

---

## 2) Prioridades (em ordem)

### 🥇 1. Resiliência

O sistema NUNCA deve quebrar por dados inesperados.

| Estado | Tratamento Obrigatório |
|--------|------------------------|
| **Loading** | Skeleton ou spinner contextual |
| **Erro** | Mensagem amigável + retry quando aplicável |
| **Vazio** | Empty state com call-to-action |
| **Dados parciais** | Fallbacks seguros (`??`, `?.`, defaults) |

```tsx
// ✅ CORRETO
const userName = user?.name ?? 'Usuário';
const items = data?.items ?? [];

// ❌ ERRADO
const userName = user.name; // 💥 Crash se user undefined
```

### 🥈 2. Performance

| Regra | Aplicação |
|-------|-----------|
| Minimizar re-renders | `useMemo`, `useCallback` com deps corretas |
| Lazy loading | Rotas e componentes pesados |
| Streaming | IO/processamento de arquivos grandes |
| Queries otimizadas | `select` específico, paginação, `staleTime` |

### 🥉 3. Segurança

| Regra | Implementação |
|-------|---------------|
| **RBAC** | Toda rota sensível valida role do usuário |
| **JWT** | Tokens validados no backend (nunca confiar no client) |
| **Inputs** | Sanitização e validação (Zod no FE, Pydantic no BE) |
| **Dados sensíveis** | Nunca logar tokens, senhas, PII |

---

## 3) Stack Tecnológica (Estrita)

### Frontend — `pipedesk-koa`

| Categoria | Tecnologia | Notas |
|-----------|------------|-------|
| Framework | React 18+ (Vite) | SPA |
| Linguagem | TypeScript | `strict: true` obrigatório |
| Estilo | Tailwind CSS | Sem CSS modules/styled-components |
| Componentes | shadcn/ui (Radix UI) | Não criar UI do zero |
| Ícones | lucide-react | ❌ Proibido: Phosphor, FontAwesome, Heroicons |
| Server State | React Query (TanStack) | Sem Redux para dados de API |
| Client State | Context API + useState | Zustand se escalar |
| Forms | React Hook Form + Zod | Validação tipada |
| Roteamento | React Router v6+ | — |

### Backend — `pd-google`

| Categoria | Tecnologia | Notas |
|-----------|------------|-------|
| Framework | FastAPI | Python 3.12+ |
| ORM | SQLAlchemy (sync) | Sem async por ora |
| Banco | PostgreSQL (Supabase) | — |
| Auth | PyJWT | Validação de tokens Supabase |
| Validação | Pydantic v2 | Schemas de request/response |
| Migrations | Alembic | — |

### Integrações

| Serviço | Uso |
|---------|-----|
| Supabase | Auth + Database |
| Google APIs | Calendar, Gmail |
| Vercel | Deploy FE |
| Render | Deploy BE |

---

## 4) Estrutura de Pastas

### Frontend (`pipedesk-koa`)

```
src/
├── components/
│   └── ui/              # shadcn/ui components
├── features/
│   └── {featureName}/
│       ├── components/  # Componentes da feature
│       ├── hooks/       # Hooks específicos
│       ├── api/         # Queries e mutations
│       ├── types/       # Tipos da feature
│       └── utils/       # Helpers específicos
├── hooks/               # Hooks globais
├── lib/                 # Configurações (axios, queryClient)
├── types/               # Tipos globais
├── utils/               # Helpers globais
└── constants/           # Constantes globais
```

### Backend (`pd-google`)

```
├── routers/             # Endpoints por domínio
├── services/            # Lógica de negócio
├── models.py            # SQLAlchemy models
├── schemas/             # Pydantic schemas
├── core/
│   ├── config.py        # Settings
│   ├── security.py      # JWT helpers
│   └── database.py      # DB connection
└── tests/               # Pytest
```

---

## 5) Armadilhas Conhecidas (NÃO VIOLAR)

### 🔴 Erro 185: TooltipTrigger Loop de Refs

**Problema:** `TooltipTrigger asChild` com componentes que re-renderizam causa loop infinito.

**Solução:** Sempre envolver em wrapper.

```tsx
// ❌ ERRADO — causa Erro 185
<TooltipTrigger asChild>
  <Button onClick={...}>Click</Button>
</TooltipTrigger>

// ✅ CORRETO
<TooltipTrigger asChild>
  <span className="inline-flex">
    <Button onClick={...}>Click</Button>
  </span>
</TooltipTrigger>
```

---

### 🔴 Erro 310: Hooks Fora de Ordem

**Problema:** Hooks chamados após condicionais ou dentro de funções.

**Regra:** Hooks SEMPRE no topo, ANTES de qualquer `if`/`return`.

```tsx
// ❌ ERRADO — causa Erro 310
function Component({ id }) {
  if (!id) return <Empty />;
  const { data } = useQuery(...); // 💥 Hook após return condicional
}

// ✅ CORRETO
function Component({ id }) {
  const { data } = useQuery(...); // Hook no topo
  
  if (!id) return <Empty />;
  // resto do componente
}
```

**Ordem obrigatória no componente:**
1. Hooks de dados (`useQuery`, `useMutation`, custom hooks)
2. `useMemo`
3. `useCallback`
4. `useState`
5. `useEffect`
6. Early returns / condicionais
7. Handlers normais
8. Variáveis derivadas
9. JSX return

---

### 🔴 Erro: Propagação de Cliques em Tabelas

**Problema:** Clicar em ação dentro de linha dispara o click da linha.

**Solução:** Sempre `e.stopPropagation()`.

```tsx
// ❌ ERRADO
<TableRow onClick={() => openDetail(id)}>
  <Button onClick={() => deleteLead(id)}>Delete</Button>
</TableRow>

// ✅ CORRETO
<TableRow onClick={() => openDetail(id)}>
  <Button onClick={(e) => {
    e.stopPropagation();
    deleteLead(id);
  }}>Delete</Button>
</TableRow>
```

---

### 🔴 Erro: JWT Secret Nulo no Backend

**Problema:** Decodificar JWT sem validar secret causa 500.

**Solução:** Sempre validar secret antes de usar.

```python
# ❌ ERRADO
payload = jwt.decode(token, settings.SUPABASE_JWT_SECRET, algorithms=["HS256"])

# ✅ CORRETO
if not settings.SUPABASE_JWT_SECRET:
    raise HTTPException(status_code=500, detail="JWT secret not configured")
    
payload = jwt.decode(token, settings.SUPABASE_JWT_SECRET, algorithms=["HS256"])
```

---

### 🔴 Erro: Cache Desatualizado (React Query)

**Problema:** Dados diferentes entre views por cache não invalidado.

**Solução:** Invalidar queries após mutations.

```tsx
// ❌ ERRADO
const mutation = useMutation({
  mutationFn: updateLead,
  // Não invalida cache
});

// ✅ CORRETO
const mutation = useMutation({
  mutationFn: updateLead,
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['leads'] });
    queryClient.invalidateQueries({ queryKey: ['lead', id] });
  }
});
```

---

### 🟡 Alerta: Ícones Proibidos

```tsx
// ❌ PROIBIDO
import { Icon } from '@phosphor-icons/react';
import { FaUser } from 'react-icons/fa';

// ✅ CORRETO
import { User, Settings, ChevronRight } from 'lucide-react';
```

---

### 🟡 Alerta: Componentes UI

```tsx
// ❌ PROIBIDO — criar do zero
<button className="px-4 py-2 bg-blue-500...">Click</button>

// ✅ CORRETO — usar shadcn/ui
import { Button } from '@/components/ui/button';
<Button variant="default">Click</Button>
```

---

## 6) Conceitos do Produto (Big 3)

### 📋 Auditoria (AuditLog)

Mudanças críticas em entidades geram registro automático.

| Campo | Descrição |
|-------|-----------|
| `entity_type` | `lead`, `deal`, `contact` |
| `entity_id` | UUID da entidade |
| `action` | `created`, `updated`, `deleted`, `status_changed` |
| `changes` | JSON com `{ field: { old, new } }` |
| `user_id` | Quem fez a mudança |
| `timestamp` | Quando ocorreu |

**Quando registrar:**
- Criação/deleção de Lead/Deal
- Mudança de status
- Mudança de responsável
- Mudança de valor (Deal)

---

### 📅 Timeline

Visão unificada de atividades via `/api/timeline/{lead_id}`.

| Tipo | Fonte | Ícone |
|------|-------|-------|
| `event` | CalendarEvents | 📅 |
| `audit` | AuditLogs | 📝 |
| `email` | Emails | ✉️ |
| `note` | Notes | 💬 |

**Ordenação:** `timestamp DESC` (mais recente primeiro)

**Filtros disponíveis:**
- Por tipo de atividade
- Por período
- Por responsável

---

### 🔐 Segurança (RBAC)

Sistema de permissões baseado em roles numéricas.

| Role | Nível | Permissões |
|------|-------|------------|
| **Admin** | 100 | Tudo |
| **Manager** | 75 | CRUD leads/deals + ver equipe |
| **Sales** | 50 | CRUD próprios leads/deals |

**Regra de acesso:**
```python
# Usuário pode acessar se seu nível >= nível requerido
def has_permission(user_role: int, required_role: int) -> bool:
    return user_role >= required_role
```

**Hierarquia de dados:**
- Admin: vê todos os dados
- Manager: vê dados da sua equipe
- Sales: vê apenas seus próprios dados

---

## 7) Protocolo de Desenvolvimento

### Antes de Codar

1. ✅ Ler `AGENTS.md` e `GOLDEN_RULES.md`
2. ✅ Verificar código existente nos arquivos-alvo
3. ✅ Identificar componentes/hooks reutilizáveis
4. ✅ Confirmar escopo e edge cases

### Durante o Desenvolvimento

1. ✅ Seguir ordem de hooks (evitar Erro 310)
2. ✅ Usar `e.stopPropagation()` em ações de tabela
3. ✅ Tratar loading/error/empty states
4. ✅ Invalidar cache após mutations

### Após Codar

1. ✅ Rodar lint/typecheck/tests
2. ✅ Verificar edge cases manualmente
3. ✅ Atualizar documentação se necessário

---

## 8) Documentação (Docs-as-Code)

### Quando Atualizar

| Mudança | Documento |
|---------|-----------|
| Nova feature concluída | `ACTION_PLAN.md` |
| Novo endpoint | `docs/backend/api.md` |
| Novo schema | `docs/backend/schemas.md` |
| Novo componente complexo | `docs/frontend/components.md` |
| Novo fluxo de UI | `docs/frontend/flows.md` |

### Formato de Atualização

```md
## [Data] - [Descrição curta]

### Adicionado
- ...

### Modificado
- ...

### Removido
- ...
```

---

## 9) Padrões de Código

### TypeScript (Frontend)

```tsx
// Tipos explícitos em props
interface Props {
  lead: Lead;
  onSave: (data: LeadFormData) => void;
  isLoading?: boolean;
}

// Defaults em destructuring
function LeadCard({ lead, onSave, isLoading = false }: Props) {
  // ...
}

// Enums como const
const LeadStatus = {
  NEW: 'new',
  CONTACTED: 'contacted',
  QUALIFIED: 'qualified',
} as const;

type LeadStatus = typeof LeadStatus[keyof typeof LeadStatus];
```

### Python (Backend)

```python
# Type hints obrigatórios
def get_lead(lead_id: UUID, db: Session) -> Lead | None:
    return db.query(Lead).filter(Lead.id == lead_id).first()

# Pydantic para schemas
class LeadCreate(BaseModel):
    name: str
    email: EmailStr
    phone: str | None = None

# HTTPException com detail
raise HTTPException(
    status_code=404,
    detail=f"Lead {lead_id} not found"
)
```

---

## 10) Comandos de Validação

### Frontend

```bash
# Rodar todos antes de entregar
npm run lint        # ESLint
npm run typecheck   # TypeScript
npm test            # Vitest
npm run build       # Build de produção
```

### Backend

```bash
# Rodar todos antes de entregar
pytest -v           # Testes
flake8 .            # Linting
mypy .              # Type checking
```

---

## 11) Formato de Entrega

Toda tarefa deve terminar com:

```md
## 📦 Entrega

### Resumo
- [5-10 bullets do que foi feito]

### Arquivos Alterados
| Arquivo | Ação |
|---------|------|
| `src/...` | Modificado |
| `src/...` | Criado |

### Comandos Executados
```sh
npm run lint → ✅
npm run typecheck → ✅
npm run build → ✅
```

### Edge Cases Tratados
- [lista]

### ROADMAP Final
| Item | Status | Obs |
|------|--------|-----|
| 1 | ✅ | |
| 2 | ⚠️ | adaptado |
| 3 | ❌ | fora do escopo |
```

---

## 📚 Referências

- [React Query Docs](https://tanstack.com/query/latest)
- [shadcn/ui](https://ui.shadcn.com/)
- [Tailwind CSS](https://tailwindcss.com/docs)
- [FastAPI](https://fastapi.tiangolo.com/)
- [GitHub Copilot Best Practices](https://docs.github.com/copilot/how-tos/agents/copilot-coding-agent/best-practices-for-using-copilot-to-work-on-tasks)
