# GOLDEN_RULES.md

Regras para escrever prompts de **GitHub Copilot Agent Session** que sejam executáveis, rápidos de convergir e com baixo risco.

> **Última atualização:** Dezembro 2024  
> **Baseado em:** [GitHub Copilot Best Practices](https://docs.github.com/copilot/how-tos/agents/copilot-coding-agent/best-practices-for-using-copilot-to-work-on-tasks), AGENTS.md, lições aprendidas

---

## 0) Princípio Central

**Prompt bom = menos texto, mais decisões executáveis.**

Um prompt ideal contém:
- Objetivo claro e bem delimitado
- Guardrails explícitos (o que NÃO fazer)
- Tarefas curtas e ordenadas
- Critérios de aceite verificáveis
- Comandos de teste
- Formato de entrega padronizado

> 💡 **Regra de ouro:** Se o prompt virou um ensaio, está grande demais. Divida.

---

## 1) Declarar Camada no Topo

Todo prompt DEVE começar declarando a camada:

```md
## 📍 FRONTEND
Repo: `owner/pipedesk-koa`
```

ou

```md
## 📍 BACKEND
Repo: `owner/pd-google`
```

**Regra:** Proibido misturar FE e BE no mesmo prompt. Se a tarefa envolve ambos, gere prompts separados e indique a ordem de execução.

---

## 2) Primeira Tarefa Obrigatória

Todo prompt DEVE incluir esta seção logo após os guardrails:

```md
### ⚠️ Primeira Tarefa Obrigatória
1) Ler e seguir 100%: `AGENTS.md` e `GOLDEN_RULES.md` (raiz do repo).
2) Verificar código existente nos arquivos-alvo ANTES de implementar.
3) Identificar componentes, hooks e utils reutilizáveis.
4) Confirmar entendimento do escopo antes de codar.
```

> 💡 **Por que isso importa:** O Copilot Coding Agent trabalha melhor quando entende o contexto do projeto antes de fazer alterações. Custom instructions no `.github/copilot-instructions.md` são lidas automaticamente, mas reforçar no prompt garante aderência.

---

## 3) Guardrails (Hard Constraints)

Liste explicitamente o que **NÃO pode mudar** (salvo instrução explícita):

```md
## 🚫 Guardrails (Hard Constraints)
- ❌ Não alterar **contratos de API** (endpoints, verbos, payloads, response shapes)
- ❌ Não alterar **lógica de negócio** (regras, validações, cálculos)
- ❌ Não adicionar **libs/dependências novas**
- ❌ Não fazer "refactor por refactor" ou "limpeza oportunista"
- ❌ Não usar **client-side filtering** para compensar problemas de API
- ❌ Não remover código que "parece não usado" sem confirmar
- ✅ Mudanças **localizadas** com máximo reuso do existente
```

### Guardrails Específicos por Camada

**Frontend (adicionar quando aplicável):**
```md
- ❌ Não usar libs de ícones além de `lucide-react`
- ❌ Não criar componentes UI do zero (usar shadcn/ui)
- ❌ Não usar CSS inline ou styled-components (usar Tailwind)
```

**Backend (adicionar quando aplicável):**
```md
- ❌ Não criar migrations sem instrução explícita
- ❌ Não alterar models existentes sem backup plan
- ❌ Não expor dados sensíveis em logs
```

---

## 4) Regra de Complexidade

Todo prompt DEVE incluir **Complexidade Estimada (0–100)**.

### Heurística de Cálculo

| Fator | Pontos |
|-------|--------|
| Por arquivo a modificar | +5 |
| Novo componente/módulo | +10 |
| Mudança de state global (Context/Store) | +15 |
| Integração com API existente | +10 |
| Nova rota de API | +20 |
| Mudança de schema/banco | +25 |
| Refactor estrutural | +20 |
| Cruzar múltiplas features | +15 |
| Por teste a criar/ajustar | +5 |

### Ação por Faixa

| Complexidade | Ação |
|--------------|------|
| 0–50 | ✅ Prompt único, execução direta |
| 51–85 | ⚠️ Revisar se pode simplificar |
| > 85 | 🔴 **Obrigatório dividir** em múltiplos prompts |

> 💡 **Preferência:** 1 prompt = 1 PR pequeno e revisável.

---

## 5) Estrutura do Prompt

Use esta estrutura sequencial (sem duplicar informações):

```md
# 🎯 Prompt para Agent Session — <título curto e descritivo>

## 📍 <FRONTEND | BACKEND>
- **Repo:** `owner/repo-name`
- **Área/Rota:** `<ex: /leads, /api/timeline>`
- **Escopo:** <1-2 frases do que será modificado>
- **Fora de escopo:** <o que NÃO deve ser tocado>

---

## 🚫 Guardrails (Hard Constraints)
- ❌ ...
- ✅ ...

---

### ⚠️ Primeira Tarefa Obrigatória
1) Ler `AGENTS.md` e `GOLDEN_RULES.md` e seguir 100%.
2) Verificar arquivos-alvo antes de codar.
3) Identificar reuso possível.

---

## 📝 Resumo
- <bullet 1: objetivo principal>
- <bullet 2: mudança chave>
- <bullet 3: resultado esperado>
- <bullet 4: edge case importante, se houver>

---

## 🔧 Mudanças Solicitadas (em ordem)

### 1. <Nome da Mudança>
**Arquivo(s):** `src/path/to/file.tsx`
**Ação:**
- <subtarefa 1>
- <subtarefa 2>
**Reuso:** <componente/hook existente a reutilizar>

### 2. <Nome da Mudança>
...

---

## ✅ Critérios de Aceite
1. [ ] <critério verificável 1>
2. [ ] <critério verificável 2>
3. [ ] Nenhum erro no console
4. [ ] Lint/typecheck/build passam

---

## 🧪 Testes
**Ajustar (se quebrar):** <testes existentes afetados>
**Criar:** <novos testes necessários>
**Comandos:**
```sh
npm run lint && npm run typecheck && npm test && npm run build
```

---

## 📋 Checklist Manual
- [ ] <fluxo principal funciona>
- [ ] <edge case 1>
- [ ] <edge case 2>

---

## 📦 Formato de Entrega do Agente
<ver seção 9>

---

## 📊 Metadados
- **Complexidade:** <X/100>
- **Tempo Estimado:** <X-Y min>
- **Risco:** <Baixo | Médio | Alto>
```

---

## 6) Mudanças de API

**Default:** NÃO mudar contratos de API.

Se (e somente se) o prompt exigir mudança de API:

| Permitido ✅ | Proibido ❌ |
|--------------|-------------|
| Adicionar campos opcionais | Remover campos existentes |
| Criar endpoints novos | Renomear endpoints |
| Adicionar query params opcionais | Mudar tipo de campo |
| Versionar endpoint (`/v2/...`) | Quebrar clients existentes |

```md
## ⚠️ Mudança de API Autorizada
- Tipo: Aditiva (backwards compatible)
- Endpoint: `POST /api/leads` → adicionar campo opcional `source`
- Impacto: Nenhum client existente quebra
```

---

## 7) Testes e Validação

Todo prompt DEVE exigir:

### Comandos Obrigatórios

**Frontend:**
```sh
npm run lint
npm run typecheck
npm test
npm run build
```

**Backend:**
```sh
pytest -v
flake8 .
mypy .
```

### Regras de Teste

1. **Mudou comportamento?** → Criar/atualizar teste
2. **Mudou UI?** → Verificar snapshot ou criar teste de interação
3. **Mudou API?** → Teste de integração obrigatório
4. **Bug fix?** → Teste que reproduz o bug (deve passar após fix)

### Checklist Manual Mínimo

Todo prompt deve incluir checklist com:
- Fluxo principal (happy path)
- 1-2 edge cases relevantes
- Verificação de não-regressão

> ⚠️ **Não exigir screenshots:** O ambiente do agente pode não renderizar UI corretamente. Validar por testes, logs e inspeção de código.

---

## 8) Tratamento de Edge Cases

Todo prompt deve considerar (quando aplicável):

### Estados de UI
- [ ] Loading state
- [ ] Error state
- [ ] Empty state (lista vazia)
- [ ] Dados parciais/incompletos

### Interações
- [ ] Cliques rápidos/duplos
- [ ] Blur/focus inesperado
- [ ] Navegação durante operação async

### Dados
- [ ] Valores `null`/`undefined`
- [ ] Strings vazias
- [ ] Arrays vazios
- [ ] IDs inválidos

### Rede/Auth
- [ ] Conexão lenta
- [ ] Token expirado
- [ ] Usuário sem permissão

---

## 9) Formato de Entrega do Agente

Todo prompt DEVE obrigar o agente a encerrar com:

```md
## 📦 Formato de Entrega (Obrigatório)

Ao finalizar, incluir:

### 1. Resumo do que foi feito (5-10 bullets)
- ...

### 2. Arquivos alterados
| Arquivo | Ação |
|---------|------|
| `src/...` | Modificado |
| `src/...` | Criado |

### 3. Comandos executados + resultados
```sh
npm run lint → ✅ passed
npm run typecheck → ✅ passed
npm run build → ✅ passed
```

### 4. Riscos e edge cases identificados
- ...

### 5. Rollback (se necessário)
```sh
git revert <commit>
```

### 6. ROADMAP Final

| Item | Status | Observações |
|------|--------|-------------|
| 1. <mudança 1> | ✅ | |
| 2. <mudança 2> | ⚠️ | adaptado: ... |
| 3. <mudança 3> | ❌ | motivo: ... |

**Legenda:** ✅ Feito | ⚠️ Adaptado | ❌ Não feito
```

---

## 10) Armadilhas Conhecidas (Erros Recorrentes)

### Erro 185: TooltipTrigger Loop de Refs

**Problema:** `TooltipTrigger asChild` com componentes que re-renderizam causa loop.

**Solução:** Sempre envolver o filho em um wrapper.

```tsx
// ❌ ERRADO
<TooltipTrigger asChild>
  <Button {...props} />
</TooltipTrigger>

// ✅ CORRETO
<TooltipTrigger asChild>
  <span className="inline-flex">
    <Button {...props} />
  </span>
</TooltipTrigger>
```

---

### Erro 310: Hooks Fora de Ordem

**Problema:** Hooks chamados após condicionais ou dentro de funções.

**Regra:** Hooks SEMPRE no topo do componente, ANTES de qualquer `if`/`return`.

**Ordem obrigatória:**
```tsx
function Component() {
  // 1. Imports (no topo do arquivo)
  
  // 2. Hooks de dados
  const { data } = useQuery(...)
  const mutation = useMutation(...)
  
  // 3. useMemo
  const computed = useMemo(() => ..., [deps])
  
  // 4. useCallback
  const handler = useCallback(() => ..., [deps])
  
  // 5. useState
  const [state, setState] = useState()
  
  // 6. useEffect
  useEffect(() => { ... }, [deps])
  
  // 7. AGORA pode ter condicionais/early returns
  if (!data) return <Loading />
  
  // 8. Funções normais (handlers simples)
  const handleClick = () => { ... }
  
  // 9. Variáveis derivadas
  const filtered = data.filter(...)
  
  // 10. JSX return
  return <div>...</div>
}
```

**Checklist de verificação:**
- [ ] Nenhum hook depois de `if (...) return`
- [ ] Nenhum hook dentro de condicionais
- [ ] Nenhum hook dentro de callbacks/funções

---

### Erro: Propagação de Cliques em Tabelas

**Problema:** Clicar em botão/badge dentro de linha dispara o click da linha.

**Solução:** Sempre usar `e.stopPropagation()` em ações dentro de células.

```tsx
// ❌ ERRADO
<Button onClick={() => handleDelete(id)}>Delete</Button>

// ✅ CORRETO
<Button onClick={(e) => {
  e.stopPropagation();
  handleDelete(id);
}}>Delete</Button>
```

---

### Erro: Cache Desatualizado (React Query)

**Problema:** Dados diferentes entre views por cache não invalidado.

**Solução:** Invalidar queries após mutations.

```tsx
const mutation = useMutation({
  mutationFn: updateLead,
  onSuccess: () => {
    // Invalidar TODAS as queries que podem ter o dado
    queryClient.invalidateQueries({ queryKey: ['leads'] });
    queryClient.invalidateQueries({ queryKey: ['lead', id] });
  }
});
```

---

## 11) Padrões de Reuso

Antes de criar algo novo, verificar se já existe:

| O que precisa | Onde procurar |
|---------------|---------------|
| Componente UI | `src/components/ui/` |
| Hook customizado | `src/hooks/` |
| Utilitário | `src/lib/` ou `src/utils/` |
| Tipo/Interface | `src/types/` |
| Constante | `src/constants/` |
| Feature completa | `src/features/<nome>/` |

**Regra:** Se existe algo similar, reutilizar ou estender. Não duplicar.

---

## 12) Integração com GitHub Copilot

### Arquivos de Configuração Recomendados

```
.github/
├── copilot-instructions.md      # Instruções globais do repo
├── copilot-setup-steps.yml      # Setup do ambiente do agent
└── instructions/
    ├── frontend.instructions.md  # Instruções específicas FE
    └── backend.instructions.md   # Instruções específicas BE
```

### Dicas para Melhor Resultado

1. **Seja específico:** "Adicionar campo `source` ao form de leads" > "Melhorar form"
2. **Forneça contexto:** Mencione arquivos, componentes, padrões existentes
3. **Use exemplos:** Se houver componente similar, referencie-o
4. **Quebre tarefas grandes:** Múltiplos prompts pequenos > 1 prompt gigante
5. **Inclua acceptance criteria:** O agente valida contra eles

---

## 13) Atualização deste Documento

Atualize este arquivo quando:
- Novo erro recorrente for identificado
- Nova best practice for descoberta
- Lição aprendida em code review

**Manter curto:** Se passar de 3 páginas impressas, está grande demais.

---

## 📚 Referências

- [GitHub Copilot Coding Agent - Best Practices](https://docs.github.com/copilot/how-tos/agents/copilot-coding-agent/best-practices-for-using-copilot-to-work-on-tasks)
- [Prompt Engineering for GitHub Copilot](https://docs.github.com/en/copilot/concepts/prompt-engineering)
- [Custom Instructions](https://docs.github.com/copilot/customizing-copilot/adding-custom-instructions-for-github-copilot)
- [5 Tips for Better Custom Instructions](https://github.blog/ai-and-ml/github-copilot/5-tips-for-writing-better-custom-instructions-for-copilot/)
