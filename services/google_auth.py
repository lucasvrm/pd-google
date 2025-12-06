import json
from typing import List, Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from config import config

class GoogleAuthService:
    """
    Centralized service for handling Google Service Account authentication.
    """

    def __init__(self, scopes: List[str], subject: Optional[str] = None):
        """
        Args:
            scopes: List of OAuth scopes.
            subject: Email of the user to impersonate (requires Domain-Wide Delegation).
        """
        self.scopes = scopes
        self.subject = subject
        self.creds = None
        self._authenticate()

    def _authenticate(self):
        if not config.GOOGLE_SERVICE_ACCOUNT_JSON:
            print("Warning: GOOGLE_SERVICE_ACCOUNT_JSON not set. Google Services will fail.")
            return

        try:
            # Handle if the env var is a file path or the JSON content string
            if config.GOOGLE_SERVICE_ACCOUNT_JSON.strip().startswith("{"):
                info = json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON)
                creds = service_account.Credentials.from_service_account_info(info, scopes=self.scopes)
            else:
                creds = service_account.Credentials.from_service_account_file(
                    config.GOOGLE_SERVICE_ACCOUNT_JSON, scopes=self.scopes
                )

            # If subject is provided, we perform impersonation
            if self.subject:
                creds = creds.with_subject(self.subject)

            self.creds = creds

        except Exception as e:
            print(f"Authentication failed: {e}")
            self.creds = None

    def get_service(self, service_name: str, version: str):
        if not self.creds:
            return None
        return build(service_name, version, credentials=self.creds)
