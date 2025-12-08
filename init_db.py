from database import engine, Base
import models
from seed_db import seed_data

def init_db():
    Base.metadata.create_all(bind=engine)
    try:
        seed_data()
        print("Database initialized and seeded.")
    except Exception as e:
        print(f"Database initialized but seeding failed: {e}")

if __name__ == "__main__":
    init_db()
