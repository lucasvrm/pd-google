import pytest
from unittest.mock import MagicMock
from sqlalchemy.orm import Session
from services.template_service import TemplateService
from services.google_drive_mock import GoogleDriveService
import models

def test_template_repair_and_idempotency():
    # 1. Setup Mock DB
    db = MagicMock(spec=Session)

    # Define a template: Root -> Child A -> Child B
    template = models.DriveStructureTemplate(entity_type="test_entity", active=True)
    # Using real integers for IDs
    node1 = models.DriveStructureNode(id=1, name="Folder A", parent_id=None, order=0)
    node2 = models.DriveStructureNode(id=2, name="Folder B", parent_id=1, order=0)
    template.nodes = [node1, node2]

    # Mock the query response
    # We mock the chain: db.query(...).filter_by(...).first()
    db.query.return_value.filter_by.return_value.first.return_value = template

    # 2. Setup Mock Drive Service
    drive_service = GoogleDriveService()
    # Reset DB for test
    drive_service.db = {"files": {}, "folders": {"root": {"id": "root", "name": "My Drive", "parents": []}}}
    drive_service._save_db() # sync to file just in case

    # 3. Initialize Template Service
    ts = TemplateService(db, drive_service)

    # 4. First Run: Create structure
    print("Running initial template application...")
    ts.apply_template("test_entity", "root")

    # Verify folders created
    folders = drive_service.list_files("root")
    folder_a = next((f for f in folders if f["name"] == "Folder A"), None)
    assert folder_a is not None, "Folder A should be created"

    # Verify subfolder
    subfolders = drive_service.list_files(folder_a["id"])
    folder_b = next((f for f in subfolders if f["name"] == "Folder B"), None)
    assert folder_b is not None, "Folder B should be created inside Folder A"

    print(f"Created Structure: A({folder_a['id']}) -> B({folder_b['id']})")

    # 5. Simulate Partial Deletion or Missing Folder
    # Let's say we manually delete Folder B from the Drive Mock (simulate a failure in previous run or accidental deletion)
    print("Deleting Folder B to simulate missing folder...")
    del drive_service.db["folders"][folder_b["id"]]
    drive_service._save_db()

    # 6. Second Run (Repair): Should re-create Folder B but NOT Folder A
    print("Running repair (second application)...")
    ts.apply_template("test_entity", "root")

    # Verify
    folders_retry = drive_service.list_files("root")
    # Should still have only one Folder A
    folders_a_list = [f for f in folders_retry if f["name"] == "Folder A"]
    assert len(folders_a_list) == 1, f"Should not duplicate Folder A. Found: {len(folders_a_list)}"

    # Verify Folder B is back
    folder_a_id = folders_a_list[0]["id"]
    subfolders_retry = drive_service.list_files(folder_a_id)
    folder_b_retry = next((f for f in subfolders_retry if f["name"] == "Folder B"), None)
    assert folder_b_retry is not None, "Folder B should be repaired"

    # Since we deleted the key, it must be a new ID
    assert folder_b_retry["id"] != folder_b["id"], "Folder B should be a new instance"

    print(f"Repaired Structure: A({folder_a_id}) -> B({folder_b_retry['id']})")
    print("Test Passed: Idempotency and Repair logic verified.")

if __name__ == "__main__":
    test_template_repair_and_idempotency()
