from sqlalchemy import inspect, text
from database import engine  # mesmo engine que você usa na app
import models

TABLES_TO_CHECK = [
    models.Lead,
    models.LeadActivityStats,
    models.LeadStatus,
    models.LeadOrigin,
    models.Deal,
    models.Tag,
    models.LeadTag,
]

def get_db_columns(table_name: str):
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = :t
                ORDER BY ordinal_position
            """),
            {"t": table_name},
        ).mappings().all()
    return {r["column_name"]: r for r in rows}

def get_orm_columns(sa_model):
    cols = {}
    for col in sa_model.__table__.columns:
        cols[col.name] = {
            "name": col.name,
            "type": str(col.type),
            "nullable": col.nullable,
            "default": str(col.default.arg) if col.default is not None else None,
        }
    return cols

def compare_table(sa_model):
    table_name = sa_model.__table__.name
    print(f"\n=== {table_name} ===")

    db_cols = get_db_columns(table_name)
    orm_cols = get_orm_columns(sa_model)

    # Colunas que ORM espera e não existem no banco
    missing_in_db = [c for c in orm_cols.keys() if c not in db_cols]
    # Colunas que existem no banco mas não estão no modelo
    missing_in_orm = [c for c in db_cols.keys() if c not in orm_cols]

    print(" - ORM columns:", sorted(orm_cols.keys()))
    print(" - DB  columns:", sorted(db_cols.keys()))

    if missing_in_db:
        print("   > MISSING IN DB (present in ORM, absent in Supabase):", missing_in_db)
    if missing_in_orm:
        print("   > MISSING IN ORM (present in Supabase, absent in ORM):", missing_in_orm)

def main():
    for model in TABLES_TO_CHECK:
        compare_table(model)

if __name__ == "__main__":
    main()
