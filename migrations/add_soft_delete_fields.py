"""
Migration script to add soft delete fields to DriveFile tables.
Run this script to add the new columns to existing databases.

NOTE: This script ONLY updates the 'drive_files' table which is owned by pd-google.
The 'google_drive_folders' table schema is managed by Supabase migrations in the main application.
"""

from sqlalchemy import text
import os
import sys

# Add parent directory to path to import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import engine

def migrate_add_soft_delete_fields():
    """Add soft delete fields to DriveFile table using safer IF NOT EXISTS syntax."""
    
    print("Starting migration: Adding soft delete fields to drive_files...")
    
    with engine.connect() as conn:
        try:
            # Iniciar uma transação explícita
            trans = conn.begin()
            
            # Usar sintaxe IF NOT EXISTS do PostgreSQL para evitar erros de transação
            print("Adding soft delete fields to drive_files table...")
            
            conn.execute(text("""
                ALTER TABLE drive_files 
                ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE,
                ADD COLUMN IF NOT EXISTS deleted_by VARCHAR,
                ADD COLUMN IF NOT EXISTS delete_reason VARCHAR
            """))
            print("  ✓ Columns ensured (deleted_at, deleted_by, delete_reason)")
            
            # Create indexes for deleted_at columns (for efficient filtering)
            print("\nCreating indexes for soft delete queries...")
            
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_drive_files_deleted_at 
                ON drive_files (deleted_at)
            """))
            print("  ✓ Created index on drive_files.deleted_at")
            
            trans.commit()
            print("\n✅ Migration completed successfully for drive_files!")
            
        except Exception as e:
            # Tenta rollback se a transação estiver ativa
            try:
                trans.rollback()
            except:
                pass
            print(f"\n❌ Migration failed: {e}")
            # Não vamos dar raise aqui para não impedir o startup da aplicação,
            # mas o erro ficará visível nos logs.

if __name__ == "__main__":
    migrate_add_soft_delete_fields()