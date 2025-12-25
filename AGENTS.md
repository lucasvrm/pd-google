# AGENTS.md

**Propósito:** Guia rápido para uso de agentes de IA no projeto PipeDesk Koa. 

**Companion doc:** [GOLDEN_RULES. md](./GOLDEN_RULES.md)  
**Última atualização:** 2025-12-25

---

## 🎯 Princípios

1. **Agentes são assistentes, não substitutos** → Sempre revisar código
2. **Seguir GOLDEN_RULES.md estritamente** → Não aceitar violações
3. **Documentar prompts complexos** → Em `docs/prompts/`
4. **Testar localmente antes de commit** → Nunca confiar cegamente

---

## 🤖 Ferramentas

| Ferramenta | Uso | Config |
|------------|-----|--------|
| **GitHub Copilot** | Autocomplete, sugestões inline | [. github/copilot-instructions.  md](.github/copilot-instructions.md) |
| **Claude** | Features complexas, refatorações | [Template de Prompt](#template-de-prompt) |
| **ChatGPT** | Explicações, brainstorming, testes | [Template de Prompt](#template-de-prompt) |
| **Gemini** | Research, comparação de libs | [Quando Usar](#quando-usar-cada-ferramenta) |
| **Playwright** | Testes E2E com autenticação | [Setup Rápido](#playwright-setup) |

---

## 📚 GitHub Copilot

**Config:** `.github/copilot-instructions. md` (carregado automaticamente)

**Comandos úteis:**
```
/explain    # Explica código
/fix        # Corrige erros
/tests      # Gera testes
/doc        # Gera documentação

@workspace  # Contexto do projeto inteiro
#file: path  # Referencia arquivo específico
```

**Atalhos:**
- `Tab` → Aceitar sugestão
- `Esc` → Rejeitar
- `Ctrl/Cmd + →` → Próxima sugestão

**✅ FAZER:** Revisar imports, verificar ordem de hooks, confirmar que usa `lucide-react`  
**❌ NÃO FAZER:** Aceitar código sem entender, confiar em types automáticos

---

## 💬 Agent Sessions (Claude/ChatGPT)

### Quando usar cada ferramenta

| Situação | Usar | Motivo |
|----------|------|--------|
| Feature completa (múltiplos arquivos) | **Claude** | Contexto 200k tokens |
| Refatoração estrutural | **Claude** | Análise de código |
| Explicação didática | **ChatGPT** | Melhor pedagógico |
| Geração de testes | **ChatGPT** | Cobertura robusta |
| Research de libs | **Gemini** | Acesso à web |
| Debugging simples | **Copilot** | Inline, rápido |

### Template de Prompt

```markdown
# 🎯 [Título] — [Repo] 

## ⚠️ OBRIGATÓRIO
1. Ler `GOLDEN_RULES.md` e `AGENTS.md`
2. Executar verificações (tabela abaixo)
3. Identificar arquivos-alvo

## 🔍 VERIFICAÇÕES

| # | Verificação | Arquivo | Se falhar |
|---|-------------|---------|-----------|
| V1 | [O que verificar] | `path/file.  ts` | [Ação] |

## 🚫 GUARDRAILS
- ❌ NÃO:  [listar proibições]
- ✅ PODE: [listar permissões]

## 🔧 TAREFAS
### T1: [Nome]
**Arquivo:** `path/file.ts` ~linha X  
**Ação:** [1-2 frases]  
**Código:** [snippet se necessário]

## ✅ ACEITE
- [ ] Lint, typecheck, build passam
- [ ] Testado manualmente

## 📦 ENTREGA
**ROADMAP (FACTUAL):**
| Item | ✅/⚠️/❌ | Observação |
|------|---------|------------|
| V1 | | |
| T1 | | |
```

**Salvar prompts em:** `docs/prompts/YYYY-MM-DD-titulo. md`

---

## 🎭 Playwright Setup

**Problema:** App requer login → Playwright precisa autenticar. 

**Solução (5 min):**

### 1. Criar `playwright/auth.setup.ts`:
```typescript
import { test as setup } from '@playwright/test';

setup('auth', async ({ page }) => {
  await page.goto('/login');
  await page.fill('input[name="email"]', process.env.TEST_USER_EMAIL! );
  await page.fill('input[name="password"]', process.env.TEST_USER_PASSWORD!);
  await page.click('button[type="submit"]');
  await page.waitForURL('**/dashboard');
  await page.context().storageState({ path: 'playwright/. auth/user.json' });
});
```

### 2. Configurar `playwright.config.ts`:
```typescript
export default defineConfig({
  projects:  [
    { name: 'setup', testMatch: /.*\. setup\.ts/ },
    {
      name: 'chromium',
      use: { storageState: 'playwright/.auth/user.json' },
      dependencies: ['setup']
    }
  ]
});
```

### 3. Criar `.env.test`:
```bash
TEST_USER_EMAIL=teste@pipedesk.com
TEST_USER_PASSWORD=senha123
```

### 4. Atualizar `.gitignore`:
```
playwright/.auth/
. env.test
```

**Comandos:**
```bash
npm run test:e2e        # Rodar testes
npm run test:e2e: ui     # Modo interativo
npx playwright test --debug  # Debug
```

---

## 📝 Prompts Reutilizáveis

### Criar Componente React
```
Crie componente [Nome]: 
- Props: [listar com tipos]
- Estados: loading, error, empty, success
- UI: shadcn/ui
- Ícones:   lucide-react
- Ordem hooks: useQuery → useMemo → useCallback → useState → useEffect
- Arquivo: src/components/[Nome].  tsx
```

### Adicionar Timeline Event
```
Adicione evento de timeline para [ação]:
1. Tipo em TimelineEventType (src/lib/types. ts)
2. Label em TIMELINE_EVENT_LABELS (src/constants/timeline.ts)
3. Ícone (lucide) em TIMELINE_EVENT_ICONS
4. Cor em DEFAULT_TIMELINE_COLORS
5. Atualizar AVAILABLE_EVENTS/FUTURE_EVENTS
```

### Fix Build Error
```
Fix build error:
- Erro: [colar]
- Arquivo: [path] linha X
- Validar: npm run lint && typecheck && build
```

---

## 🔧 Troubleshooting

| Problema | Solução |
|----------|---------|
| Agente ignora GOLDEN_RULES | Referenciar explicitamente + incluir regras no prompt |
| Lint falha | `npm run lint -- --fix` |
| Playwright não autentica | Verificar `.env.test` → `npx playwright test auth.setup.ts` |
| Build falha Vercel | Verificar Node version + env vars |
| Dependências não aprovadas | Guardrails:  "NÃO adicionar libs" |

---

## 📊 Red Flags

❌ **Sinais de uso incorreto:**
- Commits "fix lint" repetidos
- PRs >1000 linhas sem contexto
- Código sem testes
- Build quebra frequentemente
- Código viola GOLDEN_RULES.md

✅ **Sinais de uso correto:**
- Commits seguem padrões
- PRs têm contexto claro
- Coverage >=80%
- Build sempre passa
- Velocidade aumentou SEM bugs

---

## 📚 Recursos

**Interno:**
- [GOLDEN_RULES.  md](./GOLDEN_RULES.md) - Regras de código
- [. github/copilot-instructions. md](.github/copilot-instructions.md) - Config Copilot
- `docs/prompts/` - Histórico de prompts

**Externo:**
- [GitHub Copilot Docs](https://docs.github.com/en/copilot)
- [Claude Docs](https://docs.anthropic.com/claude)
- [Playwright Docs](https://playwright. dev)

---

**Versão:** 2.1 (Enxuto)  
**Mantenedor:** @lucasvrm  
**Revisar:** Mensalmente ou após incidentes

---

**TL;DR:** Siga `GOLDEN_RULES.md`, use template de prompt, teste localmente, documente em `docs/prompts/`. 🚀
