"""
Tests for Template Folder Deduplication

These tests verify that apply_template is idempotent and prevents duplicate folders
even when called multiple times or when template folders already exist.
"""

import os
# Set environment variables BEFORE any other imports
os.environ["USE_MOCK_DRIVE"] = "true"
os.environ["DRIVE_ROOT_FOLDER_ID"] = "mock-root-folder-id"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
import models
from services.hierarchy_service import HierarchyService
from services.template_service import TemplateService
from services.google_drive_mock import GoogleDriveService


# Setup Test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_template_dedup.db"
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
    from sqlalchemy import text
    with engine.connect() as conn:
        trans = conn.begin()
        try:
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
    if os.path.exists("./test_template_dedup.db"):
        os.remove("./test_template_dedup.db")
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


@pytest.fixture
def drive_service():
    """Provide a fresh GoogleDriveService instance for testing."""
    # Clean mock file before each test
    if os.path.exists("./mock_drive_db.json"):
        os.remove("./mock_drive_db.json")
    return GoogleDriveService()


@pytest.fixture
def setup_deal_template(db_session):
    """Setup a deal template with typical folder structure."""
    deal_template = models.DriveStructureTemplate(
        name="Test Deal Template",
        entity_type="deal",
        active=True
    )
    db_session.add(deal_template)
    db_session.commit()
    
    deal_nodes = [
        "00. Administração do Deal",
        "01. Originação & Mandato",
        "02. Ativo / Terreno & Garantias",
        "03. Empreendimento & Projeto",
        "04. Comercial",
        "05. Financeiro & Modelagem",
        "06. Partes & KYC",
        "07. Jurídico & Estruturação",
        "08. Operação & Monitoring"
    ]
    
    for i, name in enumerate(deal_nodes):
        node = models.DriveStructureNode(
            template_id=deal_template.id,
            name=name,
            order=i
        )
        db_session.add(node)
    
    db_session.commit()
    return deal_template


@pytest.fixture
def setup_lead_template(db_session):
    """Setup a lead template with typical folder structure."""
    lead_template = models.DriveStructureTemplate(
        name="Test Lead Template",
        entity_type="lead",
        active=True
    )
    db_session.add(lead_template)
    db_session.commit()
    
    lead_nodes = [
        "00. Administração do Lead",
        "01. Originação & Materiais",
        "02. Ativo / Terreno (Básico)",
        "03. Empreendimento & Viabilidade (Preliminar)",
        "04. Partes & KYC (Básico)",
        "05. Decisão Interna"
    ]
    
    for i, name in enumerate(lead_nodes):
        node = models.DriveStructureNode(
            template_id=lead_template.id,
            name=name,
            order=i
        )
        db_session.add(node)
    
    db_session.commit()
    return lead_template


class TestDealTemplateDeduplication:
    """Test that deal template folders are not duplicated."""
    
    def test_multiple_ensure_deal_structure_no_duplicates(
        self, db_session, hierarchy_service, setup_deal_template
    ):
        """Test that calling ensure_deal_structure multiple times doesn't create duplicate folders."""
        # Create a company and deal
        company = models.Company(id="comp-dedup-test", name="Dedup Test Company")
        db_session.add(company)
        deal = models.Deal(
            id="deal-dedup-test",
            title="Test Deal",  # Maps to client_name column
            company_id="comp-dedup-test"
        )
        db_session.add(deal)
        db_session.commit()
        
        # Call ensure_deal_structure multiple times
        for i in range(3):
            print(f"\n=== Call {i+1} to ensure_deal_structure ===")
            folder = hierarchy_service.ensure_deal_structure("deal-dedup-test")
            assert folder is not None
        
        # Get the deal's root folder
        deal_mapping = db_session.query(models.DriveFolder).filter_by(
            entity_type="deal",
            entity_id="deal-dedup-test"
        ).first()
        
        assert deal_mapping is not None
        
        # List all folders in the deal's root
        drive_service = hierarchy_service.drive_service
        children = drive_service.list_files(deal_mapping.folder_id)
        
        # Count occurrences of each folder name
        folder_names = [f['name'] for f in children if f.get('mimeType') == 'application/vnd.google-apps.folder']
        
        print(f"\nFolders created: {folder_names}")
        
        # Check for duplicates
        for folder_name in ["00. Administração do Deal", "01. Originação & Mandato", 
                           "07. Jurídico & Estruturação", "08. Operação & Monitoring"]:
            count = folder_names.count(folder_name)
            assert count <= 1, f"Folder '{folder_name}' appears {count} times (should appear at most once)"
    
    def test_apply_template_idempotent(
        self, db_session, drive_service, setup_deal_template
    ):
        """Test that apply_template is idempotent when called multiple times."""
        # Create a root folder for the deal
        root_folder = drive_service.create_folder("Test Deal Root")
        root_folder_id = root_folder['id']
        
        # Apply template multiple times
        template_service = TemplateService(db_session, drive_service)
        
        for i in range(3):
            print(f"\n=== Apply template call {i+1} ===")
            template_service.apply_template("deal", root_folder_id)
        
        # List all folders in the root
        children = drive_service.list_files(root_folder_id)
        folder_names = [f['name'] for f in children if f.get('mimeType') == 'application/vnd.google-apps.folder']
        
        print(f"\nFolders after 3 apply_template calls: {folder_names}")
        
        # Each template folder should appear exactly once
        for folder_name in ["00. Administração do Deal", "08. Operação & Monitoring"]:
            count = folder_names.count(folder_name)
            assert count == 1, f"Folder '{folder_name}' appears {count} times (should appear exactly once)"
    
    def test_repair_structure_no_new_duplicates(
        self, db_session, hierarchy_service, setup_deal_template
    ):
        """Test that repair_structure doesn't create new duplicates."""
        # Create a company and deal
        company = models.Company(id="comp-repair-test", name="Repair Test Company")
        db_session.add(company)
        deal = models.Deal(
            id="deal-repair-test",
            title="Repair Deal",  # Maps to client_name column
            company_id="comp-repair-test"
        )
        db_session.add(deal)
        db_session.commit()
        
        # Create structure initially
        hierarchy_service.ensure_deal_structure("deal-repair-test")
        
        # Call repair multiple times
        for i in range(3):
            print(f"\n=== Repair call {i+1} ===")
            success = hierarchy_service.repair_structure("deal", "deal-repair-test")
            assert success
        
        # Get the deal's root folder
        deal_mapping = db_session.query(models.DriveFolder).filter_by(
            entity_type="deal",
            entity_id="deal-repair-test"
        ).first()
        
        # List all folders in the deal's root
        drive_service = hierarchy_service.drive_service
        children = drive_service.list_files(deal_mapping.folder_id)
        folder_names = [f['name'] for f in children if f.get('mimeType') == 'application/vnd.google-apps.folder']
        
        print(f"\nFolders after repair: {folder_names}")
        
        # Check for duplicates
        for folder_name in ["00. Administração do Deal", "08. Operação & Monitoring"]:
            count = folder_names.count(folder_name)
            assert count == 1, f"Folder '{folder_name}' appears {count} times after repair (should appear exactly once)"
    
    def test_pre_existing_duplicates_not_worsened(
        self, db_session, drive_service, setup_deal_template
    ):
        """Test that applying template to folder with pre-existing duplicates doesn't make it worse."""
        # Create a root folder
        root_folder = drive_service.create_folder("Deal With Duplicates")
        root_folder_id = root_folder['id']
        
        # Manually create duplicate folders (simulating the current production issue)
        drive_service.create_folder("08. Operação & Monitoring", parent_id=root_folder_id)
        drive_service.create_folder("08. Operação & Monitoring", parent_id=root_folder_id)
        
        # Count initial duplicates
        children_before = drive_service.list_files(root_folder_id)
        count_before = sum(1 for f in children_before 
                          if f.get('name') == "08. Operação & Monitoring")
        
        print(f"\nDuplicates before template application: {count_before}")
        assert count_before == 2  # We created 2 duplicates
        
        # Apply template
        template_service = TemplateService(db_session, drive_service)
        template_service.apply_template("deal", root_folder_id)
        
        # Count duplicates after
        children_after = drive_service.list_files(root_folder_id)
        count_after = sum(1 for f in children_after 
                         if f.get('name') == "08. Operação & Monitoring")
        
        print(f"Duplicates after template application: {count_after}")
        
        # Should not create MORE duplicates
        assert count_after <= count_before, \
            f"Template application increased duplicates from {count_before} to {count_after}"


class TestLeadTemplateDeduplication:
    """Test that lead template folders are not duplicated."""
    
    def test_multiple_ensure_lead_structure_no_duplicates(
        self, db_session, hierarchy_service, setup_lead_template
    ):
        """Test that calling ensure_lead_structure multiple times doesn't create duplicate folders."""
        # Create a company and lead
        company = models.Company(id="comp-lead-dedup", name="Lead Dedup Company")
        db_session.add(company)
        lead = models.Lead(
            id="lead-dedup-test",
            title="Test Lead",  # Maps to legal_name column
            company_id="comp-lead-dedup"
        )
        db_session.add(lead)
        db_session.commit()
        
        # Call ensure_lead_structure multiple times
        for i in range(3):
            print(f"\n=== Call {i+1} to ensure_lead_structure ===")
            folder = hierarchy_service.ensure_lead_structure("lead-dedup-test")
            assert folder is not None
        
        # Get the lead's root folder
        lead_mapping = db_session.query(models.DriveFolder).filter_by(
            entity_type="lead",
            entity_id="lead-dedup-test"
        ).first()
        
        assert lead_mapping is not None
        
        # List all folders in the lead's root
        drive_service = hierarchy_service.drive_service
        children = drive_service.list_files(lead_mapping.folder_id)
        folder_names = [f['name'] for f in children if f.get('mimeType') == 'application/vnd.google-apps.folder']
        
        print(f"\nFolders created: {folder_names}")
        
        # Check for duplicates
        for folder_name in ["00. Administração do Lead", "01. Originação & Materiais", "05. Decisão Interna"]:
            count = folder_names.count(folder_name)
            assert count <= 1, f"Folder '{folder_name}' appears {count} times (should appear at most once)"
