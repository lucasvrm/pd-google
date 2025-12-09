import io
import time
import random
from typing import List, Dict, Any, Optional
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError
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

    def _retry_operation(self, func, *args, **kwargs):
        """
        Executes a function with exponential backoff retry logic for transient errors.
        Handles Rate Limits (403, 429) and Server Errors (5xx).
        """
        max_retries = 5
        base_delay = 1.0  # seconds

        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except HttpError as e:
                # Retry on Rate Limits and Server Errors
                if e.resp.status in [403, 429, 500, 502, 503, 504]:
                    if attempt == max_retries - 1:
                        print(f"Drive API Error {e.resp.status}: Max retries exceeded.")
                        raise

                    # Extract reason if possible
                    reason = "Unknown"
                    try:
                        import json
                        error_content = json.loads(e.content.decode('utf-8'))
                        reason = error_content.get('error', {}).get('message', 'Unknown')
                    except:
                        pass

                    # Calculate backoff with jitter
                    sleep_time = (base_delay * (2 ** attempt)) + (random.randint(0, 1000) / 1000)
                    print(f"Drive API Error {e.resp.status} ({reason}). Retrying in {sleep_time:.2f}s... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(sleep_time)

                    # Check if we need to refresh auth (sometimes helpful for long running processes)
                    if attempt > 2:
                         self.service = self.auth_service.get_service('drive', 'v3')
                else:
                    raise
            except Exception as e:
                # Re-raise other exceptions (like connection errors? maybe retry those too?)
                # For now, only HttpError logic is specific.
                print(f"Unexpected error in Drive operation: {e}")
                raise

    def get_or_create_folder(self, name: str, parent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Checks if a folder with the given name exists in the parent_id.
        If it exists, returns the metadata.
        If not, creates it.
        This ensures idempotency and helps in repairing folder structures.
        
        Normalizes folder names to prevent duplicates from whitespace differences.
        """
        self._check_auth()

        target_parent = parent_id if parent_id else 'root'
        # Normalize name by stripping whitespace
        normalized_name = name.strip()

        try:
            # 1. Try to find existing folder
            # list_files already uses cache, so this is efficient
            children = self.list_files(target_parent)
            for file in children:
                # Compare normalized names to handle whitespace variations
                if file.get('name', '').strip() == normalized_name and \
                   file.get('mimeType') == 'application/vnd.google-apps.folder':
                     # Found it!
                     print(f"Folder '{normalized_name}' already exists in {target_parent}. Using ID: {file['id']}")
                     return file
        except Exception as e:
            print(f"Warning: Failed to list files in get_or_create_folder: {e}. Proceeding to create attempt.")

        # 2. Create if not found (use normalized name)
        # Note: There's still a small race condition window here in production
        # where two processes might both not find the folder and both try to create it.
        # Google Drive API will create both (it allows duplicate names).
        # The cache invalidation after create_folder helps subsequent calls find it,
        # but for true prevention we rely on the local caching in template_service.
        return self.create_folder(normalized_name, parent_id)

    def create_folder(self, name: str, parent_id: Optional[str] = None) -> Dict[str, Any]:
        self._check_auth()

        file_metadata = {
            'name': name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if parent_id:
            file_metadata['parents'] = [parent_id]

        def _api_call():
            return self.service.files().create(
                body=file_metadata,
                fields='id, name, mimeType, parents, createdTime, webViewLink',
                supportsAllDrives=True
            ).execute()

        file = self._retry_operation(_api_call)
        
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

        def _api_call():
            return self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, mimeType, parents, size, createdTime, webViewLink',
                supportsAllDrives=True
            ).execute()

        file = self._retry_operation(_api_call)
        
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

        def _api_call():
            return self.service.files().list(
                q=query,
                pageSize=100,
                fields="nextPageToken, files(id, name, mimeType, parents, webViewLink, createdTime, size)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()

        results = self._retry_operation(_api_call)
        files = results.get('files', [])
        
        # Store in cache
        cache_service.set_in_cache(cache_key, files)
        
        return files

    def get_file(self, file_id: str) -> Dict[str, Any]:
        self._check_auth()
        # ADICIONADO 'trashed' para lógica de reconciliação
        def _api_call():
            return self.service.files().get(
                fileId=file_id,
                fields='id, name, mimeType, parents, webViewLink, createdTime, size, trashed',
                supportsAllDrives=True
            ).execute()

        return self._retry_operation(_api_call)

    def update_file_metadata(self, file_id: str, new_name: str) -> Dict[str, Any]:
        """Atualiza metadados de um arquivo ou pasta (ex: renomear)."""
        self._check_auth()
        
        file_metadata = {'name': new_name}
        
        def _api_call():
            return self.service.files().update(
                fileId=file_id,
                body=file_metadata,
                fields='id, name, mimeType, webViewLink',
                supportsAllDrives=True
            ).execute()
        
        # Invalidate parents cache logic is tricky because we don't know the parent without fetching.
        # But rename only affects the item itself usually, or list of its parent.
        # We should probably fetch parent to invalidate.
        # For performance, we might skip or rely on TTL.
        # But for correctness in UI, we should invalidate.
        try:
             # Try to get parent from cache or fetch
             # Or just return, client will refresh?
             pass
        except:
             pass

        return self._retry_operation(_api_call)

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

        def _api_call():
            return self.service.permissions().create(
                fileId=file_id,
                body=permission,
                fields='id',
                supportsAllDrives=True
            ).execute()

        return self._retry_operation(_api_call)

    def list_permissions(self, file_id: str) -> List[Dict[str, Any]]:
        self._check_auth()

        def _api_call():
            return self.service.permissions().list(
                fileId=file_id,
                fields='permissions(id,role,type,emailAddress)',
                supportsAllDrives=True
            ).execute()

        result = self._retry_operation(_api_call)
        return result.get('permissions', [])

    def update_permission(self, file_id: str, permission_id: str, role: str) -> Dict[str, Any]:
        self._check_auth()

        def _api_call():
            return self.service.permissions().update(
                fileId=file_id,
                permissionId=permission_id,
                body={'role': role},
                fields='id,role,type,emailAddress',
                supportsAllDrives=True
            ).execute()

        return self._retry_operation(_api_call)

    def remove_permission(self, file_id: str, permission_id: str) -> None:
        self._check_auth()

        def _api_call():
            return self.service.permissions().delete(
                fileId=file_id,
                permissionId=permission_id,
                supportsAllDrives=True
            ).execute()

        self._retry_operation(_api_call)

    def move_file(self, file_id: str, destination_parent_id: str) -> Dict[str, Any]:
        self._check_auth()

        try:
            metadata = self.get_file(file_id)
            current_parents = metadata.get('parents', [])
            remove_parents = ','.join(current_parents) if current_parents else None
        except Exception:
            remove_parents = None

        def _api_call():
            return self.service.files().update(
                fileId=file_id,
                addParents=destination_parent_id,
                removeParents=remove_parents,
                fields='id, name, mimeType, parents, webViewLink',
                supportsAllDrives=True
            ).execute()

        # Invalidate caches for involved parents
        if remove_parents:
            for parent in remove_parents.split(','):
                cache_service.delete_key(f"drive:list_files:{parent}")

        cache_service.delete_key(f"drive:list_files:{destination_parent_id}")

        return self._retry_operation(_api_call)

    def is_descendant(self, folder_id: str, ancestor_id: str) -> bool:
        """
        Verifies if folder_id is a descendant of ancestor_id.
        Walks up the parent chain using cache for performance.
        Max depth: 10
        """
        if folder_id == ancestor_id:
            return True

        current_id = folder_id
        max_depth = 10

        for _ in range(max_depth):
            # Try cache first for parent
            cache_key = f"drive:parent:{current_id}"
            parent_id = cache_service.get_from_cache(cache_key)

            if not parent_id:
                try:
                    meta = self.get_file(current_id)
                    parents = meta.get('parents', [])
                    if not parents:
                        # Reached root or orphan
                        return False
                    parent_id = parents[0]
                    # Cache parent info for 1 hour
                    cache_service.set_in_cache(cache_key, parent_id, ttl=3600)
                except Exception as e:
                    print(f"Error checking lineage for {current_id}: {e}")
                    return False

            if parent_id == ancestor_id:
                return True

            current_id = parent_id

        return False

    def get_breadcrumbs(self, folder_id: str, root_id: str) -> List[Dict[str, str]]:
        """
        Returns a list of breadcrumbs from root_id to folder_id.
        [{id: '...', name: '...'}, ...]
        """
        breadcrumbs = []
        current_id = folder_id
        max_depth = 10

        for _ in range(max_depth):
            try:
                meta = self.get_file(current_id)
                breadcrumbs.insert(0, {"id": meta["id"], "name": meta["name"]})

                if current_id == root_id:
                    break

                parents = meta.get('parents', [])
                if not parents:
                    break
                current_id = parents[0]
            except Exception as e:
                print(f"Error building breadcrumbs: {e}")
                break

        return breadcrumbs
