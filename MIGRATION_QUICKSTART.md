# 🚀 Guia Rápido: Corrigir Erro de Runtime no Endpoint /api/drive/items

## Problema

```
psycopg2.errors.UndefinedColumn: column google_drive_folders.deleted_at does not exist
```

**Causa:** Os modelos SQLAlchemy esperam colunas de soft delete (`deleted_at`, `deleted_by`, `delete_reason`) nas tabelas `google_drive_folders` e `drive_files`, mas essas colunas ainda não foram criadas no banco de dados Supabase.

## Solução Rápida (3 passos)

### Passo 1: Verifique a Conexão com o Banco

```bash
# No servidor/ambiente de produção (Render)
# Certifique-se que DATABASE_URL aponta para Supabase
echo $DATABASE_URL
```

Deve mostrar algo como: `postgresql://user:password@db.xxxxx.supabase.co:5432/postgres`

### Passo 2: Execute a Migração

**Opção A - Via Python (Recomendado):**

```bash
python migrations/add_soft_delete_fields.py
```

**Opção B - Via Supabase SQL Editor:**

1. Acesse: https://supabase.com/dashboard/project/[seu-projeto]/sql/new
2. Cole o conteúdo de `migrations/add_soft_delete_fields.sql`
3. Clique em "Run"

### Passo 3: Verifique o Sucesso

```bash
python migrations/verify_migration.py
```

Deve mostrar:
```
✅ MIGRATION VERIFIED SUCCESSFULLY
All soft delete columns exist in both tables.
```

## Teste o Endpoint

Após a migração, o endpoint deve funcionar:

```bash
curl -X GET "https://google-api-xwhd.onrender.com/api/drive/items?entityType=deal&entityId=2361292e-c692-43ac-ae63-2cb093282ad2&page=1&limit=50" \
  -H "x-user-id: test-user" \
  -H "x-user-role: admin"
```

Deve retornar `200 OK` com:
```json
{
  "items": [...],
  "total": 0
}
```

## Resolução de Problemas

### Erro: "permission denied for table google_drive_folders"
- **Solução:** Execute como usuário admin do Supabase via SQL Editor

### Erro: "relation 'drive_files' does not exist"
- **Solução:** Execute `python init_db.py` primeiro para criar as tabelas
- Ou use o SQL script que verifica se a tabela existe antes de alterar

### Erro persiste após migração
1. Verifique se conectou ao banco correto: `python -c "from database import engine; print(engine.url)"`
2. Liste as colunas manualmente:
   ```sql
   SELECT column_name FROM information_schema.columns 
   WHERE table_name = 'google_drive_folders';
   ```
3. Se `deleted_at` não aparecer, a migração não foi aplicada corretamente

## Para Desenvolvimento Local

```bash
# 1. Criar banco SQLite local
python init_db.py

# 2. Verificar
python migrations/verify_migration.py

# 3. Testar endpoint
USE_MOCK_DRIVE=true python -m pytest tests/test_drive_items_adapter.py -v
```

## Próximos Passos

Após resolver o erro:
1. ✅ Endpoint `/api/drive/items` deve retornar 200
2. ✅ Frontend não deve mais mostrar erro 500
3. ✅ DealDetailPage deve carregar normalmente

## Arquitetura Esclarecida

- **Banco Único:** Todo o sistema usa o PostgreSQL do Supabase (via `DATABASE_URL`)
- **Tabelas Compartilhadas:** `companies`, `deals`, `leads`, `google_drive_folders` existem no Supabase
- **Tabelas do pd-google:** `drive_files`, `drive_webhook_channels`, etc. também estão no mesmo banco
- **Não há banco separado** para o pd-google - tudo está no Supabase

## Referências

- [README de Migrações](migrations/README.md) - Documentação completa
- [Script de Migração Python](migrations/add_soft_delete_fields.py)
- [Script SQL para Supabase](migrations/add_soft_delete_fields.sql)
- [Script de Verificação](migrations/verify_migration.py)
