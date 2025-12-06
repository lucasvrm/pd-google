"""
Search service for advanced file and folder search functionality.
Provides filtering by entity, name, mime_type, dates, and respects soft delete.
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import List, Dict, Any, Optional
from datetime import datetime
import models


class SearchService:
    def __init__(self, db: Session):
        self.db = db

    def _format_datetime(self, dt: Optional[datetime]) -> Optional[str]:
        """Helper to format datetime to ISO string, handling None values."""
        return dt.isoformat() if dt else None

    def search_files_and_folders(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        q: Optional[str] = None,
        mime_type: Optional[str] = None,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
        include_deleted: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """
        Search for files and folders based on various filters.
        
        Args:
            entity_type: Filter by entity type (company, lead, deal)
            entity_id: Filter by specific entity ID
            q: Text search term for name (partial match)
            mime_type: Filter by MIME type
            created_from: Filter by creation date (from)
            created_to: Filter by creation date (to)
            include_deleted: Include soft-deleted items
            page: Page number (1-indexed)
            page_size: Number of results per page
            
        Returns:
            Dict containing:
                - items: List of matching files/folders
                - total: Total count of results
                - page: Current page
                - page_size: Items per page
                - total_pages: Total number of pages
        """
        # Validate pagination parameters
        page = max(1, page)
        page_size = max(1, min(100, page_size))  # Cap at 100 items per page
        
        # Build file query
        file_results = self._search_files(
            entity_type=entity_type,
            entity_id=entity_id,
            q=q,
            mime_type=mime_type,
            created_from=created_from,
            created_to=created_to,
            include_deleted=include_deleted,
        )
        
        # Build folder query
        # Only search folders if:
        # 1. No mime_type filter is specified (include all), OR
        # 2. Explicitly searching for the folder mime type
        folder_results = []
        if not mime_type or mime_type == "application/vnd.google-apps.folder":
            folder_results = self._search_folders(
                entity_type=entity_type,
                entity_id=entity_id,
                q=q,
                created_from=created_from,
                created_to=created_to,
                include_deleted=include_deleted,
            )
        
        # Combine results
        all_results = file_results + folder_results
        
        # Sort by created_at descending (newest first)
        # Handle None values by treating them as the oldest (empty string sorts before dates)
        all_results.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        
        # Apply pagination
        total = len(all_results)
        total_pages = (total + page_size - 1) // page_size  # Ceiling division
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_results = all_results[start_idx:end_idx]
        
        return {
            "items": paginated_results,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    def _search_files(
        self,
        entity_type: Optional[str],
        entity_id: Optional[str],
        q: Optional[str],
        mime_type: Optional[str],
        created_from: Optional[datetime],
        created_to: Optional[datetime],
        include_deleted: bool,
    ) -> List[Dict[str, Any]]:
        """Search files with filters."""
        query = self.db.query(models.DriveFile)
        
        # Filter by soft delete
        if not include_deleted:
            query = query.filter(models.DriveFile.deleted_at.is_(None))
        
        # Filter by name (partial match, case-insensitive)
        if q:
            query = query.filter(models.DriveFile.name.ilike(f"%{q}%"))
        
        # Filter by mime_type
        if mime_type:
            query = query.filter(models.DriveFile.mime_type == mime_type)
        
        # Filter by creation date range
        if created_from:
            query = query.filter(models.DriveFile.created_at >= created_from)
        if created_to:
            query = query.filter(models.DriveFile.created_at <= created_to)
        
        files = query.all()
        
        # Filter by entity if specified
        if entity_type or entity_id:
            files = self._filter_files_by_entity(files, entity_type, entity_id)
        
        # Convert to dict representation
        results = []
        for file in files:
            results.append({
                "id": file.file_id,
                "name": file.name,
                "mimeType": file.mime_type,
                "size": file.size,
                "parent_folder_id": file.parent_folder_id,
                "created_at": self._format_datetime(file.created_at),
                "deleted_at": self._format_datetime(file.deleted_at),
                "type": "file",
            })
        
        return results

    def _search_folders(
        self,
        entity_type: Optional[str],
        entity_id: Optional[str],
        q: Optional[str],
        created_from: Optional[datetime],
        created_to: Optional[datetime],
        include_deleted: bool,
    ) -> List[Dict[str, Any]]:
        """Search folders with filters."""
        query = self.db.query(models.DriveFolder)
        
        # Filter by soft delete
        if not include_deleted:
            query = query.filter(models.DriveFolder.deleted_at.is_(None))
        
        # Filter by entity type
        if entity_type:
            query = query.filter(models.DriveFolder.entity_type == entity_type)
        
        # Filter by entity ID
        if entity_id:
            query = query.filter(models.DriveFolder.entity_id == entity_id)
        
        # Filter by creation date range
        if created_from:
            query = query.filter(models.DriveFolder.created_at >= created_from)
        if created_to:
            query = query.filter(models.DriveFolder.created_at <= created_to)
        
        folders = query.all()
        
        # For folders, we need to fetch the name from Drive or use entity info
        # Since DriveFolder doesn't store names, we'll need to get them from the entity
        results = []
        for folder in folders:
            folder_name = self._get_folder_name(folder)
            
            # Apply name filter if specified
            if q and q.lower() not in folder_name.lower():
                continue
            
            results.append({
                "id": folder.folder_id,
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
                "entity_type": folder.entity_type,
                "entity_id": folder.entity_id,
                "created_at": self._format_datetime(folder.created_at),
                "deleted_at": self._format_datetime(folder.deleted_at),
                "type": "folder",
            })
        
        return results

    def _filter_files_by_entity(
        self, 
        files: List[models.DriveFile], 
        entity_type: Optional[str], 
        entity_id: Optional[str]
    ) -> List[models.DriveFile]:
        """Filter files by entity by checking their parent folder mapping."""
        if not (entity_type or entity_id):
            return files
        
        # Get all folders matching the entity criteria
        folder_query = self.db.query(models.DriveFolder)
        if entity_type:
            folder_query = folder_query.filter(models.DriveFolder.entity_type == entity_type)
        if entity_id:
            folder_query = folder_query.filter(models.DriveFolder.entity_id == entity_id)
        
        entity_folders = folder_query.all()
        entity_folder_ids = {folder.folder_id for folder in entity_folders}
        
        # Filter files that belong to these folders
        filtered_files = [
            file for file in files 
            if file.parent_folder_id in entity_folder_ids
        ]
        
        return filtered_files

    def _get_folder_name(self, folder: models.DriveFolder) -> str:
        """Get a human-readable name for a folder based on its entity."""
        # Try to get the entity name from the database
        if folder.entity_type == "company":
            company = self.db.query(models.Company).filter(
                models.Company.id == folder.entity_id
            ).first()
            if company:
                return company.fantasy_name or company.name or f"Company {folder.entity_id}"
        elif folder.entity_type == "lead":
            lead = self.db.query(models.Lead).filter(
                models.Lead.id == folder.entity_id
            ).first()
            if lead:
                return f"Lead - {lead.title}"
        elif folder.entity_type == "deal":
            deal = self.db.query(models.Deal).filter(
                models.Deal.id == folder.entity_id
            ).first()
            if deal:
                return f"Deal - {deal.title}"
        
        # Fallback to entity type and ID
        return f"{folder.entity_type.capitalize()} {folder.entity_id}"
