"""
Migration script to create lead_tags table if it doesn't exist.
Reads migrations/create_lead_tags_table.sql and executes it.
"""

from sqlalchemy import text
import os
import sys

# Add parent directory to path to import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import engine

def migrate_create_lead_tags_table():
    """Execute the SQL script to create lead_tags table."""

    print("Starting migration: Creating lead_tags table...")

    # We define the statements here directly to handle splitting reliably for both SQLite and Postgres
    # (Since some drivers don't support multiple statements in one call)

    # NOTE: lead_id is defined as UUID to match Production (Supabase) schema.
    # If running locally with SQLite (where leads.id might be TEXT), this might need adjustment
    # or reliance on SQLite's flexible typing.

    statements = [
        """
        CREATE TABLE IF NOT EXISTS lead_tags (
            lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
            tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            PRIMARY KEY (lead_id, tag_id)
        );
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_lead_tags_tag_id ON lead_tags(tag_id);
        """
    ]

    with engine.connect() as conn:
        try:
            trans = conn.begin()

            for stmt in statements:
                print(f"Executing: {stmt.strip().splitlines()[0]}...")
                conn.execute(text(stmt))

            trans.commit()
            print("\n✅ Migration completed successfully: lead_tags table ensured.")

        except Exception as e:
            try:
                trans.rollback()
            except:
                pass
            print(f"\n❌ Migration failed: {e}")
            # If the error is about type mismatch in local dev (TEXT vs UUID), we might log a warning
            if "type" in str(e).lower() or "key" in str(e).lower():
                print("   (Note: If running locally, this might be due to leads.id being TEXT/VARCHAR while migration expects UUID)")

if __name__ == "__main__":
    migrate_create_lead_tags_table()
