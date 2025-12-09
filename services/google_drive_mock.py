import json
import os
import uuid
import datetime
from typing import List, Optional, Dict, Any

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DB_FILE = os.path.join(PROJECT_ROOT, "mock_drive_db.json")

class GoogleDriveService:
    def __init__(self):
        self._load_db()

    def _load_db(self):
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "r") as f:
                try:
                    self.db = json.load(f)
                except json.JSONDecodeError:
                    self.db = {"files": {}, "folders": {"root": {"id": "root", "name": "My Drive", "parents": []}}}
        else:
            self.db = {
                "files": {},
                "folders": {
                    "root": {"id": "root", "name": "My Drive", "parents": []}
                },
                "permissions": {}
            }
            self._save_db()

        # Ensure permissions key exists for backward compatibility
        if "permissions" not in self.db:
            self.db["permissions"] = {}

    def _save_db(self):
        with open(DB_FILE, "w") as f:
            json.dump(self.db, f, indent=2)

    def get_or_create_folder(self, name: str, parent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Mock implementation of get_or_create_folder.
        Normalizes folder names to prevent duplicates from whitespace differences.
        """
        parent_id = parent_id or "root"
        # Normalize name by stripping whitespace
        normalized_name = name.strip()

        # 1. Check if exists with normalized comparison
        # In mock, we can iterate over folders
        self._load_db()
        for f_id, f_data in self.db["folders"].items():
            folder_name = f_data.get("name", "").strip()
            if folder_name == normalized_name and parent_id in f_data.get("parents", []):
                return f_data

        # 2. Create if not exists (use normalized name)
        return self.create_folder(normalized_name, parent_id)

    def create_folder(self, name: str, parent_id: str = "root") -> Dict[str, Any]:
        self._load_db()
        folder_id = str(uuid.uuid4())
        
        # CORREÇÃO AQUI: Adicionado webViewLink simulado
        folder = {
            "id": folder_id,
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
            "createdTime": datetime.datetime.now().isoformat(),
            "webViewLink": f"https://mock-drive.google.com/folders/{folder_id}"
        }
        self.db["folders"][folder_id] = folder
        self.db["permissions"].setdefault(folder_id, [])
        self._save_db()
        return folder

    def upload_file(self, file_content: bytes, name: str, mime_type: str, parent_id: str = "root") -> Dict[str, Any]:
        self._load_db()
        file_id = str(uuid.uuid4())

        file_meta = {
            "id": file_id,
            "name": name,
            "mimeType": mime_type,
            "parents": [parent_id],
            "size": len(file_content),
            "createdTime": datetime.datetime.now().isoformat(),
            "webViewLink": f"https://mock-drive.google.com/file/d/{file_id}/view"
        }
        self.db["files"][file_id] = file_meta
        self.db["permissions"].setdefault(file_id, [])
        self._save_db()
        return file_meta

    def list_files(self, folder_id: str = "root") -> List[Dict[str, Any]]:
        self._load_db()
        items = []
        for f in self.db["folders"].values():
            if folder_id in f.get("parents", []):
                items.append(f)
        for f in self.db["files"].values():
            if folder_id in f.get("parents", []):
                items.append(f)
        return items

    def get_file(self, file_id: str) -> Optional[Dict[str, Any]]:
        self._load_db()
        if file_id in self.db["folders"]:
            return self.db["folders"][file_id]
        if file_id in self.db["files"]:
            return self.db["files"][file_id]
        return None

    def update_file_metadata(self, file_id: str, new_name: str) -> Dict[str, Any]:
        self._load_db()
        item = self.get_file(file_id)
        if item:
            item["name"] = new_name
            self._save_db()
            return item
        raise Exception("File not found")

    def move_file(self, file_id: str, destination_parent_id: str) -> Dict[str, Any]:
        self._load_db()
        item = self.get_file(file_id)
        if not item:
            raise Exception("File not found")

        current_parents = item.get("parents", [])
        if destination_parent_id not in current_parents:
            new_parents = [destination_parent_id]
            item["parents"] = new_parents
            self._save_db()
        return item

    def list_permissions(self, file_id: str) -> List[Dict[str, Any]]:
        self._load_db()
        return list(self.db.get("permissions", {}).get(file_id, []))

    def add_permission(self, file_id: str, role: str, email: str, type: str = "user") -> Dict[str, Any]:
        self._load_db()
        permission = {
            "id": str(uuid.uuid4()),
            "role": role,
            "emailAddress": email,
            "type": type,
        }
        self.db.setdefault("permissions", {}).setdefault(file_id, []).append(permission)
        self._save_db()
        return permission

    def update_permission(self, file_id: str, permission_id: str, role: str) -> Dict[str, Any]:
        self._load_db()
        permissions = self.db.setdefault("permissions", {}).setdefault(file_id, [])
        for perm in permissions:
            if perm.get("id") == permission_id:
                perm["role"] = role
                self._save_db()
                return perm
        raise Exception("Permission not found")

    def remove_permission(self, file_id: str, permission_id: str) -> None:
        self._load_db()
        permissions = self.db.setdefault("permissions", {}).setdefault(file_id, [])
        self.db["permissions"][file_id] = [p for p in permissions if p.get("id") != permission_id]
        self._save_db()

    def is_descendant(self, folder_id: str, ancestor_id: str) -> bool:
        self._load_db()
        current_id = folder_id
        for _ in range(10):
            if current_id == ancestor_id:
                return True

            # Find item
            item = self.db["folders"].get(current_id) or self.db["files"].get(current_id)
            if not item:
                return False

            parents = item.get("parents", [])
            if not parents:
                return False
            current_id = parents[0]
        return False

    def get_breadcrumbs(self, folder_id: str, root_id: str) -> List[Dict[str, str]]:
        self._load_db()
        breadcrumbs = []
        current_id = folder_id
        for _ in range(10):
            item = self.db["folders"].get(current_id) or self.db["files"].get(current_id)
            if not item:
                break

            breadcrumbs.insert(0, {"id": item["id"], "name": item["name"]})

            if current_id == root_id:
                break

            parents = item.get("parents", [])
            if not parents:
                break
            current_id = parents[0]

        return breadcrumbs
