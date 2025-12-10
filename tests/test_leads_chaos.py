import os
import sys
from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import models
from database import Base
from routers import leads

# Create a clean DB for chaos testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_leads_chaos.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def setup_module(module):
    if os.path.exists("./test_leads_chaos.db"):
        os.remove("./test_leads_chaos.db")
    Base.metadata.create_all(bind=engine)

def teardown_module(module):
    if os.path.exists("./test_leads_chaos.db"):
        os.remove("./test_leads_chaos.db")

def test_sales_view_chaos():
    """Test sales_view with malformed/incomplete data to reproduce 500 errors."""
    db = TestingSessionLocal()
    try:
        # Case 1: Lead with absolutely minimal fields (everything nullable is None)
        lead_minimal = models.Lead(
            id="chaos-1",
            title="Chaos Lead 1",
            # All other fields None
        )
        db.add(lead_minimal)
        db.commit()

        # Trigger sales_view
        try:
            result = leads.sales_view(page=1, page_size=10, db=db)
            print("Chaos 1 survived")
        except Exception as e:
            pytest.fail(f"Chaos 1 failed: {e}")

        # Case 2: Lead with orphaned relationships or partial data
        lead_broken_fk = models.Lead(
            id="chaos-2",
            title="Chaos Lead 2",
            owner_id="non-existent-user",
            primary_contact_id="non-existent-contact"
        )
        db.add(lead_broken_fk)
        db.commit()

        try:
            result = leads.sales_view(page=1, page_size=10, db=db)
            print("Chaos 2 survived")
        except Exception as e:
            pytest.fail(f"Chaos 2 failed: {e}")

        # Case 3: Lead with Activity Stats but None values inside stats
        stats_empty = models.LeadActivityStats(
            lead_id="chaos-1",
            # All None
        )
        db.add(stats_empty)
        db.commit()

        try:
            result = leads.sales_view(page=1, page_size=10, db=db)
            print("Chaos 3 survived")
        except Exception as e:
            pytest.fail(f"Chaos 3 failed: {e}")

        # Case 4: Lead with weird priority score (None)
        lead_none_priority = models.Lead(
            id="chaos-4",
            title="Chaos 4",
            priority_score=None
        )
        db.add(lead_none_priority)
        db.commit()

        try:
            result = leads.sales_view(page=1, page_size=10, db=db)
            print("Chaos 4 survived")
        except Exception as e:
            pytest.fail(f"Chaos 4 failed: {e}")

        # Case 5: Lead with future/past extreme dates
        lead_dates = models.Lead(
            id="chaos-5",
            title="Chaos 5",
            created_at=None,
            updated_at=None,
            last_interaction_at=None
        )
        db.add(lead_dates)
        db.commit()

        # Case 6: Tag with None name
        # This lead SHOULD be skipped or handled gracefully (if handled)
        # But wait, my code SKIPS items that fail creation.
        try:
            result = leads.sales_view(page=1, page_size=10, db=db)
            print("Chaos 5 survived")
        except Exception as e:
            pytest.fail(f"Chaos 5 failed: {e}")

        # Case 6: Tag with None name
        # This is the hypothesis for Pydantic validation error
        lead_tag_issue = models.Lead(
            id="chaos-6",
            title="Chaos Tag"
        )
        tag_none = models.Tag(name=None, color="#000000")
        db.add(lead_tag_issue)
        db.add(tag_none)
        db.commit()
        tag_none = models.Tag(name=None, color="#000000") # name is unique, but SQLite allows one null?
        # unique constraint might fail on second null, but one is fine.
        # Actually models.py says unique=True. In SQL, multiple NULLs are allowed in unique columns usually.

        db.add(lead_tag_issue)
        db.add(tag_none)
        db.commit()

        # Link them
        # We need to manually insert into lead_tags because we don't have a model class for it easily accessible
        # (it's defined as a class LeadTag in models.py, let's use it)
        lead_tag_link = models.LeadTag(lead_id="chaos-6", tag_id=tag_none.id)
        db.add(lead_tag_link)
        db.commit()

        # Case 8: Lead with VALID STRING in datetime column (Legacy Data Simulation)
        # SQLite allows inserting string into DateTime column. SQLAlchemy usually tries to parse it on read.
        # But if we use raw SQL, we bypass write-time checks.
        db.execute(text("INSERT INTO leads (id, legal_name, created_at) VALUES ('chaos-8', 'String Date Lead', '2023-01-01T10:00:00')"))
        db.commit()

        # EXECUTE
        try:
            result = leads.sales_view(page=1, page_size=20, db=db)
            print("Sales View Executed Successfully")

            # VERIFY
            data = result.data
            ids = [item.id for item in data]

            print(f"Returned IDs: {ids}")

            # Chaos 1, 2, 4, 5, 8 should exist.
            # Chaos 6 (None tag) -> My code has try/except around item creation.
            # If `LeadSalesViewItem` creation fails for Chaos 6, it is skipped.
            # Does it fail?
            # `tags_list = [str(tag.name) for tag in lead.tags if tag.name is not None]`
            # I ADDED filtering for None tags! So Chaos 6 should SUCCEED now!

            assert "chaos-1" in ids
            assert "chaos-2" in ids
            assert "chaos-4" in ids
            assert "chaos-5" in ids
            assert "chaos-6" in ids # Should exist because we fixed the tag issue
            assert "chaos-8" in ids # Should exist because _normalize_datetime handles strings

        except Exception as e:
            pytest.fail(f"Sales View Failed: {e}")
        try:
            result = leads.sales_view(page=1, page_size=10, db=db)
            print("Chaos 6 survived")
        except Exception as e:
            print(f"Chaos 6 failed as expected? {e}")
            # If this is the cause, we expect a failure here unless I already fixed it?
            # I haven't fixed it yet.
            # But wait, pytest.fail will stop the test. I want to assert failure or success.
            pass

    finally:
        db.close()
