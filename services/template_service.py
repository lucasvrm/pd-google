from sqlalchemy.orm import Session
# Use Any for type hinting to support both Mock and Real service which share same method signatures but different classes
from typing import Any
import models

class TemplateService:
    def __init__(self, db: Session, drive_service: Any):
        self.db = db
        self.drive_service = drive_service

    def apply_template(self, entity_type: str, root_folder_id: str):
        """
        Finds the active template for the entity_type and creates its folder structure
        inside the given root_folder_id.
        Supports nested folders via parent_id.
        
        This method is idempotent - calling it multiple times will reuse existing folders
        and not create duplicates.
        """
        template = self.db.query(models.DriveStructureTemplate).filter_by(
            entity_type=entity_type,
            active=True
        ).first()

        if not template:
            print(f"No active template found for {entity_type}")
            return

        # Build a local cache of existing folders per parent to minimize API calls
        # and ensure consistency within a single template application
        parent_children_cache = {}
        
        def get_cached_children(parent_id: str):
            """Get children of a parent folder, using local cache."""
            if parent_id not in parent_children_cache:
                try:
                    children = self.drive_service.list_files(parent_id)
                    # Normalize names for comparison (trim whitespace)
                    parent_children_cache[parent_id] = {
                        child['name'].strip(): child 
                        for child in children 
                        if child.get('mimeType') == 'application/vnd.google-apps.folder'
                    }
                except Exception as e:
                    print(f"Warning: Failed to list children of {parent_id}: {e}")
                    parent_children_cache[parent_id] = {}
            return parent_children_cache[parent_id]
        
        def find_or_create_folder(name: str, parent_id: str) -> dict:
            """
            Find existing folder by name in parent or create it.
            Uses local cache to ensure consistency within this template application.
            """
            normalized_name = name.strip()
            
            # Check local cache first
            children = get_cached_children(parent_id)
            
            if normalized_name in children:
                print(f"Reusing existing folder: {normalized_name} in {parent_id}")
                return children[normalized_name]
            
            # Not in cache - use get_or_create_folder which does its own check
            # This handles race conditions where another process might have created it
            print(f"Creating template folder: {normalized_name} in {parent_id}")
            created = self.drive_service.get_or_create_folder(
                name=normalized_name,
                parent_id=parent_id
            )
            
            # Add to local cache to avoid duplicate checks
            if created and 'id' in created:
                children[normalized_name] = created
            
            return created

        nodes_by_id = {node.id: node for node in template.nodes}
        # Map: DB_Node_ID -> Created_Drive_Folder_ID
        node_to_drive_id = {}

        # Organize by parent_id
        tree = {} # parent_id -> [list of nodes]
        for node in template.nodes:
            pid = node.parent_id
            if pid not in tree:
                tree[pid] = []
            tree[pid].append(node)

        # Helper to process level
        # None as key means root of the template (no parent node)
        queue = sorted(tree.get(None, []), key=lambda x: x.order)

        def create_nodes_recursive(current_nodes, parent_drive_id):
            for node in current_nodes:
                # Use the new find_or_create_folder with local caching
                created = find_or_create_folder(node.name, parent_drive_id)

                if created and 'id' in created:
                    node_to_drive_id[node.id] = created['id']

                    # Process children
                    children = tree.get(node.id, [])
                    if children:
                        # Sort children by order
                        children_sorted = sorted(children, key=lambda x: x.order)
                        create_nodes_recursive(children_sorted, created['id'])
                else:
                    print(f"Error: Failed to create/get folder {node.name}. Skipping children.")

        # Start with root nodes
        create_nodes_recursive(queue, root_folder_id)

# Helper for Background Tasks
def run_apply_template_background(entity_type: str, root_folder_id: str):
    """
    Standalone function to be run in background tasks.
    Creates its own DB session and Drive Service.
    """
    from database import SessionLocal
    from config import config
    from services.google_drive_mock import GoogleDriveService
    from services.google_drive_real import GoogleDriveRealService

    print(f"Starting background template application for {entity_type} in {root_folder_id}")

    db = SessionLocal()
    try:
        if config.USE_MOCK_DRIVE:
            drive_service = GoogleDriveService()
        else:
            drive_service = GoogleDriveRealService()

        ts = TemplateService(db, drive_service)
        ts.apply_template(entity_type, root_folder_id)
        print(f"Completed background template application for {entity_type}")
    except Exception as e:
        print(f"Error in background template application: {e}")
    finally:
        db.close()
