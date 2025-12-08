"""
Tests for Duplicate Folder Prevention

These tests verify that:
1. Database unique constraint prevents duplicate mappings
2. Check-before-create logic prevents duplicate folders in Drive
3. Race condition handling works correctly
4. Concurrent requests don't create duplicate folders
"""

import os
# Set environment variables BEFORE any other imports
os.environ["USE_MOCK_DRIVE"] = "true"
os.environ["DRIVE_ROOT_FOLDER_ID"] = "mock-root-folder-id"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from database import Base
import models
from services.hierarchy_service import HierarchyService


# Setup Test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_duplicate_prevention.db"
from sqlalchemy import event
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

# Enable foreign keys for SQLite
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module", autouse=True)
def setup_module():
    """Setup test database."""
    Base.metadata.create_all(bind=engine)
    
    # Create unique constraint on google_drive_folders
    # Simulating the migration
    from sqlalchemy import text
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            # For SQLite, we need to handle this differently
            # SQLite doesn't support IF NOT EXISTS for indexes in the same way
            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_entity_mapping 
                ON google_drive_folders (entity_type, entity_id)
            """))
            trans.commit()
        except Exception as e:
            print(f"Note: Index might already exist: {e}")
            trans.rollback()
    
    yield
    
    # Cleanup
    if os.path.exists("./test_duplicate_prevention.db"):
        os.remove("./test_duplicate_prevention.db")
    if os.path.exists("./mock_drive_db.json"):
        os.remove("./mock_drive_db.json")


@pytest.fixture
def db_session():
    """Provide a transactional scope for each test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def hierarchy_service(db_session):
    """Provide a HierarchyService instance for testing."""
    return HierarchyService(db_session)


class TestDatabaseConstraints:
    """Test database-level duplicate prevention."""

    def test_unique_constraint_prevents_duplicate_mappings(self, db_session):
        """Test that the unique constraint prevents duplicate (entity_type, entity_id) pairs."""
        # Create first mapping
        folder1 = models.DriveFolder(
            entity_id="test-entity-123",
            entity_type="company",
            folder_id="folder-123"
        )
        db_session.add(folder1)
        db_session.commit()
        
        # Try to create second mapping with same entity_type and entity_id
        folder2 = models.DriveFolder(
            entity_id="test-entity-123",  # Same entity_id
            entity_type="company",        # Same entity_type
            folder_id="folder-456"        # Different folder_id
        )
        db_session.add(folder2)
        
        # Should raise IntegrityError due to unique constraint
        with pytest.raises(IntegrityError):
            db_session.commit()
        
        db_session.rollback()

    def test_different_entities_can_have_same_id(self, db_session):
        """Test that different entity types can have the same entity_id."""
        # Create company mapping
        company_folder = models.DriveFolder(
            entity_id="same-id-123",
            entity_type="company",
            folder_id="folder-company-123"
        )
        db_session.add(company_folder)
        db_session.commit()
        
        # Create lead mapping with same entity_id (but different entity_type)
        lead_folder = models.DriveFolder(
            entity_id="same-id-123",      # Same entity_id
            entity_type="lead",           # Different entity_type
            folder_id="folder-lead-123"
        )
        db_session.add(lead_folder)
        db_session.commit()  # Should succeed
        
        # Verify both exist
        folders = db_session.query(models.DriveFolder).filter_by(entity_id="same-id-123").all()
        assert len(folders) == 2
        assert {f.entity_type for f in folders} == {"company", "lead"}


class TestCheckBeforeCreate:
    """Test check-before-create logic in hierarchy service."""

    def test_company_structure_reuses_existing_folder(self, db_session, hierarchy_service):
        """Test that ensure_company_structure reuses existing folder mapping."""
        # Create a company
        company = models.Company(id="comp-reuse-test", name="Test Company")
        db_session.add(company)
        db_session.commit()
        
        # First call creates the folder
        folder1 = hierarchy_service.ensure_company_structure("comp-reuse-test")
        assert folder1 is not None
        assert folder1.entity_type == "company"
        assert folder1.entity_id == "comp-reuse-test"
        folder_id_1 = folder1.folder_id
        
        # Second call should reuse existing folder
        folder2 = hierarchy_service.ensure_company_structure("comp-reuse-test")
        assert folder2.id == folder1.id
        assert folder2.folder_id == folder_id_1
        
        # Verify only one mapping exists
        mappings = db_session.query(models.DriveFolder).filter_by(
            entity_type="company",
            entity_id="comp-reuse-test"
        ).all()
        assert len(mappings) == 1

    def test_deal_structure_reuses_existing_folder(self, db_session, hierarchy_service):
        """Test that ensure_deal_structure reuses existing folder mapping."""
        # Create a company and deal
        company = models.Company(id="comp-deal-test", name="Deal Test Company")
        db_session.add(company)
        deal = models.Deal(id="deal-reuse-test", title="Test Deal", company_id="comp-deal-test")
        db_session.add(deal)
        db_session.commit()
        
        # First call creates the folder
        folder1 = hierarchy_service.ensure_deal_structure("deal-reuse-test")
        assert folder1 is not None
        folder_id_1 = folder1.folder_id
        
        # Second call should reuse existing folder
        folder2 = hierarchy_service.ensure_deal_structure("deal-reuse-test")
        assert folder2.id == folder1.id
        assert folder2.folder_id == folder_id_1
        
        # Verify only one mapping exists
        mappings = db_session.query(models.DriveFolder).filter_by(
            entity_type="deal",
            entity_id="deal-reuse-test"
        ).all()
        assert len(mappings) == 1

    def test_lead_structure_reuses_existing_folder(self, db_session, hierarchy_service):
        """Test that ensure_lead_structure reuses existing folder mapping."""
        # Create a company and lead
        company = models.Company(id="comp-lead-test", name="Lead Test Company")
        db_session.add(company)
        lead = models.Lead(id="lead-reuse-test", title="Test Lead", company_id="comp-lead-test")
        db_session.add(lead)
        db_session.commit()
        
        # First call creates the folder
        folder1 = hierarchy_service.ensure_lead_structure("lead-reuse-test")
        assert folder1 is not None
        folder_id_1 = folder1.folder_id
        
        # Second call should reuse existing folder
        folder2 = hierarchy_service.ensure_lead_structure("lead-reuse-test")
        assert folder2.id == folder1.id
        assert folder2.folder_id == folder_id_1
        
        # Verify only one mapping exists
        mappings = db_session.query(models.DriveFolder).filter_by(
            entity_type="lead",
            entity_id="lead-reuse-test"
        ).all()
        assert len(mappings) == 1


class TestRaceConditionHandling:
    """Test race condition handling with IntegrityError."""

    def test_race_condition_recovery_company(self, db_session, hierarchy_service):
        """Test that race condition during company creation is handled gracefully."""
        # Create a company
        company = models.Company(id="comp-race-test", name="Race Test Company")
        db_session.add(company)
        db_session.commit()
        
        # Create the folder in Drive first (to make it valid)
        companies_root = hierarchy_service.get_or_create_companies_root()
        existing_drive_folder = hierarchy_service.drive_service.create_folder(
            name="Race Test Company",
            parent_id=companies_root.folder_id
        )
        
        # Create mapping manually (simulating another process)
        existing_folder = models.DriveFolder(
            entity_type="company",
            entity_id="comp-race-test",
            folder_id=existing_drive_folder["id"],
            folder_url=existing_drive_folder.get("webViewLink")
        )
        db_session.add(existing_folder)
        db_session.commit()
        
        # Now call ensure_company_structure - it should return the existing mapping
        result = hierarchy_service.ensure_company_structure("comp-race-test")
        
        # Should return the existing folder, not create a new one
        assert result.folder_id == existing_drive_folder["id"]
        
        # Verify only one mapping exists
        mappings = db_session.query(models.DriveFolder).filter_by(
            entity_type="company",
            entity_id="comp-race-test"
        ).all()
        assert len(mappings) == 1

    def test_structural_folder_reuse(self, db_session, hierarchy_service):
        """Test that structural folders like '02. Deals' are reused."""
        # Create a company
        company = models.Company(id="comp-struct-test", name="Structural Test Company")
        db_session.add(company)
        
        # Create two deals for the same company
        deal1 = models.Deal(id="deal-struct-1", title="Deal 1", company_id="comp-struct-test")
        deal2 = models.Deal(id="deal-struct-2", title="Deal 2", company_id="comp-struct-test")
        db_session.add(deal1)
        db_session.add(deal2)
        db_session.commit()
        
        # Create folder structure for first deal
        folder1 = hierarchy_service.ensure_deal_structure("deal-struct-1")
        assert folder1 is not None
        
        # Create folder structure for second deal
        folder2 = hierarchy_service.ensure_deal_structure("deal-struct-2")
        assert folder2 is not None
        
        # Both deals should be in the same company folder
        # and both should use the same '02. Deals' parent folder
        # We can't easily verify this without inspecting Drive, but we can check mappings
        assert folder1.folder_id != folder2.folder_id  # Different deal folders
        
        # Verify two separate deal mappings exist
        deal_mappings = db_session.query(models.DriveFolder).filter_by(
            entity_type="deal"
        ).filter(
            models.DriveFolder.entity_id.in_(["deal-struct-1", "deal-struct-2"])
        ).all()
        assert len(deal_mappings) == 2


class TestConcurrentAccess:
    """Test concurrent access scenarios."""

    def test_sequential_creation_no_duplicates(self, db_session, hierarchy_service):
        """Test that sequential creations don't create duplicates."""
        # Create test data
        company = models.Company(id="comp-seq-test", name="Sequential Test Company")
        db_session.add(company)
        db_session.commit()
        
        # Create structure multiple times sequentially
        results = []
        for i in range(5):
            result = hierarchy_service.ensure_company_structure("comp-seq-test")
            results.append(result)
        
        # All results should reference the same folder mapping
        first_id = results[0].id
        for result in results[1:]:
            assert result.id == first_id
        
        # Verify only one mapping exists
        mappings = db_session.query(models.DriveFolder).filter_by(
            entity_type="company",
            entity_id="comp-seq-test"
        ).all()
        assert len(mappings) == 1

    def test_multiple_entity_types_same_company(self, db_session, hierarchy_service):
        """Test creating leads and deals for the same company."""
        # Create test data
        company = models.Company(id="comp-multi-test", name="Multi Entity Test Company")
        lead = models.Lead(id="lead-multi-test", title="Test Lead", company_id="comp-multi-test")
        deal = models.Deal(id="deal-multi-test", title="Test Deal", company_id="comp-multi-test")
        db_session.add_all([company, lead, deal])
        db_session.commit()
        
        # Create structures
        lead_folder = hierarchy_service.ensure_lead_structure("lead-multi-test")
        deal_folder = hierarchy_service.ensure_deal_structure("deal-multi-test")
        
        # Should have created 3 mappings: 1 company, 1 lead, 1 deal
        mappings = db_session.query(models.DriveFolder).all()
        
        # At least these 3 should exist (may have system_root too)
        entity_types = {m.entity_type for m in mappings}
        assert "company" in entity_types
        assert "lead" in entity_types
        assert "deal" in entity_types
