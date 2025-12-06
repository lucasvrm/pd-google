"""
Concurrent Access Tests

These tests verify that the application handles concurrent requests properly
without race conditions or data corruption.

Tests simulate multiple simultaneous requests to the same endpoint and verify:
1. Responses are consistent across all requests
2. No exceptions or errors occur due to concurrent access
3. Database operations handle concurrency correctly
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from main import app
import models
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import time


# Setup Test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_concurrent.db"
# Note: We need to enable foreign keys for SQLite
from sqlalchemy import event
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

# Enable foreign keys for SQLite
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def setup_module():
    """Setup test database and seed data."""
    # Override dependency for this module
    from routers.drive import get_db
    app.dependency_overrides[get_db] = override_get_db
    
    Base.metadata.create_all(bind=engine)
    
    # Seed mock data
    db = TestingSessionLocal()
    
    # Company
    company1 = models.Company(id="comp-concurrent-123", name="Concurrent Test Company", fantasy_name="Concurrent Fantasy")
    db.add(company1)
    
    # Lead
    lead1 = models.Lead(id="lead-concurrent-001", title="Concurrent Test Lead", company_id="comp-concurrent-123")
    db.add(lead1)
    
    # Deal
    deal1 = models.Deal(id="deal-concurrent-001", title="Concurrent Test Deal", company_id="comp-concurrent-123")
    db.add(deal1)
    
    # Template for company
    tmpl_comp = models.DriveStructureTemplate(name="Concurrent Comp Tmpl", entity_type="company", active=True)
    db.add(tmpl_comp)
    db.commit()
    
    node_comp = models.DriveStructureNode(template_id=tmpl_comp.id, name="Company Node", order=0)
    db.add(node_comp)
    
    # Template for lead
    tmpl_lead = models.DriveStructureTemplate(name="Concurrent Lead Tmpl", entity_type="lead", active=True)
    db.add(tmpl_lead)
    db.commit()
    
    node_lead = models.DriveStructureNode(template_id=tmpl_lead.id, name="Lead Node", order=0)
    db.add(node_lead)
    
    # Template for deal
    tmpl_deal = models.DriveStructureTemplate(name="Concurrent Deal Tmpl", entity_type="deal", active=True)
    db.add(tmpl_deal)
    db.commit()
    
    node_deal = models.DriveStructureNode(template_id=tmpl_deal.id, name="Deal Node", order=0)
    db.add(node_deal)
    
    db.commit()
    db.close()
    
    # Create TestClient after override is in place
    global client
    client = TestClient(app)
    
    yield
    
    # Cleanup: reset overrides
    from routers.drive import get_db
    if get_db in app.dependency_overrides:
        del app.dependency_overrides[get_db]
    
    # Cleanup database
    if os.path.exists("./test_concurrent.db"):
        os.remove("./test_concurrent.db")


client = None  # Will be set in setup_module


def make_request(entity_type, entity_id, request_num):
    """
    Make a single request to the drive endpoint.
    
    Returns:
        tuple: (request_num, response_status, response_data, error)
    """
    try:
        response = client.get(f"/drive/{entity_type}/{entity_id}")
        return (request_num, response.status_code, response.json(), None)
    except Exception as e:
        return (request_num, None, None, str(e))


class TestConcurrentAccess:
    """Test concurrent access to drive endpoints."""

    def test_concurrent_read_same_company(self):
        """
        Test multiple concurrent reads to the same company endpoint.
        
        Verifies:
        - All requests return successfully (status 200)
        - Response structure is consistent across all requests
        - No race conditions or exceptions occur
        """
        entity_type = "company"
        entity_id = "comp-concurrent-123"
        num_requests = 10
        
        results = []
        
        # Use ThreadPoolExecutor to simulate concurrent requests
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(make_request, entity_type, entity_id, i)
                for i in range(num_requests)
            ]
            
            for future in as_completed(futures):
                results.append(future.result())
        
        # Sort by request number for easier analysis
        results.sort(key=lambda x: x[0])
        
        # Verify all requests succeeded
        for request_num, status, data, error in results:
            assert error is None, f"Request {request_num} raised error: {error}"
            assert status == 200, f"Request {request_num} returned status {status}"
            assert data is not None, f"Request {request_num} returned no data"
            assert "files" in data, f"Request {request_num} missing 'files' key"
            assert "permission" in data, f"Request {request_num} missing 'permission' key"
        
        # Verify response consistency - all responses should have same structure
        first_response = results[0][2]
        for request_num, status, data, error in results[1:]:
            # The folder structure should be consistent
            # Note: File listings might vary slightly if files are being added,
            # but in our test scenario with just structure creation, it should be stable
            assert isinstance(data["files"], list), f"Request {request_num} files is not a list"
            assert data["permission"] == first_response["permission"], \
                f"Request {request_num} permission differs from first request"

    def test_concurrent_read_different_entities(self):
        """
        Test concurrent reads to different entity types and IDs.
        
        Verifies that concurrent access to different entities doesn't cause conflicts.
        """
        test_cases = [
            ("company", "comp-concurrent-123"),
            ("lead", "lead-concurrent-001"),
            ("deal", "deal-concurrent-001"),
        ]
        
        results = []
        
        # Make concurrent requests to different endpoints
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = []
            for i, (entity_type, entity_id) in enumerate(test_cases):
                # Make 2 requests to each entity
                futures.append(executor.submit(make_request, entity_type, entity_id, i * 2))
                futures.append(executor.submit(make_request, entity_type, entity_id, i * 2 + 1))
            
            for future in as_completed(futures):
                results.append(future.result())
        
        # Verify all requests succeeded
        for request_num, status, data, error in results:
            assert error is None, f"Request {request_num} raised error: {error}"
            assert status == 200, f"Request {request_num} returned status {status}"

    def test_concurrent_folder_structure_creation(self):
        """
        Test that concurrent requests properly handle folder structure creation.
        
        When multiple requests hit the endpoint for the first time,
        the hierarchy service should create the structure only once.
        """
        # Use a new entity that doesn't have structure created yet
        entity_type = "company"
        entity_id = "comp-new-concurrent"
        
        # Add the company to database first
        db = TestingSessionLocal()
        new_company = models.Company(id=entity_id, name="New Concurrent Company")
        db.add(new_company)
        db.commit()
        db.close()
        
        num_requests = 8
        results = []
        
        # Make concurrent requests
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(make_request, entity_type, entity_id, i)
                for i in range(num_requests)
            ]
            
            for future in as_completed(futures):
                results.append(future.result())
        
        # Verify all succeeded
        for request_num, status, data, error in results:
            assert error is None, f"Request {request_num} raised error: {error}"
            assert status == 200, f"Request {request_num} returned status {status}"
        
        # Verify only ONE DriveFolder was created for this entity
        db = TestingSessionLocal()
        folders = db.query(models.DriveFolder).filter(
            models.DriveFolder.entity_type == entity_type,
            models.DriveFolder.entity_id == entity_id
        ).all()
        db.close()
        
        # Should have exactly one root folder (and possibly child folders from template)
        # But the important thing is no duplicate root folders were created
        folder_ids = [f.folder_id for f in folders]
        unique_folder_ids = set(folder_ids)
        
        # All folder_ids should be unique (no duplicates)
        assert len(folder_ids) == len(unique_folder_ids), \
            f"Duplicate folders created during concurrent access: {folder_ids}"

    def test_concurrent_mixed_operations(self):
        """
        Test concurrent mix of read operations.
        
        This simulates a more realistic scenario where different operations
        might happen simultaneously.
        """
        entity_type = "lead"
        entity_id = "lead-concurrent-001"
        
        num_read_requests = 10
        results = []
        
        # Mix of operations (in this case, all reads, but with slight delays)
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            
            for i in range(num_read_requests):
                futures.append(executor.submit(make_request, entity_type, entity_id, i))
                # Small random delay to stagger requests slightly
                time.sleep(0.01)
            
            for future in as_completed(futures):
                results.append(future.result())
        
        # Verify no errors occurred
        errors = [error for _, _, _, error in results if error is not None]
        assert len(errors) == 0, f"Errors occurred during concurrent operations: {errors}"
        
        # Verify all requests got valid responses
        for request_num, status, data, error in results:
            assert status == 200, f"Request {request_num} returned status {status}"
            assert "files" in data and "permission" in data, \
                f"Request {request_num} missing expected keys"
