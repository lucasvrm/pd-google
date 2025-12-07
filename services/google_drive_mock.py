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
                }
            }
            self._save_db()

    def _save_db(self):
        with open(DB_FILE, "w") as f:
            json.dump(self.db, f, indent=2)

    def get_or_create_folder(self, name: str, parent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Mock implementation of get_or_create_folder.
        """
        parent_id = parent_id or "root"

        # 1. Check if exists
        # In mock, we can iterate over folders
        self._load_db()
        for f_id, f_data in self.db["folders"].items():
            if f_data.get("name") == name and parent_id in f_data.get("parents", []):
                return f_data

        # 2. Create if not exists
        return self.create_folder(name, parent_id)

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