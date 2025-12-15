# 🏆 REGRAS DE OURO - Prompts para Agent Sessions (GitHub Copilot)

---

## 📌 **1. Sempre indicar se o prompt é FE ou BE**

**Regra:**  
Todo prompt **DEVE** começar deixando claro se é **Frontend** ou **Backend**.  

**Formato obrigatório:**
```
## 📍 **FRONTEND**
**Repositório:** `owner/repo-name`
```
ou
```
## 📍 **BACKEND**
**Repositório:** `owner/repo-name`
```

**Justificativa:**  
Evita confusão de contexto, tecnologias e convenções (React vs Flask/Django, por exemplo).

---

## 📌 **2. Obrigatório: ler AGENTS.md antes de qualquer alteração**

**Regra:**  
Todo prompt **DEVE** incluir como **primeira tarefa obrigatória** para o agente:  

```markdown
### ⚠️ **Primeira tarefa obrigatória**
Leia o arquivo **`AGENTS.md`** na raiz do repositório e siga **todas** as convenções de:  
- Arquitetura (pastas, camadas, separação de responsabilidades)
- Padrões de nomenclatura (camelCase variáveis/funções, PascalCase componentes/classes)
- Estrutura de imports/exports
- Hooks customizados (Frontend) ou decorators/middlewares (Backend)
- Boas práticas da stack (React, Flask, Django, etc.)
- Políticas de lint, formatação e testes
```

**Justificativa:**  
Garante que o agente respeite padrões do projeto desde o início, reduzindo retrabalho.

---

## 📌 **3. Preservar lógica de negócios e contratos existentes**

**Regra:**  
Explicitar **sempre** que o agente **NÃO DEVE** alterar:  

### 🚫 **Restrições Importantes**

#### **Preservar 100%:**
- ❌ **Não alterar** lógica de negócio (validações, regras, cálculos)
- ❌ **Não alterar** assinaturas de funções/métodos públicos
- ❌ **Não alterar** contratos de API (endpoints, verbos HTTP, estrutura de payloads)
- ❌ **Não alterar** estrutura de request/response (JSON shape, campos obrigatórios)
- ❌ **Não alterar** validações existentes (Zod, Yup, Joi, Pydantic, etc.)
- ❌ **Não alterar** side-effects (envio de emails, webhooks, logs, tracking, analytics)
- ❌ **Não alterar** regras de permissões/autorização
- ❌ **Não remover** código de observabilidade (logs, metrics, tracing)

#### **Mudanças localizadas:**
- ✅ Apenas criar/modificar componentes/módulos diretamente relacionados ao problema
- ✅ Apenas ajustar imports/exports necessários
- ✅ Se necessário, extrair tipos/interfaces para arquivos compartilhados (`types/`, `interfaces/`)

**Justificativa:**  
Mudanças em contratos quebram integrações; mudanças em lógica de negócio introduzem bugs sutis.

---

## 📌 **4. Um prompt não pode ter complexidade > 85/100**

**Regra:**  
Avaliar mentalmente a complexidade do prompt:

| Critério | Peso |
|----------|------|
| Número de arquivos a modificar | +10 por arquivo além de 3 |
| Mudança em API pública/contrato | +30 |
| Alteração de lógica de negócio | +25 |
| Criação de nova feature (vs bugfix) | +15 |
| Dependências externas (libs novas) | +10 |
| Refactor estrutural | +20 |

**Se ultrapassar 85:**  
Quebrar em **múltiplos prompts**, segmentados por:  
- **Responsabilidade** (ex.: separar criação de componente de integração com API)
- **Escopo** (ex.: primeiro criar tipos, depois implementar lógica)
- **Risco** (ex.: primeiro fazer em staging, depois prod)

**Exemplo:**
```
❌ Prompt único (complexidade ~95):
"Criar novo módulo de tags, refatorar API, migrar banco, atualizar frontend"

✅ Prompts segmentados:  
1. [BE - 40] Criar tabela tags + migration
2. [BE - 45] Criar endpoints CRUD /tags
3. [FE - 35] Criar componente TagManager
4. [FE - 40] Integrar componente com API
```

**Justificativa:**  
Prompts complexos geram PRs gigantes, difíceis de revisar, com maior risco de bugs.

---

## 📌 **5. Prompts segmentados por FE e BE**

**Regra:**  
**Nunca** misturar Frontend e Backend no mesmo prompt.  

**Formato obrigatório:**
```markdown
# 🎯 Prompt para Agent Session

---

## 📍 **FRONTEND**
**Repositório:** `owner/repo`
(todo escopo FE aqui)

---

## 📍 **BACKEND**
**Repositório:** `owner/repo-api`
(todo escopo BE aqui)
```

**Justificativa:**  
- Facilita revisão de código (PRs separados)
- Permite deploy independente (FE pode subir antes do BE e vice-versa)
- Reduz risco de conflitos de merge

---

## 📌 **6. Backwards compatibility quando precisar mudar resposta de API**

**Regra:**  
Qualquer mudança de contrato **DEVE** ser **aditiva**. 

**Padrão obrigatório:**
```markdown
### 🔄 **Backwards Compatibility**

**Antes:**
```json
{
  "items": [... ],
  "total": 42
}
```

**Depois (aditivo):**
```json
{
  "items": [...],
  "total": 42,
  "rootUrl": "https://...",  // ✅ NOVO campo
  "metadata": {... }           // ✅ NOVO campo
}
```

**Proibido:**
```json
{
  "data": [...],  // ❌ Renomear "items" → "data" quebra clientes
  "count": 42     // ❌ Renomear "total" → "count" quebra clientes
}
```
```

**Estratégias permitidas:**
- ✅ Adicionar novos campos opcionais
- ✅ Adicionar novos endpoints (versionados, ex.: `/v2/tags`)
- ✅ Deprecar campos (manter funcionando + avisar com `@deprecated`)

**Estratégias proibidas:**
- ❌ Remover campos existentes
- ❌ Renomear campos existentes
- ❌ Mudar tipo de campos (ex.: `string` → `number`)

**Justificativa:**  
Clientes externos (mobile apps, integrações) quebram se contratos mudarem. 

---

## 📌 **7. Evitar refactors amplos / "refatorar por refatorar"**

**Regra:**  
O agente deve **focar em corrigir o problema** com o **menor impacto possível**.

**Proibido:**
- ❌ "Aproveitar para refatorar toda a pasta `utils/`"
- ❌ "Migrar de Axios para Fetch enquanto corrige o bug"
- ❌ "Reorganizar estrutura de pastas no mesmo PR"

**Permitido:**
- ✅ Extrair função auxiliar **se necessário para resolver o problema**
- ✅ Renomear variável **no escopo do arquivo modificado** se melhorar legibilidade

**Formato obrigatório no prompt:**
```markdown
### 🎯 **Objetivo**
(Descrição clara e objetiva do problema a resolver)

**Complexidade estimada:** X/100 (justificar com base nos critérios)

**Escopo:**
- ✅ Apenas modificar arquivo X
- ✅ Apenas criar componente Y
- ❌ NÃO refatorar módulo Z (mesmo que tenha code smells)
```

**Justificativa:**  
Refactors amplos aumentam risco, dificultam revisão e podem introduzir regressões.

---

## 📌 **8. Checklist de Qualidade (executar ao final)**

**Regra:**  
Todo prompt **DEVE** incluir comandos de validação **antes** e **depois**.  

### **Template obrigatório:**

#### **FRONTEND**
```markdown
### 📊 **Checklist de Qualidade**

#### **Antes da implementação:**
```powershell
# No diretório frontend (ou caminho específico)
npm run lint        # Capturar warnings/errors iniciais
npm run typecheck   # Verificar erros de TypeScript
npm test            # Rodar testes existentes
```

#### **Depois da implementação:**
```powershell
npm run lint        # Deve ter ZERO erros adicionais
npm run typecheck   # Deve passar 100%
npm test            # Todos os testes devem continuar passando
npm run build       # Garantir que build de produção não quebrou
```

#### **Testes manuais (descrever no ROADMAP):**
- [ ] Funcionalidade X funciona
- [ ] Edge case Y tratado
- [ ] Responsivo em mobile
- [ ] Acessibilidade (navegação por teclado, screen readers)
```
```

#### **BACKEND**
```markdown
### 📊 **Checklist de Qualidade**

#### **Antes da implementação:**
```powershell
# No diretório backend (ou caminho específico)
pytest -v                    # Rodar suite de testes
flake8 .                     # Linter Python
mypy .                       # Verificar tipos (se usar)
python manage.py check       # Django health check (se aplicável)
```

#### **Depois da implementação:**
```powershell
pytest -v --cov              # Testes + coverage (não pode diminuir)
flake8 .                     # Deve ter ZERO erros adicionais
mypy .                       # Deve passar 100%
python manage.py makemigrations --check --dry-run  # Verificar migrations
```

#### **Testes de integração (descrever no ROADMAP):**
- [ ] Endpoint retorna status code esperado
- [ ] Payload de resposta válido (JSON schema)
- [ ] Validações de input funcionando (400 em casos inválidos)
- [ ] Permissões funcionando (403 quando sem autorização)
```
```

**Justificativa:**  
Garante que o PR não introduz regressões e mantém qualidade do código.

---

## 📌 **9. Medição de Impacto**

**Regra:**  
Todo prompt **DEVE** incluir seção para o agente preencher ao final. 

### **Template obrigatório:**

```markdown
### 🔍 **Medição de Impacto**

#### **Antes:**
```
Linhas de código:  X
Arquivos modificados: 0
Componentes/Módulos afetados: 0
Cobertura de testes: Y%
Tempo de build: Z segundos
```

#### **Depois:**
```
Linhas adicionadas: +A
Linhas removidas: -B
Arquivos criados: C
Arquivos modificados: D
Componentes/Módulos criados: E
Componentes/Módulos modificados:  F
APIs alteradas: 0 (ou listar quais)
Contratos quebrados: 0 (ou listar quais com plano de migração)
Cobertura de testes: Y% (delta:  ±X%)
Tempo de build: Z segundos (delta: ±W segundos)
```

#### **Riscos Identificados:**
- ⚪ Baixo: Mudança localizada, sem side-effects
- 🟡 Médio:  Altera comportamento visível, mas com testes cobrindo
- 🔴 Alto: Altera contrato público ou lógica crítica (requer revisão extra)
```

**Justificativa:**  
Torna tangível o impacto da mudança, facilitando revisão e rollback se necessário.

---

## 📌 **10. ROADMAP Final Obrigatório**

**Regra:**  
Ao concluir, o agente **DEVE** gerar documento comparando solicitado vs implementado.

### **Template obrigatório:**

```markdown
### 📝 **ROADMAP Final**

| Item Solicitado | Status | Observações |
|----------------|--------|-------------|
| Item 1: Criar componente X | ✅ | Arquivo:  `src/components/X.tsx` |
| Item 2: Integrar com API Y | ✅ | Hook: `useQuery(['key'], fetchY)` |
| Item 3: Adicionar validação Z | ⚠️ | Implementado com Zod ao invés de Yup (mais moderno) |
| Item 4: Atualizar testes | ✅ | Coverage: 85% → 88% |
| Item 5: Refatorar módulo W | ❌ | Não implementado:  fora do escopo, criaria PR complexo (>85) |

#### **Legenda:**
- ✅ **Implementado** exatamente como solicitado
- ⚠️ **Adaptado** (explicar motivo:  tecnologia melhor, constraint do framework, etc.)
- ❌ **Não implementado** (justificar:  **risco**, **dependência faltante**, **complexidade**, **tempo**, etc.)

#### **Decisões Técnicas:**
1. **Por que escolhi X ao invés de Y?**
   - (Justificativa técnica)

2. **Por que não refatorei Z?**
   - Fora do escopo (complexidade >85)
   - Risco de regressão alto
   - Pode ser feito em PR separado

#### **Próximos Passos (se aplicável):**
- [ ] Tarefa futura 1
- [ ] Tarefa futura 2
```

**Justificativa:**  
Transparência total sobre o que foi feito, documenta decisões técnicas, facilita handoff.

---

## 📌 **11. Resumo Executivo**

**Regra:**  
Todo prompt **DEVE** incluir seção de resumo no início ou final.

### **Template obrigatório:**

```markdown
## ✅ **Resumo Executivo**

**O que estamos fazendo:**  
(1-2 frases descrevendo o objetivo principal)

**O que NÃO estamos fazendo:**  
(Lista explícita de refactors/mudanças que estão FORA do escopo)

**Tecnologias envolvidas:**  
- Frontend: React, shadcn/ui, Radix UI, TypeScript
- Backend: (se aplicável) Flask, PostgreSQL, Pydantic

**Risco:**  
- ⚪ **Baixo**: Mudança localizada, sem side-effects
- 🟡 **Médio**: Altera comportamento visível, mas com testes cobrindo
- 🔴 **Alto**: Altera contrato público ou lógica crítica (requer revisão extra + testes manuais)

**Prazo estimado:**  
(Se aplicável) Desenvolvimento:  Xh | Revisão: Yh | Deploy: Zh
```

**Justificativa:**  
Permite que qualquer pessoa (PM, tech lead, outro dev) entenda o escopo rapidamente.

---

## 📌 **12. Formato de Entrega dos Prompts**

**Regra:**  
Entregar prompts completos, prontos para copiar e colar.

**Estrutura obrigatória:**

```markdown
# 🎯 Prompt para Agent Session

---

## 📍 **[FRONTEND/BACKEND]**
**Repositório:** `owner/repo-name`

---

### ⚠️ **Primeira tarefa obrigatória**
(Leitura do AGENTS. md)

---

### ✅ **Resumo Executivo**
(O que está sendo feito, o que não está, risco)

---

### 🎯 **Objetivo**
(Descrição detalhada do problema)

**Complexidade estimada:** X/100

---

### 📋 **Escopo de Implementação**

#### **1. Item detalhado**
(Explicação técnica:  onde, como, por quê)

#### **2. Item detalhado**
(Explicação técnica: onde, como, por quê)

(...)

---

### 🚫 **Restrições Importantes**
(Lista de preservações obrigatórias)

---

### 📊 **Checklist de Qualidade**
(Comandos antes/depois)

---

### 🔍 **Medição de Impacto**
(Template para o agente preencher)

---

### 📝 **ROADMAP Final Obrigatório**
(Template de comparação solicitado vs implementado)

---

## ✅ **Resumo Executivo**
(Pode repetir no final para facilitar leitura)
```

**Justificativa:**  
Padronização facilita manutenção, revisão e onboarding de novos devs.

---

## 🎯 **Como Aplicar na Prática**

### **Checklist antes de enviar prompt:**

- [ ] Prompt começa com **FRONTEND** ou **BACKEND**? 
- [ ] Incluí "Primeira tarefa obrigatória" (ler AGENTS.md)?
- [ ] Deixei explícito o que **NÃO PODE** ser alterado?
- [ ] Complexidade está abaixo de 85/100? 
- [ ] Se FE + BE, separei em blocos distintos?
- [ ] Incluí Checklist de Qualidade (comandos antes/depois)?
- [ ] Incluí template de Medição de Impacto? 
- [ ] Incluí template de ROADMAP Final? 
- [ ] Incluí Resumo Executivo (o que fazemos vs o que não fazemos)?
- [ ] Se alterando API, garanti backwards compatibility? 
- [ ] Evitei refactors desnecessários? 

---

## 📚 **Versionamento deste Documento**

Este documento deve ser atualizado sempre que:
- Novas regras forem identificadas através de lições aprendidas
- Padrões do projeto evoluírem
- Feedbacks de code reviews indicarem gaps nas regras

**Última atualização:** 2025-12-15  
**Versão:** 1.0.0
