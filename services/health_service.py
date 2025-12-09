from datetime import datetime, timezone
from typing import Callable, Dict, Optional

from sqlalchemy.orm import Session

import models
from services.google_calendar_service import GoogleCalendarService
from services.google_gmail_service import GoogleGmailService
from utils.retry import run_with_backoff
from utils.structured_logging import StructuredLogger


class HealthService:
    """Collects health metrics for Google integrations and webhook processing."""

    def __init__(
        self,
        db: Session,
        now_provider: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.db = db
        self.now_provider = now_provider
        self.logger = StructuredLogger(service="health", logger_name="pipedesk_drive.health")

    def get_calendar_metrics(self) -> Dict[str, Optional[str]]:
        now = self.now_provider()
        active_channels = self.db.query(models.CalendarSyncState).filter(
            models.CalendarSyncState.active.is_(True),
            models.CalendarSyncState.expiration > now,
        ).count()

        last_sync_obj = (
            self.db.query(models.CalendarSyncState)
            .filter(models.CalendarSyncState.active.is_(True))
            .order_by(models.CalendarSyncState.updated_at.desc())
            .first()
        )
        last_sync = last_sync_obj.updated_at.isoformat() if last_sync_obj and last_sync_obj.updated_at else None

        event_query = self.db.query(models.CalendarEvent).filter(models.CalendarEvent.status != "cancelled")
        event_count = event_query.count()

        oldest_event_obj = event_query.order_by(models.CalendarEvent.start_time.asc()).first()
        newest_event_obj = event_query.order_by(models.CalendarEvent.start_time.desc()).first()

        oldest_event = oldest_event_obj.start_time.isoformat() if oldest_event_obj and oldest_event_obj.start_time else None
        newest_event = newest_event_obj.start_time.isoformat() if newest_event_obj and newest_event_obj.start_time else None

        return {
            "active_channels": active_channels,
            "last_sync": last_sync,
            "event_count": event_count,
            "oldest_event": oldest_event,
            "newest_event": newest_event,
        }

    def _check_calendar_connectivity(self) -> Dict[str, Optional[str]]:
        try:
            calendar_service = GoogleCalendarService()
            if not calendar_service.service:
                return {"reachable": False, "detail": "Calendar service not initialized"}

            def _list_calendar():
                return calendar_service.service.calendarList().list(maxResults=1).execute()

            run_with_backoff(_list_calendar, operation_name="calendar_connectivity", max_retries=2, initial_delay=0.5)
            return {"reachable": True, "detail": "Calendar API reachable"}
        except Exception as exc:  # pragma: no cover - errors are expected in some environments
            self.logger.warning(
                action="calendar_connectivity",
                status="degraded",
                message="Calendar API connectivity issue",
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            return {"reachable": False, "detail": str(exc)}

    def _check_gmail_connectivity(self) -> Dict[str, Optional[str]]:
        status = {"reachable": False, "auth_ok": False, "detail": None}
        try:
            gmail_service = GoogleGmailService()
            if not gmail_service.service:
                status["detail"] = "Gmail service not initialized"
                return status

            status["auth_ok"] = True

            def _list_labels():
                return gmail_service.list_labels()

            run_with_backoff(_list_labels, operation_name="gmail_connectivity", max_retries=2, initial_delay=0.5)
            status["reachable"] = True
            status["detail"] = "Gmail API reachable"
            return status
        except Exception as exc:  # pragma: no cover - errors are expected in some environments
            self.logger.warning(
                action="gmail_connectivity",
                status="degraded",
                message="Gmail API connectivity issue",
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            status["detail"] = str(exc)
            return status

    def get_webhook_queue_metrics(self) -> Dict[str, Optional[int]]:
        now = self.now_provider()
        queue_depth = self.db.query(models.DriveChangeLog).count()
        oldest_event_age_seconds: Optional[int] = None

        if queue_depth:
            oldest_event = (
                self.db.query(models.DriveChangeLog)
                .order_by(models.DriveChangeLog.received_at.asc())
                .first()
            )
            if oldest_event and oldest_event.received_at:
                received_at = oldest_event.received_at
                if received_at.tzinfo is None:
                    received_at = received_at.replace(tzinfo=timezone.utc)
                oldest_event_age_seconds = int((now - received_at).total_seconds())

        return {
            "queue_depth": queue_depth,
            "oldest_event_age_seconds": oldest_event_age_seconds,
        }

    def calendar_health(self) -> Dict[str, object]:
        now = self.now_provider()
        metrics = self.get_calendar_metrics()
        connectivity = self._check_calendar_connectivity()
        queue_metrics = self.get_webhook_queue_metrics()

        status = "healthy"
        issues = []

        if metrics["active_channels"] == 0:
            status = "degraded"
            issues.append("No active webhook channels")
        if metrics["last_sync"] is None:
            status = "degraded"
            issues.append("No sync activity recorded")
        if not connectivity.get("reachable"):
            status = "degraded"
            issues.append("Calendar API unreachable")
        if queue_metrics["queue_depth"] and queue_metrics["queue_depth"] > 1000:
            status = "degraded"
            issues.append("Webhook queue depth high")

        response = {
            "service": "calendar",
            "status": status,
            "timestamp": now.isoformat(),
            **metrics,
            "calendar_api_reachable": connectivity.get("reachable"),
            "webhook_queue": queue_metrics,
        }

        if issues:
            response["issues"] = issues

        return response

    def gmail_health(self) -> Dict[str, object]:
        now = self.now_provider()
        connectivity = self._check_gmail_connectivity()

        status = "healthy" if connectivity.get("reachable") else "degraded"
        issues = []
        if not connectivity.get("auth_ok"):
            issues.append("Gmail credentials not configured")
        if not connectivity.get("reachable"):
            issues.append("Gmail API not reachable")

        response = {
            "service": "gmail",
            "status": status,
            "timestamp": now.isoformat(),
            "auth_ok": connectivity.get("auth_ok"),
            "api_reachable": connectivity.get("reachable"),
            "connectivity_detail": connectivity.get("detail"),
        }
        if issues:
            response["issues"] = issues
        return response

    def general_health(self) -> Dict[str, object]:
        now = self.now_provider()
        calendar_health = self.calendar_health()
        gmail_health = self.gmail_health()
        webhook_queue = self.get_webhook_queue_metrics()

        statuses = [calendar_health["status"], gmail_health["status"]]
        if "unhealthy" in statuses:
            overall_status = "unhealthy"
        elif "degraded" in statuses:
            overall_status = "degraded"
        else:
            overall_status = "healthy"

        self.logger.info(
            action="general_health_check",
            status=overall_status,
            message="Aggregated health check",
            calendar_status=calendar_health["status"],
            gmail_status=gmail_health["status"],
            webhook_queue_depth=webhook_queue.get("queue_depth"),
        )

        return {
            "overall_status": overall_status,
            "timestamp": now.isoformat(),
            "services": {
                "calendar": calendar_health,
                "gmail": gmail_health,
                "webhook_queue": webhook_queue,
            },
        }
