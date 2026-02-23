"""Chat endpoint tests - verifies auth protection and structure"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestChatEndpointsUnauthenticated:
    """Chat endpoints must return 401 when not authenticated"""

    def test_post_chat_message_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/chat/message", json={"message": "hello"})
        assert r.status_code == 401, f"Expected 401, got {r.status_code}"

    def test_get_chat_sessions_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/chat/sessions")
        assert r.status_code == 401, f"Expected 401, got {r.status_code}"

    def test_get_chat_history_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/chat/history/test-session-id")
        assert r.status_code == 401, f"Expected 401, got {r.status_code}"

    def test_delete_chat_session_requires_auth(self):
        r = requests.delete(f"{BASE_URL}/api/chat/session/test-session-id")
        assert r.status_code == 401, f"Expected 401, got {r.status_code}"

    def test_chat_message_empty_returns_error_structure(self):
        """Unauthenticated; response should have proper JSON error"""
        r = requests.post(f"{BASE_URL}/api/chat/message", json={"message": ""})
        assert r.status_code in [400, 401, 422]
        data = r.json()
        assert "detail" in data
