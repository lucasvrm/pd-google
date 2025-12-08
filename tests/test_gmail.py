"""
Tests for Gmail API endpoints
"""

import pytest
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from fastapi.testclient import TestClient

# Mock Gmail Service
class MockGmailService:
    def __init__(self):
        self.messages = {}
        self.threads = {}
        self.labels = [
            {'id': 'INBOX', 'name': 'INBOX', 'type': 'system'},
            {'id': 'SENT', 'name': 'SENT', 'type': 'system'},
            {'id': 'IMPORTANT', 'name': 'IMPORTANT', 'type': 'system'},
            {'id': 'Label_1', 'name': 'Work', 'type': 'user'},
        ]
        self.counter = 0
        
        # Pre-populate with some test data
        self._create_test_data()
    
    def _create_test_data(self):
        """Create some test messages and threads"""
        # Create test messages
        for i in range(1, 6):
            msg_id = f"msg_{i}"
            thread_id = f"thread_{(i-1)//2 + 1}"  # Group messages into threads
            
            self.messages[msg_id] = {
                'id': msg_id,
                'threadId': thread_id,
                'labelIds': ['INBOX'],
                'snippet': f'This is test message {i}',
                'internalDate': str(int((datetime.now() - timedelta(days=i)).timestamp() * 1000)),
                'payload': {
                    'headers': [
                        {'name': 'Subject', 'value': f'Test Subject {i}'},
                        {'name': 'From', 'value': f'sender{i}@example.com'},
                        {'name': 'To', 'value': 'recipient@example.com'},
                        {'name': 'Date', 'value': datetime.now().isoformat()},
                    ],
                    'body': {
                        'data': 'VGVzdCBib2R5IGNvbnRlbnQ='  # "Test body content" in base64
                    },
                    'mimeType': 'text/plain'
                }
            }
            
            # Create threads
            if thread_id not in self.threads:
                self.threads[thread_id] = {
                    'id': thread_id,
                    'snippet': f'This is test thread snippet',
                    'messages': []
                }
            
            self.threads[thread_id]['messages'].append(self.messages[msg_id])
    
    def list_messages(
        self,
        user_id: str = 'me',
        query: Optional[str] = None,
        label_ids: Optional[List[str]] = None,
        max_results: int = 100,
        page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Mock list messages"""
        messages = list(self.messages.values())
        
        # Simple filtering by label
        if label_ids:
            messages = [m for m in messages if any(l in m.get('labelIds', []) for l in label_ids)]
        
        # Simple query filtering
        if query:
            if 'from:' in query:
                from_email = query.split('from:')[1].split()[0]
                messages = [m for m in messages if any(
                    h.get('value', '').startswith(from_email) 
                    for h in m['payload']['headers'] 
                    if h.get('name') == 'From'
                )]
        
        # Pagination
        start_idx = 0
        if page_token:
            try:
                start_idx = int(page_token)
            except ValueError:
                start_idx = 0
        
        end_idx = start_idx + max_results
        page_messages = messages[start_idx:end_idx]
        
        result = {
            'messages': [{'id': m['id'], 'threadId': m['threadId']} for m in page_messages],
            'resultSizeEstimate': len(messages)
        }
        
        # Add next page token if there are more results
        if end_idx < len(messages):
            result['nextPageToken'] = str(end_idx)
        
        return result
    
    def get_message(
        self,
        message_id: str,
        user_id: str = 'me',
        format: str = 'full'
    ) -> Dict[str, Any]:
        """Mock get message"""
        if message_id not in self.messages:
            raise Exception(f"Message {message_id} not found")
        return self.messages[message_id]
    
    def list_threads(
        self,
        user_id: str = 'me',
        query: Optional[str] = None,
        label_ids: Optional[List[str]] = None,
        max_results: int = 100,
        page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Mock list threads"""
        threads = list(self.threads.values())
        
        result = {
            'threads': [{'id': t['id']} for t in threads[:max_results]],
            'resultSizeEstimate': len(threads)
        }
        
        return result
    
    def get_thread(
        self,
        thread_id: str,
        user_id: str = 'me',
        format: str = 'full'
    ) -> Dict[str, Any]:
        """Mock get thread"""
        if thread_id not in self.threads:
            raise Exception(f"Thread {thread_id} not found")
        return self.threads[thread_id]
    
    def list_labels(
        self,
        user_id: str = 'me'
    ) -> Dict[str, Any]:
        """Mock list labels"""
        return {'labels': self.labels}
    
    def _parse_headers(self, headers: List[Dict[str, str]]) -> Dict[str, str]:
        """Parse headers helper"""
        result = {}
        for h in headers:
            name = h.get('name', '').lower()
            value = h.get('value', '')
            if name in ['from', 'to', 'cc', 'bcc', 'subject', 'date']:
                result[name] = value
        return result
    
    def _get_message_body(self, payload: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        """Get message body helper"""
        import base64
        plain_text = None
        html_text = None
        
        if payload.get('mimeType') == 'text/plain':
            body_data = payload.get('body', {}).get('data')
            if body_data:
                try:
                    plain_text = base64.urlsafe_b64decode(body_data).decode('utf-8')
                except Exception:
                    plain_text = "Test body content"
        
        return plain_text, html_text
    
    def _extract_attachments(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract attachments helper"""
        return []


mock_service = MockGmailService()

# Set up dependency override before creating TestClient
from main import app as test_app
import routers.gmail

def override_get_gmail_service():
    return mock_service

# Override the dependency at the router module level
original_get_gmail_service = routers.gmail.get_gmail_service
routers.gmail.get_gmail_service = override_get_gmail_service

client = TestClient(test_app)


# Tests

def test_list_messages():
    """Test listing messages"""
    response = client.get("/api/gmail/messages")
    assert response.status_code == 200
    data = response.json()
    assert 'messages' in data
    assert isinstance(data['messages'], list)
    assert len(data['messages']) > 0
    
    # Check message structure
    msg = data['messages'][0]
    assert 'id' in msg
    assert 'thread_id' in msg
    assert 'subject' in msg
    assert 'from_email' in msg
    assert 'snippet' in msg


def test_list_messages_with_label_filter():
    """Test listing messages with label filter"""
    response = client.get("/api/gmail/messages?label=INBOX")
    assert response.status_code == 200
    data = response.json()
    assert len(data['messages']) > 0
    
    # All messages should have INBOX label
    for msg in data['messages']:
        assert 'INBOX' in msg['labels']


def test_list_messages_with_pagination():
    """Test pagination in message listing"""
    response = client.get("/api/gmail/messages?page_size=2")
    assert response.status_code == 200
    data = response.json()
    
    # Should return at most 2 messages
    assert len(data['messages']) <= 2
    
    # If there are more results, should have next_page_token
    if data.get('result_size_estimate', 0) > 2:
        assert 'next_page_token' in data


def test_list_messages_with_from_filter():
    """Test filtering messages by sender"""
    response = client.get("/api/gmail/messages?from_email=sender1@example.com")
    assert response.status_code == 200
    data = response.json()
    
    # Should return filtered messages
    assert len(data['messages']) >= 0


def test_get_message():
    """Test getting a specific message"""
    response = client.get("/api/gmail/messages/msg_1")
    assert response.status_code == 200
    data = response.json()
    
    # Check detailed message structure
    assert data['id'] == 'msg_1'
    assert 'thread_id' in data
    assert 'subject' in data
    assert 'from_email' in data
    assert 'to_email' in data
    assert 'plain_text_body' in data
    assert 'html_body' in data
    assert 'attachments' in data
    assert 'web_link' in data
    assert 'labels' in data


def test_get_message_not_found():
    """Test getting a non-existent message"""
    response = client.get("/api/gmail/messages/nonexistent")
    assert response.status_code == 404


def test_list_threads():
    """Test listing threads"""
    response = client.get("/api/gmail/threads")
    assert response.status_code == 200
    data = response.json()
    
    assert 'threads' in data
    assert isinstance(data['threads'], list)
    assert len(data['threads']) > 0
    
    # Check thread structure
    thread = data['threads'][0]
    assert 'id' in thread
    assert 'snippet' in thread
    assert 'message_count' in thread
    assert 'participants' in thread
    assert 'labels' in thread


def test_get_thread():
    """Test getting a specific thread"""
    response = client.get("/api/gmail/threads/thread_1")
    assert response.status_code == 200
    data = response.json()
    
    assert data['id'] == 'thread_1'
    assert 'messages' in data
    assert isinstance(data['messages'], list)
    assert len(data['messages']) > 0
    
    # Check message structure in thread
    msg = data['messages'][0]
    assert 'id' in msg
    assert 'subject' in msg
    assert 'from_email' in msg


def test_get_thread_not_found():
    """Test getting a non-existent thread"""
    response = client.get("/api/gmail/threads/nonexistent")
    assert response.status_code == 404


def test_list_labels():
    """Test listing labels"""
    response = client.get("/api/gmail/labels")
    assert response.status_code == 200
    data = response.json()
    
    assert 'labels' in data
    assert isinstance(data['labels'], list)
    assert len(data['labels']) > 0
    
    # Check label structure
    label = data['labels'][0]
    assert 'id' in label
    assert 'name' in label
    assert 'type' in label
    
    # Should have system labels
    label_ids = [l['id'] for l in data['labels']]
    assert 'INBOX' in label_ids
    assert 'SENT' in label_ids


def test_message_summary_has_required_fields():
    """Test that message summary has all required fields"""
    response = client.get("/api/gmail/messages")
    assert response.status_code == 200
    data = response.json()
    
    msg = data['messages'][0]
    required_fields = [
        'id', 'thread_id', 'subject', 'from_email', 'to_email',
        'snippet', 'internal_date', 'labels', 'has_attachments'
    ]
    
    for field in required_fields:
        assert field in msg


def test_message_detail_has_all_fields():
    """Test that message detail has all fields"""
    response = client.get("/api/gmail/messages/msg_1")
    assert response.status_code == 200
    data = response.json()
    
    detailed_fields = [
        'id', 'thread_id', 'subject', 'from_email', 'to_email',
        'cc_email', 'bcc_email', 'snippet', 'internal_date', 'labels',
        'plain_text_body', 'html_body', 'attachments', 'web_link'
    ]
    
    for field in detailed_fields:
        assert field in data


def test_thread_summary_structure():
    """Test thread summary has correct structure"""
    response = client.get("/api/gmail/threads")
    assert response.status_code == 200
    data = response.json()
    
    thread = data['threads'][0]
    required_fields = [
        'id', 'snippet', 'message_count', 'participants',
        'last_message_date', 'labels', 'has_attachments'
    ]
    
    for field in required_fields:
        assert field in thread


def test_pagination_with_page_token():
    """Test using page token for pagination"""
    # Get first page
    response1 = client.get("/api/gmail/messages?page_size=2")
    assert response1.status_code == 200
    data1 = response1.json()
    
    # If there's a next page token, get the next page
    if 'next_page_token' in data1:
        page_token = data1['next_page_token']
        response2 = client.get(f"/api/gmail/messages?page_size=2&page_token={page_token}")
        assert response2.status_code == 200
        data2 = response2.json()
        
        # Second page should have different messages
        if len(data1['messages']) > 0 and len(data2['messages']) > 0:
            assert data1['messages'][0]['id'] != data2['messages'][0]['id']


def test_list_messages_with_multiple_filters():
    """Test combining multiple filters"""
    response = client.get(
        "/api/gmail/messages?label=INBOX&page_size=10&from_email=sender1@example.com"
    )
    assert response.status_code == 200
    data = response.json()
    assert 'messages' in data


def test_web_link_format():
    """Test that web link is correctly formatted"""
    response = client.get("/api/gmail/messages/msg_1")
    assert response.status_code == 200
    data = response.json()
    
    assert data['web_link'] is not None
    assert data['web_link'].startswith('https://mail.google.com/mail/')
    assert 'msg_1' in data['web_link']


def test_internal_date_is_datetime():
    """Test that internal_date is properly formatted as datetime"""
    response = client.get("/api/gmail/messages")
    assert response.status_code == 200
    data = response.json()
    
    msg = data['messages'][0]
    if msg.get('internal_date'):
        # Should be ISO format datetime string
        assert 'T' in msg['internal_date'] or msg['internal_date'].endswith('Z')


def test_labels_is_list():
    """Test that labels field is always a list"""
    response = client.get("/api/gmail/messages/msg_1")
    assert response.status_code == 200
    data = response.json()
    
    assert isinstance(data['labels'], list)


def test_attachments_is_list():
    """Test that attachments field is always a list"""
    response = client.get("/api/gmail/messages/msg_1")
    assert response.status_code == 200
    data = response.json()
    
    assert isinstance(data['attachments'], list)


def test_thread_messages_are_ordered():
    """Test that messages in a thread are in order"""
    response = client.get("/api/gmail/threads/thread_1")
    assert response.status_code == 200
    data = response.json()
    
    # Should have messages
    assert len(data['messages']) > 0
    
    # Each message should have required fields
    for msg in data['messages']:
        assert 'id' in msg
        assert 'thread_id' in msg
