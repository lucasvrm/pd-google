# Google Tasks API Router

Este documento descreve o conjunto de endpoints expostos em `/api/tasks` para integração com o Google Tasks.

## Autenticação e escopo

- Todos os endpoints exigem autenticação via dependência `get_current_user`, compatível com JWT ou cabeçalhos legados `x-user-id`.
- As chamadas usam o escopo `https://www.googleapis.com/auth/tasks` por meio de uma conta de serviço configurada na variável `GOOGLE_SERVICE_ACCOUNT_JSON`.

## Endpoints

### Listar tarefas
- **GET** `/api/tasks`
- **Query params:**
  - `project_id` (obrigatório): ID da lista/projeto (tasklist) no Google Tasks.
  - `due_from` / `due_to` (opcionais): filtros de vencimento (RFC3339).
  - `page_token` (opcional): token de paginação retornado pelo Google.
  - `include_completed` (opcional, padrão `true`): inclui tarefas concluídas.
- **Resposta:** `TaskListResponse` com lista de tarefas e `next_page_token`.

### Obter tarefa
- **GET** `/api/tasks/{task_id}`
- **Query params:**
  - `project_id` (obrigatório): lista/projeto associado.
- **Resposta:** `TaskResponse` da tarefa específica.

### Criar tarefa
- **POST** `/api/tasks`
- **Body:** `TaskCreate` contendo `tasklist_id`, `title`, `notes`, `due` e `status` (opcionais).
- **Resposta:** `TaskResponse` com dados retornados pelo Google.

### Atualizar tarefa
- **PATCH** `/api/tasks/{task_id}`
- **Query params:**
  - `project_id` (obrigatório): lista/projeto associado.
- **Body:** `TaskUpdate` com campos parciais.
- **Resposta:** `TaskResponse` atualizado.

### Concluir tarefa
- **POST** `/api/tasks/{task_id}/complete`
- **Query params:**
  - `project_id` (obrigatório): lista/projeto associado.
- **Resposta:** `TaskResponse` com status e data de conclusão atualizados.

### Excluir tarefa
- **DELETE** `/api/tasks/{task_id}`
- **Query params:**
  - `project_id` (obrigatório): lista/projeto associado.
- **Resposta:** `204 No Content`.

## Retries e Resiliência

As chamadas ao Google Tasks usam o `GoogleTasksService`, que aplica retentativas com backoff exponencial para erros transitórios (429, 5xx ou falhas de rede), limitando a 3 tentativas com crescimento de até 16 segundos.
