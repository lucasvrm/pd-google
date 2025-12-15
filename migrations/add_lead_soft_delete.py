"""
Migration script to add soft delete field (deleted_at) to the leads table.
Run this script to add the new column to existing databases.

NOTE: This script uses IF NOT EXISTS for idempotent execution.
The leads table schema is managed by Supabase migrations in the main application,
but this script ensures the deleted_at column exists for soft delete functionality.

Usage:
    python migrations/add_lead_soft_delete.py
"""

import os
import sys

# Add parent directory to path to import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine


def migrate_add_lead_soft_delete():
    """Add deleted_at column to leads table using safer IF NOT EXISTS syntax."""

    print("Starting migration: Adding soft delete field (deleted_at) to leads...")

    with engine.connect() as conn:
        try:
            # Start an explicit transaction
            trans = conn.begin()

            # Use IF NOT EXISTS syntax for idempotent execution
            print("Adding deleted_at column to leads table...")

            conn.execute(text("""
                ALTER TABLE leads 
                ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE
            """))
            print("  ✓ Column ensured (deleted_at)")

            # Create index for deleted_at column (for efficient filtering)
            print("\nCreating index for soft delete queries...")

            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_leads_deleted_at 
                ON leads (deleted_at)
            """))
            print("  ✓ Created index on leads.deleted_at")

            trans.commit()
            print("\n✅ Migration completed successfully for leads!")

        except Exception as e:
            # Try rollback if the transaction is active
            try:
                trans.rollback()
            except Exception:
                pass
            print(f"\n❌ Migration failed: {e}")
            raise


if __name__ == "__main__":
    migrate_add_lead_soft_delete()
