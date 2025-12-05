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
        """
        template = self.db.query(models.DriveStructureTemplate).filter_by(
            entity_type=entity_type,
            active=True
        ).first()

        if not template:
            print(f"No active template found for {entity_type}")
            return

        # Sort nodes by parent dependency (parents must be created before children)
        # Simple sorting by ID or order might work if inserted in order, but topological sort is safer.
        # Given our seed strategy (parents created first), sorting by ID usually works,
        # but let's be robust: sort by 'level' or ensure we process parents first.
        # Since we don't have 'level', we can loop.

        nodes = sorted(template.nodes, key=lambda x: (x.parent_id if x.parent_id else 0, x.order))

        # Better approach:
        # 1. Get all nodes.
        # 2. Process nodes with parent_id=None (Root level relative to entity).
        # 3. Process children of created nodes recursively or iteratively.

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

        # We need to map 'None' parent_id (DB) to 'root_folder_id' (Drive Argument)
        # But 'parent_id' in create_folder logic:
        # If node has no parent_id (None), it goes into root_folder_id.
        # If node has parent_id (X), it goes into node_to_drive_id[X].

        def create_nodes_recursive(current_nodes, parent_drive_id):
            for node in current_nodes:
                print(f"Creating template folder: {node.name} inside {parent_drive_id}")
                created = self.drive_service.create_folder(
                    name=node.name,
                    parent_id=parent_drive_id
                )
                node_to_drive_id[node.id] = created['id']

                # Process children
                children = tree.get(node.id, [])
                if children:
                    # Sort children by order
                    children_sorted = sorted(children, key=lambda x: x.order)
                    create_nodes_recursive(children_sorted, created['id'])

        # Start with root nodes
        create_nodes_recursive(queue, root_folder_id)
