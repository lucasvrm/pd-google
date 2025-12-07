# Database Migrations

Este repositório contém scripts de migração para adicionar soft delete às tabelas do backend pd-google.

## ⚠️ IMPORTANTE: Arquitetura do Banco de Dados

O backend pd-google usa **UM ÚNICO BANCO DE DADOS**: o **PostgreSQL do Supabase**.

- **Em produção (Render)**: `DATABASE_URL` aponta para Supabase PostgreSQL
- **Em desenvolvimento**: Pode usar SQLite local ou PostgreSQL do Supabase
- **Todas as tabelas** (`drive_files`, `google_drive_folders`, `companies`, `deals`, `leads`, etc.) estão no mesmo banco

## 🚀 Como Aplicar as Migrações

### Opção 1: Script Python (Recomendado para Produção)

Execute o script Python que adiciona os campos de soft delete automaticamente:

```bash
# Certifique-se de que DATABASE_URL está configurado
export DATABASE_URL="postgresql://user:password@host:port/database"

# Execute a migração
python migrations/add_soft_delete_fields.py
```

**O que esse script faz:**
- ✅ Adiciona colunas `deleted_at`, `deleted_by` e `delete_reason` às tabelas `drive_files` e `google_drive_folders`
- ✅ Cria índices para queries eficientes
- ✅ É **idempotente** (seguro rodar múltiplas vezes)
- ✅ Funciona com PostgreSQL e SQLite

### Opção 2: SQL Manual (Para Supabase SQL Editor)

Se preferir executar via Supabase SQL Editor:

1. Abra seu projeto no **Supabase Dashboard**
2. Vá para **SQL Editor**
3. Copie e cole o conteúdo de `migrations/add_soft_delete_fields.sql`
4. Execute o script

**O que esse script faz:**
- ✅ Adiciona soft delete apenas à tabela `google_drive_folders` 
- ✅ É **idempotente** (seguro rodar múltiplas vezes)
- ⚠️ **Limitação**: Este script SQL não migra a tabela `drive_files`

**Para migrar ambas as tabelas via SQL**, você também precisa executar:

```sql
-- Adicionar soft delete à tabela drive_files
ALTER TABLE drive_files ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE drive_files ADD COLUMN IF NOT EXISTS deleted_by VARCHAR;
ALTER TABLE drive_files ADD COLUMN IF NOT EXISTS delete_reason VARCHAR;
CREATE INDEX IF NOT EXISTS ix_drive_files_deleted_at ON drive_files (deleted_at);
```

### Para Novas Instalações

Não precisa fazer nada! O `init_db.py` já cria as tabelas com os campos de soft delete incluídos.

```bash
python init_db.py
```

## 🔍 O Que as Migrações Fazem

Adicionam três colunas para soft delete às tabelas:

- `deleted_at` (TIMESTAMP WITH TIME ZONE) - Quando o item foi deletado
- `deleted_by` (VARCHAR) - ID do usuário que deletou
- `delete_reason` (VARCHAR) - Razão opcional para a deleção

E criam índices em `deleted_at` para queries eficientes.

## ✅ Verificação Pós-Migração

Após rodar a migração, verifique se as colunas foram criadas:

### Usando Python:
```bash
python migrations/verify_migration.py
```

### Manualmente no Banco:
```sql
-- Verificar google_drive_folders
SELECT column_name, data_type, is_nullable
FROM information_schema.columns 
WHERE table_name = 'google_drive_folders' 
  AND column_name IN ('deleted_at', 'deleted_by', 'delete_reason')
ORDER BY column_name;

-- Verificar drive_files  
SELECT column_name, data_type, is_nullable
FROM information_schema.columns 
WHERE table_name = 'drive_files' 
  AND column_name IN ('deleted_at', 'deleted_by', 'delete_reason')
ORDER BY column_name;
```

Cada query deve retornar **3 linhas**.

## 🐛 Troubleshooting

### Erro: "column google_drive_folders.deleted_at does not exist"

**Causa:** A migração ainda não foi executada no banco de dados.

**Solução:**
```bash
# Verifique se DATABASE_URL está configurado corretamente
echo $DATABASE_URL

# Execute a migração
python migrations/add_soft_delete_fields.py
```

### Erro: "relation 'drive_files' does not exist" (ao executar SQL no Supabase)

**Causa:** Você está tentando executar um script que modifica `drive_files` mas essa tabela só existe se o backend pd-google já rodou `init_db.py`.

**Solução:** 
- Se estiver usando Supabase SQL Editor, use apenas `add_soft_delete_fields.sql` (que só modifica `google_drive_folders`)
- Para migrar `drive_files`, use o script Python ou primeiro inicialize o banco com `python init_db.py`

### Verificar Conexão com Banco

```bash
python -c "from database import engine; print(engine.url)"
```

### Erro: "permission denied" ou "access denied"

**Causa:** O usuário do banco não tem permissões para ALTER TABLE.

**Solução:** Use um usuário com permissões de ALTER ou execute como administrador do banco.

## 📝 Histórico de Migrações

| Data | Versão | Descrição |
|------|--------|-----------|
| 2024-12 | 001 | Adicionar campos de soft delete (`deleted_at`, `deleted_by`, `delete_reason`) |
