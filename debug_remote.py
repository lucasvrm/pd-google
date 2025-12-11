import sys
import logging
from database import SessionLocal
from sqlalchemy.orm import joinedload
import models
from datetime import datetime
from schemas.leads import LeadSalesViewItem
from services.lead_priority_service import calculate_lead_priority, classify_priority_bucket
from services.next_action_service import suggest_next_action  # <-- NOVO

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
                stats = lead.activity_stats

                # Mesmo cálculo de prioridade da rota real
                db_score = lead.priority_score if lead.priority_score is not None else None
                score = db_score if db_score is not None else calculate_lead_priority(lead, stats)
                bucket = classify_priority_bucket(score)

                # Tags sempre como lista de string
                tags_list = []
                if lead.tags:
                    print(f"  Raw tags: {lead.tags}")
                    tags_list = [str(tag.name) for tag in lead.tags if tag.name is not None]
                print(f"  Processed Tags: {tags_list}")

                # next_action igual à rota /sales-view
                next_action = suggest_next_action(lead, stats)

                # Lead owner simples (para debug podemos ignorar name)
                lead_owner = None
                if getattr(lead, "owner", None):
                    lead_owner = {
                        "id": str(lead.owner.id),
                        "name": lead.owner.name,
                    }

                # IDs que vêm como UUID -> converter para string
                item = LeadSalesViewItem(
                    id=str(lead.id),
                    legal_name=getattr(lead, "legal_name", None) or lead.title,
                    trade_name=lead.trade_name,
                    lead_status_id=str(lead.lead_status_id) if lead.lead_status_id is not None else None,
                    lead_origin_id=str(lead.lead_origin_id) if lead.lead_origin_id is not None else None,
                    owner_user_id=str(lead.owner_user_id) if lead.owner_user_id is not None else None,
                    owner=lead_owner,
                    priority_score=score,
                    priority_bucket=bucket,
                    last_interaction_at=lead.last_interaction_at or lead.updated_at or lead.created_at,
                    qualified_master_deal_id=str(lead.qualified_master_deal_id) if lead.qualified_master_deal_id is not None else None,
                    address_city=lead.address_city,
                    address_state=lead.address_state,
                    tags=tags_list,
                    next_action=next_action,  # <- agora é um dict/obj NextAction válido
                )
                items.append(item)
                print("  Valid item created.")
                print("  Item model_dump():", item.model_dump())
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
