from typing import Dict, Any, List, Optional, Tuple
from services.google_auth import GoogleAuthService
import base64
import re
from email.utils import parsedate_to_datetime

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

class GoogleGmailService:
    """
    Service for interacting with Gmail API for read-only operations.
    Handles listing messages, threads, labels and retrieving message details.
    """
    
    def __init__(self):
        self.auth_service = GoogleAuthService(scopes=SCOPES)
        self.service = self.auth_service.get_service('gmail', 'v1')
    
    def _check_auth(self):
        """Verify that the Gmail service is properly authenticated."""
        if not self.service:
            raise Exception("Gmail Service configuration error: GOOGLE_SERVICE_ACCOUNT_JSON is missing or invalid.")
    
    def list_messages(
        self,
        user_id: str = 'me',
        query: Optional[str] = None,
        label_ids: Optional[List[str]] = None,
        max_results: int = 100,
        page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List messages from Gmail inbox.
        
        Args:
            user_id: The user's email address. Use 'me' for authenticated user.
            query: Gmail search query (e.g., 'from:user@example.com subject:important')
            label_ids: List of label IDs to filter by
            max_results: Maximum number of messages to return (1-500)
            page_token: Token for pagination
            
        Returns:
            Dictionary with 'messages' list and optional 'nextPageToken'
        """
        self._check_auth()
        
        kwargs = {
            'userId': user_id,
            'maxResults': min(max_results, 500)
        }
        
        if query:
            kwargs['q'] = query
        if label_ids:
            kwargs['labelIds'] = label_ids
        if page_token:
            kwargs['pageToken'] = page_token
        
        try:
            return self.service.users().messages().list(**kwargs).execute()
        except Exception as e:
            raise Exception(f"Failed to list messages: {str(e)}")
    
    def get_message(
        self,
        message_id: str,
        user_id: str = 'me',
        format: str = 'full'
    ) -> Dict[str, Any]:
        """
        Get a specific message by ID.
        
        Args:
            message_id: The message ID
            user_id: The user's email address
            format: Message format ('full', 'metadata', 'minimal', 'raw')
            
        Returns:
            Complete message data from Gmail API
        """
        self._check_auth()
        
        try:
            return self.service.users().messages().get(
                userId=user_id,
                id=message_id,
                format=format
            ).execute()
        except Exception as e:
            raise Exception(f"Failed to get message {message_id}: {str(e)}")
    
    def list_threads(
        self,
        user_id: str = 'me',
        query: Optional[str] = None,
        label_ids: Optional[List[str]] = None,
        max_results: int = 100,
        page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List email threads.
        
        Args:
            user_id: The user's email address
            query: Gmail search query
            label_ids: List of label IDs to filter by
            max_results: Maximum number of threads to return (1-500)
            page_token: Token for pagination
            
        Returns:
            Dictionary with 'threads' list and optional 'nextPageToken'
        """
        self._check_auth()
        
        kwargs = {
            'userId': user_id,
            'maxResults': min(max_results, 500)
        }
        
        if query:
            kwargs['q'] = query
        if label_ids:
            kwargs['labelIds'] = label_ids
        if page_token:
            kwargs['pageToken'] = page_token
        
        try:
            return self.service.users().threads().list(**kwargs).execute()
        except Exception as e:
            raise Exception(f"Failed to list threads: {str(e)}")
    
    def get_thread(
        self,
        thread_id: str,
        user_id: str = 'me',
        format: str = 'full'
    ) -> Dict[str, Any]:
        """
        Get a specific thread by ID.
        
        Args:
            thread_id: The thread ID
            user_id: The user's email address
            format: Message format for messages in thread
            
        Returns:
            Complete thread data with all messages
        """
        self._check_auth()
        
        try:
            return self.service.users().threads().get(
                userId=user_id,
                id=thread_id,
                format=format
            ).execute()
        except Exception as e:
            raise Exception(f"Failed to get thread {thread_id}: {str(e)}")
    
    def list_labels(
        self,
        user_id: str = 'me'
    ) -> Dict[str, Any]:
        """
        List all labels in the user's mailbox.
        
        Args:
            user_id: The user's email address
            
        Returns:
            Dictionary with 'labels' list
        """
        self._check_auth()
        
        try:
            return self.service.users().labels().list(userId=user_id).execute()
        except Exception as e:
            raise Exception(f"Failed to list labels: {str(e)}")
    
    # Helper methods for parsing Gmail API responses
    
    def _parse_headers(self, headers: List[Dict[str, str]]) -> Dict[str, str]:
        """Extract common headers from message headers list."""
        header_dict = {}
        for header in headers:
            name = header.get('name', '').lower()
            value = header.get('value', '')
            if name in ['from', 'to', 'cc', 'bcc', 'subject', 'date']:
                header_dict[name] = value
        return header_dict
    
    def _get_message_body(self, payload: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract plain text and HTML body from message payload.
        
        Returns:
            Tuple of (plain_text_body, html_body)
        """
        plain_text = None
        html_text = None
        
        def decode_body(data: str) -> str:
            """Decode base64url encoded body data."""
            if not data:
                return ""
            try:
                return base64.urlsafe_b64decode(data).decode('utf-8')
            except Exception:
                return ""
        
        def extract_body_recursive(part: Dict[str, Any]):
            """Recursively extract body from multipart message."""
            nonlocal plain_text, html_text
            
            mime_type = part.get('mimeType', '')
            
            if mime_type == 'text/plain' and not plain_text:
                body_data = part.get('body', {}).get('data')
                if body_data:
                    plain_text = decode_body(body_data)
            elif mime_type == 'text/html' and not html_text:
                body_data = part.get('body', {}).get('data')
                if body_data:
                    html_text = decode_body(body_data)
            
            # Recurse into parts
            if 'parts' in part:
                for subpart in part['parts']:
                    extract_body_recursive(subpart)
        
        extract_body_recursive(payload)
        return plain_text, html_text
    
    def _extract_attachments(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract attachment information from message payload.
        
        Returns:
            List of attachment dictionaries with id, filename, mimeType, size
        """
        attachments = []
        
        def extract_attachments_recursive(part: Dict[str, Any]):
            """Recursively find attachments in message parts."""
            filename = part.get('filename')
            body = part.get('body', {})
            
            if filename and body.get('attachmentId'):
                attachments.append({
                    'id': body.get('attachmentId'),
                    'filename': filename,
                    'mimeType': part.get('mimeType', 'application/octet-stream'),
                    'size': body.get('size', 0)
                })
            
            # Recurse into parts
            if 'parts' in part:
                for subpart in part['parts']:
                    extract_attachments_recursive(subpart)
        
        extract_attachments_recursive(payload)
        return attachments
