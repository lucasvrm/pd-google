import io
from typing import List, Dict, Any, Optional
from googleapiclient.http import MediaIoBaseUpload
from config import config
from cache import cache_service
from services.google_auth import GoogleAuthService

SCOPES = ['https://www.googleapis.com/auth/drive']

class GoogleDriveRealService:
    def __init__(self):
        self.auth_service = GoogleAuthService(scopes=SCOPES)
        self.service = self.auth_service.get_service('drive', 'v3')

    def _check_auth(self):
        if not self.service:
            raise Exception("Drive Service configuration error: GOOGLE_SERVICE_ACCOUNT_JSON is missing or invalid.")

    def create_folder(self, name: str, parent_id: Optional[str] = None) -> Dict[str, Any]:
        self._check_auth()

        file_metadata = {
            'name': name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if parent_id:
            file_metadata['parents'] = [parent_id]

        file = self.service.files().create(
            body=file_metadata,
            fields='id, name, mimeType, parents, createdTime',
            supportsAllDrives=True
        ).execute()
        
        # Invalidate cache for parent folder listing
        if parent_id:
            cache_key = f"drive:list_files:{parent_id}"
            cache_service.delete_key(cache_key)
        
        return file

    def upload_file(self, file_content: bytes, name: str, mime_type: str, parent_id: Optional[str] = None) -> Dict[str, Any]:
        self._check_auth()

        file_metadata = {'name': name}
        if parent_id:
            file_metadata['parents'] = [parent_id]

        media = MediaIoBaseUpload(io.BytesIO(file_content), mimetype=mime_type, resumable=True)

        file = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, mimeType, parents, size, createdTime, webViewLink',
            supportsAllDrives=True
        ).execute()
        
        # Invalidate cache for parent folder listing
        if parent_id:
            cache_key = f"drive:list_files:{parent_id}"
            cache_service.delete_key(cache_key)
        
        return file

    def list_files(self, folder_id: str) -> List[Dict[str, Any]]:
        self._check_auth()
        
        # Try to get from cache first
        cache_key = f"drive:list_files:{folder_id}"
        cached_result = cache_service.get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result

        query = f"'{folder_id}' in parents and trashed = false"
        results = self.service.files().list(
            q=query,
            pageSize=100,
            fields="nextPageToken, files(id, name, mimeType, parents, webViewLink, createdTime, size)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()

        files = results.get('files', [])
        
        # Store in cache
        cache_service.set_in_cache(cache_key, files)
        
        return files

    def get_file(self, file_id: str) -> Dict[str, Any]:
        self._check_auth()
        return self.service.files().get(
            fileId=file_id,
            fields='id, name, mimeType, parents, webViewLink, createdTime, size',
            supportsAllDrives=True
        ).execute()

    def add_permission(self, file_id: str, role: str, email: str, type: str = 'user'):
        """
        role: 'owner', 'organizer', 'fileOrganizer', 'writer', 'reader'
        """
        self._check_auth()

        permission = {
            'type': type,
            'role': role,
            'emailAddress': email
        }
        return self.service.permissions().create(
            fileId=file_id,
            body=permission,
            fields='id',
            supportsAllDrives=True
        ).execute()
