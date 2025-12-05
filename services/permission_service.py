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
        if user_role == "admin":
            return "owner"
        elif user_role == "manager":
            return "writer"
        else:
            return "reader"

    def mock_check_permission(self, user_id: str, entity_type: str) -> str:
        """
        Retrieves the user's role and returns the Drive permission.
        For now, defaults to 'manager' (writer) to keep backwards compatibility.
        """
        # In a real app, we'd query UserRole. For now, default to 'manager' (writer)
        return self.get_permission("manager", entity_type)

    # ------------------------------------------------------------
    # NOVO: mapeia papel do app (admin/analyst/new_business/client)
    # diretamente para a permissão de Drive (owner/writer/reader).
    # ------------------------------------------------------------
    def get_drive_permission_from_app_role(
        self, app_role: str, entity_type: str
    ) -> str:
        """
        Map roles from the main app (admin, analyst, new_business, client, etc.)
        into Drive permissions (owner, writer, reader).
        """
        if not app_role:
            return self.get_permission("manager", entity_type)

        role = app_role.strip().lower()

        # Normaliza algumas variações
        if role in ("admin", "superadmin", "super_admin"):
            return "owner"

        if role in ("manager", "analyst", "new_business", "newbusiness"):
            return "writer"

        if role in ("client", "customer"):
            return "reader"

        # Fallback: princípio de menor privilégio
        return "reader"
