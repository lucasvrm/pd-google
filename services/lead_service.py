"""
Lead Service - Business logic for lead operations.

This service provides:
1. Lead ownership change with validation
2. Member management for leads
3. Notification triggers for ownership changes
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
import logging

from sqlalchemy.orm import Session

from models import Lead, User, LeadMember, AuditLog
from services.audit_service import get_audit_actor
from services.gmail_service import GmailService
from auth.dependencies import ROLE_HIERARCHY

logger = logging.getLogger("pipedesk_drive.lead_service")


class LeadService:
    """Service for lead-related business operations."""

    def __init__(self, db: Session):
        self.db = db

    def validate_change_owner_request(
        self,
        lead_id: str,
        new_owner_id: str,
        current_user_id: str,
        current_user_role: str,
    ) -> Tuple[Lead, User, Optional[str]]:
        """
        Validate a change owner request.
        
        Returns:
            Tuple of (lead, new_owner_user, error_message)
            If error_message is not None, the request is invalid.
        
        Raises:
            ValueError: With appropriate HTTP status code context
        """
        # 1. Check if lead exists
        lead = self.db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            raise ValueError(f"404:Lead {lead_id} not found")

        # 2. Check if lead is deleted/qualified
        if lead.deleted_at is not None:
            raise ValueError(f"400:Lead {lead_id} is already deleted or qualified")

        # 3. Check if new owner exists
        new_owner = self.db.query(User).filter(User.id == new_owner_id).first()
        if not new_owner:
            raise ValueError(f"404:User {new_owner_id} not found")

        # 4. Check if new owner is active
        # Handle None is_active as active (default behavior)
        if new_owner.is_active is not None and not new_owner.is_active:
            raise ValueError(f"400:User {new_owner_id} is inactive")

        # 5. Check if new owner is different from current owner
        if lead.owner_user_id == new_owner_id:
            raise ValueError(f"400:New owner is the same as current owner")

        # 6. Check permissions: owner, manager, or admin can change
        user_role_level = ROLE_HIERARCHY.get(current_user_role.lower(), 0)
        is_current_owner = lead.owner_user_id == current_user_id
        is_manager_or_admin = user_role_level >= ROLE_HIERARCHY.get("manager", 75)

        if not is_current_owner and not is_manager_or_admin:
            raise ValueError(
                f"403:Permission denied. Only the current owner, a manager, or an admin can change lead ownership"
            )

        return lead, new_owner, None

    def change_owner(
        self,
        lead: Lead,
        new_owner: User,
        add_previous_owner_as_member: bool,
        changed_by_user_id: str,
    ) -> Dict[str, Any]:
        """
        Execute the ownership change.
        
        Args:
            lead: The lead to change ownership of
            new_owner: The new owner user
            add_previous_owner_as_member: Whether to add previous owner as a collaborator
            changed_by_user_id: ID of the user making the change
        
        Returns:
            Dictionary with change details
        """
        now = datetime.now(timezone.utc)
        previous_owner_id = lead.owner_user_id
        previous_owner_added = False

        # Update lead owner
        lead.owner_user_id = new_owner.id
        lead.updated_at = now

        # Add previous owner as member if requested and they exist
        if add_previous_owner_as_member and previous_owner_id:
            # Check if already a member
            existing_member = (
                self.db.query(LeadMember)
                .filter(
                    LeadMember.lead_id == lead.id,
                    LeadMember.user_id == previous_owner_id,
                )
                .first()
            )

            if not existing_member:
                new_member = LeadMember(
                    lead_id=lead.id,
                    user_id=previous_owner_id,
                    role="collaborator",
                    added_at=now,
                    added_by=changed_by_user_id,
                )
                self.db.add(new_member)
                previous_owner_added = True
                logger.info(
                    f"Added previous owner {previous_owner_id} as collaborator on lead {lead.id}"
                )

        # Create audit log for owner change
        self._create_owner_change_audit_log(
            lead_id=lead.id,
            previous_owner_id=previous_owner_id,
            new_owner_id=new_owner.id,
            changed_by=changed_by_user_id,
            timestamp=now,
        )

        self.db.commit()

        logger.info(
            f"Lead {lead.id} ownership changed from {previous_owner_id} to {new_owner.id} by {changed_by_user_id}"
        )

        return {
            "lead_id": lead.id,
            "previous_owner_id": previous_owner_id,
            "new_owner_id": new_owner.id,
            "previous_owner_added_as_member": previous_owner_added,
            "changed_at": now,
            "changed_by": changed_by_user_id,
        }

    def _create_owner_change_audit_log(
        self,
        lead_id: str,
        previous_owner_id: Optional[str],
        new_owner_id: str,
        changed_by: str,
        timestamp: datetime,
    ) -> None:
        """Create an audit log entry for owner change."""
        changes = {
            "owner_user_id": {
                "old": previous_owner_id,
                "new": new_owner_id,
            }
        }

        # Insert directly to avoid session flush issues
        self.db.execute(
            AuditLog.__table__.insert().values(
                entity_type="lead",
                entity_id=lead_id,
                actor_id=changed_by,
                action="lead.owner_changed",
                changes=changes,
                timestamp=timestamp,
            )
        )

    def notify_new_owner(
        self,
        new_owner: User,
        lead: Lead,
        changed_by_user_id: str,
    ) -> bool:
        """
        Send email notification to the new owner about the lead assignment.
        
        Args:
            new_owner: The new owner user
            lead: The lead that was assigned
            changed_by_user_id: ID of the user who made the change
        
        Returns:
            True if notification was sent successfully, False otherwise
        """
        if not new_owner.email:
            logger.warning(
                f"Cannot notify new owner {new_owner.id}: no email address configured"
            )
            return False

        try:
            # Get the user who made the change
            changed_by_user = (
                self.db.query(User).filter(User.id == changed_by_user_id).first()
            )
            changed_by_name = changed_by_user.name if changed_by_user else "System"

            lead_name = lead.legal_name or lead.trade_name or "Lead"
            subject = f"🎯 Novo Lead Atribuído: {lead_name}"

            body_html = f"""
            <html>
            <body>
                <h2>Você foi atribuído como responsável por um novo lead!</h2>
                <p><strong>Lead:</strong> {lead_name}</p>
                <p><strong>Novo Responsável:</strong> {new_owner.name or new_owner.email}</p>
                <p><strong>Atribuído por:</strong> {changed_by_name}</p>
                <hr>
                <p>Acesse o sistema para ver mais detalhes do lead.</p>
            </body>
            </html>
            """

            body_text = f"""
            Você foi atribuído como responsável por um novo lead!
            
            Lead: {lead_name}
            Novo Responsável: {new_owner.name or new_owner.email}
            Atribuído por: {changed_by_name}
            
            Acesse o sistema para ver mais detalhes do lead.
            """

            gmail_service = GmailService()
            gmail_service.send_email(
                to=[new_owner.email],
                subject=subject,
                body_html=body_html,
                body_text=body_text,
            )

            logger.info(f"Notification sent to new owner {new_owner.id} for lead {lead.id}")
            return True

        except Exception as e:
            logger.error(
                f"Failed to send notification to new owner {new_owner.id} for lead {lead.id}: {e}",
                exc_info=True,
            )
            return False
