from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional, Any
import models
from services.google_drive_mock import GoogleDriveService
from services.google_drive_real import GoogleDriveRealService
from config import config
import uuid

# Factory for Drive Service
def get_drive_service():
    if config.USE_MOCK_DRIVE:
        return GoogleDriveService()
    else:
        return GoogleDriveRealService()

# Constant UUID for the system root folder to satisfy database constraints
# We use a deterministic UUID so it remains consistent across restarts/deploys
COMPANIES_ROOT_UUID = str(uuid.UUID('00000000-0000-0000-0000-000000000001'))

class HierarchyService:
    def __init__(self, db: Session):
        self.db = db
        self.drive_service = get_drive_service()

    def _validate_mapping(self, mapping: models.DriveFolder) -> bool:
        """
        Checks if the mapped folder actually exists in Drive and is not trashed.
        """
        try:
            # get_file should return dict or raise Exception if 404
            f = self.drive_service.get_file(mapping.folder_id)
            if f.get('trashed'):
                print(f"Mapping {mapping.entity_type}/{mapping.entity_id} points to TRASHED folder.")
                return False
            return True
        except Exception as e:
            print(f"Mapping {mapping.entity_type}/{mapping.entity_id} is INVALID (Ghost): {e}")
            return False

    def _find_existing_folder(self, parent_id: str, folder_name: str) -> Optional[dict]:
        """
        Helper method to check if a folder with the given name exists in the parent.
        Returns the folder metadata if found, None otherwise.
        """
        try:
            children = self.drive_service.list_files(parent_id)
            for file in children:
                if file.get('name') == folder_name and file.get('mimeType') == 'application/vnd.google-apps.folder':
                    print(f"Found existing folder '{folder_name}' in parent {parent_id}: {file['id']}")
                    return file
        except Exception as e:
            print(f"Warning: Could not list files in parent folder {parent_id}: {e}")
        return None

    def _handle_mapping_race_condition(self, entity_type: str, entity_id: str, new_mapping: models.DriveFolder) -> models.DriveFolder:
        """
        Helper method to handle IntegrityError when saving a mapping.
        Returns the existing mapping on race condition, or raises if unexpected.
        """
        try:
            self.db.add(new_mapping)
            self.db.commit()
            self.db.refresh(new_mapping)
            return new_mapping
        except IntegrityError:
            # Race condition: another process created the mapping
            print(f"Race condition detected: mapping already exists for {entity_type} {entity_id}")
            self.db.rollback()
            # Query for the existing record
            existing_mapping = self.db.query(models.DriveFolder).filter_by(
                entity_type=entity_type,
                entity_id=entity_id
            ).first()
            if existing_mapping:
                return existing_mapping
            else:
                # Unexpected case, re-raise
                raise

    def _get_or_create_structural_folder(self, name: str, parent_id: str) -> str:
        """
        Helper method to get or create structural folders like '01. Leads' or '02. Deals'.
        Returns the folder ID.
        """
        existing_folder = self._find_existing_folder(parent_id, name)
        if existing_folder:
            return existing_folder['id']
        else:
            folder = self.drive_service.create_folder(name, parent_id=parent_id)
            return folder['id']

    def get_or_create_companies_root(self) -> models.DriveFolder:
        """
        Ensures the root folder '/Companies' exists.
        Checks DB first, then Drive to avoid duplicates (repair scenario).
        """
        root_name = "Companies"
        
        # 1. Check if we already mapped it in DB
        mapped_root = self.db.query(models.DriveFolder).filter_by(
            entity_type="system_root",
            entity_id=COMPANIES_ROOT_UUID
        ).first()

        if mapped_root:
            if self._validate_mapping(mapped_root):
                return mapped_root
            else:
                self.db.delete(mapped_root)
                self.db.commit()

        if not config.DRIVE_ROOT_FOLDER_ID:
            raise ValueError("DRIVE_ROOT_FOLDER_ID not configured. Operations require a strict Shared Drive root.")

        # 2. Check if it exists in Drive (Prevent Duplicates)
        print(f"Checking for existing '{root_name}' in Drive root...")
        
        # List children of the root folder to find if 'Companies' already exists
        children = self.drive_service.list_files(config.DRIVE_ROOT_FOLDER_ID)
        
        existing_folder = None
        for file in children:
            if file.get('name') == root_name and file.get('mimeType') == 'application/vnd.google-apps.folder':
                existing_folder = file
                break
        
        if existing_folder:
            print(f"Found existing System Root in Drive: {existing_folder['id']}")
            folder_id = existing_folder['id']
            folder_url = existing_folder.get('webViewLink')
        else:
            # 3. Create only if not found
            print(f"Creating System Root: {root_name} in {config.DRIVE_ROOT_FOLDER_ID}")
            folder = self.drive_service.create_folder(name=root_name, parent_id=config.DRIVE_ROOT_FOLDER_ID)
            folder_id = folder['id']
            folder_url = folder.get('webViewLink')

        # 4. Save Mapping to DB (Repair or New)
        new_mapping = models.DriveFolder(
            entity_type="system_root",
            entity_id=COMPANIES_ROOT_UUID,
            folder_id=folder_id,
            folder_url=folder_url
        )
        self.db.add(new_mapping)
        self.db.commit()
        self.db.refresh(new_mapping)
        
        return new_mapping

    def ensure_company_structure(self, company_id: str, background_tasks: Optional[Any] = None) -> models.DriveFolder:
        """
        Ensures '/Companies/[Company Name]' exists.
        """
        # 1. Check if already exists in mapping
        existing = self.db.query(models.DriveFolder).filter_by(
            entity_type="company",
            entity_id=company_id
        ).first()

        if existing:
            if self._validate_mapping(existing):
                return existing
            else:
                self.db.delete(existing)
                self.db.commit()

        # 2. Get Company Name from Supabase DB
        company = self.db.query(models.Company).filter_by(id=company_id).first()
        if not company:
            # Fallback if company not found in DB
            folder_name = f"Company {company_id}"
        else:
            folder_name = company.name or f"Company {company_id}"

        # 3. Get Parent (Companies Root)
        companies_root = self.get_or_create_companies_root()

        # 4. Check if folder already exists in Drive before creating
        print(f"Checking for existing Company Folder: {folder_name}")
        existing_folder = self._find_existing_folder(companies_root.folder_id, folder_name)

        # 5. Create Folder only if it doesn't exist
        if existing_folder:
            folder = existing_folder
        else:
            print(f"Creating Company Folder: {folder_name}")
            folder = self.drive_service.create_folder(name=folder_name, parent_id=companies_root.folder_id)

        # 6. Save Mapping with race condition handling
        new_mapping = models.DriveFolder(
            entity_type="company",
            entity_id=company_id,
            folder_id=folder["id"],
            folder_url=folder.get("webViewLink")
        )
        
        result = self._handle_mapping_race_condition("company", company_id, new_mapping)

        # 7. Apply Template (only if we just created the mapping)
        if result == new_mapping:
            from services.template_service import TemplateService, run_apply_template_background

            if background_tasks:
                print(f"Queueing background template for company {company_id}")
                background_tasks.add_task(run_apply_template_background, "company", folder["id"])
            else:
                ts = TemplateService(self.db, self.drive_service)
                ts.apply_template("company", folder["id"])

        return result

    def ensure_deal_structure(self, deal_id: str, background_tasks: Optional[Any] = None) -> models.DriveFolder:
        """
        Ensures '/Companies/[Company]/02. Deals/Deal - [Name]' exists.
        """
        existing = self.db.query(models.DriveFolder).filter_by(
            entity_type="deal",
            entity_id=deal_id
        ).first()

        if existing:
            if self._validate_mapping(existing):
                return existing
            else:
                self.db.delete(existing)
                self.db.commit()

        # Get Deal info
        deal = self.db.query(models.Deal).filter_by(id=deal_id).first()
        if not deal:
            raise ValueError(f"Deal {deal_id} not found in database")

        if not deal.company_id:
            print(f"Warning: Deal {deal_id} has no company_id. Creating in root.")
            deal_name = getattr(deal, 'client_name', getattr(deal, 'title', 'Unknown'))
            folder_name = f"Deal - {deal_name}"
            folder = self.drive_service.create_folder(name=folder_name) # Root
        else:
            # Ensure Company Structure
            company_folder = self.ensure_company_structure(deal.company_id, background_tasks=background_tasks)

            # Get or create '02. Deals' folder
            deals_folder_id = self._get_or_create_structural_folder("02. Deals", company_folder.folder_id)

            # Check if the Deal folder already exists
            deal_name = getattr(deal, 'client_name', getattr(deal, 'title', 'Unknown'))
            folder_name = f"Deal - {deal_name}"
            
            print(f"Checking for existing Deal Folder: {folder_name}")
            existing_deal_folder = self._find_existing_folder(deals_folder_id, folder_name)

            # Create Deal folder only if it doesn't exist
            if existing_deal_folder:
                folder = existing_deal_folder
            else:
                folder = self.drive_service.create_folder(name=folder_name, parent_id=deals_folder_id)

        # Map with race condition handling
        new_mapping = models.DriveFolder(
            entity_type="deal",
            entity_id=deal_id,
            folder_id=folder["id"],
            folder_url=folder.get("webViewLink")
        )
        
        result = self._handle_mapping_race_condition("deal", deal_id, new_mapping)

        # Apply Template (only if we just created the mapping)
        if result == new_mapping:
            from services.template_service import TemplateService, run_apply_template_background

            if background_tasks:
                print(f"Queueing background template for deal {deal_id}")
                background_tasks.add_task(run_apply_template_background, "deal", folder["id"])
            else:
                ts = TemplateService(self.db, self.drive_service)
                ts.apply_template("deal", folder["id"])

        return result

    def ensure_lead_structure(self, lead_id: str, background_tasks: Optional[Any] = None) -> models.DriveFolder:
        """
        Ensures '/Companies/[Company]/01. Leads/Lead - [Name]' exists.
        """
        existing = self.db.query(models.DriveFolder).filter_by(
            entity_type="lead",
            entity_id=lead_id
        ).first()

        if existing:
            if self._validate_mapping(existing):
                return existing
            else:
                self.db.delete(existing)
                self.db.commit()

        lead = self.db.query(models.Lead).filter_by(id=lead_id).first()
        if not lead:
            raise ValueError(f"Lead {lead_id} not found")

        # Determinar nome seguro para o Lead
        lead_name = getattr(lead, 'legal_name', getattr(lead, 'name', 'Unknown'))

        if not lead.company_id:
            print(f"Warning: Lead {lead_id} has no company_id.")
            folder_name = f"Lead - {lead_name}"
            folder = self.drive_service.create_folder(name=folder_name)
        else:
            company_folder = self.ensure_company_structure(lead.company_id, background_tasks=background_tasks)

            # Get or create '01. Leads' folder
            leads_folder_id = self._get_or_create_structural_folder("01. Leads", company_folder.folder_id)

            # Check if the Lead folder already exists
            folder_name = f"Lead - {lead_name}"
            
            print(f"Checking for existing Lead Folder: {folder_name}")
            existing_lead_folder = self._find_existing_folder(leads_folder_id, folder_name)

            # Create Lead folder only if it doesn't exist
            if existing_lead_folder:
                folder = existing_lead_folder
            else:
                folder = self.drive_service.create_folder(name=folder_name, parent_id=leads_folder_id)

        # Map with race condition handling
        new_mapping = models.DriveFolder(
            entity_type="lead",
            entity_id=lead_id,
            folder_id=folder["id"],
            folder_url=folder.get("webViewLink")
        )
        
        result = self._handle_mapping_race_condition("lead", lead_id, new_mapping)

        # Apply Template (only if we just created the mapping)
        if result == new_mapping:
            from services.template_service import TemplateService, run_apply_template_background

            if background_tasks:
                print(f"Queueing background template for lead {lead_id}")
                background_tasks.add_task(run_apply_template_background, "lead", folder["id"])
            else:
                ts = TemplateService(self.db, self.drive_service)
                ts.apply_template("lead", folder["id"])

        return result

    def sync_folder_name(self, entity_type: str, entity_id: str) -> None:
        """
        Verifies if the entity name in DB matches the folder name in Drive.
        If different, renames the folder in Drive.
        Should be called by the application whenever an entity is updated.
        """
        # 1. Fetch mapped folder
        mapping = self.db.query(models.DriveFolder).filter_by(
            entity_type=entity_type, 
            entity_id=entity_id
        ).first()
        
        if not mapping:
            return # Nothing to do if no folder exists
            
        # 2. Fetch updated entity name from DB
        entity_name = None
        
        if entity_type == "company":
            ent = self.db.query(models.Company).filter_by(id=entity_id).first()
            if ent: entity_name = ent.name
            
        elif entity_type == "deal":
            ent = self.db.query(models.Deal).filter_by(id=entity_id).first()
            # CORREÇÃO: Usa client_name se disponível, senão tenta name ou title
            if ent: 
                raw_name = getattr(ent, 'client_name', getattr(ent, 'name', getattr(ent, 'title', 'Deal')))
                entity_name = f"Deal - {raw_name}"
                
        elif entity_type == "lead":
            ent = self.db.query(models.Lead).filter_by(id=entity_id).first()
            # CORREÇÃO: Usa legal_name se disponível, senão tenta name ou title
            if ent: 
                raw_name = getattr(ent, 'legal_name', getattr(ent, 'name', getattr(ent, 'title', 'Lead')))
                entity_name = f"Lead - {raw_name}"
            
        if not entity_name:
            return

        # 3. Fetch real name from Google Drive
        try:
            drive_file = self.drive_service.get_file(mapping.folder_id)
            current_drive_name = drive_file.get('name')
            
            # 4. Compare and Update if needed
            if current_drive_name != entity_name:
                print(f"Renaming folder {mapping.folder_id}: '{current_drive_name}' -> '{entity_name}'")
                self.drive_service.update_file_metadata(mapping.folder_id, entity_name)
        except Exception as e:
            print(f"Error syncing folder name: {e}")

    def repair_structure(self, entity_type: str, entity_id: str) -> bool:
        """
        Forces the re-application of the folder template for a given entity.
        Useful for fixing missing folders or partial creations.
        """
        # 1. Fetch or create the main folder mapping
        # If it doesn't exist, ensure_..._structure will create it AND call apply_template
        # But if it exists, it returns early. So we need to handle the 'exists' case here by manually calling apply_template.

        mapping = None
        try:
            if entity_type == "company":
                mapping = self.ensure_company_structure(entity_id)
            elif entity_type == "lead":
                mapping = self.ensure_lead_structure(entity_id)
            elif entity_type == "deal":
                mapping = self.ensure_deal_structure(entity_id)
            else:
                raise ValueError(f"Unknown entity type: {entity_type}")
        except Exception as e:
            print(f"Repair: Error resolving root folder: {e}")
            return False

        if not mapping or not mapping.folder_id:
            return False

        print(f"Repairing structure for {entity_type} {entity_id} (Folder: {mapping.folder_id})")
        from services.template_service import TemplateService
        ts = TemplateService(self.db, self.drive_service)
        ts.apply_template(entity_type, mapping.folder_id)

        return True
