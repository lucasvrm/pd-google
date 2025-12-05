import json
import io
from typing import List, Dict, Any, Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from config import config

SCOPES = ['https://www.googleapis.com/auth/drive']

class GoogleDriveRealService:
    def __init__(self):
        self.creds = None
        self.service = None
        self._authenticate()

    def _authenticate(self):
        if not config.GOOGLE_SERVICE_ACCOUNT_JSON:
            print("Warning: GOOGLE_SERVICE_ACCOUNT_JSON not set. Real Drive Service will fail.")
            return

        try:
            # Handle if the env var is a file path or the JSON content string
            if config.GOOGLE_SERVICE_ACCOUNT_JSON.strip().startswith("{"):
                info = json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON)
                self.creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
            else:
                self.creds = service_account.Credentials.from_service_account_file(
                    config.GOOGLE_SERVICE_ACCOUNT_JSON, scopes=SCOPES
                )

            self.service = build('drive', 'v3', credentials=self.creds)
        except Exception as e:
            print(f"Authentication failed: {e}")

    def create_folder(self, name: str, parent_id: Optional[str] = None) -> Dict[str, Any]:
        if not self.service: raise Exception("Drive Service not authenticated")

        file_metadata = {
            'name': name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if parent_id:
            file_metadata['parents'] = [parent_id]

        file = self.service.files().create(body=file_metadata, fields='id, name, mimeType, parents, createdTime').execute()
        return file

    def upload_file(self, file_content: bytes, name: str, mime_type: str, parent_id: Optional[str] = None) -> Dict[str, Any]:
        if not self.service: raise Exception("Drive Service not authenticated")

        file_metadata = {'name': name}
        if parent_id:
            file_metadata['parents'] = [parent_id]

        media = MediaIoBaseUpload(io.BytesIO(file_content), mimetype=mime_type, resumable=True)

        file = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, mimeType, parents, size, createdTime, webViewLink'
        ).execute()
        return file

    def list_files(self, folder_id: str) -> List[Dict[str, Any]]:
        if not self.service: raise Exception("Drive Service not authenticated")

        query = f"'{folder_id}' in parents and trashed = false"
        results = self.service.files().list(
            q=query,
            pageSize=100,
            fields="nextPageToken, files(id, name, mimeType, parents, webViewLink, createdTime, size)"
        ).execute()

        return results.get('files', [])

    def get_file(self, file_id: str) -> Dict[str, Any]:
        if not self.service: raise Exception("Drive Service not authenticated")
        return self.service.files().get(fileId=file_id, fields='id, name, mimeType, parents, webViewLink, createdTime, size').execute()

    def add_permission(self, file_id: str, role: str, email: str, type: str = 'user'):
        """
        role: 'owner', 'organizer', 'fileOrganizer', 'writer', 'reader'
        """
        if not self.service: raise Exception("Drive Service not authenticated")

        permission = {
            'type': type,
            'role': role,
            'emailAddress': email
        }
        return self.service.permissions().create(
            fileId=file_id,
            body=permission,
            fields='id'
        ).execute()
