import pytest
from unittest.mock import MagicMock
from services.google_drive_mock import GoogleDriveService
import models

def test_drive_navigation_logic():
    # Setup Mock
    drive_service = GoogleDriveService()
    # Reset DB manually for test
    drive_service.db = {"files": {}, "folders": {"root": {"id": "root", "name": "My Drive", "parents": []}}}

    # Create Hierarchy:
    # Root (Deal)
    #   -> Folder A
    #      -> Folder B
    # Other Root (Other Deal)

    root = drive_service.create_folder("Deal Root")
    root_id = root["id"]

    folder_a = drive_service.create_folder("Folder A", parent_id=root_id)
    folder_b = drive_service.create_folder("Folder B", parent_id=folder_a["id"])

    other_root = drive_service.create_folder("Other Root")
    other_root_id = other_root["id"]

    # 1. Test Lineage Success (Root -> Folder B)
    print("Testing Lineage Success...")
    assert drive_service.is_descendant(folder_b["id"], root_id) is True

    # 2. Test Lineage Failure (Other Root -> Folder B)
    print("Testing Lineage Failure...")
    assert drive_service.is_descendant(folder_b["id"], other_root_id) is False

    # 3. Test Breadcrumbs
    print("Testing Breadcrumbs...")
    breadcrumbs = drive_service.get_breadcrumbs(folder_b["id"], root_id)
    # Expect: [Root, Folder A, Folder B]
    # Note: get_breadcrumbs implementation includes current folder at the end?
    # Let's check logic: insert(0, current). loop up.
    # Current = B. Breadcrumbs = [B]. Parent = A.
    # Loop. Current = A. Breadcrumbs = [A, B]. Parent = Root.
    # Loop. Current = Root. Breadcrumbs = [Root, A, B]. Break.

    assert len(breadcrumbs) == 3
    assert breadcrumbs[0]["name"] == "Deal Root"
    assert breadcrumbs[1]["name"] == "Folder A"
    assert breadcrumbs[2]["name"] == "Folder B"

    print("Navigation tests passed.")

if __name__ == "__main__":
    test_drive_navigation_logic()
