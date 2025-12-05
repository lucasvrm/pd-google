from sqlalchemy.orm import Session
from services.google_drive_mock import GoogleDriveService
import models

class TemplateService:
    def __init__(self, db: Session, drive_service: GoogleDriveService):
        self.db = db
        self.drive_service = drive_service

    def apply_template(self, entity_type: str, root_folder_id: str):
        """
        Finds the active template for the entity_type and creates its folder structure
        inside the given root_folder_id.
        """
        template = self.db.query(models.DriveStructureTemplate).filter_by(
            entity_type=entity_type,
            active=True
        ).first()

        if not template:
            print(f"No active template found for {entity_type}")
            return

        # Sort nodes by order
        nodes = sorted(template.nodes, key=lambda x: x.order)

        for node in nodes:
            # Create folder in Mock Drive
            print(f"Creating template folder: {node.name}")
            self.drive_service.create_folder(
                name=node.name,
                parent_id=root_folder_id
            )
