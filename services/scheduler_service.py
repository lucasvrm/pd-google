from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from database import SessionLocal
import models
from services.google_calendar_service import GoogleCalendarService
from services.google_drive_real import GoogleDriveRealService
from services.google_drive_mock import GoogleDriveService
from utils.structured_logging import calendar_logger
import logging
from config import config

logger = logging.getLogger("pipedesk_drive.scheduler")

class SchedulerService:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()

    def get_calendar_service(self, db: Session) -> GoogleCalendarService:
        """Get calendar service instance with database session"""
        return GoogleCalendarService(db)

    def start(self):
        """
        Start the scheduler and add jobs.
        """
        if not self.scheduler.running:
            # Check for expiring channels every 6 hours
            self.scheduler.add_job(
                self.renew_channels_job,
                IntervalTrigger(hours=6),
                id="renew_channels",
                replace_existing=True
            )
            
            # Reconcile Drive State (Every 1 hour)
            # Checks for consistency between DB and Drive (e.g. deleted folders)
            self.scheduler.add_job(
                self.reconcile_drive_state_job,
                IntervalTrigger(hours=1), 
                id="reconcile_drive",
                replace_existing=True
            )
            
            # Cleanup old calendar events (Every 24 hours)
            # Archives/deletes events older than retention period
            self.scheduler.add_job(
                self.cleanup_old_events_job,
                IntervalTrigger(hours=24),
                id="cleanup_old_events",
                replace_existing=True
            )
            
            self.scheduler.start()
            logger.info("Scheduler started.")

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped.")

    def renew_channels_job(self):
        """
        Job wrapper to handle database session.
        """
        logger.info("Running channel renewal job...")
        db = SessionLocal()
        try:
            self.renew_expiring_channels(db)
        except Exception as e:
            logger.error(f"Error in renewal job: {e}")
        finally:
            db.close()

    def reconcile_drive_state_job(self):
        """
        Job wrapper for reconciliation.
        """
        logger.info("Running Drive reconciliation job...")
        db = SessionLocal()
        try:
            self.reconcile_folders(db)
        except Exception as e:
            logger.error(f"Error in reconciliation job: {e}")
        finally:
            db.close()
    
    def cleanup_old_events_job(self):
        """
        Job wrapper for cleaning up old calendar events.
        """
        calendar_logger.info(
            action="cleanup_job",
            status="started",
            message="Running calendar event cleanup job"
        )
        db = SessionLocal()
        try:
            count = self.cleanup_old_calendar_events(db)
            calendar_logger.info(
                action="cleanup_job",
                status="success",
                message=f"Cleaned up {count} old calendar events",
                cleaned_count=count
            )
        except Exception as e:
            calendar_logger.error(
                action="cleanup_job",
                message="Error in cleanup job",
                error=e
            )
        finally:
            db.close()

    def renew_expiring_channels(self, db: Session):
        """
        Find channels expiring in less than 24 hours and renew them.
        """
        threshold = datetime.now(timezone.utc) + timedelta(hours=24)

        # Find Calendar Channels
        expiring_channels = db.query(models.CalendarSyncState).filter(
            models.CalendarSyncState.active == True,
            models.CalendarSyncState.expiration <= threshold
        ).all()

        logger.info(f"Found {len(expiring_channels)} expiring calendar channels.")

        for channel in expiring_channels:
            try:
                self._renew_calendar_channel(db, channel)
            except Exception as e:
                logger.error(f"Failed to renew channel {channel.channel_id}: {e}")

    def _renew_calendar_channel(self, db: Session, channel: models.CalendarSyncState):
        """
        Renew a specific calendar channel by stopping it and starting a new one.
        """
        calendar_service = self.get_calendar_service(db)
        
        # 1. Stop old channel (Best effort)
        try:
            calendar_service.stop_channel(channel.channel_id, channel.resource_id)
        except Exception as e:
            logger.warning(f"Failed to stop old channel {channel.channel_id}: {e}")

        # 2. Create new channel
        import uuid
        new_channel_id = str(uuid.uuid4())
        webhook_url = f"{config.WEBHOOK_BASE_URL}/webhooks/google-drive" # Same endpoint

        # 7 days from now
        expiration_ms = int((datetime.now().timestamp() + 7 * 24 * 3600) * 1000)

        response = calendar_service.watch_events(
            channel_id=new_channel_id,
            webhook_url=webhook_url,
            calendar_id=channel.calendar_id,
            token=config.WEBHOOK_SECRET,
            expiration=expiration_ms
        )

        logger.info(f"Renewed channel. Old: {channel.channel_id}, New: {new_channel_id}")

        channel.channel_id = new_channel_id
        channel.resource_id = response.get('resourceId')
        channel.expiration = datetime.fromtimestamp(int(response.get('expiration', expiration_ms)) / 1000, tz=timezone.utc)
        channel.updated_at = datetime.now(timezone.utc)

        db.commit()

    def reconcile_folders(self, db: Session):
        """
        Verifies if active folders in DB still exist in Drive.
        If deleted externally and webhook missed, mark as deleted in DB.
        """
        if config.USE_MOCK_DRIVE:
            drive_service = GoogleDriveService()
        else:
            drive_service = GoogleDriveRealService()

        # Get all folders that system thinks are active
        active_folders = db.query(models.DriveFolder).filter(
            models.DriveFolder.deleted_at.is_(None)
        ).all()

        for folder in active_folders:
            try:
                # Try fetching from Google
                g_file = drive_service.get_file(folder.folder_id)
                
                # Check if trashed
                if g_file.get('trashed') is True:
                    logger.info(f"Reconcile: Found trashed folder {folder.folder_id}, updating DB.")
                    folder.deleted_at = datetime.now(timezone.utc)
                    folder.delete_reason = "reconciled_trash"
                    folder.deleted_by = "system"
                    db.commit()
                    
            except Exception as e:
                # If 404, folder is gone permanently
                if "404" in str(e) or "File not found" in str(e):
                    logger.info(f"Reconcile: Folder {folder.folder_id} not found in Drive, marking deleted.")
                    folder.deleted_at = datetime.now(timezone.utc)
                    folder.delete_reason = "reconciled_missing"
                    folder.deleted_by = "system"
                    db.commit()
                else:
                    # Other errors (network, auth), log and skip
                    logger.warning(f"Reconcile check failed for {folder.folder_id}: {e}")
    
    def cleanup_old_calendar_events(self, db: Session) -> int:
        """
        Archive or delete calendar events older than retention period.
        
        Args:
            db: Database session
        
        Returns:
            Number of events cleaned up
        """
        retention_days = config.CALENDAR_EVENT_RETENTION_DAYS
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
        
        # Find old events (ended more than retention_days ago)
        old_events = db.query(models.CalendarEvent).filter(
            models.CalendarEvent.end_time < cutoff_date,
            models.CalendarEvent.status != 'cancelled'  # Don't double-process cancelled events
        ).all()
        
        count = 0
        for event in old_events:
            # Mark as cancelled (soft delete approach)
            event.status = 'cancelled'
            count += 1
        
        if count > 0:
            db.commit()
            logger.info(f"Marked {count} old events as cancelled (older than {retention_days} days)")
        
        return count

scheduler_service = SchedulerService()
