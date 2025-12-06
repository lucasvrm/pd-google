# RELATÓRIO DE ESTRATÉGIA: Integração Gmail (Via Domain-Wide Delegation)

## 1. Mudança de Paradigma: Impersonation (Domain-Wide Delegation)
Diferente do Calendar/Drive (onde a Service Account agia por si mesma), no Gmail precisamos que o sistema **aja em nome do usuário** (ex: `joao@empresa.com` envia e-mail, e não `service-account@gcp...`).

*   **Requisito Crítico (Infra):** Você precisará habilitar o **Domain-Wide Delegation (DWD)** no Google Admin Console.
    *   **Client ID:** O ID da Service Account existente.
    *   **Scopes:** `https://www.googleapis.com/auth/gmail.modify` (para ler, enviar e organizar).
*   **No Código:** A autenticação mudará. O objeto `Credentials` da Service Account precisará ser instanciado com `subject='email.do.usuario@empresa.com'`.

## 2. Estratégia de Sincronização (Leitura Passiva)
O Gmail não envia webhooks simples (HTTP POST) como o Drive. Ele usa **Google Cloud Pub/Sub**, que exige configuração complexa de infraestrutura GCP.
**Recomendação para MVP (Simplicidade):** **Polling Inteligente (Cron Job) + History API**.
1.  A cada X minutos, o sistema verifica a API `users.history.list` para cada usuário ativo.
2.  Busca apenas mensagens novas desde o último `historyId`.
3.  **Filtragem de Relevância:**
    *   O e-mail recebido é de um remetente que consta na tabela `leads` ou `contacts`?
    *   Se SIM: Importa o e-mail para o CRM.
    *   Se NÃO: Ignora (privacidade do usuário).

## 3. Integração com Drive (Anexos)
Aproveitaremos a infraestrutura de Drive já criada.
*   Ao processar um e-mail relevante, se houver anexos:
    1.  Baixa o stream do anexo do Gmail.
    2.  Identifica a pasta do Lead/Deal no Drive (via tabela `google_drive_folders`).
    3.  Upload imediato usando o `GoogleDriveRealService`.
    4.  Cria registro na tabela `drive_files`.

## 4. Modelo de Dados

```sql
CREATE TABLE emails (
    id SERIAL PRIMARY KEY,
    google_message_id VARCHAR(255) UNIQUE NOT NULL,
    thread_id VARCHAR(255) NOT NULL,

    -- Associações
    user_email VARCHAR(255),       -- Quem enviou/recebeu (o dono da caixa)
    entity_id VARCHAR(255),        -- Lead/Deal ID vinculado
    entity_type VARCHAR(50),       -- 'lead', 'deal'

    -- Conteúdo
    subject VARCHAR(255),
    from_address VARCHAR(255),
    to_address TEXT,               -- Lista de emails
    snippet TEXT,                  -- Resumo curto
    body_html TEXT,                -- Conteúdo completo (sanitizado)

    internal_date TIMESTAMP,       -- Data real do email
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE email_attachments (
    id SERIAL PRIMARY KEY,
    email_id INTEGER REFERENCES emails(id),
    drive_file_id INTEGER REFERENCES drive_files(id), -- Link com o arquivo salvo no Drive
    file_name VARCHAR(255),
    mime_type VARCHAR(255)
);
```

## 5. Fluxos de API Propostos

### A. Envio de Email (Frontend -> Backend)
**`POST /gmail/send`**
*   **Header:** `x-user-email: vendedor@empresa.com` (Obrigatório para saber quem impersonar).
*   **Body:**
    ```json
    {
      "to": "cliente@externo.com",
      "subject": "Proposta Comercial",
      "body": "<p>Olá...</p>",
      "entity_id": "deal_123",  // Para já vincular no histórico
      "attachments": [...]      // Opcional (IDs de arquivos do Drive ou upload novo)
    }
    ```

### B. Listagem (Backend -> Frontend)
**`GET /gmail/threads/{entity_id}`**
*   Retorna todos os e-mails trocados com aquele Lead/Deal, ordenados cronologicamente.
*   Lê do banco local (`emails`), garantindo performance instantânea.

### C. Sincronização (Background Task)
**`POST /gmail/sync`** (Pode ser chamado por um cron externo ou manualmente)
*   Itera sobre os usuários ativos.
*   Chama `GmailService.sync_history(user_email)`.
*   Processa mensagens e salva anexos.

## 6. Próximos Passos (Plano de Ação)
1.  **Fase 1: Auth & Core:** Atualizar `GoogleAuthService` para suportar `subject` (impersonation) e criar `GoogleGmailService`.
2.  **Fase 2: Envio:** Implementar endpoint de envio de e-mail.
3.  **Fase 3: DB & Sync:** Criar tabelas e lógica de leitura (`history.list`).
4.  **Fase 4: Anexos:** Ligar Gmail -> Drive.
