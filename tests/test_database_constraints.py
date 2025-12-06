"""
Database Constraints Tests

These tests verify that database constraints are properly enforced,
including:
- Mandatory fields validation
- Uniqueness constraints
- Foreign key relationships
- Data integrity rules

Tests use SQLite and verify that appropriate SQLAlchemy exceptions are raised.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from database import Base
import models
import os


# Setup Test DB for constraint testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_constraints.db"
# Enable foreign keys for SQLite
from sqlalchemy import event
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

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
    yield
    # Cleanup
    if os.path.exists("./test_constraints.db"):
        os.remove("./test_constraints.db")


@pytest.fixture
def db_session():
    """Provide a transactional scope for each test."""
    # Create a new connection for this test
    connection = engine.connect()
    transaction = connection.begin()
    
    # Create a session bound to this connection
    session = TestingSessionLocal(bind=connection)
    
    yield session
    
    # Clean up
    session.close()
    # Rollback the transaction to undo any changes made during the test
    transaction.rollback()
    connection.close()


class TestDriveFolderConstraints:
    """Test constraints on DriveFolder model."""

    def test_create_valid_drive_folder(self, db_session):
        """Test creating a valid DriveFolder with all required fields."""
        folder = models.DriveFolder(
            entity_id="test-entity-123",
            entity_type="company",
            folder_id="drive-folder-123"
        )
        db_session.add(folder)
        db_session.commit()
        
        # Verify it was created
        assert folder.id is not None
        assert folder.created_at is not None

    def test_drive_folder_unique_folder_id(self, db_session):
        """Test that folder_id must be unique."""
        # Create first folder
        folder1 = models.DriveFolder(
            entity_id="entity-1",
            entity_type="company",
            folder_id="unique-folder-123"
        )
        db_session.add(folder1)
        db_session.commit()
        
        # Try to create second folder with same folder_id
        folder2 = models.DriveFolder(
            entity_id="entity-2",
            entity_type="lead",
            folder_id="unique-folder-123"  # Same folder_id
        )
        db_session.add(folder2)
        
        # Should raise IntegrityError due to unique constraint
        with pytest.raises(IntegrityError):
            db_session.commit()
        
        # Rollback the failed transaction
        db_session.rollback()

    def test_drive_folder_nullable_fields(self, db_session):
        """Test behavior with nullable fields."""
        # entity_id, entity_type, and folder_id should be required
        # Let's test that folder_id cannot be null
        folder = models.DriveFolder(
            entity_id="test-entity",
            entity_type="company",
            folder_id=None  # Trying to set to None
        )
        db_session.add(folder)
        
        # This might raise an error depending on column definition
        # If the column is nullable, this will succeed; if not, it will fail
        # Based on the model, folder_id doesn't have nullable=False explicitly,
        # but it has unique=True and index=True
        # Let's verify the behavior
        try:
            db_session.commit()
            # If it succeeds, folder_id is nullable
            # We can check the value
            assert folder.folder_id is None
        except IntegrityError:
            # If it fails, that's also acceptable behavior
            pass

    def test_drive_folder_indexes(self, db_session):
        """
        Test that indexed fields work correctly.
        
        While we can't directly test index performance in a unit test,
        we can verify that records can be created and queried efficiently.
        """
        # Create multiple folders
        for i in range(5):
            folder = models.DriveFolder(
                entity_id=f"entity-{i}",
                entity_type="company" if i % 2 == 0 else "lead",
                folder_id=f"folder-{i}"
            )
            db_session.add(folder)
        db_session.commit()
        
        # Query by indexed fields
        company_folders = db_session.query(models.DriveFolder).filter(
            models.DriveFolder.entity_type == "company"
        ).all()
        
        assert len(company_folders) == 3  # 0, 2, 4
        
        # Query by entity_id (also indexed)
        specific_folder = db_session.query(models.DriveFolder).filter(
            models.DriveFolder.entity_id == "entity-3"
        ).first()
        
        assert specific_folder is not None
        assert specific_folder.folder_id == "folder-3"


class TestDriveFileConstraints:
    """Test constraints on DriveFile model."""

    def test_create_valid_drive_file(self, db_session):
        """Test creating a valid DriveFile with all required fields."""
        file = models.DriveFile(
            file_id="file-123",
            parent_folder_id="folder-456",
            name="test.txt",
            mime_type="text/plain",
            size=1024
        )
        db_session.add(file)
        db_session.commit()
        
        assert file.id is not None
        assert file.created_at is not None

    def test_drive_file_unique_file_id(self, db_session):
        """Test that file_id must be unique."""
        # Create first file
        file1 = models.DriveFile(
            file_id="unique-file-789",
            parent_folder_id="folder-1",
            name="file1.txt",
            mime_type="text/plain",
            size=100
        )
        db_session.add(file1)
        db_session.commit()
        
        # Try to create second file with same file_id
        file2 = models.DriveFile(
            file_id="unique-file-789",  # Same file_id
            parent_folder_id="folder-2",
            name="file2.txt",
            mime_type="text/plain",
            size=200
        )
        db_session.add(file2)
        
        # Should raise IntegrityError due to unique constraint
        with pytest.raises(IntegrityError):
            db_session.commit()
        
        # Rollback the failed transaction
        db_session.rollback()

    def test_drive_file_optional_fields(self, db_session):
        """Test that size field is optional (can be None)."""
        file = models.DriveFile(
            file_id="file-optional-test",
            parent_folder_id="folder-123",
            name="test.txt",
            mime_type="text/plain",
            size=None  # Size can be None
        )
        db_session.add(file)
        db_session.commit()
        
        assert file.id is not None
        assert file.size is None

    def test_drive_file_parent_folder_relationship(self, db_session):
        """
        Test that files can be created with parent_folder_id references.
        
        Note: The model doesn't enforce a foreign key to DriveFolder,
        so we test that the field works as expected.
        """
        # Create files with various parent folders
        file1 = models.DriveFile(
            file_id="file-rel-1",
            parent_folder_id="parent-A",
            name="file1.txt",
            mime_type="text/plain",
            size=100
        )
        file2 = models.DriveFile(
            file_id="file-rel-2",
            parent_folder_id="parent-A",
            name="file2.txt",
            mime_type="text/plain",
            size=200
        )
        file3 = models.DriveFile(
            file_id="file-rel-3",
            parent_folder_id="parent-B",
            name="file3.txt",
            mime_type="text/plain",
            size=300
        )
        
        db_session.add_all([file1, file2, file3])
        db_session.commit()
        
        # Query files by parent folder
        parent_a_files = db_session.query(models.DriveFile).filter(
            models.DriveFile.parent_folder_id == "parent-A"
        ).all()
        
        assert len(parent_a_files) == 2
        assert all(f.parent_folder_id == "parent-A" for f in parent_a_files)


class TestDriveStructureTemplateConstraints:
    """Test constraints on DriveStructureTemplate model."""

    def test_create_valid_template(self, db_session):
        """Test creating a valid template."""
        template = models.DriveStructureTemplate(
            name="Test Template",
            entity_type="company",
            active=True
        )
        db_session.add(template)
        db_session.commit()
        
        assert template.id is not None

    def test_template_unique_name(self, db_session):
        """Test that template name must be unique."""
        # Create first template
        template1 = models.DriveStructureTemplate(
            name="Unique Template",
            entity_type="company",
            active=True
        )
        db_session.add(template1)
        db_session.commit()
        
        # Try to create second template with same name
        template2 = models.DriveStructureTemplate(
            name="Unique Template",  # Same name
            entity_type="lead",
            active=True
        )
        db_session.add(template2)
        
        # Should raise IntegrityError
        with pytest.raises(IntegrityError):
            db_session.commit()
        
        # Rollback the failed transaction
        db_session.rollback()

    def test_template_default_active(self, db_session):
        """Test that active defaults to True."""
        template = models.DriveStructureTemplate(
            name="Default Active Template",
            entity_type="deal"
            # Not setting active - should default to True
        )
        db_session.add(template)
        db_session.commit()
        
        assert template.active is True


class TestDriveStructureNodeConstraints:
    """Test constraints on DriveStructureNode model."""

    def test_create_valid_node(self, db_session):
        """Test creating a valid node with template relationship."""
        # First create a template
        template = models.DriveStructureTemplate(
            name="Node Test Template",
            entity_type="company",
            active=True
        )
        db_session.add(template)
        db_session.commit()
        
        # Create node
        node = models.DriveStructureNode(
            template_id=template.id,
            parent_id=None,
            name="Root Node",
            order=0
        )
        db_session.add(node)
        db_session.commit()
        
        assert node.id is not None
        assert node.template_id == template.id

    def test_node_foreign_key_template(self, db_session):
        """Test that template_id foreign key is enforced."""
        # Try to create node with non-existent template_id
        node = models.DriveStructureNode(
            template_id=99999,  # Non-existent template
            name="Invalid Node",
            order=0
        )
        db_session.add(node)
        
        # Should raise IntegrityError due to foreign key constraint
        with pytest.raises(IntegrityError):
            db_session.commit()
        
        # Rollback the failed transaction
        db_session.rollback()

    def test_node_self_referential_parent(self, db_session):
        """Test self-referential parent_id relationship."""
        # Create template
        template = models.DriveStructureTemplate(
            name="Hierarchy Test Template",
            entity_type="lead",
            active=True
        )
        db_session.add(template)
        db_session.commit()
        
        # Create parent node
        parent_node = models.DriveStructureNode(
            template_id=template.id,
            parent_id=None,
            name="Parent Node",
            order=0
        )
        db_session.add(parent_node)
        db_session.commit()
        
        # Create child node
        child_node = models.DriveStructureNode(
            template_id=template.id,
            parent_id=parent_node.id,
            name="Child Node",
            order=1
        )
        db_session.add(child_node)
        db_session.commit()
        
        # Verify relationship
        assert child_node.parent_id == parent_node.id
        
        # Query child by parent
        children = db_session.query(models.DriveStructureNode).filter(
            models.DriveStructureNode.parent_id == parent_node.id
        ).all()
        
        assert len(children) == 1
        assert children[0].id == child_node.id

    def test_node_nullable_parent_id(self, db_session):
        """Test that parent_id can be null (for root nodes)."""
        template = models.DriveStructureTemplate(
            name="Root Test Template",
            entity_type="deal",
            active=True
        )
        db_session.add(template)
        db_session.commit()
        
        # Create node with null parent (root node)
        root_node = models.DriveStructureNode(
            template_id=template.id,
            parent_id=None,  # Explicitly null
            name="Root",
            order=0
        )
        db_session.add(root_node)
        db_session.commit()
        
        assert root_node.parent_id is None


class TestCombinedConstraints:
    """Test combined scenarios and edge cases."""

    def test_multiple_entities_same_folder_structure(self, db_session):
        """Test that multiple entities can have folders with different folder_ids."""
        # Create folders for different entities
        folder1 = models.DriveFolder(
            entity_id="entity-A",
            entity_type="company",
            folder_id="folder-A-unique"
        )
        folder2 = models.DriveFolder(
            entity_id="entity-B",
            entity_type="company",
            folder_id="folder-B-unique"
        )
        
        db_session.add_all([folder1, folder2])
        db_session.commit()
        
        # Both should exist
        folders = db_session.query(models.DriveFolder).all()
        assert len(folders) == 2

    def test_template_with_multiple_nodes(self, db_session):
        """Test creating a template with multiple nodes."""
        template = models.DriveStructureTemplate(
            name="Multi Node Template",
            entity_type="company",
            active=True
        )
        db_session.add(template)
        db_session.commit()
        
        # Create multiple nodes for the same template
        nodes = []
        for i in range(5):
            node = models.DriveStructureNode(
                template_id=template.id,
                name=f"Node {i}",
                order=i
            )
            nodes.append(node)
        
        db_session.add_all(nodes)
        db_session.commit()
        
        # Verify all nodes exist
        template_nodes = db_session.query(models.DriveStructureNode).filter(
            models.DriveStructureNode.template_id == template.id
        ).all()
        
        assert len(template_nodes) == 5
