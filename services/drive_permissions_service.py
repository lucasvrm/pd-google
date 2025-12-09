from typing import List, Dict, Any, Optional

from config import config
from services.google_drive_mock import GoogleDriveService as MockDriveService
from services.google_drive_real import GoogleDriveRealService


class DrivePermissionsService:
    def __init__(self, drive_service: Optional[Any] = None):
        if drive_service:
            self.drive_service = drive_service
        else:
            self.drive_service = MockDriveService() if config.USE_MOCK_DRIVE else GoogleDriveRealService()

    def list_permissions(self, file_id: str) -> List[Dict[str, Any]]:
        if hasattr(self.drive_service, "list_permissions"):
            return self.drive_service.list_permissions(file_id)
        raise NotImplementedError("The configured drive service does not support listing permissions.")

    def add_permission(self, file_id: str, role: str, email: str, type: str = "user") -> Dict[str, Any]:
        if hasattr(self.drive_service, "add_permission"):
            return self.drive_service.add_permission(file_id, role, email, type)
        raise NotImplementedError("The configured drive service does not support adding permissions.")

    def update_permission(self, file_id: str, permission_id: str, role: str) -> Dict[str, Any]:
        if hasattr(self.drive_service, "update_permission"):
            return self.drive_service.update_permission(file_id, permission_id, role)
        raise NotImplementedError("The configured drive service does not support updating permissions.")

    def remove_permission(self, file_id: str, permission_id: str) -> None:
        if hasattr(self.drive_service, "remove_permission"):
            return self.drive_service.remove_permission(file_id, permission_id)
        raise NotImplementedError("The configured drive service does not support removing permissions.")

    def move_file(self, file_id: str, destination_parent_id: str) -> Dict[str, Any]:
        if hasattr(self.drive_service, "move_file"):
            return self.drive_service.move_file(file_id, destination_parent_id)
        raise NotImplementedError("The configured drive service does not support moving files.")

    def rename(self, file_id: str, new_name: str) -> Dict[str, Any]:
        if hasattr(self.drive_service, "update_file_metadata"):
            return self.drive_service.update_file_metadata(file_id, new_name)
        raise NotImplementedError("The configured drive service does not support renaming files.")
