"""
Tests for RBAC (Role-Based Access Control) functionality.

These tests verify that the role-based access control system works correctly,
including the role hierarchy, access checks, and protected endpoints.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from auth.dependencies import (
    _check_role_access,
    get_current_user_with_role,
    ROLE_HIERARCHY,
)
from auth.jwt import UserContext
from database import Base
from main import app
import models
import os

# Setup Test DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_rbac.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


MOCK_JSON = Path("mock_drive_db.json")
TEST_DB = Path("./test_rbac.db")


def setup_module(module):
    # Clean up files from previous test runs (using pathlib for cleaner code)
    MOCK_JSON.unlink(missing_ok=True)
    TEST_DB.unlink(missing_ok=True)

    # Configure mock mode
    os.environ["USE_MOCK_DRIVE"] = "true"

    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # Create test entities
    company = models.Company(id="comp-rbac-1", name="RBAC Test Company")
    db.add(company)

    lead = models.Lead(id="lead-rbac-1", title="RBAC Test Lead", qualified_company_id="comp-rbac-1")
    db.add(lead)

    deal = models.Deal(id="deal-rbac-1", title="RBAC Test Deal", company_id="comp-rbac-1")
    db.add(deal)

    # Create templates
    tmpl_company = models.DriveStructureTemplate(name="Company RBAC Tmpl", entity_type="company", active=True)
    db.add(tmpl_company)
    db.commit()

    tmpl_lead = models.DriveStructureTemplate(name="Lead RBAC Tmpl", entity_type="lead", active=True)
    db.add(tmpl_lead)
    db.commit()

    tmpl_deal = models.DriveStructureTemplate(name="Deal RBAC Tmpl", entity_type="deal", active=True)
    db.add(tmpl_deal)
    db.commit()

    db.commit()
    db.close()


def teardown_module(module):
    # Clear ALL dependency overrides to avoid conflicts with other tests
    app.dependency_overrides.clear()
    
    # Clean up test files (using pathlib for cleaner code)
    TEST_DB.unlink(missing_ok=True)
    MOCK_JSON.unlink(missing_ok=True)


class TestRoleHierarchy:
    """Test role hierarchy configuration"""

    def test_admin_has_highest_level(self):
        """Admin roles should have the highest privilege level"""
        assert ROLE_HIERARCHY["admin"] == 100
        assert ROLE_HIERARCHY["superadmin"] == 100
        assert ROLE_HIERARCHY["super_admin"] == 100

    def test_manager_has_medium_high_level(self):
        """Manager should have medium-high privilege level"""
        assert ROLE_HIERARCHY["manager"] == 75

    def test_analyst_has_medium_level(self):
        """Analyst and similar roles should have medium privilege level"""
        assert ROLE_HIERARCHY["analyst"] == 50
        assert ROLE_HIERARCHY["new_business"] == 50
        assert ROLE_HIERARCHY["sales"] == 50

    def test_viewer_has_low_level(self):
        """Viewer/client roles should have low privilege level"""
        assert ROLE_HIERARCHY["viewer"] == 10
        assert ROLE_HIERARCHY["client"] == 10
        assert ROLE_HIERARCHY["customer"] == 10


class TestCheckRoleAccess:
    """Test the _check_role_access function"""

    def test_empty_required_roles_allows_all(self):
        """Empty required_roles should allow any authenticated user"""
        assert _check_role_access("viewer", []) is True
        assert _check_role_access("admin", []) is True

    def test_direct_role_match(self):
        """User should have access if their role matches exactly"""
        assert _check_role_access("admin", ["admin"]) is True
        assert _check_role_access("manager", ["manager"]) is True
        assert _check_role_access("analyst", ["analyst"]) is True

    def test_case_insensitive_match(self):
        """Role matching should be case insensitive"""
        assert _check_role_access("ADMIN", ["admin"]) is True
        assert _check_role_access("Admin", ["admin"]) is True
        assert _check_role_access("admin", ["ADMIN"]) is True

    def test_higher_privilege_allows_access(self):
        """User with higher privilege should access lower-required endpoints"""
        # Admin should be able to access manager-required endpoints
        assert _check_role_access("admin", ["manager"]) is True
        # Manager should be able to access analyst-required endpoints
        assert _check_role_access("manager", ["analyst"]) is True

    def test_lower_privilege_denied(self):
        """User with lower privilege should be denied"""
        # Viewer cannot access admin-required endpoints
        assert _check_role_access("viewer", ["admin"]) is False
        # Client cannot access manager-required endpoints
        assert _check_role_access("client", ["manager"]) is False

    def test_multiple_required_roles(self):
        """Should allow if user has any of the required roles"""
        assert _check_role_access("manager", ["admin", "manager"]) is True
        assert _check_role_access("analyst", ["admin", "manager", "analyst"]) is True

    def test_unknown_role_denied(self):
        """Unknown roles should be denied access"""
        assert _check_role_access("unknown_role", ["admin"]) is False
        assert _check_role_access("hacker", ["manager"]) is False

    def test_none_role_denied(self):
        """None or empty string roles should be denied"""
        assert _check_role_access(None, ["admin"]) is False
        assert _check_role_access("", ["admin"]) is False


class TestGetCurrentUserWithRole:
    """Test the get_current_user_with_role factory function"""

    @pytest.mark.asyncio
    async def test_allowed_role_returns_user(self):
        """When user has required role, should return UserContext"""
        mock_user = UserContext(id="user-1", role="admin")
        
        dependency = get_current_user_with_role(["admin"])
        
        # Create a mock that the dependency can call
        with patch('auth.dependencies.get_current_user', return_value=mock_user):
            # The inner function needs the user passed in
            inner_func = dependency
            result = await inner_func(current_user=mock_user)
            assert result.id == "user-1"
            assert result.role == "admin"

    @pytest.mark.asyncio
    async def test_denied_role_raises_403(self):
        """When user lacks required role, should raise HTTPException 403"""
        mock_user = UserContext(id="user-2", role="viewer")
        
        dependency = get_current_user_with_role(["admin"])
        
        with pytest.raises(HTTPException) as exc_info:
            await dependency(current_user=mock_user)
        
        assert exc_info.value.status_code == 403
        assert "Access denied" in exc_info.value.detail


class TestProtectedEndpoints:
    """Test that protected endpoints enforce RBAC correctly"""

    @pytest.fixture(scope="class")
    def client(self):
        """Create test client with dependency overrides"""
        from routers.drive import get_db as original_get_db
        app.dependency_overrides[original_get_db] = override_get_db
        
        with patch("routers.drive.config.USE_MOCK_DRIVE", True), \
             patch("services.hierarchy_service.config.USE_MOCK_DRIVE", True), \
             patch("services.hierarchy_service.config.DRIVE_ROOT_FOLDER_ID", "mock-root-id"):
            yield TestClient(app)
        
        app.dependency_overrides.clear()

    def test_timeline_requires_authentication(self, client):
        """Timeline endpoint should require authentication"""
        response = client.get("/api/timeline/lead/lead-rbac-1")
        assert response.status_code == 401
        # For /api routes, error is in "message" field
        response_json = response.json()
        assert "Not authenticated" in response_json.get("message", response_json.get("detail", ""))

    def test_timeline_allows_authenticated_user(self, client):
        """Timeline endpoint should allow any authenticated user to attempt access"""
        response = client.get(
            "/api/timeline/lead/lead-rbac-1",
            headers={"x-user-id": "test-user", "x-user-role": "viewer"}
        )
        # The key test is that auth doesn't fail (401/403)
        # It may fail for other reasons like 404 (entity not found) or 500 (database issues)
        # The RBAC is working if we don't get 401 or 403
        assert response.status_code not in [401, 403], f"Auth should pass but got {response.status_code}"

    def test_delete_folder_requires_admin_or_manager(self, client):
        """Delete folder should require admin or manager role"""
        # First, create the folder structure
        client.get(
            "/api/drive/company/comp-rbac-1",
            headers={"x-user-id": "admin-user", "x-user-role": "admin"}
        )
        
        # Try to delete as viewer - should be denied
        response = client.delete(
            "/api/drive/company/comp-rbac-1/folders/test-folder-id",
            headers={"x-user-id": "viewer-user", "x-user-role": "viewer"}
        )
        assert response.status_code == 403
        response_json = response.json()
        assert "Access denied" in response_json.get("message", response_json.get("detail", ""))

    def test_delete_folder_allows_admin(self, client):
        """Delete folder should allow admin role"""
        # First, create the folder structure
        client.get(
            "/api/drive/company/comp-rbac-1",
            headers={"x-user-id": "admin-user", "x-user-role": "admin"}
        )
        
        # Try to delete as admin - should be allowed (may fail for other reasons)
        response = client.delete(
            "/api/drive/company/comp-rbac-1/folders/nonexistent-folder",
            headers={"x-user-id": "admin-user", "x-user-role": "admin"}
        )
        # Should not be 403 (access denied) - may be 404 (not found) or other error
        assert response.status_code != 403

    def test_delete_folder_allows_manager(self, client):
        """Delete folder should allow manager role"""
        # First, create the folder structure
        client.get(
            "/api/drive/company/comp-rbac-1",
            headers={"x-user-id": "manager-user", "x-user-role": "manager"}
        )
        
        # Try to delete as manager - should be allowed (may fail for other reasons)
        response = client.delete(
            "/api/drive/company/comp-rbac-1/folders/nonexistent-folder",
            headers={"x-user-id": "manager-user", "x-user-role": "manager"}
        )
        # Should not be 403 (access denied) - may be 404 (not found) or other error
        assert response.status_code != 403

    def test_delete_folder_denies_analyst(self, client):
        """Delete folder should deny analyst role (needs manager or above)"""
        # First, create the folder structure
        client.get(
            "/api/drive/company/comp-rbac-1",
            headers={"x-user-id": "admin-user", "x-user-role": "admin"}
        )
        
        # Try to delete as analyst - should be denied
        response = client.delete(
            "/api/drive/company/comp-rbac-1/folders/test-folder-id",
            headers={"x-user-id": "analyst-user", "x-user-role": "analyst"}
        )
        assert response.status_code == 403
        response_json = response.json()
        assert "Access denied" in response_json.get("message", response_json.get("detail", ""))


class TestConvenienceDependencies:
    """Test convenience dependency functions"""

    @pytest.mark.asyncio
    async def test_require_admin_allows_admin(self):
        """require_admin should allow admin role"""
        from auth.dependencies import require_admin
        
        mock_user = UserContext(id="user-1", role="admin")
        
        # Mock the inner dependency
        with patch('auth.dependencies.get_current_user', return_value=mock_user):
            # The require_admin function expects the inner dependency result
            result = await require_admin(current_user=mock_user)
            assert result.role == "admin"

    @pytest.mark.asyncio
    async def test_require_manager_or_above_allows_manager(self):
        """require_manager_or_above should allow manager role"""
        from auth.dependencies import require_manager_or_above
        
        mock_user = UserContext(id="user-1", role="manager")
        
        result = await require_manager_or_above(current_user=mock_user)
        assert result.role == "manager"

    @pytest.mark.asyncio
    async def test_require_writer_or_above_allows_analyst(self):
        """require_writer_or_above should allow analyst role"""
        from auth.dependencies import require_writer_or_above
        
        mock_user = UserContext(id="user-1", role="analyst")
        
        result = await require_writer_or_above(current_user=mock_user)
        assert result.role == "analyst"
