from sqlalchemy.orm import Session
import models

class PermissionService:
    def __init__(self, db: Session):
        self.db = db

    def get_permission(self, user_role: str, entity_type: str) -> str:
        """
        Determines the permission level (owner, writer, reader) based on the user's role.
        For MVP, we use hardcoded rules.
        """
        if user_role == 'admin':
            return 'owner'
        elif user_role == 'manager':
            return 'writer'
        else:
            return 'reader'

    def mock_check_permission(self, user_id: str, entity_type: str) -> str:
        """
        Retrieves the user's role and returns the Drive permission.
        """
        # In a real app, we'd query UserRole. For now, default to 'manager' (writer)
        return self.get_permission('manager', entity_type)
