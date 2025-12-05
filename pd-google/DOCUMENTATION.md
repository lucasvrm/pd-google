# Documentação Técnica Completa: pd-google (Google Drive Integration Service)

**Versão:** 1.0.0
**Status:** Produção / Desenvolvimento Híbrido
**Responsável:** Equipe de Engenharia PipeDesk

---

## 1. Visão Geral do Projeto

O **pd-google** é um microsserviço desenvolvido em Python utilizando o framework **FastAPI**, projetado para gerenciar a integração entre o ecossistema PipeDesk e o Google Drive. Seu objetivo principal é abstrair a complexidade da API do Google, oferecendo endpoints simplificados e focados nas regras de negócio da empresa, como a criação automática de estruturas de pastas baseadas em templates e o controle de permissões (ACL) mapeado para papéis de usuários do sistema.

### 1.1. Objetivos Principais
1.  **Abstração:** O Frontend (`pipedesk-koa`) não deve conhecer a API do Google Drive diretamente. Ele consome APIs RESTful do `pd-google`.
2.  **Padronização:** Garantir que todo Cliente, Deal ou Lead criado no PipeDesk tenha exatamente a mesma estrutura de pastas (ex: Contratos, Propostas) no Google Drive.
3.  **Segurança:** Centralizar a autenticação via *Service Account*, evitando que tokens de usuários trafeguem pelo cliente, e aplicar regras de permissão (quem pode ver/editar) no lado do servidor.
4.  **Flexibilidade de Desenvolvimento:** Permitir que desenvolvedores trabalhem no projeto sem necessidade de conexão com a internet ou credenciais reais do Google, através de um sistema robusto de Mocking.

---

## 2. Arquitetura do Sistema

O sistema segue uma arquitetura em camadas (Layered Architecture), separando responsabilidades de roteamento, lógica de negócio, acesso a dados e integração externa.

### 2.1. Diagrama de Camadas
```
[ Frontend (React) ]
       | (HTTP/JSON)
       v
[ API Router (FastAPI) ]  <-- Camada de Entrada
       |
[ Services Layer ]        <-- Camada de Negócio (Templates, Permissions)
       |
[ Drivers / Adapters ]    <-- Camada de Infraestrutura (Google API Client ou Mock)
       |
[ Database (SQLAlchemy) ] <-- Camada de Persistência (Postgres/SQLite)
```

### 2.2. Tecnologias Utilizadas
*   **Linguagem:** Python 3.12+
*   **Web Framework:** FastAPI (Alta performance, validação automática com Pydantic, documentação OpenAPI nativa).
*   **ORM:** SQLAlchemy (Abstração de banco de dados, suportando SQLite para dev e PostgreSQL para prod).
*   **Google SDK:** `google-api-python-client` e `google-auth` para comunicação oficial.
*   **Driver Postgres:** `psycopg2-binary`.
*   **Server:** Uvicorn (ASGI server).

---

## 3. Configuração e Ambiente

O serviço é configurado através de variáveis de ambiente, seguindo a metodologia *12-Factor App*. Isso permite que o mesmo código rode em ambiente local, de testes e de produção apenas alterando o arquivo `.env` ou as configurações do PAAS (Render).

### 3.1. Variáveis de Ambiente Críticas

| Variável | Tipo | Descrição | Valor Padrão / Exemplo |
| :--- | :--- | :--- | :--- |
| `DATABASE_URL` | String | String de conexão com o banco de dados. Se omitida, usa SQLite local. | `postgresql://user:pass@host/db` |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | JSON/Path | Conteúdo do JSON da Service Account ou caminho para o arquivo. | `{"type": "service_account", ...}` |
| `USE_MOCK_DRIVE` | Boolean | Se `true`, ignora a API do Google e usa o sistema de arquivos local/memória. | `false` |
| `DRIVE_ROOT_FOLDER_ID` | String | (Opcional) ID da pasta raiz no Drive onde tudo será criado. | `1A2b3C...` |

### 3.2. Modos de Operação (Mock vs Real)

Uma das características mais fortes do `pd-google` é o sistema de injeção de dependência condicional localizado em `routers/drive.py`.

*   **Modo Mock (`USE_MOCK_DRIVE=true`):**
    *   Instancia `GoogleDriveService` (do módulo `google_drive_mock`).
    *   Persiste dados em um arquivo JSON local (`mock_drive_db.json`).
    *   **Vantagem:** Desenvolvimento rápido, testes unitários, sem custo de API, funciona offline.
*   **Modo Real (`USE_MOCK_DRIVE=false`):**
    *   Instancia `GoogleDriveRealService` (do módulo `google_drive_real`).
    *   Autentica usando `google.oauth2.service_account`.
    *   Realiza chamadas HTTP reais para `www.googleapis.com`.

---

## 4. Banco de Dados e Modelagem

O sistema mantém um "espelho" (metadata) das informações críticas para evitar chamadas excessivas à API do Google e para manter relações com as entidades do PipeDesk (Tabelas do Supabase).

### 4.1. Tabelas Principais (`models.py`)

#### `google_drive_folders` (`DriveFolder`)
Mapeia uma entidade do PipeDesk (ex: Cliente #123) para sua pasta raiz no Google Drive.
*   `entity_id` (String): ID do registro no PipeDesk/Supabase.
*   `entity_type` (String): Tipo da entidade ('client', 'deal', 'lead').
*   `folder_id` (String): ID da pasta no Google Drive (Hash `1F8...`).
*   **Uso:** Quando o frontend pede os arquivos do Cliente #123, o backend consulta essa tabela. Se não existir, cria a pasta no Drive e insere o registro.

#### `drive_structure_templates` (`DriveStructureTemplate`)
Define os modelos de pastas. Permite criar árvores de diretórios padronizadas.
*   `name`: Nome do template (ex: "Standard Client").
*   `entity_type`: A qual entidade se aplica (ex: "client").
*   `active`: Flag para desativar templates antigos.

#### `drive_structure_nodes` (`DriveStructureNode`)
Os nós (pastas) individuais dentro de um template.
*   `name`: Nome da pasta (ex: "Contratos").
*   `order`: Ordem de criação/exibição.
*   `parent_id`: Suporte a aninhamento (sub-pastas), permitindo árvores complexas.

#### `user_roles` (`UserRole`)
(Simplificado para o MVP) Mapeia usuários do sistema para papéis de acesso.
*   `user_id`: ID do usuário.
*   `role`: 'admin', 'manager', 'sales'.

---

## 5. Serviços Internos (Core Logic)

A lógica de negócio reside na pasta `services/`.

### 5.1. `TemplateService` (`template_service.py`)
Este serviço é o coração da padronização.
*   **Gatilho:** É invocado automaticamente no `GET /drive/{type}/{id}` quando se detecta que é o primeiro acesso (a pasta raiz ainda não existe).
*   **Fluxo:**
    1.  Verifica se existe um `DriveStructureTemplate` ativo para o `entity_type`.
    2.  Carrega todos os `DriveStructureNode` associados.
    3.  Itera sobre os nós (respeitando a ordem) e chama o `drive_service.create_folder`.
    4.  Cria as subpastas dentro da pasta raiz recém-criada da entidade.

### 5.2. `PermissionService` (`permission_service.py`)
Responsável pela tradução de papéis do negócio para permissões do Drive (ACL).
*   **Lógica Atual (MVP):**
    *   `Admin` -> Retorna `owner` (acesso total).
    *   `Manager` -> Retorna `writer` (pode editar/upload).
    *   `Sales` -> Retorna `reader` (somente leitura).
*   **Integração Frontend:** O frontend recebe essa string e decide se mostra ou esconde os botões de "Upload" e "Criar Pasta".

### 5.3. `GoogleDriveRealService` (`google_drive_real.py`)
Implementação concreta da comunicação com a API v3 do Google Drive.
*   **Autenticação:** Carrega credenciais da variável de ambiente. Suporta tanto o JSON bruto (string) quanto o caminho para o arquivo (file path), aumentando a compatibilidade com diferentes ambientes de deploy (Docker Secrets, Vercel Env, Render Env).
*   **Upload (Streaming):** Utiliza `MediaIoBaseUpload` para realizar uploads de forma eficiente, permitindo envio de arquivos maiores sem estourar a memória do servidor, pois faz o streaming de bytes.
*   **Listagem:** Implementa query strings (`q='...' in parents`) para filtrar arquivos apenas da pasta solicitada.

---

## 6. Referência da API (Endpoints)

A API é RESTful e retorna JSON.

### 6.1. Consultar/Inicializar Pasta
**GET** `/drive/{entity_type}/{entity_id}`

*   **Descrição:** Retorna a lista de arquivos e a permissão do usuário. **Efeito colateral:** Se for o primeiro acesso, cria a pasta raiz e aplica o template de pastas automaticamente.
*   **Response:**
    ```json
    {
      "files": [
        { "id": "...", "name": "Contratos", "mimeType": "application/vnd.google-apps.folder", ... },
        { "id": "...", "name": "doc.pdf", "mimeType": "application/pdf", ... }
      ],
      "permission": "writer"
    }
    ```

### 6.2. Criar Subpasta
**POST** `/drive/{entity_type}/{entity_id}/folder`

*   **Payload:** `{ "name": "Nova Pasta" }`
*   **Lógica:** Busca o ID da pasta raiz da entidade no banco e cria a subpasta dentro dela. Verifica se o usuário tem permissão (implicitamente via role, mas idealmente via middleware no futuro).

### 6.3. Upload de Arquivo
**POST** `/drive/{entity_type}/{entity_id}/upload`

*   **Body:** `multipart/form-data` com campo `file`.
*   **Lógica:**
    1.  Recebe o stream do arquivo.
    2.  Envia para o Google Drive (ou Mock).
    3.  Registra metadados na tabela `drive_files` (opcional no MVP, mas implementado para auditoria).
    4.  Retorna o objeto do arquivo criado, incluindo `webViewLink` para abertura direta.

---

## 7. Guia de Integração Frontend (`pipedesk-koa`)

O frontend deve ser agnóstico à implementação do Drive. Ele apenas consome os dados padronizados.

### 7.1. Configuração do Cliente API
No arquivo `src/services/api.ts`, a base URL é definida dinamicamente:
```typescript
const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
```
Isso permite que no ambiente de produção (Vercel), a variável aponte para o Render (`https://pd-google.onrender.com`), enquanto localmente aponta para localhost.

### 7.2. Componente `DocumentManager`
Este componente encapsula toda a lógica de UI.
*   **Badges de Permissão:** Usa a propriedade `permission` da resposta da API para renderizar um badge visual (ex: "WRITER" em verde, "READER" em cinza).
*   **Bloqueio de Ações:** Se `permission === 'reader'`, os inputs de upload e criação de pasta são removidos do DOM, impedindo ações não autorizadas na interface.

---

## 8. Procedimentos de Deploy

### 8.1. Deploy do Backend (Render/Railway)
1.  Provisionar um serviço Python (Web Service).
2.  Configurar comando de build: `pip install -r pd-google/requirements.txt`.
3.  Configurar comando de start: `uvicorn main:app --host 0.0.0.0 --port $PORT`.
4.  **Variáveis de Ambiente:**
    *   Setar `DATABASE_URL` com a string de conexão do Supabase (Transaction Pooler recomended).
    *   Setar `GOOGLE_SERVICE_ACCOUNT_JSON` com o conteúdo do arquivo JSON da conta de serviço.
    *   Setar `USE_MOCK_DRIVE=false`.

### 8.2. Migração de Banco de Dados
Ao iniciar, o serviço verifica se as tabelas existem. Para produção, recomenda-se usar uma ferramenta de migração como **Alembic**. No MVP atual, o script `init_db.py` ou a inicialização no `main.py` usa `Base.metadata.create_all`, o que é seguro para criar tabelas novas, mas não altera tabelas existentes.

Para popular os templates iniciais em produção, deve-se rodar o script `seed_db.py` uma única vez, ou expor um endpoint administrativo para invocar o seed.

---

## 9. Solução de Problemas (Troubleshooting)

### 9.1. Erro "Service Account not authenticated"
*   **Causa:** Variável `GOOGLE_SERVICE_ACCOUNT_JSON` vazia ou inválida.
*   **Solução:** Verificar se o JSON está completo e se as quebras de linha estão corretas (em alguns painéis de CI/CD, JSONs multi-linha precisam ser codificados em base64 ou escapados).

### 9.2. Erro "ReadOnly Database" (SQLite)
*   **Causa:** Permissões de escrita no diretório onde o arquivo `.db` está salvo, ou uso de `/tmp` em sistemas efêmeros que limpam o disco.
*   **Solução:** Em produção, **sempre usar Postgres**. O SQLite é estritamente para desenvolvimento local.

### 9.3. Frontend não conecta (CORS)
*   **Causa:** O backend está bloqueando a origem do frontend.
*   **Solução:** Verificar a configuração de `CORSMiddleware` no `main.py`. Atualmente configurado para `*` (permissivo) ou `localhost`. Em produção, adicione o domínio do Vercel (`https://seu-app.vercel.app`) à lista `origins`.

---

## 10. Próximos Passos (Roadmap Sugerido)

1.  **Webhooks (Google Drive Push Notifications):** Implementar um endpoint para receber avisos do Google quando um arquivo for modificado externamente (fora do PipeDesk), mantendo o banco sincronizado.
2.  **Visualização Embedada:** Integrar a API de visualização do Google para abrir documentos dentro de um modal no React, em vez de abrir nova aba.
3.  **Migrações Reais:** Adicionar Alembic ao projeto para gerenciar alterações de esquema do banco de forma segura.

---
*Documentação gerada automaticamente por Jules (AI Engineering Agent).*
