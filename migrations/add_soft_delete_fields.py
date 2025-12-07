"""
Migration script to add soft delete fields to DriveFile tables.
Run this script to add the new columns to existing databases.

NOTE: This script ONLY updates the 'drive_files' table which is owned by pd-google.
The 'google_drive_folders' table schema is managed by Supabase migrations in the main application.
"""

from sqlalchemy import create_engine, text
import os
import sys

# Add parent directory to path to import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import engine

def migrate_add_soft_delete_fields():
    """Add soft delete fields to DriveFile table."""
    
    print("Starting migration: Adding soft delete fields to drive_files...")
    
    with engine.connect() as conn:
        try:
            # Add soft delete fields to drive_files table
            print("Adding soft delete fields to drive_files table...")
            
            # Check if columns already exist (SQLite and PostgreSQL compatible approach)
            try:
                conn.execute(text("""
                    ALTER TABLE drive_files 
                    ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE
                """))
                print("  ✓ Added deleted_at to drive_files")
            except Exception as e:
                if "already exists" in str(e) or "duplicate column" in str(e).lower():
                    print("  - deleted_at already exists in drive_files")
                else:
                    raise
            
            try:
                conn.execute(text("""
                    ALTER TABLE drive_files 
                    ADD COLUMN deleted_by VARCHAR
                """))
                print("  ✓ Added deleted_by to drive_files")
            except Exception as e:
                if "already exists" in str(e) or "duplicate column" in str(e).lower():
                    print("  - deleted_by already exists in drive_files")
                else:
                    raise
            
            try:
                conn.execute(text("""
                    ALTER TABLE drive_files 
                    ADD COLUMN delete_reason VARCHAR
                """))
                print("  ✓ Added delete_reason to drive_files")
            except Exception as e:
                if "already exists" in str(e) or "duplicate column" in str(e).lower():
                    print("  - delete_reason already exists in drive_files")
                else:
                    raise
            
            # Create indexes for deleted_at columns (for efficient filtering)
            print("\nCreating indexes for soft delete queries...")
            
            try:
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_drive_files_deleted_at 
                    ON drive_files (deleted_at)
                """))
                print("  ✓ Created index on drive_files.deleted_at")
            except Exception as e:
                print(f"  - Index creation note: {e}")
            
            conn.commit()
            print("\n✅ Migration completed successfully for drive_files!")
            print("Note: google_drive_folders schema must be updated via Supabase migrations.")
            
        except Exception as e:
            conn.rollback()
            print(f"\n❌ Migration failed: {e}")
            raise

if __name__ == "__main__":
    migrate_add_soft_delete_fields()
