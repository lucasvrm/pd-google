import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional

from googleapiclient.errors import HttpError

from services.google_auth import GoogleAuthService

logger = logging.getLogger("pipedesk.google_tasks")

SCOPES = ["https://www.googleapis.com/auth/tasks"]


class GoogleTasksService:
    def __init__(self):
        self.auth_service = GoogleAuthService(scopes=SCOPES)
        self.service = self.auth_service.get_service("tasks", "v1")

    def _check_auth(self):
        if not self.service:
            raise Exception(
                "Tasks Service configuration error: GOOGLE_SERVICE_ACCOUNT_JSON is missing or invalid."
            )

    def _execute_with_retry(self, func, *args, **kwargs):
        max_retries = 3
        delay = 1.0
        transient_statuses = {429, 500, 502, 503, 504}

        for attempt in range(max_retries + 1):
            try:
                return func(*args, **kwargs)
            except HttpError as error:
                status = getattr(error.resp, "status", None)
                if status in transient_statuses and attempt < max_retries:
                    logger.warning(
                        "Transient Google Tasks error %s on attempt %s. Retrying in %.1fs.",
                        status,
                        attempt + 1,
                        delay,
                    )
                    time.sleep(delay)
                    delay = min(delay * 2, 16)
                    continue
                logger.error("Google Tasks HttpError: %s", error)
                raise
            except (ConnectionError, TimeoutError) as error:
                if attempt < max_retries:
                    logger.warning(
                        "Network error on Google Tasks attempt %s. Retrying in %.1fs.",
                        attempt + 1,
                        delay,
                    )
                    time.sleep(delay)
                    delay = min(delay * 2, 16)
                    continue
                logger.error("Network retries exhausted for Google Tasks: %s", error)
                raise

        raise Exception("Google Tasks retry loop exhausted")

    def list_tasks(
        self,
        tasklist_id: str,
        page_token: Optional[str] = None,
        due_min: Optional[str] = None,
        due_max: Optional[str] = None,
        show_completed: bool = True,
    ) -> Dict[str, Any]:
        self._check_auth()
        params: Dict[str, Any] = {
            "tasklist": tasklist_id,
            "showCompleted": show_completed,
        }
        if page_token:
            params["pageToken"] = page_token
        if due_min:
            params["dueMin"] = due_min
        if due_max:
            params["dueMax"] = due_max

        return self._execute_with_retry(
            self.service.tasks().list, **params
        ).execute()

    def get_task(self, tasklist_id: str, task_id: str) -> Dict[str, Any]:
        self._check_auth()
        return self._execute_with_retry(
            self.service.tasks().get, tasklist=tasklist_id, task=task_id
        ).execute()

    def create_task(self, tasklist_id: str, task_data: Dict[str, Any]) -> Dict[str, Any]:
        self._check_auth()
        return self._execute_with_retry(
            self.service.tasks().insert, tasklist=tasklist_id, body=task_data
        ).execute()

    def update_task(self, tasklist_id: str, task_id: str, task_data: Dict[str, Any]) -> Dict[str, Any]:
        self._check_auth()
        return self._execute_with_retry(
            self.service.tasks().patch, tasklist=tasklist_id, task=task_id, body=task_data
        ).execute()

    def delete_task(self, tasklist_id: str, task_id: str) -> None:
        self._check_auth()
        self._execute_with_retry(
            self.service.tasks().delete, tasklist=tasklist_id, task=task_id
        ).execute()

    def complete_task(self, tasklist_id: str, task_id: str) -> Dict[str, Any]:
        self._check_auth()
        completion_time = datetime.utcnow().isoformat() + "Z"
        body = {"status": "completed", "completed": completion_time}
        return self._execute_with_retry(
            self.service.tasks().patch, tasklist=tasklist_id, task=task_id, body=body
        ).execute()
