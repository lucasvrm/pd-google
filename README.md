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
  - Suporta `include_deleted=true` para incluir itens marcados como deletados
- ✅ **POST** `/drive/{entity_type}/{entity_id}/folder` - Criar subpasta
- ✅ **POST** `/drive/{entity_type}/{entity_id}/upload` - Upload de arquivo
- ✅ **DELETE** `/drive/{entity_type}/{entity_id}/files/{file_id}` - Soft delete de arquivo
- ✅ **DELETE** `/drive/{entity_type}/{entity_id}/folders/{folder_id}` - Soft delete de pasta

### 4. Soft Delete

- ✅ Arquivos e pastas podem ser marcados como deletados sem remoção física do Drive
- ✅ Campos de auditoria: `deleted_at`, `deleted_by`, `delete_reason`
- ✅ Itens deletados não aparecem em listagens por padrão
- ✅ Parâmetro `include_deleted=true` permite visualizar itens deletados (uso administrativo)
- ✅ Integração com cache (invalidação automática após soft delete)
- ✅ Registro em audit log (DriveChangeLog) de todas as operações de soft delete
- ✅ Requer permissão de escrita (writer ou owner)

### 5. Sistema de Permissões

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
- Redis (opcional, para cache de operações do Drive)
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

# Redis Cache (opcional, recomendado para produção)
REDIS_URL=redis://localhost:6379/0
REDIS_CACHE_ENABLED=true
REDIS_DEFAULT_TTL=180  # Tempo de vida do cache em segundos (padrão: 180s = 3min)
```

**Modo Mock (desenvolvimento/testes):**
```env
USE_MOCK_DRIVE=true
# Cache é automaticamente desabilitado em modo mock
```

**Desabilitar Cache:**
```env
REDIS_CACHE_ENABLED=false
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

### 6. Configurar Redis (Opcional, Recomendado para Produção)

O Redis é usado como cache para reduzir chamadas repetidas à API do Google Drive, melhorando significativamente a performance em operações de listagem.

**Instalar Redis localmente:**

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

**macOS (via Homebrew):**
```bash
brew install redis
brew services start redis
```

**Docker:**
```bash
docker run -d -p 6379:6379 --name redis redis:alpine
```

**Verificar se Redis está rodando:**
```bash
redis-cli ping
# Deve retornar: PONG
```

**Configurar variáveis de ambiente:**
```env
REDIS_URL=redis://localhost:6379/0
REDIS_CACHE_ENABLED=true
REDIS_DEFAULT_TTL=180  # 3 minutos
```

**Como funciona o cache:**
- ✅ Operações de **leitura** (`list_files`) usam cache com TTL configurável
- ✅ Cache é **invalidado automaticamente** após operações de escrita (upload, criação de pasta)
- ✅ Em modo **mock** (`USE_MOCK_DRIVE=true`), o cache é automaticamente desabilitado
- ✅ Se Redis não estiver disponível, o sistema continua funcionando normalmente (degradação graciosa)

**Monitorar cache:**
```bash
# Ver chaves armazenadas
redis-cli KEYS "drive:*"

# Ver valor de uma chave específica
redis-cli GET "drive:list_files:folder-id"

# Limpar todo o cache
redis-cli FLUSHDB
```

### 7. Executar a Aplicação

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

#### 4. Soft Delete de Arquivo

```bash
DELETE /drive/{entity_type}/{entity_id}/files/{file_id}

Headers:
  x-user-role: admin|manager (requer permissão de escrita)
  x-user-id: user-uuid

Query Parameters:
  reason: (opcional) Motivo da exclusão

Resposta:
{
  "status": "deleted",
  "file_id": "file-id",
  "deleted_at": "2025-12-06T16:00:00.000000+00:00",
  "deleted_by": "user-uuid"
}
```

**Exemplo:**
```bash
curl -X DELETE "http://localhost:8000/drive/lead/lead-001/files/file-abc123?reason=Arquivo%20duplicado" \
  -H "x-user-role: admin" \
  -H "x-user-id: user-123"
```

#### 5. Soft Delete de Pasta

```bash
DELETE /drive/{entity_type}/{entity_id}/folders/{folder_id}

Headers:
  x-user-role: admin|manager (requer permissão de escrita)
  x-user-id: user-uuid

Query Parameters:
  reason: (opcional) Motivo da exclusão

Resposta:
{
  "status": "deleted",
  "folder_id": "folder-id",
  "deleted_at": "2025-12-06T16:00:00.000000+00:00",
  "deleted_by": "user-uuid"
}
```

**Exemplo:**
```bash
curl -X DELETE "http://localhost:8000/drive/company/comp-001/folders/folder-xyz789?reason=Reorganizacao" \
  -H "x-user-role: admin" \
  -H "x-user-id: user-123"
```

#### 6. Listar com Itens Deletados

Para incluir itens marcados como deletados na listagem (uso administrativo):

```bash
curl -X GET "http://localhost:8000/drive/company/comp-001?include_deleted=true" \
  -H "x-user-role: admin"
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
  "created_at": datetime,
  # Campos de soft delete
  "deleted_at": datetime,  # Timestamp da exclusão (null se não deletado)
  "deleted_by": str,       # User ID que realizou a exclusão
  "delete_reason": str     # Motivo da exclusão (opcional)
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
  "created_at": datetime,
  # Campos de soft delete
  "deleted_at": datetime,  # Timestamp da exclusão (null se não deletado)
  "deleted_by": str,       # User ID que realizou a exclusão
  "delete_reason": str     # Motivo da exclusão (opcional)
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

**Cache integrado:**
- ✅ `list_files(folder_id)` usa cache Redis (TTL configurável)
- ✅ `upload_file()` e `create_folder()` invalidam cache automaticamente
- ✅ Cache desabilitado em modo mock ou quando `REDIS_CACHE_ENABLED=false`

### CacheService
Camada de cache Redis para operações do Google Drive.

**Funcionalidades:**
- `get_from_cache(key)` - Recupera valor do cache
- `set_in_cache(key, value, ttl)` - Armazena valor no cache
- `delete_key(key)` - Remove chave específica
- `invalidate_cache(pattern)` - Remove todas as chaves que correspondem a um padrão
- `flush_all()` - Limpa todo o cache (use com cautela)

**Comportamento:**
- Habilitado apenas em modo **real** (`USE_MOCK_DRIVE=false`)
- Degradação graciosa: se Redis não estiver disponível, continua funcionando sem cache
- Chaves de cache: formato `drive:list_files:{folder_id}`
- TTL padrão: 180 segundos (configurável via `REDIS_DEFAULT_TTL`)

**Invalidação automática:**
- Upload de arquivo → invalida cache da pasta pai
- Criação de pasta → invalida cache da pasta pai
- Soft delete → invalida cache da pasta impactada

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
├── test_cache.py              # Testes do sistema de cache Redis
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

#### test_cache.py
- ✅ `test_cache_disabled_in_mock_mode` - Cache desabilitado em modo mock
- ✅ `test_cache_disabled_when_redis_cache_enabled_false` - Cache desabilitado via configuração
- ✅ `test_cache_operations_when_disabled` - Operações seguras quando desabilitado
- ✅ `test_cache_set_and_get` - Operações básicas de set/get
- ✅ `test_cache_get_miss` - Comportamento em cache miss
- ✅ `test_cache_delete_key` - Deletar chave específica
- ✅ `test_cache_invalidate_pattern` - Invalidar por padrão
- ✅ `test_cache_flush_all` - Limpar todo o cache
- ✅ `test_cache_connection_failure` - Degradação graciosa em falha de conexão
- ✅ `test_cache_with_default_ttl` - TTL padrão configurável

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
   - **Runtime:** `Python 3.12` (ou versão compatível - veja `requirements.txt`)
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn -k uvicorn.workers.UvicornWorker main:app`

**Nota:** O Render configura automaticamente a variável `PORT` e o binding de rede. O comando acima usa o mesmo formato do `Procfile` existente.

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
- Para conectar o PostgreSQL ao web service automaticamente:
  1. No painel do Web Service, vá em **"Environment"**
  2. Clique em **"Add from database"** e selecione o banco PostgreSQL criado
  3. O Render preencherá automaticamente a variável `DATABASE_URL`
- Alternativamente, copie manualmente a **Internal Database URL** do PostgreSQL e adicione como variável de ambiente
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
- **Não recomendado:** Executar migrations automaticamente no `Build Command` pode causar problemas com múltiplas instâncias sendo deployadas simultaneamente. Prefira executar manualmente via Shell após o primeiro deploy.

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
- ✅ `WEBHOOK_BASE_URL` - URL pública base para webhooks (ex: `https://pipedesk-drive-backend.onrender.com`)
- ⚠️ `WEBHOOK_SECRET` - (Opcional) Token secreto para validação de webhooks

## 🔔 Webhooks do Google Drive

A aplicação suporta **notificações em tempo real** do Google Drive através de webhooks. Quando arquivos ou pastas são modificados no Drive, o Google envia uma notificação HTTP para o backend, permitindo sincronização e auditoria de mudanças.

### Visão Geral

O sistema de webhooks permite:
- ✅ **Notificações em tempo real** de mudanças (add, update, remove, trash, etc.)
- ✅ **Registro de canais** de notificação para pastas específicas
- ✅ **Renovação automática** de canais antes da expiração
- ✅ **Auditoria completa** de todas as mudanças recebidas
- ✅ **Mapeamento automático** para entidades internas (Company, Lead, Deal)

### Arquitetura

```
Google Drive → Webhook Notification → POST /webhooks/google-drive
                                           ↓
                                  Validate Headers & Channel
                                           ↓
                                  Log to DriveChangeLog
                                           ↓
                                  Map to DriveFolder/DriveFile
```

### Configuração

#### 1. Variáveis de Ambiente

```env
# URL pública da aplicação (obrigatório para webhooks)
WEBHOOK_BASE_URL=https://pipedesk-drive-backend.onrender.com

# Token secreto para validação (opcional, mas recomendado)
WEBHOOK_SECRET=seu-token-secreto-aleatorio
```

#### 2. Habilitar na Google Cloud Console

Para usar webhooks em produção, você precisa configurar o domínio na Google Cloud:

1. Acesse [Google Cloud Console](https://console.cloud.google.com)
2. Navegue até **APIs & Services** → **Domain Verification**
3. Adicione e verifique seu domínio (ex: `pipedesk-drive-backend.onrender.com`)
4. Em **APIs & Services** → **Drive API**, certifique-se que a API está habilitada
5. A Service Account precisa ter permissões para criar notificações

**Nota:** A verificação de domínio é necessária apenas para ambientes de produção. Em desenvolvimento com `USE_MOCK_DRIVE=true`, os webhooks são simulados.

### API de Webhooks

#### Endpoint Principal

```
POST /webhooks/google-drive
```

Este endpoint recebe notificações do Google Drive. **Não deve ser chamado manualmente** - apenas pelo Google Drive.

**Headers Esperados:**
- `X-Goog-Channel-ID`: ID único do canal
- `X-Goog-Resource-ID`: ID único do recurso
- `X-Goog-Resource-State`: Estado da notificação (`sync`, `add`, `update`, `remove`, `trash`, `untrash`, `change`)
- `X-Goog-Resource-URI`: URI do recurso modificado
- `X-Goog-Message-Number`: Número sequencial da mensagem
- `X-Goog-Channel-Token`: Token de verificação (se configurado)

**Estados de Notificação:**
- `sync` - Notificação inicial quando canal é criado (handshake)
- `add` - Novo arquivo/pasta criado
- `remove` - Arquivo/pasta removido
- `update` - Arquivo/pasta modificado
- `change` - Mudança genérica
- `trash` - Movido para lixeira
- `untrash` - Restaurado da lixeira

**Exemplo de Resposta:**
```json
{
  "status": "ok",
  "message": "notification received and logged",
  "resource_state": "update",
  "channel_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

#### Status dos Canais

```
GET /webhooks/google-drive/status
```

Retorna informações sobre todos os canais ativos de webhook.

**Resposta:**
```json
{
  "active_channels": 2,
  "channels": [
    {
      "channel_id": "123e4567-e89b-12d3-a456-426614174000",
      "watched_resource": "folder-abc-123",
      "resource_type": "folder",
      "expires_at": "2025-12-07T15:23:55.000Z",
      "created_at": "2025-12-06T15:23:55.000Z"
    }
  ]
}
```

### Gerenciamento de Canais

Use o `WebhookService` para gerenciar canais de notificação:

```python
from services.webhook_service import WebhookService
from database import SessionLocal

db = SessionLocal()
webhook_service = WebhookService(db)

# Registrar novo canal para uma pasta
channel = webhook_service.register_webhook_channel(
    folder_id="1234567890abcdef",  # ID da pasta no Google Drive
    resource_type="folder",
    ttl_hours=24  # Tempo de vida (máximo 24h)
)

# Renovar canal antes da expiração
new_channel = webhook_service.renew_webhook_channel(
    channel_id=channel.channel_id,
    ttl_hours=24
)

# Parar canal
webhook_service.stop_webhook_channel(channel_id=channel.channel_id)

# Listar canais ativos
active_channels = webhook_service.get_active_channels()

# Limpar canais expirados
count = webhook_service.cleanup_expired_channels()
```

### Modelos de Dados

#### DriveWebhookChannel

Armazena informações sobre canais de notificação registrados.

```python
{
  "id": 1,
  "channel_id": "123e4567-e89b-12d3-a456-426614174000",
  "resource_id": "xyz-resource-789",
  "resource_type": "folder",
  "watched_resource_id": "folder-abc-123",
  "expires_at": "2025-12-07T15:23:55.000Z",
  "active": true,
  "created_at": "2025-12-06T15:23:55.000Z"
}
```

#### DriveChangeLog

Registra todas as notificações recebidas (audit log).

```python
{
  "id": 1,
  "channel_id": "123e4567-e89b-12d3-a456-426614174000",
  "resource_id": "xyz-resource-789",
  "resource_state": "update",
  "changed_resource_id": "file-def-456",
  "event_type": "content,parents",
  "received_at": "2025-12-06T15:24:00.000Z",
  "raw_headers": "{...}"  // JSON com todos os headers
}
```

### Ciclo de Vida dos Canais

1. **Registro**: Canal é criado com TTL de até 24 horas
2. **Sync**: Google envia notificação `sync` inicial (handshake)
3. **Notificações**: Google envia notificações de mudanças enquanto ativo
4. **Renovação**: Antes da expiração, canal deve ser renovado
5. **Expiração**: Canais expirados são automaticamente desativados
6. **Limpeza**: Use `cleanup_expired_channels()` periodicamente

**Importante:** Canais do Google Drive expiram em até 24 horas. É recomendado configurar um job periódico (ex: cron) para renovar canais antes da expiração.

### Exemplo de Fluxo Completo

```python
# 1. Criar estrutura de pastas para uma empresa
from services.hierarchy_service import HierarchyService

hierarchy = HierarchyService(db)
company_folder = hierarchy.ensure_company_structure("company-123")

# 2. Registrar webhook para monitorar a pasta da empresa
webhook_service = WebhookService(db)
channel = webhook_service.register_webhook_channel(
    folder_id=company_folder.folder_id,
    ttl_hours=24
)

# 3. Google Drive envia notificações quando arquivos são modificados
# → POST /webhooks/google-drive

# 4. Consultar log de mudanças
logs = db.query(DriveChangeLog).filter(
    DriveChangeLog.channel_id == channel.channel_id
).all()

for log in logs:
    print(f"{log.resource_state}: {log.changed_resource_id}")
```

### Testes

Execute os testes de webhook:

```bash
pytest tests/test_webhooks.py -v
```

**Cobertura de Testes:**
- ✅ Validação de headers obrigatórios
- ✅ Notificações sync vs change
- ✅ Validação de token secreto
- ✅ Registro e renovação de canais
- ✅ Limpeza de canais expirados
- ✅ Mapeamento para entidades internas

### Modo Mock (Desenvolvimento)

Com `USE_MOCK_DRIVE=true`, os webhooks funcionam em modo simulado:
- Canais são registrados no banco, mas não no Google
- Notificações podem ser enviadas manualmente via HTTP
- Útil para testes locais sem configurar Google Cloud

**Exemplo de teste manual:**
```bash
curl -X POST http://localhost:8000/webhooks/google-drive \
  -H "X-Goog-Channel-ID: test-channel" \
  -H "X-Goog-Resource-ID: test-resource" \
  -H "X-Goog-Resource-State: update" \
  -H "X-Goog-Channel-Token: test-secret-123"
```

### Limitações e Considerações

- **Máximo de 24 horas**: Canais expiram após 24h e devem ser renovados
- **Limite de canais**: Google limita número de canais por projeto (consulte quotas)
- **Notificações agregadas**: Google pode agregar múltiplas mudanças em uma notificação
- **Ordem não garantida**: Notificações podem chegar fora de ordem
- **Reenvios**: Google pode reenviar notificações em caso de falha

### Troubleshooting

**Webhook não recebe notificações:**
1. Verifique se `WEBHOOK_BASE_URL` está configurado corretamente
2. Certifique-se que o domínio está verificado no Google Cloud
3. Confirme que o canal está ativo: `GET /webhooks/google-drive/status`
4. Verifique logs da aplicação para erros

**Token inválido:**
- Certifique-se que `WEBHOOK_SECRET` está configurado igual no código e no registro do canal

**Canais expiram frequentemente:**
- Configure um job cron para executar `cleanup_expired_channels()` e renovar canais automaticamente

## 📝 Próximos Passos

### Features Planejadas

#### Alta Prioridade
- [x] **Webhooks do Google Drive** - Notificações em tempo real de mudanças ✅
- [x] **Sistema de Cache** - Redis para reduzir chamadas à API do Drive ✅
- [x] **Soft Delete** - Marcar pastas/arquivos como deletados sem remover ✅
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
