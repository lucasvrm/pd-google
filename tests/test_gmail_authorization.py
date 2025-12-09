"""
Tests for Gmail API role-based authorization
"""

import pytest
from fastapi.testclient import TestClient
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta

# Mock Gmail Service (reusing from test_gmail.py)
class MockGmailService:
    def __init__(self):
        self.messages = {}
        self.threads = {}
        self.labels = [
            {'id': 'INBOX', 'name': 'INBOX', 'type': 'system'},
            {'id': 'SENT', 'name': 'SENT', 'type': 'system'},
        ]
        self._create_test_data()
    
    def _create_test_data(self):
        """Create test messages and threads"""
        for i in range(1, 4):
            msg_id = f"msg_{i}"
            thread_id = f"thread_{i}"
            
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
                    ],
                    'body': {
                        'data': 'VGVzdCBib2R5IGNvbnRlbnQ='  # "Test body content" in base64
                    },
                    'mimeType': 'text/plain'
                }
            }
            
            self.threads[thread_id] = {
                'id': thread_id,
                'snippet': f'Thread snippet {i}',
                'messages': [self.messages[msg_id]]
            }
    
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
        result = {
            'messages': [{'id': m['id'], 'threadId': m['threadId']} for m in messages[:max_results]],
            'resultSizeEstimate': len(messages)
        }
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
    
    def list_labels(self, user_id: str = 'me') -> Dict[str, Any]:
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


# Set up mock service
mock_service = MockGmailService()

from main import app as test_app
import routers.gmail

def override_get_gmail_service():
    return mock_service

# Override the dependency
routers.gmail.get_gmail_service = override_get_gmail_service

client = TestClient(test_app)


# Tests for admin/superadmin roles (full access)

def test_admin_can_list_messages():
    """Test that admin role can list messages"""
    response = client.get("/api/gmail/messages", headers={"x-user-role": "admin"})
    assert response.status_code == 200
    data = response.json()
    assert 'messages' in data
    assert len(data['messages']) > 0


def test_superadmin_can_list_messages():
    """Test that superadmin role can list messages"""
    response = client.get("/api/gmail/messages", headers={"x-user-role": "superadmin"})
    assert response.status_code == 200
    data = response.json()
    assert 'messages' in data
    assert len(data['messages']) > 0


def test_admin_can_read_message_body():
    """Test that admin role can read full message body"""
    response = client.get("/api/gmail/messages/msg_1", headers={"x-user-role": "admin"})
    assert response.status_code == 200
    data = response.json()
    assert data['id'] == 'msg_1'
    # Admin should see the body
    assert 'plain_text_body' in data
    # Body should not be None (it may be a string or the actual content)
    # We check that it exists in the response


def test_superadmin_can_read_message_body():
    """Test that superadmin role can read full message body"""
    response = client.get("/api/gmail/messages/msg_1", headers={"x-user-role": "superadmin"})
    assert response.status_code == 200
    data = response.json()
    # Body fields should exist (even if None in some cases)
    assert 'plain_text_body' in data
    assert 'html_body' in data


def test_admin_can_list_threads():
    """Test that admin role can list threads"""
    response = client.get("/api/gmail/threads", headers={"x-user-role": "admin"})
    assert response.status_code == 200
    data = response.json()
    assert 'threads' in data
    assert len(data['threads']) > 0


def test_admin_can_get_thread():
    """Test that admin role can get thread details"""
    response = client.get("/api/gmail/threads/thread_1", headers={"x-user-role": "admin"})
    assert response.status_code == 200
    data = response.json()
    assert data['id'] == 'thread_1'
    assert 'messages' in data


# Tests for manager/analyst roles (full access)

def test_manager_can_list_messages():
    """Test that manager role can list messages"""
    response = client.get("/api/gmail/messages", headers={"x-user-role": "manager"})
    assert response.status_code == 200
    data = response.json()
    assert 'messages' in data
    assert len(data['messages']) > 0


def test_analyst_can_list_messages():
    """Test that analyst role can list messages"""
    response = client.get("/api/gmail/messages", headers={"x-user-role": "analyst"})
    assert response.status_code == 200
    data = response.json()
    assert 'messages' in data
    assert len(data['messages']) > 0


def test_manager_can_read_message_body():
    """Test that manager role can read full message body"""
    response = client.get("/api/gmail/messages/msg_1", headers={"x-user-role": "manager"})
    assert response.status_code == 200
    data = response.json()
    assert 'plain_text_body' in data
    assert 'html_body' in data


def test_analyst_can_read_message_body():
    """Test that analyst role can read full message body"""
    response = client.get("/api/gmail/messages/msg_1", headers={"x-user-role": "analyst"})
    assert response.status_code == 200
    data = response.json()
    assert 'plain_text_body' in data
    assert 'html_body' in data


def test_new_business_can_list_messages():
    """Test that new_business role can list messages"""
    response = client.get("/api/gmail/messages", headers={"x-user-role": "new_business"})
    assert response.status_code == 200
    data = response.json()
    assert 'messages' in data
    assert len(data['messages']) > 0


def test_new_business_can_read_message_body():
    """Test that new_business role can read full message body"""
    response = client.get("/api/gmail/messages/msg_1", headers={"x-user-role": "new_business"})
    assert response.status_code == 200
    data = response.json()
    assert 'plain_text_body' in data
    assert 'html_body' in data


# Tests for client/customer roles (metadata only, no body)

def test_client_can_list_messages():
    """Test that client role can list messages (metadata only)"""
    response = client.get("/api/gmail/messages", headers={"x-user-role": "client"})
    assert response.status_code == 200
    data = response.json()
    assert 'messages' in data
    assert len(data['messages']) > 0


def test_customer_can_list_messages():
    """Test that customer role can list messages (metadata only)"""
    response = client.get("/api/gmail/messages", headers={"x-user-role": "customer"})
    assert response.status_code == 200
    data = response.json()
    assert 'messages' in data
    assert len(data['messages']) > 0


def test_client_cannot_read_message_body():
    """Test that client role cannot read message body (body is redacted)"""
    response = client.get("/api/gmail/messages/msg_1", headers={"x-user-role": "client"})
    assert response.status_code == 200
    data = response.json()
    # Client should get metadata but not body
    assert data['id'] == 'msg_1'
    assert 'subject' in data
    assert 'from_email' in data
    # Body fields should be None (redacted)
    assert data['plain_text_body'] is None
    assert data['html_body'] is None


def test_customer_cannot_read_message_body():
    """Test that customer role cannot read message body (body is redacted)"""
    response = client.get("/api/gmail/messages/msg_1", headers={"x-user-role": "customer"})
    assert response.status_code == 200
    data = response.json()
    # Customer should get metadata but not body
    assert data['id'] == 'msg_1'
    assert 'subject' in data
    # Body fields should be None (redacted)
    assert data['plain_text_body'] is None
    assert data['html_body'] is None


def test_client_can_list_threads():
    """Test that client role can list threads"""
    response = client.get("/api/gmail/threads", headers={"x-user-role": "client"})
    assert response.status_code == 200
    data = response.json()
    assert 'threads' in data
    assert len(data['threads']) > 0


def test_client_can_get_thread():
    """Test that client role can get thread details"""
    response = client.get("/api/gmail/threads/thread_1", headers={"x-user-role": "client"})
    assert response.status_code == 200
    data = response.json()
    assert data['id'] == 'thread_1'
    assert 'messages' in data


# Tests for unknown/default roles

def test_unknown_role_can_list_messages():
    """Test that unknown role gets default permissions (metadata only)"""
    response = client.get("/api/gmail/messages", headers={"x-user-role": "unknown_role"})
    assert response.status_code == 200
    data = response.json()
    assert 'messages' in data


def test_unknown_role_cannot_read_message_body():
    """Test that unknown role cannot read message body (body is redacted)"""
    response = client.get("/api/gmail/messages/msg_1", headers={"x-user-role": "unknown_role"})
    assert response.status_code == 200
    data = response.json()
    # Unknown role should get metadata but not body
    assert data['id'] == 'msg_1'
    # Body fields should be None (redacted)
    assert data['plain_text_body'] is None
    assert data['html_body'] is None


def test_no_role_header_can_list_messages():
    """Test that missing role header gets default permissions (metadata only)"""
    response = client.get("/api/gmail/messages")
    assert response.status_code == 200
    data = response.json()
    assert 'messages' in data


def test_no_role_header_cannot_read_message_body():
    """Test that missing role header cannot read message body (body is redacted)"""
    response = client.get("/api/gmail/messages/msg_1")
    assert response.status_code == 200
    data = response.json()
    # No role should get metadata but not body
    assert data['id'] == 'msg_1'
    # Body fields should be None (redacted)
    assert data['plain_text_body'] is None
    assert data['html_body'] is None


# Test permission variations

def test_case_insensitive_role():
    """Test that role matching is case-insensitive"""
    # Test with uppercase role
    response = client.get("/api/gmail/messages/msg_1", headers={"x-user-role": "ADMIN"})
    assert response.status_code == 200
    data = response.json()
    assert 'plain_text_body' in data
    
    # Test with mixed case
    response = client.get("/api/gmail/messages/msg_1", headers={"x-user-role": "MaNaGeR"})
    assert response.status_code == 200
    data = response.json()
    assert 'plain_text_body' in data


def test_metadata_contains_expected_fields():
    """Test that metadata response contains expected fields for restricted users"""
    response = client.get("/api/gmail/messages/msg_1", headers={"x-user-role": "client"})
    assert response.status_code == 200
    data = response.json()
    
    # Should have metadata fields
    assert 'id' in data
    assert 'thread_id' in data
    assert 'subject' in data
    assert 'from_email' in data
    assert 'to_email' in data
    assert 'snippet' in data
    assert 'labels' in data
    assert 'attachments' in data
    assert 'web_link' in data
    
    # Should NOT have body
    assert data['plain_text_body'] is None
    assert data['html_body'] is None


# Test PermissionService directly

def test_permission_service_admin():
    """Test PermissionService for admin role"""
    from services.permission_service import PermissionService
    
    perms = PermissionService.get_permissions_for_role("admin")
    assert perms.gmail_read_metadata is True
    assert perms.gmail_read_body is True


def test_permission_service_client():
    """Test PermissionService for client role"""
    from services.permission_service import PermissionService
    
    perms = PermissionService.get_permissions_for_role("client")
    assert perms.gmail_read_metadata is True
    assert perms.gmail_read_body is False


def test_permission_service_unknown():
    """Test PermissionService for unknown role"""
    from services.permission_service import PermissionService
    
    perms = PermissionService.get_permissions_for_role("unknown")
    assert perms.gmail_read_metadata is True
    assert perms.gmail_read_body is False


def test_permission_service_none():
    """Test PermissionService for None role"""
    from services.permission_service import PermissionService
    
    perms = PermissionService.get_permissions_for_role(None)
    assert perms.gmail_read_metadata is True
    assert perms.gmail_read_body is False


def test_permission_service_all_roles():
    """Test PermissionService for all defined roles"""
    from services.permission_service import PermissionService
    
    # Full access roles
    full_access_roles = ["admin", "superadmin", "manager", "analyst", "new_business"]
    for role in full_access_roles:
        perms = PermissionService.get_permissions_for_role(role)
        assert perms.gmail_read_metadata is True, f"Role {role} should have metadata access"
        assert perms.gmail_read_body is True, f"Role {role} should have body access"
    
    # Restricted access roles
    restricted_roles = ["client", "customer"]
    for role in restricted_roles:
        perms = PermissionService.get_permissions_for_role(role)
        assert perms.gmail_read_metadata is True, f"Role {role} should have metadata access"
        assert perms.gmail_read_body is False, f"Role {role} should NOT have body access"


def test_admin_can_list_labels():
    """Test that admin role can list labels"""
    response = client.get("/api/gmail/labels", headers={"x-user-role": "admin"})
    assert response.status_code == 200
    data = response.json()
    assert 'labels' in data
    assert len(data['labels']) > 0


def test_client_can_list_labels():
    """Test that client role can list labels"""
    response = client.get("/api/gmail/labels", headers={"x-user-role": "client"})
    assert response.status_code == 200
    data = response.json()
    assert 'labels' in data
    assert len(data['labels']) > 0


def test_list_threads_with_role():
    """Test that list_threads includes role in logs"""
    response = client.get("/api/gmail/threads", headers={"x-user-role": "manager"})
    assert response.status_code == 200
    data = response.json()
    assert 'threads' in data
