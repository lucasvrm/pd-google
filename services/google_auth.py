import json
from typing import List, Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from config import config

class GoogleAuthService:
    """
    Centralized service for handling Google Service Account authentication.
    Supports Domain-Wide Delegation (impersonation) if GOOGLE_IMPERSONATE_EMAIL is set.
    """

    def __init__(self, scopes: List[str]):
        self.scopes = scopes
        self.creds = None
        self._authenticate()

    def _authenticate(self):
        if not config.GOOGLE_SERVICE_ACCOUNT_JSON:
            print("Warning: GOOGLE_SERVICE_ACCOUNT_JSON not set. Google Services will fail.")
            return

        try:
            # 1. Carrega as credenciais básicas (identidade do robô)
            if config.GOOGLE_SERVICE_ACCOUNT_JSON.strip().startswith("{"):
                info = json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON)
                self.creds = service_account.Credentials.from_service_account_info(info, scopes=self.scopes)
            else:
                self.creds = service_account.Credentials.from_service_account_file(
                    config.GOOGLE_SERVICE_ACCOUNT_JSON, scopes=self.scopes
                )
            
            # 2. [MODIFICAÇÃO] Aplica Impersonation (se configurado)
            # Transforma o robô no usuário real (ex: admin@suaempresa.com)
            if config.GOOGLE_IMPERSONATE_EMAIL:
                print(f"Authentication: Impersonating user {config.GOOGLE_IMPERSONATE_EMAIL}")
                self.creds = self.creds.with_subject(config.GOOGLE_IMPERSONATE_EMAIL)
            else:
                print("Authentication: Using Service Account directly (No impersonation)")

        except Exception as e:
            print(f"Authentication failed: {e}")
            self.creds = None

    def get_service(self, service_name: str, version: str):
        if not self.creds:
            return None
        return build(service_name, version, credentials=self.creds)
