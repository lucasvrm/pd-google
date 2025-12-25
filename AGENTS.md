# AGENTS.md

**Propósito:** Documentar a configuração e uso de agentes de IA no projeto PipeDesk Koa. 

**Companion doc:** [GOLDEN_RULES. md](./GOLDEN_RULES.md) - Regras de código e boas práticas

**Última atualização:** 2025-12-25

---

## 📚 Índice

1. [Filosofia de Uso de Agentes](#filosofia-de-uso-de-agentes)
2. [GitHub Copilot](#github-copilot)
3. [Claude (Agent Sessions)](#claude-agent-sessions)
4. [ChatGPT (Agent Sessions)](#chatgpt-agent-sessions)
5. [Gemini](#gemini)
6. [OpenAI Codex](#openai-codex)
7. [Playwright (Testes E2E)](#playwright-testes-e2e)
8. [Prompts Reutilizáveis](#prompts-reutilizáveis)
9. [Troubleshooting](#troubleshooting)

---

## 🎯 Filosofia de Uso de Agentes

### Princípios

1. **Agentes são assistentes, não substitutos**
   - Sempre revisar código gerado
   - Validar lógica de negócio
   - Testar localmente antes de commit

2. **Consistência acima de velocidade**
   - Seguir `GOLDEN_RULES.md` sempre
   - Manter padrões do projeto
   - Não aceitar código que viole convenções

3. **Documentação é obrigatória**
   - Todo prompt complexo deve ser documentado
   - Agent Sessions devem gerar ROADMAP
   - Mudanças estruturais precisam de ADR

4. **Segurança em primeiro lugar**
   - Nunca expor credenciais em prompts
   - Revisar código gerado por vulnerabilidades
   - Validar dependências adicionadas

---

## 🤖 GitHub Copilot

### Configuração

**Arquivo:** `.github/copilot-instructions.md`

Este arquivo é carregado automaticamente pelo GitHub Copilot e influencia todas as sugestões no repositório.

**Conteúdo obrigatório:**

```markdown
# GitHub Copilot Instructions - PipeDesk Koa

## Stack Tecnológica
- **Frontend:** React 18 + TypeScript + Vite
- **Styling:** Tailwind CSS + shadcn/ui
- **Icons:** lucide-react (ÚNICO PERMITIDO - nunca Phosphor, FontAwesome, Heroicons)
- **State Management:** React Query + Context API
- **Forms:** React Hook Form + Zod
- **Backend:** Supabase (PostgreSQL + Auth + Storage)

## Convenções de Nomenclatura
- **camelCase:** variáveis, funções (`getUserData`, `isLoading`)
- **PascalCase:** componentes React, classes (`LeadDetailPage`, `StatusBadge`)
- **SCREAMING_SNAKE_CASE:** constantes (`API_BASE_URL`, `MAX_RETRIES`)
- **kebab-case:** arquivos CSS, nomes de arquivos utilitários (`utils. ts`, `getContrastColor.ts`)

## Ordem de Hooks React (OBRIGATÓRIA)

**SEMPRE seguir esta ordem para evitar React Errors 185 e 310:**

1. **Queries/Mutations** (React Query)
   ```tsx
   const { data, isLoading } = useQuery(...)
   const mutation = useMutation(...)
   ```

2. **useMemo** (computações pesadas)
   ```tsx
   const computedValue = useMemo(() => .. ., [deps])
   ```

3. **useCallback** (funções memorizadas)
   ```tsx
   const handleClick = useCallback(() => ..., [deps])
   ```

4. **useState** (estado local)
   ```tsx
   const [value, setValue] = useState(initial)
   ```

5. **useEffect** (efeitos colaterais)
   ```tsx
   useEffect(() => { ... }, [deps])
   ```

6. **Condicionais/Early Returns**
   ```tsx
   if (! data) return <Loading />
   ```

7. **JSX Return**
   ```tsx
   return <Component />
   ```

## Armadilhas Conhecidas

### ❌ React Error 185
**Causa:** TooltipTrigger sem wrapper

**Errado:**
```tsx
<TooltipTrigger>
  <Button />
</TooltipTrigger>
```

**Correto:**
```tsx
<TooltipTrigger asChild>
  <span className="inline-flex">
    <Button />
  </span>
</TooltipTrigger>
```

### ❌ React Error 310
**Causa:** Hooks após condicionais

**Errado:**
```tsx
if (!data) return null
const [state, setState] = useState() // ❌ Hook após condicional
```

**Correto:**
```tsx
const [state, setState] = useState() // ✅ Hook ANTES
if (!data) return null
```

## Padrões de Código

### Componentes React
```tsx
interface MyComponentProps {
  id: string
  onAction: (value: string) => void
}

export function MyComponent({ id, onAction }: MyComponentProps) {
  // 1. Queries
  const { data } = useQuery(...)
  
  // 2. useMemo
  const computed = useMemo(() => ..., [])
  
  // 3. useCallback
  const handleClick = useCallback(() => ..., [])
  
  // 4. useState
  const [state, setState] = useState(false)
  
  // 5. useEffect
  useEffect(() => { ... }, [])
  
  // 6. Early returns
  if (!data) return <Loading />
  
  // 7. JSX
  return <div>... </div>
}
```

### Estados Obrigatórios
Todo componente que busca dados DEVE implementar:
- **Loading:** Skeleton ou Spinner
- **Error:** Mensagem de erro amigável + retry
- **Empty:** Estado vazio (sem dados)
- **Success:** Dados renderizados

```tsx
if (isLoading) return <Skeleton />
if (error) return <ErrorMessage error={error} onRetry={refetch} />
if (! data?. length) return <EmptyState />
return <DataList data={data} />
```

### Try-Catch Obrigatório
Todas operações async DEVEM ter tratamento de erro: 

```tsx
const handleSubmit = async (data: FormData) => {
  try {
    await mutation.mutateAsync(data)
    toast.success('Sucesso!')
  } catch (error) {
    console.error('[handleSubmit] Error:', error)
    toast.error('Erro ao processar')
  }
}
```

## Imports
**Ordem:**
1. React/Libs externas
2. Componentes internos (@/components)
3. Hooks (@/hooks)
4. Services (@/services)
5. Utils (@/lib)
6. Types (@/lib/types)
7. CSS

## Proibições
- ❌ Phosphor Icons, FontAwesome, Heroicons (usar APENAS lucide-react)
- ❌ styled-components, CSS modules (usar APENAS Tailwind + shadcn/ui)
- ❌ Hooks após condicionais
- ❌ TooltipTrigger sem asChild + wrapper
- ❌ any sem justificativa
- ❌ console.log em produção (usar logger)
- ❌ Credenciais hardcoded

## Referências Obrigatórias
- **Regras completas:** [GOLDEN_RULES.md](../../GOLDEN_RULES.md)
- **Configuração de agentes:** [AGENTS.md](../../AGENTS.md)
```

**Localização:** `.github/copilot-instructions.md`

### Como usar

**Sugestões inline:**
- Escreva comentário descritivo → Copilot sugere código
- Aceite com `Tab` ou rejeite com `Esc`

**GitHub Copilot Chat:**
```
# No VSCode, abra o chat (Ctrl/Cmd + I)

/explain    # Explica código selecionado
/fix        # Corrige erros
/tests      # Gera testes
/doc        # Gera documentação
```

**Workspace Chat (contexto do projeto):**
- `@workspace` - Pergunta sobre todo o projeto
- `#file: caminho/arquivo.ts` - Referencia arquivo específico
- `#selection` - Usa código selecionado

**Exemplos:**
```
@workspace Como implementar autenticação com Supabase?
#file:src/hooks/useSystemMetadata.ts Como adicionar campo color? 
#selection Adicionar tratamento de erro aqui
```

### Boas práticas

✅ **FAZER:**
- Revisar TODAS as sugestões antes de aceitar
- Verificar se segue ordem de hooks
- Confirmar que usa lucide-react (não outros ícones)
- Testar localmente antes de commit

❌ **NÃO FAZER:**
- Aceitar código sem entender
- Confiar cegamente em imports
- Pular validação de tipos
- Usar sugestões que violam GOLDEN_RULES.md

---

## 💬 Claude (Agent Sessions)

### Quando usar

**Ideal para:**
- ✅ Features completas (múltiplos arquivos)
- ✅ Refatorações estruturais
- ✅ Debugging complexo
- ✅ Análise de código existente
- ✅ Geração de documentação

**NÃO usar para:**
- ❌ Mudanças triviais (typos, formatação)
- ❌ Alterações em arquivo único (usar Copilot)
- ❌ Experimentação rápida

### Recursos do Claude

**Artifacts (Code Artifacts):**
- Código executável em sandbox
- Ideal para protótipos e validação
- Exportar para projeto depois de validar

**Analysis Tools:**
- Leitura de arquivos do projeto
- Análise de estrutura
- Sugestões contextualizadas

**Extended Context (200k tokens):**
- Pode processar arquivos grandes
- Mantém contexto de múltiplas mensagens
- Ideal para debugging complexo

### Template de Prompt para Claude

```markdown
# 🎯 Prompt para Agent Session — [Título da Task]

**Versão:** 1.0 | **Compatível com:** GOLDEN_RULES.md v2.0, AGENTS.md

---

## 📍 CONTEXTO

**Repo:** `lucasvrm/pipedesk-koa`  
**Área:** [Frontend/Backend/Fullstack]  
**Rotas afetadas:** [listar]

**Escopo:**
1. [Item 1]
2. [Item 2]

**Fora de escopo:** [Listar explicitamente]

---

## ⚠️ PRIMEIRA AÇÃO OBRIGATÓRIA

1.  Ler `AGENTS.md` e `GOLDEN_RULES.md` (v2.0)
2. Executar verificações de pré-requisitos
3. Identificar arquivos-alvo

---

## 🔍 VERIFICAÇÕES DE PRÉ-REQUISITOS

**EXECUTAR ANTES DE CODAR:**

| # | Verificação | Arquivo | Ação se FALHAR |
|---|-------------|---------|----------------|
| V1 | [Descrever] | `src/path/file.ts` | [Ação específica] |
| V2 | [Descrever] | `src/path/file.ts` | [Ação específica] |

**Output esperado:**
```sh
✅ [V1] Verificação passou
❌ [V2] Verificação falhou → corrigir antes de prosseguir
```

---

## 🚫 GUARDRAILS

**NÃO:**
- [Lista de proibições específicas]
- Alterar schema de banco
- Adicionar novas libs sem aprovação

**PODE:**
- [Lista de permissões específicas]
- Ajustar cache invalidation
- Modificar CSS/Tailwind

---

## 🛡️ RESILIÊNCIA

**Implementar fallbacks para operações arriscadas:**

```typescript
// Exemplo: Cache invalidation
try {
  queryClient.invalidateQueries({ queryKey: [... ] })
} catch (error) {
  console.warn('[Context] Cache invalidation failed:', error)
  // Continua sem quebrar
}

// Exemplo:  Validação de dados
if (color && /^#[0-9A-F]{6}$/i. test(color)) {
  // Usar cor válida
} else {
  console.warn(`Invalid color "${color}", using fallback`)
  // Fallback semântico
}
```

---

## 🔧 TAREFAS

### **T1: [Nome da Tarefa]**

**Arquivo:** `src/path/file.ts` (linha ~X-Y)

**Ação:**
[Descrição detalhada e específica]

**Implementação:**
```typescript
// Código exemplo ou estrutura esperada
```

**Validação:**
- [ ] Lint passa
- [ ] Funcionalidade testada manualmente

---

## ✅ CRITÉRIOS DE ACEITE

### Pré-condições
- [ ] Verificações V1-VX executadas
- [ ] Fallbacks implementados

### T1 - [Nome]
- [ ] [Critério específico 1]
- [ ] [Critério específico 2]
- [ ] **Edge case:** [Cenário de borda]

### Geral
- [ ] `npm run lint` ✅
- [ ] `npm run typecheck` ✅
- [ ] `npm run build` ✅
- [ ] Sem erros no console

---

## 📦 FORMATO DE ENTREGA

### 1. Resumo (5-10 bullets)
- Ex: "Adicionado prop `color` ao StatusBadge"

### 2. Arquivos modificados/criados
| Arquivo | Ação | Motivo |
|---------|------|--------|
| `file.ts` | Modificado | [Motivo] |

### 3. Comandos executados
```sh
npm run lint → ✅ passed
npm run typecheck → ✅ passed
npm run build → ✅ passed
```

### 4. ROADMAP Final (HONESTIDADE OBRIGATÓRIA)

| Item | Status | Observações FACTUAIS |
|------|--------|----------------------|
| V1 | ✅/❌ | "Campo presente" OU "Adicionado linha X" |
| T1 | ✅/⚠️/❌ | "Implementado conforme spec" OU "Adaptado porque..." |

**Legenda:** ✅ Feito | ⚠️ Adaptado (EXPLICAR) | ❌ Não feito (EXPLICAR)

---

## 📊 METADADOS

**Complexidade:** X/100  
**Tempo Estimado:** X-Y min  
**Risco:** Baixo/Médio/Alto

---

## 📚 REFERÊNCIAS

- [GOLDEN_RULES.md](./GOLDEN_RULES.md)
- [AGENTS.md](./AGENTS.md)
```

### Boas práticas com Claude

✅ **FAZER:**
- Fornecer contexto completo (arquivos, estrutura, erros)
- Usar Artifacts para prototipar
- Pedir validação de mudanças
- Solicitar ROADMAP ao final

❌ **NÃO FAZER:**
- Prompts vagos ("fix this")
- Copiar código sem revisar
- Pular verificações de pré-requisitos
- Omitir contexto do projeto

---

## 🤖 ChatGPT (Agent Sessions)

### Diferenças do Claude

**ChatGPT é melhor para:**
- Explicações didáticas (ensinar conceitos)
- Brainstorming de soluções
- Geração de testes unitários
- Documentação técnica

**Claude é melhor para:**
- Análise de código existente (200k context)
- Refatorações complexas
- Debugging com múltiplos arquivos
- Code artifacts (protótipos)

### Template de Prompt para ChatGPT

**Usar o mesmo template do Claude**, mas ajustar tom: 

```markdown
# 🎯 Prompt para ChatGPT — [Título]

[Mesmo conteúdo, mas adicionar:]

## 💡 CONTEXTO ADICIONAL

**Problema que estamos resolvendo:**
[Explicação em linguagem natural do problema de negócio]

**Por que essa abordagem:**
[Justificativa técnica]

**Alternativas consideradas:**
1. [Opção A] - Descartada porque... 
2. [Opção B] - Descartada porque... 
3. [Opção C] - **ESCOLHIDA** porque... 
```

### Boas práticas com ChatGPT

✅ **FAZER:**
- Fornecer contexto de negócio (não só técnico)
- Pedir explicações detalhadas
- Usar para gerar testes
- Solicitar alternativas

❌ **NÃO FAZER:**
- Assumir que entende estrutura do projeto (contexto menor que Claude)
- Pedir análise de múltiplos arquivos grandes (limitação de contexto)
- Confiar em "conhecimento" de libs específicas (pode estar desatualizado)

---

## 🔮 Gemini

### Quando usar

**Ideal para:**
- ✅ Busca de informação atualizada (acesso à web)
- ✅ Análise de documentação de libs
- ✅ Comparação de abordagens
- ✅ Pesquisa de best practices

**NÃO usar para:**
- ❌ Geração de código complexo (menos confiável que Claude/ChatGPT)
- ❌ Refatorações estruturais
- ❌ Debugging crítico

### Recursos do Gemini

**Grounding (acesso à web):**
- Busca documentação atualizada
- Verifica versões de libs
- Encontra soluções em GitHub Issues

**Multimodal:**
- Pode analisar screenshots de erros
- Processa diagramas de arquitetura

### Template de Prompt para Gemini

```markdown
Pesquise e compare as seguintes abordagens para [problema]: 

1. [Abordagem A]
2. [Abordagem B]
3. [Abordagem C]

Para cada uma, forneça:
- ✅ Vantagens
- ❌ Desvantagens
- 📚 Links para documentação oficial
- 🔍 Exemplos de uso em projetos open-source
- ⚠️ Gotchas conhecidos

Contexto do projeto: 
- Stack: React 18 + TypeScript + Supabase
- Constraints: [listar]
```

### Boas práticas com Gemini

✅ **FAZER:**
- Usar para research (não code generation)
- Pedir links e referências
- Validar informações (pode alucinar menos que outros, mas ainda pode)
- Usar para encontrar breaking changes de libs

❌ **NÃO FAZER:**
- Confiar em código gerado sem revisar
- Usar para decisões críticas sem validação
- Assumir que informação está 100% atualizada

---

## 🔧 OpenAI Codex

### Quando usar

**Codex (via GitHub Copilot) é melhor para:**
- ✅ Autocomplete inteligente (inline suggestions)
- ✅ Geração de boilerplate
- ✅ Tradução de pseudocódigo para código
- ✅ Refatoração de funções isoladas

**NÃO usar para:**
- ❌ Arquitetura de sistema (usar Claude/ChatGPT)
- ❌ Debugging complexo (usar Claude)
- ❌ Decisões de design (discutir com time)

### Como maximizar uso do Codex

**1. Comentários descritivos:**
```typescript
// Função que calcula prioridade de lead baseado em: 
// - Último contato (peso 40%)
// - Valor potencial (peso 30%)
// - Engajamento (peso 30%)
// Retorna: 'hot' | 'warm' | 'cold'
function calculateLeadPriority(lead: Lead): PriorityBucket {
  // Codex completa aqui
}
```

**2. Exemplos no comentário:**
```typescript
// Parse date in format DD/MM/YYYY to ISO string
// Example: "25/12/2025" → "2025-12-25T00:00:00.000Z"
function parseDate(dateStr: string): string {
  // Codex completa
}
```

**3. Type hints:**
```typescript
interface User {
  id: string
  name: string
  role: 'admin' | 'manager' | 'user'
}

// Codex agora sabe os tipos disponíveis
function getUsersByRole(role: User['role']): User[] {
  // Completa com type safety
}
```

### Boas práticas com Codex

✅ **FAZER:**
- Escrever comentários detalhados
- Fornecer exemplos de input/output
- Usar TypeScript (melhor inferência)
- Aceitar sugestões de boilerplate

❌ **NÃO FAZER:**
- Aceitar sugestões de lógica de negócio sem revisar
- Confiar em imports automáticos (sempre verificar)
- Usar sugestões que violam padrões do projeto

---

## 🎭 Playwright (Testes E2E)

### Configuração de Autenticação

**Problema:** Playwright não consegue acessar rotas protegidas por login. 

**Solução:** Storage State (Recomendada)

#### Setup Completo

**1. Criar script de autenticação:**

```typescript
// playwright/auth.setup.ts
import { test as setup, expect } from '@playwright/test';

const authFile = 'playwright/.auth/user.json';

setup('authenticate', async ({ page }) => {
  // Ir para login
  await page.goto('http://localhost:5173/login');
  
  // Preencher credenciais
  await page.fill('input[name="email"]', process.env.TEST_USER_EMAIL!);
  await page.fill('input[name="password"]', process.env.TEST_USER_PASSWORD!);
  
  // Submeter
  await page.click('button[type="submit"]');
  
  // Aguardar redirecionamento
  await page.waitForURL('**/dashboard');
  
  // Verificar autenticação
  await expect(page. locator('[data-testid="user-menu"]')).toBeVisible();
  
  // Salvar estado
  await page.context().storageState({ path: authFile });
});
```

**2. Configurar Playwright:**

```typescript
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  
  projects: [
    // Setup project (roda antes dos testes)
    { 
      name: 'setup', 
      testMatch: /.*\.setup\.ts/ 
    },
    
    // Testes com autenticação
    {
      name: 'chromium',
      use: { 
        ...devices['Desktop Chrome'],
        storageState: 'playwright/.auth/user.json'
      },
      dependencies: ['setup']
    },
    
    // Testes sem autenticação (opcional)
    {
      name: 'chromium-no-auth',
      use: { ... devices['Desktop Chrome'] },
    }
  ],
});
```

**3. Criar `.env.test`:**

```bash
# .env.test
TEST_USER_EMAIL=teste@pipedesk.com
TEST_USER_PASSWORD=SenhaSegura123! 

# Outros usuários (para testar roles)
TEST_ADMIN_EMAIL=admin@pipedesk.com
TEST_ADMIN_PASSWORD=AdminPass123! 

TEST_MANAGER_EMAIL=manager@pipedesk.com
TEST_MANAGER_PASSWORD=ManagerPass123!
```

**4. Atualizar `.gitignore`:**

```gitignore
# Playwright
playwright/. auth/
playwright-report/
test-results/

# Credenciais de teste
. env. test
```

**5. Adicionar ao `package.json`:**

```json
{
  "scripts": {
    "test: e2e": "playwright test",
    "test:e2e:ui": "playwright test --ui",
    "test:e2e: debug": "playwright test --debug"
  }
}
```

### Exemplo de Teste

```typescript
// tests/e2e/leads.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Leads Management', () => {
  test('deve criar um lead', async ({ page }) => {
    // JÁ ESTÁ AUTENTICADO (graças ao storage state)
    await page.goto('/leads');
    
    // Clicar em criar
    await page.click('[data-testid="create-lead-button"]');
    
    // Preencher formulário
    await page.fill('input[name="companyName"]', 'Empresa Teste');
    await page.fill('input[name="contactName"]', 'João Silva');
    await page.fill('input[name="email"]', 'joao@teste.com');
    
    // Submeter
    await page.click('button[type="submit"]');
    
    // Verificar sucesso
    await expect(page. locator('text=Lead criado com sucesso')).toBeVisible();
    await expect(page).toHaveURL(/\/leads\/[a-z0-9-]+/);
  });
  
  test('deve filtrar leads por status', async ({ page }) => {
    await page.goto('/leads');
    
    // Abrir filtros
    await page.click('[data-testid="filters-button"]');
    
    // Selecionar status
    await page. click('[data-testid="status-filter"]');
    await page.click('text=Qualificado');
    
    // Aplicar
    await page.click('text=Aplicar Filtros');
    
    // Verificar resultados
    const leads = page.locator('[data-testid="lead-row"]');
    await expect(leads).not.toHaveCount(0);
  });
});
```

### Comandos Úteis

```bash
# Rodar todos os testes
npm run test:e2e

# Rodar apenas setup de auth
npx playwright test auth.setup.ts

# UI Mode (interativo)
npm run test:e2e:ui

# Debug mode
npm run test:e2e:debug

# Rodar teste específico
npx playwright test leads.spec.ts

# Gerar relatório
npx playwright show-report
```

### Boas práticas

✅ **FAZER:**
- Usar `data-testid` para seletores estáveis
- Aguardar elementos antes de interagir (`waitFor`, `expect().toBeVisible()`)
- Isolar testes (cada teste independente)
- Limpar dados de teste após execução
- Usar Page Object Model para testes complexos

❌ **NÃO FAZER:**
- Seletores CSS frágeis (`div > span. class`)
- Depender de ordem de execução
- Testes que modificam dados de produção
- Esperas fixas (`page.waitForTimeout(5000)`)

---

## 📝 Prompts Reutilizáveis

### 1. Criar Componente React

```
Crie um componente React chamado [Nome] que:
- Recebe props:  [listar com tipos]
- Implementa estados: loading, error, empty, success
- Usa shadcn/ui para UI
- Segue ordem de hooks: useQuery → useMemo → useCallback → useState → useEffect
- Usa APENAS lucide-react para ícones
- Arquivo: src/components/[Nome].tsx

Exemplo de uso: 
<[Nome] prop1="valor" prop2={123} />
```

### 2. Adicionar Feature à Timeline

```
Adicione evento de timeline para [ação]: 

Passos:
1. Adicionar tipo em TimelineEventType (src/lib/types.ts)
2. Adicionar label em TIMELINE_EVENT_LABELS (src/constants/timeline.ts)
3. Adicionar ícone (lucide-react) em TIMELINE_EVENT_ICONS
4. Adicionar cor hex em DEFAULT_TIMELINE_COLORS
5. Atualizar AVAILABLE_EVENTS (se implementado) ou FUTURE_EVENTS (se planejado)
6. Criar evento na função de callback relevante

Exemplo de evento:
{
  type:  'novo_evento',
  content: 'Descrição do evento',
  createdAt: new Date().toISOString(),
  author: { id, name, avatar }
}
```

### 3. Corrigir Erro de Build

```
Fix build error no Vercel:

**Erro:**
[colar erro completo]

**Arquivo:** [arquivo. ts linha X]

**Contexto:**
- Build local: [passa/falha]
- Lint: [passa/falha]
- TypeCheck: [passa/falha]

**Ações:**
1. Identificar causa raiz
2. Corrigir sem quebrar funcionalidade
3. Validar:  npm run lint && npm run typecheck && npm run build
4. Testar localmente antes de push
```

### 4. Adicionar Testes

```
Crie testes para [componente/função]:

**Casos felizes:**
1. [Cenário 1]
2. [Cenário 2]

**Edge cases:**
1. [Cenário edge 1]
2. [Cenário edge 2]

**Especificações:**
- Framework:  Vitest + React Testing Library
- Coverage mínimo: 80%
- Arquivo: src/[path]/__tests__/[nome].test. tsx
- Seguir padrão: Arrange → Act → Assert
```

### 5. Refatorar para Pattern

```
Refatore [componente/função] para usar [pattern]:

**Antes (problemas):**
- [Problema 1]
- [Problema 2]

**Depois (benefícios):**
- [Benefício 1]
- [Benefício 2]

**Constraints:**
- Manter interface pública inalterada
- Manter testes passando
- Não adicionar dependências
```

---

## 🔧 Troubleshooting

### Problema: Agente ignora GOLDEN_RULES. md

**Sintomas:**
- Código usa Phosphor Icons ao invés de lucide-react
- Ordem de hooks incorreta
- Não implementa estados (loading, error, empty)

**Solução:**
1. Referenciar explicitamente: 
   ```
   Ler e seguir 100% o GOLDEN_RULES.md antes de começar
   ```
2. Incluir regras críticas no prompt:
   ```
   OBRIGATÓRIO: 
   - Usar APENAS lucide-react para ícones
   - Seguir ordem de hooks: useQuery → useMemo → useCallback → useState → useEffect
   - Implementar try-catch em operações async
   ```
3. Validar output com checklist

---

### Problema: Código não passa no lint

**Sintomas:**
```
Error: 'variable' is assigned a value but never used
Error: Missing return type on function
```

**Solução:**
```bash
# Rodar lint com fix automático
npm run lint -- --fix

# Se persistir, revisar manualmente
npm run lint

# Verificar . eslintrc.cjs para regras específicas
```

---

### Problema:  Agente adiciona dependências não aprovadas

**Sintomas:**
- `package.json` tem libs não documentadas
- Imports de libs desconhecidas

**Solução:**
1. Guardrails no prompt:
   ```
   NÃO adicionar novas dependências sem aprovação explícita
   ```
2. Revisar `package.json` antes de aceitar PR
3. Se necessário: 
   ```bash
   # Remover dependência
   npm uninstall [package]
   
   # Limpar node_modules
   rm -rf node_modules package-lock.json
   npm install
   ```

---

### Problema: Playwright não autentica

**Sintomas:**
```
Error: page.goto: net::ERR_NAME_NOT_RESOLVED
Error:  Timeout 30000ms exceeded waiting for locator
```

**Solução:**
1. Verificar `.env.test`:
   ```bash
   cat .env.test
   # Deve ter TEST_USER_EMAIL e TEST_USER_PASSWORD
   ```

2. Rodar setup manualmente:
   ```bash
   npx playwright test auth.setup. ts
   ```

3. Verificar arquivo gerado:
   ```bash
   ls -la playwright/. auth/
   # Deve ter user.json
   ```

4. Testar login manual:
   ```bash
   # Abrir browser em modo debug
   npx playwright test --debug auth.setup.ts
   ```

---

### Problema: Build passa local mas falha no Vercel

**Sintomas:**
```
Error: Command "npm run build" exited with 1
```

**Solução:**
1. Verificar versão do Node: 
   ```json
   // package.json
   "engines":  {
     "node": ">=18.0.0"
   }
   ```

2. Verificar variáveis de ambiente no Vercel:
   - `VITE_SUPABASE_URL`
   - `VITE_SUPABASE_ANON_KEY`

3. Rodar build com mesmas condições:
   ```bash
   NODE_ENV=production npm run build
   ```

4. Verificar logs do Vercel para erro específico

---

## 📊 Métricas de Sucesso

**Indicadores de que agentes estão sendo bem usados:**

✅ **Positivos:**
- Commits seguem padrões (`feat: `, `fix:`, `docs:`)
- Pull requests têm descrição clara e contexto
- Código gerado tem testes
- Build nunca quebra em produção
- Lint/TypeCheck passam sempre
- Velocidade de desenvolvimento aumentou
- Bugs em produção não aumentaram

❌ **Red flags:**
- Commits com "fix lint" repetidamente
- PRs enormes (>1000 linhas) sem contexto
- Código sem testes ou com coverage baixo
- Build quebra frequentemente
- Dependências não aprovadas instaladas
- Código não segue GOLDEN_RULES.md
- Hotfixes frequentes pós-deploy

---

## 🔄 Manutenção

**Revisar este documento:**
- **Mensalmente:** Atualizar com novas descobertas
- **Após incidentes:** Adicionar lições aprendidas na seção Troubleshooting
- **Quando adicionar ferramenta:** Documentar configuração

**Responsável:** Tech Lead / Maintainer do projeto (@lucasvrm)

**Processo de atualização:**
1. Criar branch `docs/update-agents-md`
2. Fazer mudanças
3. Abrir PR com contexto das mudanças
4. Revisar com time
5. Mergear e comunicar no Slack/Discord

---

## 📚 Recursos

### Documentação Interna
- [GOLDEN_RULES.md](./GOLDEN_RULES.md) - Regras de código completas
- [. github/copilot-instructions.md](./. github/copilot-instructions. md) - Instruções do Copilot

### Documentação Externa
- [GitHub Copilot Docs](https://docs.github.com/en/copilot)
- [Claude Documentation](https://docs.anthropic.com/claude/docs)
- [ChatGPT Best Practices](https://platform.openai.com/docs/guides/prompt-engineering)
- [Gemini Documentation](https://ai.google. dev/docs)
- [Playwright Docs](https://playwright.dev/)
- [React Testing Library](https://testing-library.com/react)

### Comunidade
- [GitHub Copilot Discord](https://discord.gg/github)
- [Playwright Discord](https://discord.gg/playwright)

---

**Última revisão:** 2025-12-25  
**Versão:** 2.0  
**Mantenedor:** @lucasvrm

---

**Lembre-se:** Agentes são ferramentas poderosas, mas a responsabilidade final pelo código é sempre humana.  Revise, teste, valide.  🚀
