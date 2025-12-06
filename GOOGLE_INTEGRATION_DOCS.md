# Documentação Técnica: Integração Google Workspace (pd-google)

Esta documentação detalha a arquitetura, funcionamento e guia de implementação para a integração dos serviços Google (Drive, Calendar, Meet, Gmail) no backend `pd-google` e suas interfaces com o frontend.

---

## 1. Visão Geral da Arquitetura

O sistema utiliza uma abordagem híbrida de autenticação para interagir com o Google Workspace, priorizando a segurança e a centralização da gestão.

### 1.1. Estratégia de Autenticação
1.  **Service Account (Conta de Serviço):** É o "coração" da integração. Uma identidade de máquina (`service-account@project.iam.gserviceaccount.com`) que possui credenciais próprias.
2.  **Service Account Direta (Drive & Calendar):** Para operações de arquivos e calendário, a Service Account atua como ela mesma. Ela é a "dona" dos arquivos e a "organizadora" das reuniões, convidando os usuários humanos.
3.  **Impersonation / Domain-Wide Delegation (Gmail):** Para enviar e ler e-mails, a Service Account "finge ser" (impersonates) o usuário humano (ex: `vendedor@empresa.com`). Isso permite que o e-mail saia com o remetente correto sem que o usuário precise fazer login via OAuth2 (pop-up).

### 1.2. Fluxo de Dados
*   **Ações do Usuário (Síncronas):** O Frontend chama a API -> Backend chama Google API -> Resposta imediata.
*   **Sincronização (Assíncrona):**
    *   **Drive & Calendar:** Usam **Webhooks** (Push Notifications). O Google avisa o Backend quando algo muda, e o Backend atualiza o banco local.
    *   **Gmail:** Usa **Polling Inteligente** (History API). O Backend consulta periodicamente mudanças na caixa de entrada para importar novos e-mails.

---

## 2. Configuração de Ambiente (DevOps & Admin)

Para que o sistema funcione, as seguintes configurações são obrigatórias no ambiente de produção (Render/Servidor) e no Google Workspace Admin.

### 2.1. Variáveis de Ambiente
*   `GOOGLE_SERVICE_ACCOUNT_JSON`: Conteúdo JSON da chave da Service Account.
*   `WEBHOOK_BASE_URL`: URL pública do backend (ex: `https://api.pipedesk.com`). Necessário para o Google enviar notificações.
*   `WEBHOOK_SECRET`: Token aleatório para validar que o webhook veio mesmo do Google.

### 2.2. Google Workspace (Domain-Wide Delegation)
No painel **Google Admin Console** > **Security** > **API Controls** > **Domain-Wide Delegation**, adicione a Client ID da Service Account com os seguintes escopos:
*   `https://www.googleapis.com/auth/gmail.modify` (Ler e enviar e-mails)
*   `https://www.googleapis.com/auth/calendar` (Gerenciar agenda)
*   `https://www.googleapis.com/auth/drive` (Gerenciar arquivos)

---

## 3. Guia de Implementação: Frontend

O Frontend é responsável por disparar ações e exibir os dados sincronizados. Não é necessário implementar fluxo de OAuth (Login com Google) para o usuário final.

### 3.1. Cabeçalhos Obrigatórios
Para rotas do Gmail (que usam impersonation), é **obrigatório** enviar o cabeçalho identificando o usuário atual:
*   `X-User-Email`: O e-mail do usuário logado no sistema (ex: `joao@empresa.com`).

### 3.2. Módulo: Google Calendar & Meet

**Cenário:** O vendedor quer agendar uma reunião com um Lead.

1.  **Interface de Agendamento:**
    *   Crie um formulário com: Título, Descrição, Data/Hora Início, Data/Hora Fim, Participantes (Emails).
    *   Checkbox: "Gerar link do Google Meet?" (Default: True).

2.  **Chamada de API:**
    *   **POST** `/calendar/events`
    *   **Payload:**
        ```json
        {
          "summary": "Demo com Cliente X",
          "description": "Pauta: Apresentação...",
          "start_time": "2023-10-30T14:00:00Z",
          "end_time": "2023-10-30T15:00:00Z",
          "attendees": ["cliente@empresa.com", "vendedor@suaempresa.com"],
          "create_meet_link": true
        }
        ```

3.  **Resposta & UI:**
    *   O Backend retorna o objeto do evento, incluindo `meet_link`.
    *   Exiba o link na tela e na timeline do Deal.

4.  **Listagem de Eventos:**
    *   Use **GET** `/calendar/events?start_time=...&end_time=...` para mostrar uma agenda visual.
    *   O Backend serve esses dados do banco local (rápido), que é mantido atualizado via Webhooks.

### 3.3. Módulo: Gmail

**Cenário A: Enviar um E-mail**
1.  **Interface:** Editor de texto rico (Rich Text) dentro do Deal.
2.  **Chamada de API:**
    *   **POST** `/gmail/send`
    *   **Header:** `X-User-Email: vendedor@suaempresa.com`
    *   **Payload:**
        ```json
        {
          "to": "cliente@destino.com",
          "subject": "Proposta Comercial",
          "body_html": "<p>Olá, segue a proposta...</p>",
          "entity_id": "deal-uuid-123",  // Opcional: para vincular ao deal
          "entity_type": "deal"
        }
        ```

**Cenário B: Ler E-mails (Sincronização)**
*   O Frontend **não busca no Google**. Ele deve consultar o endpoint de histórico do Backend (a ser implementado na listagem de timeline) que lê da tabela `emails`.
*   **Gatilho de Sync Manual:** Se o usuário quiser ver e-mails novos "agora" (sem esperar o cron job):
    *   **POST** `/gmail/sync`
    *   **Header:** `X-User-Email: ...`
    *   Isso força o Backend a ir no Gmail buscar novidades.

### 3.4. Módulo: Google Drive

**Cenário:** Upload de Arquivo.
1.  **Fluxo:** O Frontend faz upload para o Backend -> Backend salva no Google Drive na pasta correta.
2.  **Rota:** `POST /drive/{entity_type}/{entity_id}/upload`
3.  O Frontend deve enviar o arquivo via `multipart/form-data`.

---

## 4. Referência de API (Endpoints Chave)

| Módulo | Método | Rota | Descrição |
| :--- | :--- | :--- | :--- |
| **Calendar** | `GET` | `/calendar/events` | Lista eventos (filtros: `time_min`, `time_max`). |
| **Calendar** | `POST` | `/calendar/events` | Cria evento + Link Meet. |
| **Calendar** | `PATCH` | `/calendar/events/{id}` | Atualiza horário/detalhes. |
| **Calendar** | `DELETE` | `/calendar/events/{id}` | Cancela evento. |
| **Calendar** | `POST` | `/calendar/watch` | (Admin) Inicia webhook de sync. |
| **Gmail** | `POST` | `/gmail/send` | Envia e-mail (Header `X-User-Email` obrigatório). |
| **Gmail** | `POST` | `/gmail/sync` | Força sincronização de entrada. |
| **Drive** | `POST` | `/drive/{type}/{id}/upload` | Upload de arquivo para pasta da entidade. |
| **Drive** | `POST` | `/drive/{type}/{id}/folders` | Cria estrutura de pastas inicial. |

---

## 5. Detalhes de Implementação Backend (Deep Dive)

### 5.1. Sincronização Bidirecional (Calendar)
*   O Backend registra um **Webhook** (`watch`) no calendário da Service Account.
*   Quando ocorre uma mudança (criação, edição no Google Agenda Web), o Google chama `POST /webhooks/google-drive`.
*   O Backend usa um `syncToken` armazenado no banco (`calendar_sync_states`) para pedir ao Google "apenas o que mudou desde a última vez".
*   Isso garante eficiência e evita loops infinitos.

### 5.2. Gmail History API
*   Diferente de webhooks simples, o Gmail usa uma API de Histórico (`users.history.list`).
*   O Backend guarda o `historyId` mais recente de cada usuário.
*   Na sincronização, ele pede "todas as mensagens alteradas após o `historyId` X".
*   As mensagens são baixadas, processadas (extração de corpo/anexos) e salvas no banco `emails`.

### 5.3. Tabelas Principais (SQL)
*   `calendar_events`: Espelho local da agenda.
*   `emails`: Armazena cabeçalhos e corpo dos e-mails trocados.
*   `email_attachments`: Metadados dos anexos (com link futuro para `drive_files`).
*   `drive_files`: Arquivos gerenciados no Drive.

---

## 6. Checklist para o Frontend Team

1.  [ ] **Garantir Header X-User-Email:** Em todas as chamadas `/gmail/*`, injetar o e-mail do usuário logado.
2.  [ ] **Interface de Agenda:** Implementar visualização consumindo o banco local (`GET /calendar/events`), não a API do Google direta (para evitar latência e quotas).
3.  [ ] **Botão "Sincronizar E-mails":** Adicionar botão na tela de e-mails para chamar `/gmail/sync` com feedback visual de "Carregando...".
4.  [ ] **Link Meet:** Ao exibir detalhes de uma reunião, verificar se o campo `meet_link` existe e mostrar botão "Entrar na Reunião".
