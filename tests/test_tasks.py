from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import os
import sys

sys.path.append(os.path.abspath("."))

from auth.jwt import UserContext
from routers import tasks as tasks_router
from schemas.tasks import TaskCreate, TaskUpdate


class FakeTasksService:
    def __init__(self):
        self._counter = 0
        self.tasks: Dict[str, Dict[str, Any]] = {}

    def _new_id(self) -> str:
        self._counter += 1
        return f"task-{self._counter}"

    def list_tasks(
        self,
        tasklist_id: str,
        page_token: Optional[str] = None,
        due_min: Optional[str] = None,
        due_max: Optional[str] = None,
        show_completed: bool = True,
    ) -> Dict[str, Any]:
        items = [t for t in self.tasks.values() if t["tasklist"] == tasklist_id]
        if not show_completed:
            items = [t for t in items if t.get("status") != "completed"]
        if due_min:
            min_dt = datetime.fromisoformat(due_min.replace("Z", "+00:00"))
            items = [
                t for t in items if not t.get("due") or datetime.fromisoformat(t["due"].replace("Z", "+00:00")) >= min_dt
            ]
        if due_max:
            max_dt = datetime.fromisoformat(due_max.replace("Z", "+00:00"))
            items = [
                t for t in items if not t.get("due") or datetime.fromisoformat(t["due"].replace("Z", "+00:00")) <= max_dt
            ]
        return {"items": items, "nextPageToken": None}

    def get_task(self, tasklist_id: str, task_id: str) -> Dict[str, Any]:
        return self.tasks[task_id]

    def create_task(self, tasklist_id: str, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_id = self._new_id()
        task = {"id": task_id, "tasklist": tasklist_id, **task_data}
        self.tasks[task_id] = task
        return task

    def update_task(self, tasklist_id: str, task_id: str, task_data: Dict[str, Any]) -> Dict[str, Any]:
        self.tasks[task_id].update(task_data)
        return self.tasks[task_id]

    def delete_task(self, tasklist_id: str, task_id: str) -> None:
        self.tasks.pop(task_id, None)

    def complete_task(self, tasklist_id: str, task_id: str) -> Dict[str, Any]:
        completion_time = datetime.utcnow().isoformat() + "Z"
        self.tasks[task_id].update({"status": "completed", "completed": completion_time})
        return self.tasks[task_id]


def build_user() -> UserContext:
    return UserContext(id="tester", role="admin")


def test_create_and_get_task():
    service = FakeTasksService()
    user = build_user()

    task = TaskCreate(tasklist_id="project-1", title="Primeira", notes="Detalhe")
    created = tasks_router.create_task(task=task, service=service, current_user=user)

    assert created.title == "Primeira"
    fetched = tasks_router.get_task(
        task_id=created.id, project_id="project-1", service=service, current_user=user
    )
    assert fetched.id == created.id


def test_list_tasks_with_due_filters():
    service = FakeTasksService()
    user = build_user()
    early_due = datetime.utcnow() + timedelta(days=1)
    late_due = datetime.utcnow() + timedelta(days=5)

    service.create_task("project-2", {"title": "T1", "due": early_due.isoformat() + "Z"})
    service.create_task("project-2", {"title": "T2", "due": late_due.isoformat() + "Z"})

    result = tasks_router.list_tasks(
        project_id="project-2",
        due_from=datetime.utcnow() + timedelta(days=2),
        due_to=datetime.utcnow() + timedelta(days=6),
        service=service,
        current_user=user,
    )
    assert len(result.tasks) == 1
    assert result.tasks[0].title == "T2"


def test_update_task():
    service = FakeTasksService()
    user = build_user()
    task = service.create_task("project-3", {"title": "Old", "notes": "N"})

    updated = tasks_router.update_task(
        task_id=task["id"],
        project_id="project-3",
        updates=TaskUpdate(notes="Updated"),
        service=service,
        current_user=user,
    )
    assert updated.notes == "Updated"


def test_complete_task():
    service = FakeTasksService()
    user = build_user()
    task = service.create_task("project-4", {"title": "Do it"})

    completed = tasks_router.complete_task(
        task_id=task["id"],
        project_id="project-4",
        service=service,
        current_user=user,
    )
    assert completed.status == "completed"
    assert completed.completed is not None


def test_delete_task():
    service = FakeTasksService()
    user = build_user()
    task = service.create_task("project-5", {"title": "Remove"})

    tasks_router.delete_task(
        task_id=task["id"], project_id="project-5", service=service, current_user=user
    )

    result = tasks_router.list_tasks(
        project_id="project-5",
        due_from=None,
        due_to=None,
        service=service,
        current_user=user,
    )
    assert result.tasks == []
