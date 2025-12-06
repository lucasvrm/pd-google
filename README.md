# PipeDesk Google Drive Backend

Backend API para gerenciamento de estruturas hierárquicas de pastas no Google Drive para o sistema CRM PipeDesk.

## 📋 Índice

- [Visão Geral](#visão-geral)
- [Arquitetura](#arquitetura)
- [Funcionalidades Implementadas](#funcionalidades-implementadas)
- [Instalação e Configuração](#instalação-e-configuração)
- [Uso da API](#uso-da-api)
- [Modelos de Dados](#modelos-de-dados)
- [Serviços](#serviços)
- [Testes](#testes)
- [Deploy](#deploy)
- [Próximos Passos](#próximos-passos)

## 🎯 Visão Geral

O **PipeDesk Google Drive Backend** é uma aplicação FastAPI que gerencia automaticamente estruturas de pastas hierárquicas no Google Drive para entidades de um sistema CRM (Empresas, Leads e Deals). A aplicação:

- Cria e mantém estruturas de pastas organizadas baseadas em templates configuráveis
- Implementa controle de permissões baseado em roles de usuário
- Suporta operações de upload, criação de pastas e listagem de arquivos
- Oferece modo mock para desenvolvimento e testes sem necessidade de credenciais do Google
- Integra-se com banco de dados Supabase para buscar informações das entidades

## 🏗️ Arquitetura

### Componentes Principais

```
pd-google/
├── main.py                 # Aplicação FastAPI principal
├── config.py              # Configurações e variáveis de ambiente
├── database.py            # Configuração SQLAlchemy
├── models.py              # Modelos de dados (ORM)
├── routers/
│   └── drive.py          # Endpoints da API
├── services/
│   ├── google_drive_mock.py      # Implementação mock do Drive
│   ├── google_drive_real.py      # Implementação real do Drive
│   ├── hierarchy_service.py      # Lógica de hierarquia de pastas
│   ├── permission_service.py     # Controle de permissões
│   └── template_service.py       # Aplicação de templates
├── tests/                 # Testes automatizados
├── init_db.py            # Script de inicialização do BD
└── seed_db.py            # Script de seed com dados exemplo
```

### Fluxo de Dados

1. **Cliente** → Requisição HTTP com headers de autenticação
2. **Router** → Valida entidade e permissões
3. **HierarchyService** → Garante estrutura de pastas existe
4. **TemplateService** → Aplica template se necessário
5. **DriveService** → Executa operações no Google Drive (Real ou Mock)
6. **Database** → Mantém mapeamento de entidades ↔ pastas

## ✅ Funcionalidades Implementadas

### 1. Gestão de Estruturas Hierárquicas

- ✅ Criação automática de hierarquia: `/Companies/[Nome da Empresa]/01. Leads/` e `/02. Deals/`
- ✅ Estruturas baseadas em templates configuráveis por tipo de entidade
- ✅ Suporte a subpastas aninhadas (recursão)
- ✅ Mapeamento persistente entre entidades (Company, Lead, Deal) e pastas do Drive

### 2. Templates de Pastas

**Template para Leads:**
```
Lead - [Nome do Lead]/
├── 00. Administração do Lead
├── 01. Originação & Materiais
├── 02. Ativo / Terreno (Básico)
├── 03. Empreendimento & Viabilidade (Preliminar)
├── 04. Partes & KYC (Básico)
└── 05. Decisão Interna
```

**Template para Deals:**
```
Deal - [Nome do Deal]/
├── 00. Administração do Deal
├── 01. Originação & Mandato
├── 02. Ativo / Terreno & Garantias
│   ├── 02.01 Matrículas & RI
│   ├── 02.02 Escrituras / C&V Terreno
│   ├── 02.03 Alvarás & Licenças
│   ├── 02.04 Colateral Adicional
│   └── 02.05 Seguros & Apólices
├── 03. Empreendimento & Projeto
│   ├── 03.01 Plantas & Projetos
│   ├── 03.02 Memoriais & Quadros de Áreas
│   ├── 03.03 Pesquisas de Mercado
│   └── 03.04 Books & Teasers
├── 04. Comercial
│   ├── 04.01 Tabelas de Vendas
│   ├── 04.02 Contratos C&V Clientes
│   └── 04.03 Recebíveis & Borderôs
├── 05. Financeiro & Modelagem
│   ├── 05.01 Viabilidades
│   ├── 05.02 Fluxos de Caixa
│   ├── 05.03 Cronogramas Físico-Financeiros
│   └── 05.04 Planilhas KOA & Modelos
├── 06. Partes & KYC
│   ├── 06.01 Sócios PF
│   └── 06.02 PJs
├── 07. Jurídico & Estruturação
│   ├── 07.01 DD Jurídica
│   └── 07.02 Contratos Estruturais (SCPs, crédito, etc.)
└── 08. Operação & Monitoring
    ├── 08.01 Relatórios Operacionais
    ├── 08.02 Recebíveis / Cash Flow Realizado
    └── 08.03 Comunicação Recorrente
```

**Template para Companies:**
```
[Nome da Empresa]/
├── 01. Leads
├── 02. Deals
├── 03. Documentos Gerais
│   ├── 03.01 Dossiê Sócios PF
│   ├── 03.02 Dossiê PJs
│   └── 03.03 Modelos / Planilhas KOA
├── 90. Compartilhamento Externo
└── 99. Arquivo / Encerrados
```

### 3. Operações de Drive

- ✅ **GET** `/drive/{entity_type}/{entity_id}` - Listar arquivos e pastas
- ✅ **POST** `/drive/{entity_type}/{entity_id}/folder` - Criar subpasta
- ✅ **POST** `/drive/{entity_type}/{entity_id}/upload` - Upload de arquivo

### 4. Sistema de Permissões

- ✅ Mapeamento de roles da aplicação para permissões do Drive:
  - `admin`, `superadmin` → **owner** (controle total)
  - `manager`, `analyst`, `new_business` → **writer** (ler e escrever)
  - `client`, `customer` → **reader** (apenas leitura)
- ✅ Headers HTTP para autenticação: `x-user-id` e `x-user-role`

### 5. Modo Mock e Real

- ✅ **Mock Drive Service**: Simulação em JSON para desenvolvimento (`mock_drive_db.json`)
- ✅ **Real Drive Service**: Integração com Google Drive API usando Service Account
- ✅ Alternância via variável de ambiente `USE_MOCK_DRIVE`

### 6. Integração com Database

- ✅ Suporte a PostgreSQL (produção) e SQLite (desenvolvimento)
- ✅ Modelos para entidades Supabase (Company, Lead, Deal)
- ✅ Modelos para templates e estruturas de pastas
- ✅ Scripts de inicialização (`init_db.py`) e seed (`seed_db.py`)

## 🚀 Instalação e Configuração

### Pré-requisitos

- Python 3.12+
- pip
- PostgreSQL (produção) ou SQLite (desenvolvimento)
- Conta Google Cloud com Drive API habilitada (para modo real)

### 1. Clonar o Repositório

```bash
git clone https://github.com/lucasvrm/pd-google.git
cd pd-google
```

### 2. Instalar Dependências

```bash
pip install -r requirements.txt
```

### 3. Configurar Variáveis de Ambiente

Crie um arquivo `.env` na raiz do projeto:

```env
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/pipedesk_drive
# ou para SQLite local:
# DATABASE_URL=sqlite:///./pd_google.db

# Google Drive (modo real)
USE_MOCK_DRIVE=false
GOOGLE_SERVICE_ACCOUNT_JSON={"type": "service_account", "project_id": "...", ...}
# Ou caminho para o arquivo:
# GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/service-account.json

# Opcional: Pasta raiz no Drive (para isolar estruturas)
DRIVE_ROOT_FOLDER_ID=1234567890abcdef
```

**Modo Mock (desenvolvimento/testes):**
```env
USE_MOCK_DRIVE=true
```

### 4. Inicializar o Banco de Dados

```bash
python init_db.py
```

### 5. Popular com Dados de Exemplo (Opcional)

```bash
python seed_db.py
```

Isso criará:
- Templates para Lead, Deal e Company
- Dados exemplo de Company, Lead e Deal (apenas em SQLite)

### 6. Executar a Aplicação

**Desenvolvimento:**
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Produção (com Gunicorn):**
```bash
gunicorn -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:8000
```

A aplicação estará disponível em `http://localhost:8000`

## 📚 Uso da API

### Documentação Interativa

Acesse a documentação Swagger em: `http://localhost:8000/docs`

### Endpoints Principais

#### 1. Listar Arquivos de uma Entidade

```bash
GET /drive/{entity_type}/{entity_id}

Headers:
  x-user-role: admin|manager|analyst|new_business|client
  x-user-id: user-uuid (opcional)

Parâmetros:
  entity_type: company | lead | deal
  entity_id: UUID da entidade

Resposta:
{
  "files": [
    {
      "id": "folder-uuid",
      "name": "01. Leads",
      "mimeType": "application/vnd.google-apps.folder",
      ...
    }
  ],
  "permission": "writer"
}
```

**Exemplo:**
```bash
curl -X GET "http://localhost:8000/drive/company/comp-123" \
  -H "x-user-role: admin"
```

#### 2. Criar Subpasta

```bash
POST /drive/{entity_type}/{entity_id}/folder

Headers:
  x-user-role: admin|manager (requer permissão de escrita)

Body:
{
  "name": "Nova Pasta"
}

Resposta:
{
  "id": "new-folder-id",
  "name": "Nova Pasta",
  "mimeType": "application/vnd.google-apps.folder",
  ...
}
```

**Exemplo:**
```bash
curl -X POST "http://localhost:8000/drive/deal/deal-001/folder" \
  -H "x-user-role: admin" \
  -H "Content-Type: application/json" \
  -d '{"name": "Documentos Adicionais"}'
```

#### 3. Upload de Arquivo

```bash
POST /drive/{entity_type}/{entity_id}/upload

Headers:
  x-user-role: admin|manager (requer permissão de escrita)

Form Data:
  file: [arquivo]

Resposta:
{
  "id": "file-id",
  "name": "documento.pdf",
  "mimeType": "application/pdf",
  "size": 12345,
  "webViewLink": "https://drive.google.com/..."
}
```

**Exemplo:**
```bash
curl -X POST "http://localhost:8000/drive/lead/lead-001/upload" \
  -H "x-user-role: manager" \
  -F "file=@/path/to/documento.pdf"
```

## 🗄️ Modelos de Dados

### DriveFolder
Mapeia entidades do CRM para pastas no Google Drive.

```python
{
  "id": int,
  "entity_id": str,        # UUID da entidade (company, lead, deal)
  "entity_type": str,      # "company" | "lead" | "deal" | "system_root"
  "folder_id": str,        # ID da pasta no Google Drive
  "created_at": datetime
}
```

### DriveFile
Metadados de arquivos armazenados no Drive.

```python
{
  "id": int,
  "file_id": str,          # ID do arquivo no Google Drive
  "parent_folder_id": str, # ID da pasta pai
  "name": str,
  "mime_type": str,
  "size": int,
  "created_at": datetime
}
```

### DriveStructureTemplate
Define templates de estrutura de pastas por tipo de entidade.

```python
{
  "id": int,
  "name": str,             # Nome do template
  "entity_type": str,      # "company" | "lead" | "deal"
  "active": bool,
  "nodes": [...]           # Lista de DriveStructureNode
}
```

### DriveStructureNode
Nó individual da árvore de pastas em um template.

```python
{
  "id": int,
  "template_id": int,
  "parent_id": int,        # ID do nó pai (null para raiz)
  "name": str,             # Nome da pasta (pode ter placeholders como {{year}})
  "order": int             # Ordem de criação
}
```

### Entidades do CRM (Supabase)

**Company:**
```python
{
  "id": str (UUID),
  "name": str,             # Razão Social
  "fantasy_name": str      # Nome Fantasia
}
```

**Lead:**
```python
{
  "id": str (UUID),
  "title": str,
  "company_id": str
}
```

**Deal:**
```python
{
  "id": str (UUID),
  "title": str,
  "company_id": str
}
```

## 🔧 Serviços

### GoogleDriveService (Mock)
Implementação mock que armazena estruturas em arquivo JSON local.

**Métodos:**
- `create_folder(name, parent_id)` - Cria pasta
- `upload_file(file_content, name, mime_type, parent_id)` - Upload de arquivo
- `list_files(folder_id)` - Lista conteúdo de pasta
- `get_file(file_id)` - Obtém metadados de arquivo

### GoogleDriveRealService
Integração real com Google Drive API v3.

**Autenticação:** Service Account JSON  
**Métodos:** Mesmos do Mock + `add_permission(file_id, role, email)`

### HierarchyService
Gerencia criação e manutenção de hierarquias de pastas.

**Métodos principais:**
- `ensure_company_structure(company_id)` - Garante estrutura da empresa
- `ensure_lead_structure(lead_id)` - Garante estrutura do lead
- `ensure_deal_structure(deal_id)` - Garante estrutura do deal
- `get_or_create_companies_root()` - Cria pasta raiz "Companies"

**Lógica:**
1. Verifica se estrutura já existe no BD
2. Se não existe, busca nome da entidade no Supabase
3. Cria estrutura de pastas no Drive
4. Aplica template configurado
5. Salva mapeamento no BD

### TemplateService
Aplica templates de estrutura de pastas.

**Método principal:**
- `apply_template(entity_type, root_folder_id)` - Cria estrutura recursiva baseada no template ativo

**Funcionalidades:**
- Suporte a aninhamento de pastas (recursão)
- Ordenação por `parent_id` e `order`
- Processamento topológico da árvore de pastas

### PermissionService
Controle de permissões baseado em roles.

**Métodos:**
- `get_drive_permission_from_app_role(app_role, entity_type)` - Mapeia role → permissão
- `mock_check_permission(user_id, entity_type)` - Compatibilidade legada

**Mapeamento:**
```
admin/superadmin → owner
manager/analyst/new_business → writer
client/customer → reader
(padrão) → reader
```

## 🧪 Testes

### Estrutura de Testes

```
tests/
├── test_hierarchy.py          # Testes de hierarquia e integração
├── test_mock_drive.py         # Testes do serviço mock
└── test_template_recursion.py # Testes de templates aninhados
```

### Executar Testes

**Todos os testes:**
```bash
pytest tests/ -v
```

**Teste específico:**
```bash
pytest tests/test_mock_drive.py -v
```

**Com cobertura:**
```bash
pytest tests/ --cov=. --cov-report=html
```

### Configuração de Testes

Os testes usam:
- **Banco de dados:** SQLite em memória (`test.db`, `test_template.db`)
- **Drive Service:** Mock (via `USE_MOCK_DRIVE=true`)
- **Fixtures:** Dados de exemplo criados em `setup_module()`

### Testes Existentes

#### test_mock_drive.py
- ✅ `test_create_folder` - Criação de pasta
- ✅ `test_upload_file` - Upload de arquivo

#### test_hierarchy.py
- ✅ `test_read_root` - Endpoint raiz
- ⚠️ `test_get_drive_company` - Estrutura de empresa (placeholder)
- ✅ `test_invalid_entity_type` - Validação de tipo inválido
- ✅ `test_contact_disabled` - Validação que tipo 'contact' não é suportado

#### test_template_recursion.py
- ⚠️ `test_template_recursion` - Templates aninhados (requer `USE_MOCK_DRIVE=true`)

### Criando Novos Testes

**Estrutura básica:**

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from main import app
import models
import os

# Setup Test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_custom.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

from routers.drive import get_db
app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

def setup_module(module):
    # Configurar USE_MOCK_DRIVE=true
    os.environ["USE_MOCK_DRIVE"] = "true"
    
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    # Seed de dados de teste
    company = models.Company(id="test-comp", name="Test Company")
    db.add(company)
    db.commit()
    db.close()

def teardown_module(module):
    if os.path.exists("./test_custom.db"):
        os.remove("./test_custom.db")

def test_example():
    response = client.get("/drive/company/test-comp", headers={"x-user-role": "admin"})
    assert response.status_code == 200
    data = response.json()
    assert "files" in data
    assert data["permission"] == "owner"
```

### Testes Recomendados a Implementar

- [ ] **test_permissions.py** - Validação de permissões por role
- [ ] **test_upload_flow.py** - Fluxo completo de upload
- [ ] **test_template_creation.py** - Criação e aplicação de templates
- [ ] **test_error_handling.py** - Tratamento de erros (entidade não existe, permissão negada, etc.)
- [ ] **test_real_drive_integration.py** - Testes de integração com Drive real (CI/CD)
- [ ] **test_concurrent_access.py** - Acesso concorrente ao mesmo recurso
- [ ] **test_database_constraints.py** - Validações de constraints do BD

## 🚀 Deploy

### Render

A aplicação está configurada para deploy no Render, utilizando o `Procfile` existente:

```
web: gunicorn -k uvicorn.workers.UvicornWorker main:app
```

**Passos para Deploy:**

#### 1. Criar Web Service no Render

1. Acesse [render.com](https://render.com) e faça login
2. No dashboard, clique em **"New +"** → **"Web Service"**
3. Conecte seu repositório GitHub (`lucasvrm/pd-google`)
4. Configure o serviço:
   - **Name:** `pipedesk-drive-backend` (ou nome desejado)
   - **Region:** Escolha a região mais próxima dos usuários
   - **Branch:** `main`
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:$PORT`

#### 2. Configurar Banco de Dados PostgreSQL

1. No dashboard do Render, clique em **"New +"** → **"PostgreSQL"**
2. Configure o banco:
   - **Name:** `pipedesk-drive-db`
   - **Database:** `pipedesk_drive`
   - **User:** (gerado automaticamente)
   - **Region:** Mesma do web service
3. Após criação, copie a **Internal Database URL** (formato: `postgresql://user:pass@host/db`)

#### 3. Configurar Variáveis de Ambiente

No painel do Web Service, vá em **"Environment"** e adicione:

```bash
# Database - usar Internal Database URL do PostgreSQL criado
DATABASE_URL=postgresql://user:password@host:5432/pipedesk_drive

# Google Drive - modo de operação
USE_MOCK_DRIVE=false

# Credenciais Google Service Account (JSON completo como string)
GOOGLE_SERVICE_ACCOUNT_JSON={"type": "service_account", "project_id": "...", "private_key": "...", ...}

# Opcional: Pasta raiz no Drive para isolar estruturas
DRIVE_ROOT_FOLDER_ID=1234567890abcdef
```

**Importante:**
- A variável `DATABASE_URL` será preenchida automaticamente se você conectar o PostgreSQL do Render
- Para `GOOGLE_SERVICE_ACCOUNT_JSON`, cole todo o conteúdo do arquivo JSON da Service Account (em uma única linha ou entre aspas)
- Se preferir usar arquivo, faça upload via SSH ou configure como secret file

#### 4. Deploy Automático

Após configurar as variáveis:
1. O Render iniciará o build automaticamente
2. A aplicação será deployada quando o build completar
3. Acesse a URL fornecida pelo Render (ex: `https://pipedesk-drive-backend.onrender.com`)

#### 5. Inicializar Banco de Dados

Para executar scripts de inicialização no Render, use o **Shell** do serviço:

1. No dashboard do Web Service, clique em **"Shell"** (ou use o Render CLI)
2. Execute os comandos:

```bash
python init_db.py
python seed_db.py
```

**Alternativa via Render CLI:**
```bash
# Instalar Render CLI
npm install -g render

# Login
render login

# Executar comandos
render shell pipedesk-drive-backend
python init_db.py
python seed_db.py
```

**⚠️ Atenção:**
- O plano gratuito do Render pode ter limitações de tempo de execução
- Considere criar um **Background Worker** separado para scripts longos de inicialização
- Migrations podem ser executadas automaticamente adicionando ao `Build Command`:
  ```
  pip install -r requirements.txt && python init_db.py
  ```

#### 6. Monitoramento e Logs

- **Logs em tempo real:** Disponíveis na aba "Logs" do dashboard
- **Métricas:** CPU, memória e latência disponíveis na aba "Metrics"
- **Health checks:** Configure endpoint `/health` se necessário

### Docker (Futuro)

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "main:app", "--bind", "0.0.0.0:8000"]
```

### Variáveis de Ambiente em Produção

- ✅ `DATABASE_URL` - Connection string PostgreSQL (fornecida pelo Render ou manual)
- ✅ `GOOGLE_SERVICE_ACCOUNT_JSON` - Credenciais Google Service Account (JSON completo como string)
- ✅ `USE_MOCK_DRIVE=false` - Usar Google Drive real (não mock)
- ⚠️ `DRIVE_ROOT_FOLDER_ID` - (Opcional) ID da pasta raiz no Drive para isolar ambientes
- ⚠️ `PORT` - (Automático) Porta fornecida pelo Render (geralmente já configurada)

## 📝 Próximos Passos

### Features Planejadas

#### Alta Prioridade
- [ ] **Webhooks do Google Drive** - Notificações em tempo real de mudanças
- [ ] **Sistema de Cache** - Redis para reduzir chamadas à API do Drive
- [ ] **Audit Log** - Registro de todas as operações (quem, quando, o quê)
- [ ] **Soft Delete** - Marcar pastas/arquivos como deletados sem remover
- [ ] **Busca Avançada** - Buscar arquivos por nome, conteúdo, data, etc.

#### Média Prioridade
- [ ] **Versionamento de Arquivos** - Controle de versões de documentos
- [ ] **Compartilhamento Externo** - Gerar links compartilháveis com expiração
- [ ] **Migração de Estruturas** - Reorganizar pastas de deals antigos
- [ ] **Templates Dinâmicos** - Placeholders como `{{year}}`, `{{company_name}}`
- [ ] **API de Templates** - CRUD completo de templates via API
- [ ] **Sincronização Bidirecional** - Sincronizar mudanças do Drive → BD

#### Baixa Prioridade / Melhorias
- [ ] **GraphQL API** - Alternativa ao REST
- [ ] **Rate Limiting** - Proteção contra abuso
- [ ] **Métricas e Monitoring** - Prometheus/Grafana
- [ ] **Documentação de Código** - Docstrings e type hints completos
- [ ] **CI/CD Pipeline** - GitHub Actions para testes e deploy automático
- [ ] **Docker Compose** - Ambiente de desenvolvimento completo
- [ ] **Suporte a Múltiplos Idiomas** - i18n para mensagens de erro

### Melhorias Técnicas

#### Database
- [ ] Migrations com Alembic
- [ ] Índices adicionais para performance
- [ ] Particionamento de tabelas grandes (arquivos)

#### Segurança
- [ ] Criptografia de credenciais no BD
- [ ] Rate limiting por usuário/IP
- [ ] Validação de MIME types no upload
- [ ] Scan de vírus em uploads (ClamAV)

#### Performance
- [ ] Paginação em listagens grandes
- [ ] Lazy loading de metadados
- [ ] Compressão de respostas (gzip)
- [ ] CDN para arquivos estáticos (se houver)

#### DevOps
- [ ] Health check endpoint (`/health`)
- [ ] Readiness check para K8s
- [ ] Logs estruturados (JSON)
- [ ] Tracing distribuído (OpenTelemetry)

### Bugs Conhecidos

- ⚠️ Testes com Drive real falham sem `USE_MOCK_DRIVE=true`
- ⚠️ Warnings de SQLAlchemy 2.0 (usar `declarative_base()` deprecado)
- ⚠️ Falta validação de tamanho máximo de arquivo no upload
- ⚠️ Possível race condition na criação simultânea de estruturas

## 🤝 Contribuindo

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/NovaFuncionalidade`)
3. Commit suas mudanças (`git commit -m 'Add: Nova funcionalidade'`)
4. Push para a branch (`git push origin feature/NovaFuncionalidade`)
5. Abra um Pull Request

### Convenções de Código

- **Python:** PEP 8
- **Imports:** Usar ordem: stdlib → third-party → local
- **Type Hints:** Sempre que possível
- **Docstrings:** Google style
- **Commits:** Conventional Commits (feat, fix, docs, etc.)

## 📄 Licença

Este projeto é privado e propriedade da PipeDesk.

## 📞 Contato

Para dúvidas ou suporte, contate o time de desenvolvimento PipeDesk.

---

**Última atualização:** 2025-12-06
