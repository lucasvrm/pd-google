from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
from services.google_drive_mock import GoogleDriveService
from services.google_drive_real import GoogleDriveRealService
from services.template_service import TemplateService
from services.permission_service import PermissionService
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
def get_entity_drive(entity_type: str, entity_id: str, db: Session = Depends(get_db)):
    try:
        # 1. Check if we have a root folder mapping for this entity
        entity_folder = db.query(models.DriveFolder).filter(
            models.DriveFolder.entity_type == entity_type,
        models.DriveFolder.entity_id == entity_id
    ).first()

        if not entity_folder:
            # If not, create a root folder for this entity in the Mock Drive
            # For simplicity, we create it under 'root'
            folder_name = f"{entity_type}_{entity_id}"
            drive_folder = drive_service.create_folder(folder_name)

            # Save mapping
            new_mapping = models.DriveFolder(
                entity_id=entity_id,
                entity_type=entity_type,
                folder_id=drive_folder["id"]
            )
            db.add(new_mapping)
            db.commit()
            db.refresh(new_mapping)

            # Apply Template Logic
            print(f"Applying template for {entity_type}...")
            template_service = TemplateService(db, drive_service)
            template_service.apply_template(entity_type, drive_folder["id"])

            root_id = new_mapping.folder_id
        else:
            root_id = entity_folder.folder_id

        # 2. List contents of this folder
        items = drive_service.list_files(root_id)

        # 3. Determine permissions
        perm_service = PermissionService(db)
        permission = perm_service.mock_check_permission("user_123", entity_type) # Mock user ID

        return {"files": items, "permission": permission}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/drive/{entity_type}/{entity_id}/folder")
def create_subfolder(entity_type: str, entity_id: str, request: CreateFolderRequest, db: Session = Depends(get_db)):
    # 1. Get root folder
    entity_folder = db.query(models.DriveFolder).filter(
        models.DriveFolder.entity_type == entity_type,
        models.DriveFolder.entity_id == entity_id
    ).first()

    if not entity_folder:
        raise HTTPException(status_code=404, detail="Entity root folder not found. Call list first.")

    # 2. Create folder in Mock Drive
    new_folder = drive_service.create_folder(request.name, parent_id=entity_folder.folder_id)
    return new_folder

@router.post("/drive/{entity_type}/{entity_id}/upload")
async def upload_file(entity_type: str, entity_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    # 1. Get root folder
    entity_folder = db.query(models.DriveFolder).filter(
        models.DriveFolder.entity_type == entity_type,
        models.DriveFolder.entity_id == entity_id
    ).first()

    if not entity_folder:
        raise HTTPException(status_code=404, detail="Entity root folder not found. Call list first.")

    # 2. Read file content
    content = await file.read()

    # 3. Upload to Mock Drive
    uploaded_file = drive_service.upload_file(
        file_content=content,
        name=file.filename,
        mime_type=file.content_type or "application/octet-stream",
        parent_id=entity_folder.folder_id
    )

    # 4. Save metadata in local DB (Optional for MVP, but good practice)
    new_file_record = models.DriveFile(
        file_id=uploaded_file["id"],
        parent_folder_id=entity_folder.folder_id,
        name=uploaded_file["name"],
        mime_type=uploaded_file["mimeType"],
        size=uploaded_file["size"]
    )
    db.add(new_file_record)
    db.commit()

    return uploaded_file
