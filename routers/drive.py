from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Header
from sqlalchemy.orm import Session
from database import SessionLocal
from services.google_drive_mock import GoogleDriveService
from services.google_drive_real import GoogleDriveRealService
from services.template_service import TemplateService
from services.permission_service import PermissionService
from services.hierarchy_service import HierarchyService
import models
from typing import List, Dict, Any
from pydantic import BaseModel
from config import config

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

        # 3. Determine permissions
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
