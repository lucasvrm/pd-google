cat << 'EOF' > debug_remote.py
import sys
import logging
from database import SessionLocal
from sqlalchemy import func
from sqlalchemy.orm import joinedload
import models
from datetime import datetime
from schemas.leads import LeadSalesViewResponse, LeadSalesViewItem, Pagination
from services.lead_priority_service import calculate_lead_priority, classify_priority_bucket

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def debug_query():
    print("Starting debug query and response validation...")
    db = SessionLocal()
    try:
        print("Constructing base query...")
        base_query = (
            db.query(models.Lead)
            .outerjoin(models.LeadActivityStats)
            .outerjoin(models.User, models.User.id == models.Lead.owner_user_id)
            .options(
                joinedload(models.Lead.activity_stats),
                joinedload(models.Lead.owner),
                joinedload(models.Lead.lead_status),
                joinedload(models.Lead.lead_origin),
                joinedload(models.Lead.qualified_master_deal),
                joinedload(models.Lead.tags),
            )
        )
        
        print("Executing fetch all (limit 1)...")
        leads = base_query.limit(1).all()
        print(f"Fetched {len(leads)} leads.")
        
        print("Processing leads into items...")
        items = []
        for i, lead in enumerate(leads):
            print(f"Processing lead {i}: ID={lead.id}")
            try:
                # Replicate extraction logic from routers/leads.py
                tags_list = []
                if lead.tags:
                    print(f"  Raw tags: {lead.tags}")
                    tags_list = [str(tag.name) for tag in lead.tags if tag.name is not None]
                
                print(f"  Processed Tags: {tags_list}")
                
                # Try to create the Pydantic model
                item = LeadSalesViewItem(
                    id=str(lead.id),
                    legal_name=getattr(lead, "legal_name", None) or lead.title,
                    trade_name=lead.trade_name,
                    lead_status_id=lead.lead_status_id,
                    lead_origin_id=lead.lead_origin_id,
                    owner_user_id=lead.owner_user_id,
                    owner=None, 
                    priority_score=lead.priority_score or 0,
                    priority_bucket="cold", 
                    last_interaction_at=None,
                    qualified_master_deal_id=lead.qualified_master_deal_id,
                    address_city=lead.address_city,
                    address_state=lead.address_state,
                    tags=tags_list,
                    next_action=None
                )
                items.append(item)
                print("  Valid item created.")
            except Exception as e:
                print(f"  FAILED to create item for lead {lead.id}: {e}")
                import traceback
                traceback.print_exc()

    except Exception as e:
        print(f"\nCRITICAL ERROR in main flow: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    debug_query()
EOF
