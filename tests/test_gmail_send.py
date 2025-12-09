import base64

from fastapi.testclient import TestClient

from main import app as test_app
import routers.gmail


class MockGmailSendService:
    def __init__(self):
        self.sent_payload = None
        self.drafts = {}
        self.labels = {}

    def send_email(self, **kwargs):
        self.sent_payload = kwargs
        return {
            "id": "msg_123",
            "threadId": kwargs.get("thread_id"),
            "labelIds": ["SENT"],
        }

    def create_draft(self, **kwargs):
        draft_id = f"draft_{len(self.drafts) + 1}"
        raw = kwargs.get("body_text", "")
        self.drafts[draft_id] = {
            "id": draft_id,
            "message": {"id": f"msg_{draft_id}", "threadId": kwargs.get("thread_id"), "raw": raw},
        }
        return self.drafts[draft_id]

    def get_draft(self, draft_id: str):
        if draft_id not in self.drafts:
            raise Exception("404")
        return self.drafts[draft_id]

    def _build_message(self, **kwargs):
        # minimal stand-in for private builder; encode a simple payload
        return base64.urlsafe_b64encode(kwargs.get("body_text", "").encode()).decode()

    def update_draft(self, draft_id: str, message):
        self.drafts[draft_id] = {"id": draft_id, "message": message}
        return self.drafts[draft_id]

    def delete_draft(self, draft_id: str):
        if draft_id not in self.drafts:
            raise Exception("404")
        del self.drafts[draft_id]

    def update_labels(self, message_id: str, add_labels=None, remove_labels=None):
        self.labels[message_id] = (add_labels or [], remove_labels or [])
        return {"id": message_id, "labelIds": [*(add_labels or []), "EXISTING"]}


mock_send_service = MockGmailSendService()


def override_gmail_send_service():
    return mock_send_service


test_app.dependency_overrides[routers.gmail.get_gmail_send_service] = override_gmail_send_service

client = TestClient(test_app)


def test_send_message_route():
    payload = {
        "to": ["recipient@example.com"],
        "subject": "Hello",
        "body_text": "Test",
    }
    response = client.post("/api/gmail/send", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "msg_123"
    assert mock_send_service.sent_payload["to"] == ["recipient@example.com"]


def test_create_and_get_draft():
    payload = {
        "to": ["recipient@example.com"],
        "subject": "Draft",
        "body_text": "Draft body",
    }
    create_resp = client.post("/api/gmail/drafts", json=payload)
    assert create_resp.status_code == 200
    draft_data = create_resp.json()
    draft_id = draft_data["id"]

    get_resp = client.get(f"/api/gmail/drafts/{draft_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == draft_id


def test_update_labels_route():
    payload = {"add_labels": ["IMPORTANT"], "remove_labels": ["SPAM"]}
    resp = client.post("/api/gmail/messages/abc123/labels", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "abc123"
    assert "IMPORTANT" in data["label_ids"]
