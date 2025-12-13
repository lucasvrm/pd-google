from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from services.google_auth import GoogleAuthService
from utils.retry import exponential_backoff_retry

SCOPES = ['https://www.googleapis.com/auth/calendar']

class GoogleCalendarService:
    def __init__(self, db: Session):
        """
        Initialize Google Calendar Service with database session.
        
        Args:
            db: SQLAlchemy database session for persistence operations
        """
        self.db = db
        self.auth_service = GoogleAuthService(scopes=SCOPES)
        self.service = self.auth_service.get_service('calendar', 'v3')

    def _check_auth(self):
        if not self.service:
            raise Exception("Calendar Service configuration error: GOOGLE_SERVICE_ACCOUNT_JSON is missing or invalid.")

    @exponential_backoff_retry(max_retries=3, initial_delay=1.0)
    def create_event(self, event_data: Dict[str, Any], calendar_id: str = 'primary') -> Dict[str, Any]:
        """
        Creates an event in the specified calendar.
        """
        self._check_auth()

        # If create_meet_link is true (conceptually), ensure conferenceData is set
        # This parameter enables Meet link generation
        conference_data_version = 1

        event = self.service.events().insert(
            calendarId=calendar_id,
            body=event_data,
            conferenceDataVersion=conference_data_version
        ).execute()

        return event

    @exponential_backoff_retry(max_retries=3, initial_delay=1.0)
    def list_events(self, calendar_id: str = 'primary', time_min: Optional[str] = None, time_max: Optional[str] = None, sync_token: Optional[str] = None) -> Dict[str, Any]:
        """
        Lists events. Supports time filtering and sync tokens.
        """
        self._check_auth()

        kwargs = {
            'calendarId': calendar_id,
            'singleEvents': True, # Expand recurring events into single instances
            'orderBy': 'startTime'
        }

        if sync_token:
            kwargs['syncToken'] = sync_token
            # When syncing, time params are invalid
            if 'singleEvents' in kwargs: del kwargs['singleEvents']
            if 'orderBy' in kwargs: del kwargs['orderBy']
        else:
            if time_min: kwargs['timeMin'] = time_min
            if time_max: kwargs['timeMax'] = time_max

        return self.service.events().list(**kwargs).execute()

    @exponential_backoff_retry(max_retries=3, initial_delay=1.0)
    def get_event(self, event_id: str, calendar_id: str = 'primary') -> Dict[str, Any]:
        self._check_auth()
        return self.service.events().get(calendarId=calendar_id, eventId=event_id).execute()

    @exponential_backoff_retry(max_retries=3, initial_delay=1.0)
    def update_event(self, event_id: str, event_data: Dict[str, Any], calendar_id: str = 'primary') -> Dict[str, Any]:
        self._check_auth()
        return self.service.events().patch(calendarId=calendar_id, eventId=event_id, body=event_data).execute()

    @exponential_backoff_retry(max_retries=3, initial_delay=1.0)
    def delete_event(self, event_id: str, calendar_id: str = 'primary'):
        self._check_auth()
        return self.service.events().delete(calendarId=calendar_id, eventId=event_id).execute()

    @exponential_backoff_retry(max_retries=3, initial_delay=1.0)
    def watch_events(self, channel_id: str, webhook_url: str, calendar_id: str = 'primary', token: Optional[str] = None, expiration: Optional[int] = None) -> Dict[str, Any]:
        """
        Register a webhook channel for calendar changes.
        expiration: milliseconds
        """
        self._check_auth()

        body = {
            'id': channel_id,
            'type': 'web_hook',
            'address': webhook_url
        }
        if token:
            body['token'] = token
        if expiration:
            body['expiration'] = expiration

        return self.service.events().watch(calendarId=calendar_id, body=body).execute()

    @exponential_backoff_retry(max_retries=3, initial_delay=1.0)
    def stop_channel(self, channel_id: str, resource_id: str):
        """
        Stop a webhook channel.
        """
        self._check_auth()
        return self.service.channels().stop(body={
            'id': channel_id,
            'resourceId': resource_id
        }).execute()
