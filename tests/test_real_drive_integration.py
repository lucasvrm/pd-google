"""
Real Google Drive Integration Tests

These tests are designed to run against the actual Google Drive API.
They are OPTIONAL and will be skipped by default if credentials are not configured.

To run these tests:
1. Set the environment variable GOOGLE_SERVICE_ACCOUNT_JSON to your service account JSON
2. Run pytest with the integration marker: pytest -v -m integration

Note: These tests are NOT run in CI by default to avoid dependency on credentials.
"""

import pytest
import os
from services.google_drive_real import GoogleDriveRealService
from config import config


# Helper function to check if real Drive credentials are available
def has_real_drive_credentials():
    """Check if Google Drive credentials are properly configured."""
    return bool(config.GOOGLE_SERVICE_ACCOUNT_JSON)


# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


class TestRealDriveIntegration:
    """Integration tests for real Google Drive API."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Setup and teardown for each test."""
        # Skip if credentials not available
        if not has_real_drive_credentials():
            pytest.skip("GOOGLE_SERVICE_ACCOUNT_JSON not configured - skipping real Drive integration test")
        
        self.service = GoogleDriveRealService()
        self.created_folder_ids = []
        
        yield
        
        # Cleanup: Delete created test folders
        # Note: In production, you might want to implement cleanup logic
        # For now, we'll rely on manual cleanup or use a dedicated test folder
        pass

    def test_initialize_real_service(self):
        """Test that the real Drive service can be initialized with valid credentials."""
        assert self.service.service is not None, "Drive service should be initialized"
        assert self.service.creds is not None, "Credentials should be loaded"

    def test_create_folder_and_list(self):
        """
        Test creating a folder in Google Drive and verifying it appears in listings.
        
        This test:
        1. Creates a test folder with a unique name
        2. Verifies the folder was created successfully
        3. Lists folders in the parent location
        4. Verifies the created folder appears in the listing
        """
        # Create a test folder with a unique name to avoid conflicts
        import datetime
        folder_name = f"Test Folder {datetime.datetime.now().isoformat()}"
        
        # Create the folder (in root or in DRIVE_ROOT_FOLDER_ID if configured)
        parent_id = config.DRIVE_ROOT_FOLDER_ID
        folder = self.service.create_folder(folder_name, parent_id=parent_id)
        
        # Verify folder creation
        assert folder is not None, "Folder should be created"
        assert "id" in folder, "Folder should have an ID"
        assert folder["name"] == folder_name, "Folder name should match"
        assert folder["mimeType"] == "application/vnd.google-apps.folder", "Should be a folder type"
        
        # Track for potential cleanup
        self.created_folder_ids.append(folder["id"])
        
        # List files in the parent location to verify the folder appears
        parent_to_list = parent_id if parent_id else folder["parents"][0] if "parents" in folder else None
        
        if parent_to_list:
            # List files and check if our folder is there
            files = self.service.list_files(parent_to_list)
            folder_ids = [f["id"] for f in files]
            
            assert folder["id"] in folder_ids, "Created folder should appear in parent folder listing"

    def test_create_nested_folder_structure(self):
        """
        Test creating a nested folder structure.
        
        This verifies that folders can be created with parent references
        and that the hierarchy is properly maintained.
        """
        import datetime
        
        # Create parent folder
        parent_name = f"Parent Folder {datetime.datetime.now().isoformat()}"
        parent_folder = self.service.create_folder(parent_name, parent_id=config.DRIVE_ROOT_FOLDER_ID)
        
        assert parent_folder is not None
        self.created_folder_ids.append(parent_folder["id"])
        
        # Create child folder
        child_name = "Child Folder"
        child_folder = self.service.create_folder(child_name, parent_id=parent_folder["id"])
        
        assert child_folder is not None
        assert "parents" in child_folder
        assert parent_folder["id"] in child_folder["parents"], "Child should have parent in parents list"
        
        self.created_folder_ids.append(child_folder["id"])
        
        # Verify child appears in parent listing
        parent_files = self.service.list_files(parent_folder["id"])
        child_ids = [f["id"] for f in parent_files]
        
        assert child_folder["id"] in child_ids, "Child folder should appear in parent listing"


# Optional: Add a test that runs even without credentials to verify graceful degradation
@pytest.mark.unit
def test_real_service_without_credentials():
    """Test that RealDriveService handles missing credentials gracefully."""
    # Temporarily clear the credentials
    original_creds = config.GOOGLE_SERVICE_ACCOUNT_JSON
    config.GOOGLE_SERVICE_ACCOUNT_JSON = None
    
    try:
        service = GoogleDriveRealService()
        # Service should initialize but service attribute should be None
        assert service.service is None, "Service should be None without credentials"
        
        # Attempting to use the service should raise an appropriate error
        with pytest.raises(Exception) as exc_info:
            service.create_folder("Test")
        
        assert "configuration error" in str(exc_info.value).lower() or "missing" in str(exc_info.value).lower()
    finally:
        # Restore original credentials
        config.GOOGLE_SERVICE_ACCOUNT_JSON = original_creds
