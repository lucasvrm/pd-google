from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from database import SessionLocal
from services.google_gmail_service import GoogleGmailService
import models

router = APIRouter(
    prefix="/gmail",
    tags=["gmail"]
)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class EmailSendRequest(BaseModel):
    to: EmailStr
    subject: str
    body_html: str
    entity_id: Optional[str] = None
    entity_type: Optional[str] = None

@router.post("/send")
def send_email(
    request: EmailSendRequest,
    x_user_email: str = Header(..., alias="X-User-Email"),
    db: Session = Depends(get_db)
):
    """
    Send an email impersonating the user specified in X-User-Email header.
    Requires Domain-Wide Delegation to be configured.
    """
    if not x_user_email:
        raise HTTPException(status_code=400, detail="X-User-Email header is required")

    try:
        service = GoogleGmailService(user_email=x_user_email)
        sent_msg = service.send_message(request.to, request.subject, request.body_html)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")

    # Save to DB
    new_email = models.Email(
        google_message_id=sent_msg.get('id'),
        thread_id=sent_msg.get('threadId'),
        user_email=x_user_email,
        to_address=request.to,
        from_address=x_user_email,
        subject=request.subject,
        body_html=request.body_html,
        entity_id=request.entity_id,
        entity_type=request.entity_type
        # snippet and internal_date would require a subsequent get() call, skipping for MVP speed
    )
    db.add(new_email)
    db.commit()

    return {"status": "sent", "id": sent_msg.get('id'), "threadId": sent_msg.get('threadId')}

@router.post("/sync")
def sync_emails(
    x_user_email: str = Header(..., alias="X-User-Email"),
    last_history_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Trigger manual sync of emails for the user.
    Uses History API to fetch changes since last_history_id.
    """
    from services.gmail_sync_service import GmailSyncService

    if not x_user_email:
        raise HTTPException(status_code=400, detail="X-User-Email header is required")

    try:
        syncer = GmailSyncService(db, x_user_email)
        new_history_id = syncer.sync_messages(start_history_id=last_history_id)
        return {"status": "synced", "new_history_id": new_history_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")
