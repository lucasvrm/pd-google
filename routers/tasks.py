from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from auth.dependencies import get_current_user
from auth.jwt import UserContext
from schemas.tasks import TaskCreate, TaskListResponse, TaskResponse, TaskUpdate
from services.google_tasks_service import GoogleTasksService

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def get_tasks_service():
    return GoogleTasksService()


def _to_iso8601(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.isoformat() + "Z"
    return dt.isoformat()


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        cleaned = value.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned)
    except (TypeError, ValueError):
        return None


def _map_task_response(task: dict, tasklist_id: Optional[str] = None) -> TaskResponse:
    return TaskResponse(
        id=task.get("id", ""),
        tasklist_id=tasklist_id or task.get("tasklist"),
        title=task.get("title"),
        notes=task.get("notes"),
        status=task.get("status"),
        due=_parse_datetime(task.get("due")),
        completed=_parse_datetime(task.get("completed")),
        updated=_parse_datetime(task.get("updated")),
    )


def _build_task_payload(task_data: TaskUpdate) -> dict:
    payload = {}
    if task_data.title is not None:
        payload["title"] = task_data.title
    if task_data.notes is not None:
        payload["notes"] = task_data.notes
    if task_data.status is not None:
        payload["status"] = task_data.status
    if task_data.due is not None:
        iso_due = _to_iso8601(task_data.due)
        if iso_due:
            payload["due"] = iso_due
    return payload


@router.get("", response_model=TaskListResponse)
def list_tasks(
    project_id: str = Query(..., description="Lista/projeto do Google Tasks"),
    due_from: Optional[datetime] = Query(
        None, description="Filtrar tarefas com vencimento a partir desta data"
    ),
    due_to: Optional[datetime] = Query(
        None, description="Filtrar tarefas com vencimento até esta data"
    ),
    page_token: Optional[str] = Query(None, description="Token de paginação"),
    include_completed: bool = Query(
        True, description="Se verdadeiro, inclui tarefas concluídas no resultado"
    ),
    service: GoogleTasksService = Depends(get_tasks_service),
    current_user: UserContext = Depends(get_current_user),
):
    del current_user  # Explicitly acknowledge authentication dependency
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id é obrigatório")

    due_min = _to_iso8601(due_from)
    due_max = _to_iso8601(due_to)

    tasks_response = service.list_tasks(
        tasklist_id=project_id,
        page_token=page_token,
        due_min=due_min,
        due_max=due_max,
        show_completed=include_completed,
    )

    mapped_tasks: List[TaskResponse] = [
        _map_task_response(task, tasklist_id=project_id)
        for task in tasks_response.get("items", [])
    ]

    return TaskListResponse(
        tasks=mapped_tasks,
        next_page_token=tasks_response.get("nextPageToken"),
    )


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: str,
    project_id: str = Query(..., description="Lista/projeto do Google Tasks"),
    service: GoogleTasksService = Depends(get_tasks_service),
    current_user: UserContext = Depends(get_current_user),
):
    del current_user
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id é obrigatório")

    task = service.get_task(tasklist_id=project_id, task_id=task_id)
    return _map_task_response(task, tasklist_id=project_id)


@router.post("", response_model=TaskResponse, status_code=201)
def create_task(
    task: TaskCreate,
    service: GoogleTasksService = Depends(get_tasks_service),
    current_user: UserContext = Depends(get_current_user),
):
    del current_user
    payload = _build_task_payload(task)
    created = service.create_task(tasklist_id=task.tasklist_id, task_data=payload)
    return _map_task_response(created, tasklist_id=task.tasklist_id)


@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: str,
    project_id: str = Query(..., description="Lista/projeto do Google Tasks"),
    updates: TaskUpdate = ...,  # type: ignore
    service: GoogleTasksService = Depends(get_tasks_service),
    current_user: UserContext = Depends(get_current_user),
):
    del current_user
    payload = _build_task_payload(updates)
    if not payload:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    updated = service.update_task(
        tasklist_id=project_id, task_id=task_id, task_data=payload
    )
    return _map_task_response(updated, tasklist_id=project_id)


@router.delete("/{task_id}", status_code=204)
def delete_task(
    task_id: str,
    project_id: str = Query(..., description="Lista/projeto do Google Tasks"),
    service: GoogleTasksService = Depends(get_tasks_service),
    current_user: UserContext = Depends(get_current_user),
):
    del current_user
    service.delete_task(tasklist_id=project_id, task_id=task_id)


@router.post("/{task_id}/complete", response_model=TaskResponse)
def complete_task(
    task_id: str,
    project_id: str = Query(..., description="Lista/projeto do Google Tasks"),
    service: GoogleTasksService = Depends(get_tasks_service),
    current_user: UserContext = Depends(get_current_user),
):
    del current_user
    task = service.complete_task(tasklist_id=project_id, task_id=task_id)
    return _map_task_response(task, tasklist_id=project_id)
