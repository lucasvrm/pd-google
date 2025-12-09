"""
Service for extracting contact emails from CRM entities.
This service provides a strategy for associating emails and calendar events
with Company, Lead, and Deal entities based on their contact emails.
"""

from typing import List, Set, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
import models


class CRMContactService:
    """
    Service for managing contact email associations with CRM entities.
    
    Strategy:
    - For Companies: Extract from company email fields and related contacts
    - For Leads: Extract from lead email fields and qualified company contacts
    - For Deals: Extract from deal email fields and company contacts
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_entity_contact_emails(
        self, 
        entity_type: str, 
        entity_id: str
    ) -> List[str]:
        """
        Get all contact email addresses associated with a CRM entity.
        
        Args:
            entity_type: Type of entity (company, lead, deal)
            entity_id: UUID of the entity
            
        Returns:
            List of email addresses associated with the entity
        """
        entity_type = entity_type.lower()
        
        if entity_type == "company":
            return self._get_company_emails(entity_id)
        elif entity_type == "lead":
            return self._get_lead_emails(entity_id)
        elif entity_type == "deal":
            return self._get_deal_emails(entity_id)
        else:
            raise ValueError(f"Unknown entity type: {entity_type}")
    
    def _get_company_emails(self, company_id: str) -> List[str]:
        """
        Extract email addresses for a company.
        
        Strategy:
        1. Get company email field (if exists)
        2. Get emails from associated contacts table (if exists)
        3. Fallback to empty list if no email sources found
        """
        emails: Set[str] = set()
        
        # Try to get company object
        company = self.db.query(models.Company).filter(
            models.Company.id == company_id
        ).first()
        
        if not company:
            return []
        
        # Try to get email from company object (if field exists)
        if hasattr(company, 'email') and company.email:
            emails.add(company.email.lower().strip())
        
        # Try to query contacts table (if exists)
        # Using raw SQL to avoid errors if table doesn't exist
        try:
            result = self.db.execute(
                text("""
                    SELECT DISTINCT email 
                    FROM contacts 
                    WHERE company_id = :company_id 
                    AND email IS NOT NULL 
                    AND email != ''
                """),
                {"company_id": company_id}
            )
            for row in result:
                if row[0]:
                    emails.add(row[0].lower().strip())
        except Exception:
            # Table might not exist, that's okay
            pass
        
        return sorted(list(emails))
    
    def _get_lead_emails(self, lead_id: str) -> List[str]:
        """
        Extract email addresses for a lead.
        
        Strategy:
        1. Get lead email field (if exists)
        2. Get emails from qualified company (if exists)
        3. Get emails from lead contacts (if exists)
        """
        emails: Set[str] = set()
        
        # Try to get lead object
        lead = self.db.query(models.Lead).filter(
            models.Lead.id == lead_id
        ).first()
        
        if not lead:
            return []
        
        # Try to get email from lead object (if field exists)
        if hasattr(lead, 'email') and lead.email:
            emails.add(lead.email.lower().strip())
        
        # If lead has a qualified company, get company emails too
        if lead.qualified_company_id:
            company_emails = self._get_company_emails(lead.qualified_company_id)
            emails.update(company_emails)
        
        # Try to query lead contacts (if exists)
        try:
            result = self.db.execute(
                text("""
                    SELECT DISTINCT email 
                    FROM contacts 
                    WHERE lead_id = :lead_id 
                    AND email IS NOT NULL 
                    AND email != ''
                """),
                {"lead_id": lead_id}
            )
            for row in result:
                if row[0]:
                    emails.add(row[0].lower().strip())
        except Exception:
            # Table might not exist, that's okay
            pass
        
        return sorted(list(emails))
    
    def _get_deal_emails(self, deal_id: str) -> List[str]:
        """
        Extract email addresses for a deal.
        
        Strategy:
        1. Get deal email field (if exists)
        2. Get emails from associated company (if exists)
        3. Get emails from deal contacts (if exists)
        """
        emails: Set[str] = set()
        
        # Try to get deal object
        deal = self.db.query(models.Deal).filter(
            models.Deal.id == deal_id
        ).first()
        
        if not deal:
            return []
        
        # Try to get email from deal object (if field exists)
        if hasattr(deal, 'email') and deal.email:
            emails.add(deal.email.lower().strip())
        
        # If deal has a company, get company emails too
        if deal.company_id:
            company_emails = self._get_company_emails(deal.company_id)
            emails.update(company_emails)
        
        # Try to query deal contacts (if exists)
        try:
            result = self.db.execute(
                text("""
                    SELECT DISTINCT email 
                    FROM contacts 
                    WHERE deal_id = :deal_id 
                    AND email IS NOT NULL 
                    AND email != ''
                """),
                {"deal_id": deal_id}
            )
            for row in result:
                if row[0]:
                    emails.add(row[0].lower().strip())
        except Exception:
            # Table might not exist, that's okay
            pass
        
        return sorted(list(emails))
