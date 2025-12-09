from services.drive_permissions_service import DrivePermissionsService
from services.google_drive_mock import GoogleDriveService


def setup_mock_drive():
    drive = GoogleDriveService()
    drive.db = {
        "files": {},
        "folders": {"root": {"id": "root", "name": "My Drive", "parents": []}},
        "permissions": {},
    }
    drive._save_db()
    return drive


def test_permission_crud_and_move_with_mock_drive():
    drive = setup_mock_drive()
    service = DrivePermissionsService(drive)

    root = drive.create_folder("Entity Root")
    target_folder = drive.create_folder("Folder A", parent_id=root["id"])
    destination = drive.create_folder("Folder B", parent_id=root["id"])
    file_meta = drive.upload_file(b"content", "file.txt", "text/plain", parent_id=target_folder["id"])

    created_perm = service.add_permission(file_meta["id"], "writer", "user@example.com")
    assert created_perm["role"] == "writer"

    permissions = service.list_permissions(file_meta["id"])
    assert len(permissions) == 1
    assert permissions[0]["emailAddress"] == "user@example.com"

    updated_perm = service.update_permission(file_meta["id"], created_perm["id"], "reader")
    assert updated_perm["role"] == "reader"

    renamed = service.rename(file_meta["id"], "renamed.txt")
    assert renamed["name"] == "renamed.txt"

    moved = service.move_file(file_meta["id"], destination["id"])
    assert destination["id"] in moved.get("parents", [])

    service.remove_permission(file_meta["id"], created_perm["id"])
    assert service.list_permissions(file_meta["id"]) == []
