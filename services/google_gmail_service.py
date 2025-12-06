import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, List, Optional
from services.google_auth import GoogleAuthService

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

class GoogleGmailService:
    def __init__(self, user_email: str):
        """
        Args:
            user_email: The email of the user to impersonate.
        """
        self.user_email = user_email
        self.auth_service = GoogleAuthService(scopes=SCOPES, subject=user_email)
        self.service = self.auth_service.get_service('gmail', 'v1')

    def _check_auth(self):
        if not self.service:
            raise Exception("Gmail Service configuration error: Service Account or Subject invalid.")

    def send_message(self, to: str, subject: str, body_html: str) -> Dict[str, Any]:
        """
        Send an email on behalf of the user.
        """
        self._check_auth()

        message = MIMEMultipart()
        message['to'] = to
        message['from'] = self.user_email
        message['subject'] = subject

        msg = MIMEText(body_html, 'html')
        message.attach(msg)

        # Encode the message (URL-safe base64)
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        body = {'raw': raw_message}

        try:
            return self.service.users().messages().send(userId='me', body=body).execute()
        except Exception as e:
            print(f"Error sending email: {e}")
            raise e

    def get_profile(self) -> Dict[str, Any]:
        """
        Get user profile to retrieve current historyId.
        """
        self._check_auth()
        return self.service.users().getProfile(userId='me').execute()

    def list_history(self, start_history_id: str) -> Dict[str, Any]:
        """
        List history of changes since start_history_id.
        """
        self._check_auth()
        return self.service.users().history().list(userId='me', startHistoryId=start_history_id).execute()

    def list_messages(self, q: str = None, max_results: int = 50) -> Dict[str, Any]:
        """
        List messages (fallback for initial sync).
        """
        self._check_auth()
        return self.service.users().messages().list(userId='me', q=q, maxResults=max_results).execute()

    def get_message(self, message_id: str) -> Dict[str, Any]:
        """
        Get full message details.
        """
        self._check_auth()
        return self.service.users().messages().get(userId='me', id=message_id).execute()

    def get_attachment(self, message_id: str, attachment_id: str) -> Dict[str, Any]:
        """
        Get attachment data.
        """
        self._check_auth()
        return self.service.users().messages().attachments().get(userId='me', messageId=message_id, id=attachment_id).execute()
