import pytest
import httpx
from unittest.mock import patch, Mock
from quickstart import create_task, poll_status, TTVCreateError, TTVTimeoutError

PROVIDER = {
    "name": "Test",
    "create_endpoint": "/test/create",
    "status_endpoint": "/test/status",
    "payload": {"foo": "bar"},
}

def test_create_task_success():
    """Успешное создание задачи (status == True)"""
    with patch("quickstart.httpx.Client") as MockClient:
        mock_client = MockClient.return_value.__enter__.return_value
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": True, "task_id": "abc123"}
        mock_client.post.return_value = mock_response

        task_id = create_task(PROVIDER)
        assert task_id == "abc123"

def test_create_task_success_with_task_id_only():
    """Успешное создание (только task_id, без status)"""
    with patch("quickstart.httpx.Client") as MockClient:
        mock_client = MockClient.return_value.__enter__.return_value
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"task_id": "def456"}
        mock_client.post.return_value = mock_response

        task_id = create_task(PROVIDER)
        assert task_id == "def456"

def test_create_task_http_error():
    """Ошибка HTTP 400 – не ретраим, возвращаем None"""
    with patch("quickstart.httpx.Client") as MockClient:
        mock_client = MockClient.return_value.__enter__.return_value
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_client.post.return_value = mock_response

        task_id = create_task(PROVIDER)
        assert task_id is None

def test_poll_status_ready():
    """Опрос: статус ready, возвращаем URL"""
    with patch("quickstart.httpx.Client") as MockClient:
        mock_client = MockClient.return_value.__enter__.return_value
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ready", "url": "https://video.url"}
        mock_client.get.return_value = mock_response

        url = poll_status(PROVIDER, "task123")
        assert url == "https://video.url"

def test_poll_status_pending():
    """Опрос: статус pending, затем таймаут (сокращаем TIMEOUT)"""
    with patch("quickstart.httpx.Client") as MockClient, \
         patch("quickstart.TIMEOUT", 1), \
         patch("quickstart.POLL_INTERVAL", 0.1):
        mock_client = MockClient.return_value.__enter__.return_value
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "pending"}
        mock_client.get.return_value = mock_response

        url = poll_status(PROVIDER, "task123")
        assert url is None

def test_poll_status_error_code():
    """Опрос: ответ с err_code – сразу выход"""
    with patch("quickstart.httpx.Client") as MockClient:
        mock_client = MockClient.return_value.__enter__.return_value
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"err_code": "NOT_FOUND", "err_msg": "Task not found"}
        mock_client.get.return_value = mock_response

        url = poll_status(PROVIDER, "task123")
        assert url is None
def main():
    test_create_task_success()
    print("===================")
    test_create_task_success_with_task_id_only()
    print("===================")
    test_create_task_http_error()
    print("===================")
    test_poll_status_ready()
    print("===================")
    test_poll_status_pending()
    print("===================")
    test_poll_status_error_code()
    print("===================")
if __name__ == "__main__":
    main()