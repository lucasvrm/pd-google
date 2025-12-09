from sqlalchemy.orm import Session
from typing import Optional
from enum import Enum
import models


class Role(str, Enum):
    """Enum for user roles"""
    ADMIN = "admin"
    SUPERADMIN = "superadmin"
    MANAGER = "manager"
    ANALYST = "analyst"
    NEW_BUSINESS = "new_business"
    CLIENT = "client"
    CUSTOMER = "customer"
    DEFAULT = "default"


class GmailPermissions:
    """Structure to hold Gmail permissions for a role"""
    def __init__(self, gmail_read_metadata: bool = False, gmail_read_body: bool = False):
        self.gmail_read_metadata = gmail_read_metadata
        self.gmail_read_body = gmail_read_body


class CalendarPermissions:
    """Structure to hold Calendar permissions for a role"""
    def __init__(self, calendar_read_details: bool = False):
        self.calendar_read_details = calendar_read_details


class CRMPermissions:
    """Structure to hold CRM communication permissions for a role"""
    def __init__(self, crm_read_communications: bool = False):
        self.crm_read_communications = crm_read_communications


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

    # ------------------------------------------------------------
    # Gmail Permissions - role-based access control
    # ------------------------------------------------------------
    @staticmethod
    def get_permissions_for_role(role: Optional[str]) -> GmailPermissions:
        """
        Get Gmail permissions based on user role.
        
        Permission matrix:
        - admin/superadmin: Full access (metadata + body)
        - manager/analyst: Full access (metadata + body)
        - new_business: Full access (metadata + body)
        - client/customer: Metadata only (no body)
        - default/unknown: Metadata only (no body)
        
        Args:
            role: User role from x-user-role header
            
        Returns:
            GmailPermissions object with permission flags
        """
        if not role:
            # No role provided - apply least privilege
            return GmailPermissions(gmail_read_metadata=True, gmail_read_body=False)
        
        role_normalized = role.strip().lower()
        
        # Admin and superadmin have full access
        if role_normalized in ("admin", "superadmin", "super_admin"):
            return GmailPermissions(gmail_read_metadata=True, gmail_read_body=True)
        
        # Manager, analyst, and new_business have full access
        if role_normalized in ("manager", "analyst", "new_business", "newbusiness"):
            return GmailPermissions(gmail_read_metadata=True, gmail_read_body=True)
        
        # Client and customer have restricted access (metadata only)
        if role_normalized in ("client", "customer"):
            return GmailPermissions(gmail_read_metadata=True, gmail_read_body=False)
        
        # Unknown role - apply least privilege (metadata only)
        return GmailPermissions(gmail_read_metadata=True, gmail_read_body=False)

    # ------------------------------------------------------------
    # Calendar Permissions - role-based access control
    # ------------------------------------------------------------
    @staticmethod
    def get_calendar_permissions_for_role(role: Optional[str]) -> CalendarPermissions:
        """
        Get Calendar permissions based on user role.
        
        Permission matrix:
        - admin/superadmin: Full access (can see description, attendees, meet_link)
        - manager/analyst: Full access (can see description, attendees, meet_link)
        - new_business: Full access (can see description, attendees, meet_link)
        - client/customer: Limited access (cannot see description, attendees, meet_link)
        - None/empty (backward compatibility): Full access (can see description, attendees, meet_link)
        - unknown: Limited access (cannot see description, attendees, meet_link)
        
        Args:
            role: User role from x-user-role header
            
        Returns:
            CalendarPermissions object with permission flags
        """
        if not role:
            # No role provided - for backward compatibility, grant full access
            # This maintains existing behavior for clients not sending role headers
            return CalendarPermissions(calendar_read_details=True)
        
        role_normalized = role.strip().lower()
        
        # Admin and superadmin have full access
        if role_normalized in ("admin", "superadmin", "super_admin"):
            return CalendarPermissions(calendar_read_details=True)
        
        # Manager, analyst, and new_business have full access
        if role_normalized in ("manager", "analyst", "new_business", "newbusiness"):
            return CalendarPermissions(calendar_read_details=True)
        
        # Client and customer have restricted access (no details)
        if role_normalized in ("client", "customer"):
            return CalendarPermissions(calendar_read_details=False)
        
        # Unknown role - apply least privilege (no details)
        return CalendarPermissions(calendar_read_details=False)

    # ------------------------------------------------------------
    # CRM Communication Permissions - role-based access control
    # ------------------------------------------------------------
    @staticmethod
    def get_crm_permissions_for_role(role: Optional[str]) -> CRMPermissions:
        """
        Get CRM communication permissions based on user role.
        
        Permission matrix:
        - admin/superadmin: Full access (can access CRM emails and events)
        - manager/analyst: Full access (can access CRM emails and events)
        - new_business: Full access (can access CRM emails and events)
        - client/customer: No access (403 on CRM communication endpoints)
        - None/empty (backward compatibility): Full access (can access CRM emails and events)
        - unknown: No access (403 on CRM communication endpoints)
        
        Args:
            role: User role from x-user-role header
            
        Returns:
            CRMPermissions object with permission flags
        """
        if not role:
            # No role provided - for backward compatibility, grant full access
            # This maintains existing behavior for clients not sending role headers
            return CRMPermissions(crm_read_communications=True)
        
        role_normalized = role.strip().lower()
        
        # Admin and superadmin have full access
        if role_normalized in ("admin", "superadmin", "super_admin"):
            return CRMPermissions(crm_read_communications=True)
        
        # Manager, analyst, and new_business have full access
        if role_normalized in ("manager", "analyst", "new_business", "newbusiness"):
            return CRMPermissions(crm_read_communications=True)
        
        # Client and customer have no access to CRM communications
        if role_normalized in ("client", "customer"):
            return CRMPermissions(crm_read_communications=False)
        
        # Unknown role - apply least privilege (no access)
        return CRMPermissions(crm_read_communications=False)
