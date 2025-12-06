# PLANO DE AÇÃO: Integração Gmail (Domain-Wide Delegation)

Este plano detalha a implementação da integração com Gmail, permitindo envio e sincronização de e-mails agindo em nome dos usuários (Impersonation).

## Fase 1: Infraestrutura & Autenticação
**Objetivo:** Preparar o terreno para autenticação via impersonation e armazenar dados de e-mail.

1.  **Atualizar `services/google_auth.py`:**
    *   Modificar `_authenticate` para aceitar um argumento opcional `subject` (email do usuário).
    *   Se `subject` for fornecido, usar `creds.with_subject(subject)`.
2.  **Migração SQL (`migrations/gmail_tables.sql`):**
    *   Criar tabela `emails` (armazenar remetente, assunto, body, thread_id).
    *   Criar tabela `email_attachments` (linkar e-mail -> arquivo drive).
3.  **Atualizar `models.py`:**
    *   Adicionar classes `Email` e `EmailAttachment`.

## Fase 2: Envio de E-mails
**Objetivo:** Permitir que o frontend dispare e-mails usando a identidade do vendedor.

1.  **Criar `services/google_gmail_service.py`:**
    *   Inicializar com `user_email` (passado para o Auth Service).
    *   Método `send_message(to, subject, body, attachments)`.
2.  **Criar `routers/gmail.py`:**
    *   Endpoint `POST /gmail/send`:
        *   Recebe `x-user-email` no header.
        *   Chama o serviço para enviar.
        *   Salva o e-mail enviado na tabela `emails` (para histórico imediato).

## Fase 3: Sincronização (Leitura Passiva)
**Objetivo:** Trazer e-mails relevantes (de clientes) para dentro do CRM.

1.  **Método `list_history` no Service:**
    *   Usar `users.history.list` com `startHistoryId`.
    *   Se `startHistoryId` for nulo (primeira vez), usar `users.messages.list` (sync inicial limitado).
2.  **Lógica de Filtragem:**
    *   Ao ler uma mensagem, verificar se `From` ou `To` match com `leads` ou `contacts` no banco.
    *   Ignorar e-mails pessoais ou irrelevantes.
3.  **Endpoint `POST /gmail/sync`:**
    *   Recebe `x-user-email`.
    *   Executa a lógica de sync e persiste no banco.

## Fase 4: Anexos & Drive
**Objetivo:** Salvar anexos de e-mails importantes diretamente no Google Drive.

1.  **Pipeline de Anexos:**
    *   No sync, se mensagem tem anexo:
        *   Baixar conteúdo (`users.messages.attachments.get`).
        *   Identificar pasta do Deal/Lead (via tabela `google_drive_folders`).
        *   Upload via `GoogleDriveRealService`.
        *   Criar registro em `email_attachments`.

---

## Riscos & Atenção
*   **Permissões:** O Domain-Wide Delegation **precisa** estar configurado corretamente no Admin Console do Workspace, senão o erro `unauthorized_client` ocorrerá.
*   **Privacidade:** A lógica de filtragem deve ser rigorosa para não expor e-mails pessoais do vendedor no CRM.
