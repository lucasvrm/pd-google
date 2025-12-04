import json
import os
import uuid
import datetime
from typing import List, Optional, Dict, Any

# Get the directory where this file (google_drive_mock.py) is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Go up one level to pd-google root (assuming services/ is one level deep)
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DB_FILE = os.path.join(PROJECT_ROOT, "mock_drive_db.json")

class GoogleDriveService:
    def __init__(self):
        self._load_db()

    def _load_db(self):
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "r") as f:
                self.db = json.load(f)
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

    def create_folder(self, name: str, parent_id: str = "root") -> Dict[str, Any]:
        folder_id = str(uuid.uuid4())
        folder = {
            "id": folder_id,
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
            "createdTime": datetime.datetime.now().isoformat()
        }
        self.db["folders"][folder_id] = folder
        self._save_db()
        return folder

    def upload_file(self, file_content: bytes, name: str, mime_type: str, parent_id: str = "root") -> Dict[str, Any]:
        file_id = str(uuid.uuid4())
        # In a real mock, we might save the content to disk. Here we just store metadata.
        # We'll save content to a 'uploads' folder for simulation realism if needed,
        # but the prompt focuses on metadata/structure mainly.

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
        # Return all folders and files whose parent is folder_id
        items = []
        for f in self.db["folders"].values():
            if folder_id in f.get("parents", []):
                items.append(f)
        for f in self.db["files"].values():
            if folder_id in f.get("parents", []):
                items.append(f)
        return items

    def get_file(self, file_id: str) -> Optional[Dict[str, Any]]:
        if file_id in self.db["folders"]:
            return self.db["folders"][file_id]
        if file_id in self.db["files"]:
            return self.db["files"][file_id]
        return None
