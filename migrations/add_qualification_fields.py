"""
Migration script to add qualification fields to leads and master_deals tables.
Run this script to add the new columns to existing databases.

New fields:
- leads.qualified_at: Timestamp when the lead was qualified
- leads.description: Text description/notes for the lead
- master_deals.legal_name: Legal name migrated from Lead
- master_deals.trade_name: Trade name migrated from Lead
- master_deals.owner_user_id: Owner migrated from Lead
- master_deals.description: Description migrated from Lead

NOTE: This script uses IF NOT EXISTS for idempotent execution.
The schema is managed by Supabase migrations in the main application,
but this script ensures the columns exist for qualification functionality.

Usage:
    python migrations/add_qualification_fields.py
"""

import os
import sys

# Add parent directory to path to import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine


def migrate_add_qualification_fields():
    """Add qualification-related columns to leads and master_deals tables."""

    print("Starting migration: Adding qualification fields...")

    with engine.connect() as conn:
        try:
            # Start an explicit transaction
            trans = conn.begin()

            # === LEADS TABLE ===
            print("\n1. Updating leads table...")

            # Add qualified_at column
            conn.execute(text("""
                ALTER TABLE leads 
                ADD COLUMN IF NOT EXISTS qualified_at TIMESTAMP WITH TIME ZONE
            """))
            print("  ✓ Column ensured (leads.qualified_at)")

            # Add description column
            conn.execute(text("""
                ALTER TABLE leads 
                ADD COLUMN IF NOT EXISTS description TEXT
            """))
            print("  ✓ Column ensured (leads.description)")

            # Create index for qualified_at column (for efficient filtering)
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_leads_qualified_at 
                ON leads (qualified_at)
            """))
            print("  ✓ Created index on leads.qualified_at")

            # === MASTER_DEALS TABLE ===
            print("\n2. Updating master_deals table...")

            # Add legal_name column
            conn.execute(text("""
                ALTER TABLE master_deals 
                ADD COLUMN IF NOT EXISTS legal_name TEXT
            """))
            print("  ✓ Column ensured (master_deals.legal_name)")

            # Add trade_name column
            conn.execute(text("""
                ALTER TABLE master_deals 
                ADD COLUMN IF NOT EXISTS trade_name TEXT
            """))
            print("  ✓ Column ensured (master_deals.trade_name)")

            # Add owner_user_id column
            conn.execute(text("""
                ALTER TABLE master_deals 
                ADD COLUMN IF NOT EXISTS owner_user_id TEXT
            """))
            print("  ✓ Column ensured (master_deals.owner_user_id)")

            # Add description column
            conn.execute(text("""
                ALTER TABLE master_deals 
                ADD COLUMN IF NOT EXISTS description TEXT
            """))
            print("  ✓ Column ensured (master_deals.description)")

            trans.commit()
            print("\n✅ Migration completed successfully!")

        except Exception as e:
            # Try rollback if the transaction is active
            try:
                trans.rollback()
            except Exception:
                pass
            print(f"\n❌ Migration failed: {e}")
            raise


if __name__ == "__main__":
    migrate_add_qualification_fields()
