from sqlalchemy.orm import Session
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

    def get_or_create_companies_root(self) -> models.DriveFolder:
        """
        Ensures the root folder '/Companies' exists.
        """
        root_name = "Companies"
        # Check if we already mapped it
        mapped_root = self.db.query(models.DriveFolder).filter_by(
            entity_type="system_root",
            entity_id=COMPANIES_ROOT_UUID
        ).first()

        if mapped_root:
            return mapped_root

        if not config.DRIVE_ROOT_FOLDER_ID:
            raise ValueError("DRIVE_ROOT_FOLDER_ID not configured. Operations require a strict Shared Drive root.")

        print(f"Creating System Root: {root_name} in {config.DRIVE_ROOT_FOLDER_ID}")
        folder = self.drive_service.create_folder(name=root_name, parent_id=config.DRIVE_ROOT_FOLDER_ID)

        # CORREÇÃO AQUI: Passando folder_url
        new_mapping = models.DriveFolder(
            entity_type="system_root",
            entity_id=COMPANIES_ROOT_UUID,
            folder_id=folder["id"],
            folder_url=folder.get("webViewLink")
        )
        self.db.add(new_mapping)
        self.db.commit()
        self.db.refresh(new_mapping)
        return new_mapping

    def ensure_company_structure(self, company_id: str) -> models.DriveFolder:
        """
        Ensures '/Companies/[Company Name]' exists.
        """
        # 1. Check if already exists in mapping
        existing = self.db.query(models.DriveFolder).filter_by(
            entity_type="company",
            entity_id=company_id
        ).first()
        if existing:
            return existing

        # 2. Get Company Name from Supabase DB
        company = self.db.query(models.Company).filter_by(id=company_id).first()
        if not company:
            # Fallback if company not found in DB
            folder_name = f"Company {company_id}"
        else:
            folder_name = company.name or f"Company {company_id}"

        # 3. Get Parent (Companies Root)
        companies_root = self.get_or_create_companies_root()

        # 4. Create Folder
        print(f"Creating Company Folder: {folder_name}")
        folder = self.drive_service.create_folder(name=folder_name, parent_id=companies_root.folder_id)

        # 5. Save Mapping
        # CORREÇÃO AQUI: Passando folder_url
        new_mapping = models.DriveFolder(
            entity_type="company",
            entity_id=company_id,
            folder_id=folder["id"],
            folder_url=folder.get("webViewLink")
        )
        self.db.add(new_mapping)
        self.db.commit()
        self.db.refresh(new_mapping)

        # 6. Apply Template
        from services.template_service import TemplateService
        ts = TemplateService(self.db, self.drive_service)
        ts.apply_template("company", folder["id"])

        return new_mapping

    def ensure_deal_structure(self, deal_id: str) -> models.DriveFolder:
        """
        Ensures '/Companies/[Company]/02. Deals/Deal - [Name]' exists.
        """
        existing = self.db.query(models.DriveFolder).filter_by(
            entity_type="deal",
            entity_id=deal_id
        ).first()
        if existing:
            return existing

        # Get Deal info
        deal = self.db.query(models.Deal).filter_by(id=deal_id).first()
        if not deal:
            raise ValueError(f"Deal {deal_id} not found in database")

        if not deal.company_id:
            print(f"Warning: Deal {deal_id} has no company_id. Creating in root.")
            folder_name = f"Deal - {deal.title}"
            folder = self.drive_service.create_folder(name=folder_name) # Root
        else:
            # Ensure Company Structure
            company_folder = self.ensure_company_structure(deal.company_id)

            # Find '02. Deals' folder inside Company Folder
            children = self.drive_service.list_files(company_folder.folder_id)
            deals_folder_id = None
            for child in children:
                if "02. Deals" in child['name']:
                    deals_folder_id = child['id']
                    break

            if not deals_folder_id:
                print("Repairing: Creating '02. Deals' folder")
                f = self.drive_service.create_folder("02. Deals", parent_id=company_folder.folder_id)
                deals_folder_id = f['id']

            folder_name = f"Deal - {deal.title}"
            folder = self.drive_service.create_folder(name=folder_name, parent_id=deals_folder_id)

        # Map
        # CORREÇÃO AQUI: Passando folder_url
        new_mapping = models.DriveFolder(
            entity_type="deal",
            entity_id=deal_id,
            folder_id=folder["id"],
            folder_url=folder.get("webViewLink")
        )
        self.db.add(new_mapping)
        self.db.commit()

        # Apply Template
        from services.template_service import TemplateService
        ts = TemplateService(self.db, self.drive_service)
        ts.apply_template("deal", folder["id"])

        return new_mapping

    def ensure_lead_structure(self, lead_id: str) -> models.DriveFolder:
        """
        Ensures '/Companies/[Company]/01. Leads/Lead - [Name]' exists.
        """
        existing = self.db.query(models.DriveFolder).filter_by(
            entity_type="lead",
            entity_id=lead_id
        ).first()
        if existing:
            return existing

        lead = self.db.query(models.Lead).filter_by(id=lead_id).first()
        if not lead:
            raise ValueError(f"Lead {lead_id} not found")

        if not lead.company_id:
            print(f"Warning: Lead {lead_id} has no company_id.")
            folder_name = f"Lead - {lead.title}"
            folder = self.drive_service.create_folder(name=folder_name)
        else:
            company_folder = self.ensure_company_structure(lead.company_id)

            # Find '01. Leads'
            children = self.drive_service.list_files(company_folder.folder_id)
            leads_folder_id = None
            for child in children:
                if "01. Leads" in child['name']:
                    leads_folder_id = child['id']
                    break

            if not leads_folder_id:
                print("Repairing: Creating '01. Leads' folder")
                f = self.drive_service.create_folder("01. Leads", parent_id=company_folder.folder_id)
                leads_folder_id = f['id']

            folder_name = f"Lead - {lead.title}"
            folder = self.drive_service.create_folder(name=folder_name, parent_id=leads_folder_id)

        # CORREÇÃO AQUI: Passando folder_url
        new_mapping = models.DriveFolder(
            entity_type="lead",
            entity_id=lead_id,
            folder_id=folder["id"],
            folder_url=folder.get("webViewLink")
        )
        self.db.add(new_mapping)
        self.db.commit()

        from services.template_service import TemplateService
        ts = TemplateService(self.db, self.drive_service)
        ts.apply_template("lead", folder["id"])

        return new_mapping