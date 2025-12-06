from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Header, Query
from sqlalchemy.orm import Session
from database import SessionLocal
from services.google_drive_mock import GoogleDriveService
from services.google_drive_real import GoogleDriveRealService
from services.template_service import TemplateService
from services.permission_service import PermissionService
from services.hierarchy_service import HierarchyService
from cache import cache_service
import models
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from config import config
from datetime import datetime, timezone
import json

router = APIRouter()

# Dependency Injection based on Config
if config.USE_MOCK_DRIVE:
    print("Using MOCK Drive Service")
    drive_service = GoogleDriveService()
else:
    print("Using REAL Drive Service")
    drive_service = GoogleDriveRealService()


class DriveResponse(BaseModel):
    files: List[Dict[str, Any]]
    permission: str


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class CreateFolderRequest(BaseModel):
    name: str


@router.get("/drive/{entity_type}/{entity_id}", response_model=DriveResponse)
def get_entity_drive(
    entity_type: str,
    entity_id: str,
    include_deleted: bool = Query(default=False, description="Include soft-deleted items in the response"),
    db: Session = Depends(get_db),
    user_id: str | None = Header(default=None, alias="x-user-id"),
    user_role: str | None = Header(default=None, alias="x-user-role"),
):
    try:
        # 0. Validate Entity Type
        allowed_types = ["company", "lead", "deal"]
        # 'contact' commented out for now as per instructions
        if entity_type not in allowed_types:
            raise HTTPException(status_code=400, detail=f"Invalid entity_type. Allowed: {allowed_types}")

        # 1. Check/Ensure Folder Structure (Hierarchical)
        hierarchy_service = HierarchyService(db)
        entity_folder = None

        if entity_type == "company":
            entity_folder = hierarchy_service.ensure_company_structure(entity_id)
        elif entity_type == "lead":
            entity_folder = hierarchy_service.ensure_lead_structure(entity_id)
        elif entity_type == "deal":
            entity_folder = hierarchy_service.ensure_deal_structure(entity_id)

        if not entity_folder:
            raise HTTPException(status_code=500, detail="Failed to resolve/create folder structure")

        root_id = entity_folder.folder_id

        # 2. List contents of this folder
        items = drive_service.list_files(root_id)

        # 3. Filter out soft-deleted items unless include_deleted=True
        if not include_deleted:
            # Get IDs of soft-deleted files and folders from database
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
            
            # Filter items based on soft delete status
            items = [
                item for item in items
                if item.get("id") not in deleted_file_ids and item.get("id") not in deleted_folder_ids
            ]

        # 4. Determine permissions
        perm_service = PermissionService(db)

        if user_role:
            # Usa o papel vindo do app (ex: admin, analyst, new_business, client)
            permission = perm_service.get_drive_permission_from_app_role(
                user_role, entity_type
            )
        else:
            # Fallback para o comportamento antigo (mock) se nenhum papel for enviado
            permission = perm_service.mock_check_permission(
                user_id or "anonymous", entity_type
            )

        return {"files": items, "permission": permission}
    except HTTPException:
        # Re-raise HTTPExceptions without change
        raise
    except ValueError as ve:
        # Catch errors from HierarchyService (e.g. Lead not found in DB)
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/drive/{entity_type}/{entity_id}/folder")
def create_subfolder(
    entity_type: str,
    entity_id: str,
    request: CreateFolderRequest,
    db: Session = Depends(get_db),
    user_role: str | None = Header(default=None, alias="x-user-role"),
):
    allowed_types = ["company", "lead", "deal"]
    if entity_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Invalid entity_type. Allowed: {allowed_types}")

    # 1. Check permission
    perm_service = PermissionService(db)
    if user_role:
        permission = perm_service.get_drive_permission_from_app_role(
            user_role, entity_type
        )
    else:
        # Fallback: mantém compatível com o antigo comportamento (writer)
        permission = perm_service.mock_check_permission("anonymous", entity_type)

    if permission == "reader":
        raise HTTPException(
            status_code=403, detail="User does not have permission to create folders"
        )

    # 2. Get root folder
    # We use HierarchyService to ensure it exists if called (idempotent)
    hierarchy_service = HierarchyService(db)
    # We could call ensure_..._structure here again, but usually GET is called first.
    # To be safe, let's query the DB mapping directly.
    entity_folder = (
        db.query(models.DriveFolder)
        .filter(
            models.DriveFolder.entity_type == entity_type,
            models.DriveFolder.entity_id == entity_id,
        )
        .first()
    )

    if not entity_folder:
        raise HTTPException(
            status_code=404,
            detail="Entity root folder not found. Call list (GET) first to initialize structure.",
        )

    # 3. Create folder in Drive
    new_folder = drive_service.create_folder(
        request.name, parent_id=entity_folder.folder_id
    )
    return new_folder


@router.post("/drive/{entity_type}/{entity_id}/upload")
async def upload_file(
    entity_type: str,
    entity_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user_role: str | None = Header(default=None, alias="x-user-role"),
):
    allowed_types = ["company", "lead", "deal"]
    if entity_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Invalid entity_type. Allowed: {allowed_types}")

    # 1. Check permission
    perm_service = PermissionService(db)
    if user_role:
        permission = perm_service.get_drive_permission_from_app_role(
            user_role, entity_type
        )
    else:
        permission = perm_service.mock_check_permission("anonymous", entity_type)

    if permission == "reader":
        raise HTTPException(
            status_code=403, detail="User does not have permission to upload files"
        )

    # 2. Get root folder
    entity_folder = (
        db.query(models.DriveFolder)
        .filter(
            models.DriveFolder.entity_type == entity_type,
            models.DriveFolder.entity_id == entity_id,
        )
        .first()
    )

    if not entity_folder:
        raise HTTPException(
            status_code=404,
            detail="Entity root folder not found. Call list (GET) first to initialize structure.",
        )

    # 3. Read file content
    content = await file.read()

    # 4. Upload to Drive
    uploaded_file = drive_service.upload_file(
        file_content=content,
        name=file.filename,
        mime_type=file.content_type or "application/octet-stream",
        parent_id=entity_folder.folder_id,
    )

    # 5. Save metadata in local DB (Optional for MVP, but good practice)
    new_file_record = models.DriveFile(
        file_id=uploaded_file["id"],
        parent_folder_id=entity_folder.folder_id,
        name=uploaded_file["name"],
        mime_type=uploaded_file["mimeType"],
        size=uploaded_file["size"],
    )
    db.add(new_file_record)
    db.commit()

    return uploaded_file


@router.delete("/drive/{entity_type}/{entity_id}/files/{file_id}")
def soft_delete_file(
    entity_type: str,
    entity_id: str,
    file_id: str,
    reason: Optional[str] = Query(default=None, description="Reason for deleting the file"),
    db: Session = Depends(get_db),
    user_id: str | None = Header(default=None, alias="x-user-id"),
    user_role: str | None = Header(default=None, alias="x-user-role"),
):
    """
    Soft delete a file - marks it as deleted without removing from Google Drive.
    Requires write permission (writer or owner role).
    """
    allowed_types = ["company", "lead", "deal"]
    if entity_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Invalid entity_type. Allowed: {allowed_types}")

    # 1. Check permission - only writer/owner can delete
    perm_service = PermissionService(db)
    if user_role:
        permission = perm_service.get_drive_permission_from_app_role(user_role, entity_type)
    else:
        permission = perm_service.mock_check_permission(user_id or "anonymous", entity_type)

    if permission == "reader":
        raise HTTPException(
            status_code=403, detail="User does not have permission to delete files"
        )

    # 2. Verify entity folder exists (validates entity_type and entity_id mapping)
    entity_folder = (
        db.query(models.DriveFolder)
        .filter(
            models.DriveFolder.entity_type == entity_type,
            models.DriveFolder.entity_id == entity_id,
        )
        .first()
    )

    if not entity_folder:
        raise HTTPException(
            status_code=404,
            detail="Entity folder not found. The entity may not have been initialized.",
        )

    # 3. Find the file in database
    file_record = db.query(models.DriveFile).filter(models.DriveFile.file_id == file_id).first()

    if not file_record:
        raise HTTPException(status_code=404, detail="File not found in database")

    # 4. Check if already deleted
    if file_record.deleted_at:
        raise HTTPException(status_code=400, detail="File is already marked as deleted")

    # 5. Mark as deleted (soft delete)
    file_record.deleted_at = datetime.now(timezone.utc)
    file_record.deleted_by = user_id
    file_record.delete_reason = reason

    db.commit()

    # 6. Log to audit log (DriveChangeLog)
    audit_metadata = {
        "user_id": user_id,
        "user_role": user_role,
        "reason": reason
    }
    audit_entry = models.DriveChangeLog(
        channel_id="soft_delete",
        resource_id=file_id,
        resource_state="soft_delete",
        changed_resource_id=file_id,
        event_type="file_soft_delete",
        raw_headers=json.dumps(audit_metadata),
    )
    db.add(audit_entry)
    db.commit()

    # 7. Invalidate cache for the parent folder
    cache_service.invalidate_cache(f"drive:list_files:{file_record.parent_folder_id}*")

    return {
        "status": "deleted",
        "file_id": file_id,
        "deleted_at": file_record.deleted_at.isoformat(),
        "deleted_by": file_record.deleted_by,
    }


@router.delete("/drive/{entity_type}/{entity_id}/folders/{folder_id}")
def soft_delete_folder(
    entity_type: str,
    entity_id: str,
    folder_id: str,
    reason: Optional[str] = Query(default=None, description="Reason for deleting the folder"),
    db: Session = Depends(get_db),
    user_id: str | None = Header(default=None, alias="x-user-id"),
    user_role: str | None = Header(default=None, alias="x-user-role"),
):
    """
    Soft delete a folder - marks it as deleted without removing from Google Drive.
    Requires write permission (writer or owner role).
    """
    allowed_types = ["company", "lead", "deal"]
    if entity_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Invalid entity_type. Allowed: {allowed_types}")

    # 1. Check permission - only writer/owner can delete
    perm_service = PermissionService(db)
    if user_role:
        permission = perm_service.get_drive_permission_from_app_role(user_role, entity_type)
    else:
        permission = perm_service.mock_check_permission(user_id or "anonymous", entity_type)

    if permission == "reader":
        raise HTTPException(
            status_code=403, detail="User does not have permission to delete folders"
        )

    # 2. Verify entity folder exists (validates entity_type and entity_id mapping)
    entity_folder = (
        db.query(models.DriveFolder)
        .filter(
            models.DriveFolder.entity_type == entity_type,
            models.DriveFolder.entity_id == entity_id,
        )
        .first()
    )

    if not entity_folder:
        raise HTTPException(
            status_code=404,
            detail="Entity folder not found. The entity may not have been initialized.",
        )

    # 3. Prevent deleting the entity's root folder
    if folder_id == entity_folder.folder_id:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete the entity's root folder. Only subfolders can be deleted.",
        )

    # 4. Find the folder in database
    folder_record = db.query(models.DriveFolder).filter(models.DriveFolder.folder_id == folder_id).first()

    # Note: Subfolders might not be tracked in DriveFolder table, they could be in Drive only
    # For now, we'll return success if folder isn't tracked but exists in Drive
    if not folder_record:
        # Log the soft delete attempt even if folder isn't in our DB
        audit_metadata = {
            "user_id": user_id,
            "user_role": user_role,
            "reason": reason,
            "note": "Folder not tracked in database"
        }
        audit_entry = models.DriveChangeLog(
            channel_id="soft_delete",
            resource_id=folder_id,
            resource_state="soft_delete",
            changed_resource_id=folder_id,
            event_type="folder_soft_delete_untracked",
            raw_headers=json.dumps(audit_metadata),
        )
        db.add(audit_entry)
        db.commit()

        # Invalidate cache for the entity folder
        cache_service.invalidate_cache(f"drive:list_files:{entity_folder.folder_id}*")

        return {
            "status": "deleted",
            "folder_id": folder_id,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by": user_id,
            "note": "Folder was not tracked in database but soft delete was logged",
        }

    # 5. Check if already deleted
    if folder_record.deleted_at:
        raise HTTPException(status_code=400, detail="Folder is already marked as deleted")

    # 6. Mark as deleted (soft delete)
    folder_record.deleted_at = datetime.now(timezone.utc)
    folder_record.deleted_by = user_id
    folder_record.delete_reason = reason

    db.commit()

    # 7. Log to audit log (DriveChangeLog)
    audit_metadata = {
        "user_id": user_id,
        "user_role": user_role,
        "reason": reason
    }
    audit_entry = models.DriveChangeLog(
        channel_id="soft_delete",
        resource_id=folder_id,
        resource_state="soft_delete",
        changed_resource_id=folder_id,
        event_type="folder_soft_delete",
        raw_headers=json.dumps(audit_metadata),
    )
    db.add(audit_entry)
    db.commit()

    # 8. Invalidate cache for the parent folder
    cache_service.invalidate_cache(f"drive:list_files:{entity_folder.folder_id}*")

    return {
        "status": "deleted",
        "folder_id": folder_id,
        "deleted_at": folder_record.deleted_at.isoformat(),
        "deleted_by": folder_record.deleted_by,
    }

