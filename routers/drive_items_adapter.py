"""
Drive Items Adapter Router

This adapter provides a frontend-compatible endpoint at /api/drive/items
that wraps the existing /drive/{entity_type}/{entity_id} functionality.

Purpose: Eliminate CORS/404 errors in the frontend by providing the exact
contract expected by the frontend without requiring frontend changes.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
from services.google_drive_mock import GoogleDriveService
from services.google_drive_real import GoogleDriveRealService
from services.hierarchy_service import HierarchyService
from auth.dependencies import get_current_user
from auth.jwt import UserContext
import models
from typing import List, Optional, Literal
from pydantic import BaseModel
from config import config
from datetime import datetime
import traceback

router = APIRouter()

# Dependency Injection based on Config
if config.USE_MOCK_DRIVE:
    drive_service = GoogleDriveService()
else:
    drive_service = GoogleDriveRealService()

# --- Pydantic Schemas ---

class DriveItemResponse(BaseModel):
    """Frontend-expected format for each drive item"""
    id: str
    name: str
    url: Optional[str] = None
    createdAt: Optional[str] = None
    mimeType: str
    type: Literal["file", "folder"]
    size: Optional[int] = None

class DriveItemsResponse(BaseModel):
    """Frontend-expected response format"""
    items: List[DriveItemResponse]
    total: int
    root_url: Optional[str] = None


@router.get("/items", response_model=DriveItemsResponse)
def get_drive_items(
    entityType: str = Query(..., description="Entity type: company, lead, or deal"),
    entityId: str = Query(..., description="UUID of the entity"),
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(default=50, ge=1, le=200, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
):
    """
    Adapter endpoint for frontend compatibility.
    
    This endpoint wraps the existing /drive/{entity_type}/{entity_id} logic
    but returns data in the format expected by the frontend: { items, total }
    
    Query Parameters:
    - entityType: Entity type (company, lead, deal)
    - entityId: UUID of the entity
    - page: Page number (default: 1)
    - limit: Items per page (default: 50)
    
    Returns:
    - items: Paginated list of drive items
    - total: Total number of items before pagination
    """
    try:
        # 0. Validate Entity Type
        allowed_types = ["company", "lead", "deal"]
        if entityType not in allowed_types:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid entityType. Allowed: {allowed_types}"
            )

        # 1. Ensure Folder Structure (using the same logic as /drive/{entity_type}/{entity_id})
        hierarchy_service = HierarchyService(db)
        entity_folder = None

        if entityType == "company":
            entity_folder = hierarchy_service.ensure_company_structure(entityId)
        elif entityType == "lead":
            entity_folder = hierarchy_service.ensure_lead_structure(entityId)
        elif entityType == "deal":
            entity_folder = hierarchy_service.ensure_deal_structure(entityId)

        if not entity_folder:
            raise HTTPException(
                status_code=500, 
                detail="Failed to resolve/create folder structure"
            )

        root_id = entity_folder.folder_id

        # 2. List all files from the folder (same as existing endpoint)
        items = drive_service.list_files(root_id)

        # 3. Filter out soft-deleted items (same logic as existing endpoint)
        deleted_file_ids = {
            f.file_id for f in db.query(models.DriveFile)
            .filter(models.DriveFile.deleted_at.isnot(None))
            .all()
        }
        deleted_folder_ids = {
            f.folder_id for f in db.query(models.DriveFolder)
            .filter(models.DriveFolder.deleted_at.isnot(None))
            .all()
        }
        
        items = [
            item for item in items
            if item.get("id") not in deleted_file_ids and item.get("id") not in deleted_folder_ids
        ]

        # 4. Transform to frontend-expected format
        drive_items = []
        for item in items:
            # Determine type
            mime = item.get("mimeType", "")
            item_type = "folder" if mime == "application/vnd.google-apps.folder" else "file"
            
            # Format createdAt to ISO string if it exists
            created_at = None
            if item.get("createdTime"):
                created_time = item["createdTime"]
                if isinstance(created_time, datetime):
                    created_at = created_time.isoformat()
                else:
                    created_at = created_time

            drive_items.append(DriveItemResponse(
                id=item["id"],
                name=item["name"],
                url=item.get("webViewLink"),
                createdAt=created_at,
                mimeType=mime,
                type=item_type,
                size=item.get("size")
            ))

        # 5. Pagination (in-memory)
        total = len(drive_items)
        start = (page - 1) * limit
        end = start + limit
        paginated_items = drive_items[start:end]

        return DriveItemsResponse(
            items=paginated_items,
            total=total,
            root_url=entity_folder.folder_url
        )

    except HTTPException:
        # Re-raise HTTPExceptions without change
        raise
    except ValueError as ve:
        # Catch errors from HierarchyService (e.g. entity not found)
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
