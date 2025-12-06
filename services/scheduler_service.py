from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from database import SessionLocal
import models
from services.google_calendar_service import GoogleCalendarService
import logging
from config import config

logger = logging.getLogger("pipedesk_drive.scheduler")

class SchedulerService:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.calendar_service = GoogleCalendarService()

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

    def renew_expiring_channels(self, db: Session):
        """
        Find channels expiring in less than 24 hours and renew them.
        """
        threshold = datetime.now(timezone.utc) + timedelta(hours=24)

        # 1. Find Drive Channels (if we want to renew them too)
        # Note: DriveWebhookChannel expiration logic might differ slightly, focusing on Calendar for now as per plan
        # But good to cover both if possible.

        # 2. Find Calendar Channels
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
        (Google API 'watch' doesn't support 'renew' directly, you usually stop and watch again,
        or just watch again and let the old one die).
        """
        # Strategy: Stop old channel, Create new one.

        # 1. Stop old channel (Best effort)
        try:
            self.calendar_service.stop_channel(channel.channel_id, channel.resource_id)
        except Exception as e:
            logger.warning(f"Failed to stop old channel {channel.channel_id}: {e}")

        # 2. Create new channel
        import uuid
        new_channel_id = str(uuid.uuid4())
        webhook_url = f"{config.WEBHOOK_BASE_URL}/webhooks/google-drive" # Same endpoint

        # 7 days from now
        expiration_ms = int((datetime.now().timestamp() + 7 * 24 * 3600) * 1000)

        response = self.calendar_service.watch_events(
            channel_id=new_channel_id,
            webhook_url=webhook_url,
            calendar_id=channel.calendar_id,
            token=config.WEBHOOK_SECRET,
            expiration=expiration_ms
        )

        # 3. Update DB
        # We can either update the existing row or create a new one.
        # Updating allows keeping the sync_token history associated with the "logical" sync state.
        # However, channel_id must be unique.

        logger.info(f"Renewed channel. Old: {channel.channel_id}, New: {new_channel_id}")

        channel.channel_id = new_channel_id
        channel.resource_id = response.get('resourceId')
        channel.expiration = datetime.fromtimestamp(int(response.get('expiration', expiration_ms)) / 1000, tz=timezone.utc)
        channel.updated_at = datetime.now(timezone.utc)

        db.commit()

scheduler_service = SchedulerService()
