"""
Verification script to check if soft delete migration was applied successfully.
Run this after applying the migration to ensure all columns exist.
"""

import sys
import os

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text
from database import engine

def verify_migration():
    """Verify that soft delete columns exist in both tables."""
    
    print("=" * 60)
    print("SOFT DELETE MIGRATION VERIFICATION")
    print("=" * 60)
    print()
    
    inspector = inspect(engine)
    
    # Define expected columns
    expected_columns = ['deleted_at', 'deleted_by', 'delete_reason']
    
    # Tables to check
    tables_to_check = ['google_drive_folders', 'drive_files']
    
    all_passed = True
    
    for table_name in tables_to_check:
        print(f"Checking table: {table_name}")
        print("-" * 60)
        
        # Check if table exists
        if not inspector.has_table(table_name):
            print(f"  ❌ Table '{table_name}' does not exist!")
            print(f"     Run 'python init_db.py' to create initial tables.")
            all_passed = False
            print()
            continue
        
        # Get all columns
        columns = inspector.get_columns(table_name)
        column_names = [col['name'] for col in columns]
        
        # Check each expected column
        missing_columns = []
        for expected_col in expected_columns:
            if expected_col in column_names:
                # Get column details
                col_info = next(c for c in columns if c['name'] == expected_col)
                nullable = "NULL" if col_info.get('nullable', True) else "NOT NULL"
                print(f"  ✅ {expected_col:20} - {col_info['type']} {nullable}")
            else:
                print(f"  ❌ {expected_col:20} - MISSING")
                missing_columns.append(expected_col)
                all_passed = False
        
        # Check indexes
        indexes = inspector.get_indexes(table_name)
        deleted_at_indexed = any(
            'deleted_at' in idx.get('column_names', []) 
            for idx in indexes
        )
        
        if deleted_at_indexed:
            print(f"  ✅ Index on deleted_at exists")
        else:
            print(f"  ⚠️  No index on deleted_at (recommended for performance)")
        
        print()
        
        if missing_columns:
            print(f"  Missing columns: {', '.join(missing_columns)}")
            print(f"  Run: python migrations/add_soft_delete_fields.py")
            print()
    
    print("=" * 60)
    
    if all_passed:
        print("✅ MIGRATION VERIFIED SUCCESSFULLY")
        print()
        print("All soft delete columns exist in both tables.")
        print("Your database is ready for soft delete operations.")
        return 0
    else:
        print("❌ MIGRATION INCOMPLETE")
        print()
        print("Some columns are missing. Please run the migration:")
        print("  python migrations/add_soft_delete_fields.py")
        print()
        print("Or for Supabase SQL Editor:")
        print("  Execute migrations/add_soft_delete_fields.sql")
        return 1
    
    print("=" * 60)

def check_database_connection():
    """Test database connection before verification."""
    print("Testing database connection...")
    print(f"Database URL: {engine.url}")
    print()
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
            print("✅ Database connection successful")
            print()
            return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print()
        print("Please check your DATABASE_URL environment variable.")
        return False

if __name__ == "__main__":
    # First check connection
    if not check_database_connection():
        sys.exit(1)
    
    # Then verify migration
    exit_code = verify_migration()
    sys.exit(exit_code)
