from database import engine, Base
import models
from migrations.add_soft_delete_fields import migrate_add_soft_delete_fields
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("init_db")

def init_db():
    logger.info("Initializing database...")
    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)
    logger.info("Tables created (if missing).")

    # Run migrations to ensure schema is up to date (e.g. adding new columns to existing tables)
    logger.info("Running migrations...")
    migrate_add_soft_delete_fields()
    logger.info("Migrations completed.")

if __name__ == "__main__":
    init_db()
    print("Database initialized.")
