# Database Migrations

Este repositório contém scripts de migração para adicionar soft delete às tabelas do backend pd-google.

## Arquitetura

- **Backend pd-google**: Tem seu próprio banco de dados (PostgreSQL/SQLite) com as tabelas `drive_files` e `google_drive_folders`
- **Supabase**: Banco principal do projeto onde apenas `google_drive_folders` é compartilhada
- A tabela `drive_files` existe APENAS no banco do pd-google

## Como Aplicar as Migrações

### Para Bancos Existentes do Backend pd-google

Execute o script Python que adiciona os campos de soft delete:

```bash
python migrations/add_soft_delete_fields.py
```

Este script adiciona as colunas `deleted_at`, `deleted_by` e `delete_reason` às tabelas `drive_files` e `google_drive_folders` no banco do backend.

### Para Novas Instalações

Não precisa fazer nada! O `init_db.py` já cria as tabelas com os campos de soft delete incluídos.

```bash
python init_db.py
```

### Para o Supabase

Use o arquivo `add_soft_delete_fields.sql` **apenas para a tabela google_drive_folders**:

1. Abra o projeto no Supabase
2. Vá para o **SQL Editor**
3. Copie o conteúdo de `migrations/add_soft_delete_fields.sql`
4. Execute o script

**Importante:** Este script SQL foi projetado para o Supabase e manipula apenas `google_drive_folders`. A lógica de arquivos (`drive_files`) fica totalmente no banco do pd-google.

Para gerenciar migrações do Supabase de forma adequada, use a pasta `supabase/migrations/` do projeto principal, seguindo o fluxo oficial do Supabase.

## O Que as Migrações Fazem

Adicionam três colunas para soft delete:

- `deleted_at` (TIMESTAMP WITH TIME ZONE) - Quando o item foi deletado
- `deleted_by` (VARCHAR) - ID do usuário que deletou
- `delete_reason` (VARCHAR) - Razão opcional para a deleção

E criam índices em `deleted_at` para queries eficientes.

## Script Python vs SQL

- **Python** (`add_soft_delete_fields.py`): Para o banco do backend pd-google (recomendado)
- **SQL** (`add_soft_delete_fields.sql`): Para adicionar campos no Supabase apenas em `google_drive_folders`

## Verificação

Após rodar a migração, verifique se as colunas foram criadas:

**No banco do pd-google:**
```python
python -c "from database import engine; from sqlalchemy import inspect; inspector = inspect(engine); print([c['name'] for c in inspector.get_columns('drive_files')])"
```

**No Supabase:**
```sql
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'google_drive_folders' 
  AND column_name IN ('deleted_at', 'deleted_by', 'delete_reason');
```

Deve retornar 3 linhas.
