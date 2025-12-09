from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class TaskBase(BaseModel):
    title: str = Field(..., description="Título da tarefa")
    notes: Optional[str] = Field(None, description="Notas ou descrição detalhada")
    due: Optional[datetime] = Field(None, description="Data/hora de vencimento (RFC3339)")
    status: Optional[str] = Field(
        "needsAction",
        description="Status da tarefa (needsAction ou completed)",
    )


class TaskCreate(TaskBase):
    tasklist_id: str = Field(..., description="Identificador da lista/projeto no Google Tasks")


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, description="Novo título da tarefa")
    notes: Optional[str] = Field(None, description="Novas notas da tarefa")
    due: Optional[datetime] = Field(None, description="Nova data de vencimento")
    status: Optional[str] = Field(None, description="Atualização de status")


class TaskResponse(BaseModel):
    id: str
    tasklist_id: Optional[str] = Field(None, description="Lista/projeto associado")
    title: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    due: Optional[datetime] = None
    completed: Optional[datetime] = None
    updated: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TaskListResponse(BaseModel):
    tasks: List[TaskResponse]
    next_page_token: Optional[str] = Field(
        None, description="Token para paginação fornecido pelo Google Tasks"
    )
