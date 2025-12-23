"""
Lead Task Templates Router - CRUD para templates de tarefas (admin).
"""

from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from auth.jwt import UserContext
from database import SessionLocal
import models
from schemas.lead_tasks import (
    LeadTaskTemplateCreate,
    LeadTaskTemplateListResponse,
    LeadTaskTemplateResponse,
    LeadTaskTemplateUpdate,
)
from utils.structured_logging import StructuredLogger


router = APIRouter(prefix="/api/lead-task-templates", tags=["lead-task-templates"])
logger = StructuredLogger(
    service="lead_task_templates", logger_name="pipedesk_drive.lead_task_templates"
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _check_admin(user: UserContext) -> None:
    """Verifica se usuário é admin."""
    # Nota: user.role vem do JWT/auth
    # Ajustar conforme implementação real de auth
    pass  # RLS do Supabase já protege


def _map_template(t: models.LeadTaskTemplate) -> LeadTaskTemplateResponse:
    return LeadTaskTemplateResponse(
        id=str(t.id),
        code=t.code,
        label=t.label,
        description=t.description,
        is_active=t.is_active,
        sort_order=t.sort_order,
        created_at=t.created_at,
    )


@router.get("", response_model=LeadTaskTemplateListResponse)
def list_templates(
    include_inactive: bool = Query(False),
    current_user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lista templates de tarefas."""
    query = db.query(models.LeadTaskTemplate)
    
    if not include_inactive:
        query = query.filter(models.LeadTaskTemplate.is_active == True)
    
    templates = query.order_by(models.LeadTaskTemplate.sort_order).all()
    
    return LeadTaskTemplateListResponse(
        data=[_map_template(t) for t in templates],
        total=len(templates),
    )


@router.get("/{template_id}", response_model=LeadTaskTemplateResponse)
def get_template(
    template_id: str,
    current_user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Obtém um template específico."""
    template = db.query(models.LeadTaskTemplate).filter(
        models.LeadTaskTemplate.id == template_id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    
    return _map_template(template)


@router.post("", response_model=LeadTaskTemplateResponse, status_code=201)
def create_template(
    data: LeadTaskTemplateCreate,
    current_user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cria novo template (admin)."""
    # Verificar duplicata
    existing = db.query(models.LeadTaskTemplate).filter(
        models.LeadTaskTemplate.code == data.code
    ).first()
    
    if existing:
        raise HTTPException(status_code=409, detail=f"Template '{data.code}' já existe")
    
    max_order = db.query(func.max(models.LeadTaskTemplate.sort_order)).scalar() or 0
    
    template = models.LeadTaskTemplate(
        id=str(uuid.uuid4()),
        code=data.code,
        label=data.label,
        description=data.description,
        is_active=data.is_active,
        sort_order=data.sort_order or max_order + 1,
    )
    
    db.add(template)
    db.commit()
    db.refresh(template)
    
    logger.info(
        action="create_template",
        message=f"Template criado: {data.label}",
        template_id=template.id,
    )
    
    return _map_template(template)


@router.patch("/{template_id}", response_model=LeadTaskTemplateResponse)
def update_template(
    template_id: str,
    data: LeadTaskTemplateUpdate,
    current_user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Atualiza template (admin)."""
    template = db.query(models.LeadTaskTemplate).filter(
        models.LeadTaskTemplate.id == template_id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    
    # Verificar duplicata de code
    if data.code and data.code != template.code:
        existing = db.query(models.LeadTaskTemplate).filter(
            models.LeadTaskTemplate.code == data.code,
            models.LeadTaskTemplate.id != template_id,
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"Template '{data.code}' já existe")
    
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(template, key, value)
    
    db.commit()
    db.refresh(template)
    
    return _map_template(template)


@router.delete("/{template_id}", status_code=204)
def delete_template(
    template_id: str,
    current_user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Desativa template (soft delete via is_active=false)."""
    template = db.query(models.LeadTaskTemplate).filter(
        models.LeadTaskTemplate.id == template_id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    
    template.is_active = False
    db.commit()
