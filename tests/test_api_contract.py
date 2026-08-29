import pytest

from semaphore_ui.api import APIError, SemaphoreClient
from semaphore_ui.cli import _wait


def test_create_task_rejects_invalid_task_id():
    client = SemaphoreClient(
        "https://semaphore.example",
        "secret",
        responses={("POST", "/api/project/1/tasks"): {"id": None, "status": "waiting"}},
    )

    with pytest.raises(APIError, match="positive integer"):
        client.create_task(1, 7, {"target": "host"})


def test_create_task_rejects_missing_status():
    client = SemaphoreClient(
        "https://semaphore.example",
        "secret",
        responses={("POST", "/api/project/1/tasks"): {"id": 4}},
    )

    with pytest.raises(APIError, match="status"):
        client.create_task(1, 7, {"target": "host"})


def test_malformed_output_items_raise_api_error():
    client = SemaphoreClient(
        "https://semaphore.example",
        "secret",
        responses={("GET", "/api/project/1/tasks/4/output"): [{"output": "ok"}, "bad"]},
    )

    with pytest.raises(APIError, match="list of objects"):
        client.get_output(1, 4)


def test_wait_rejects_negative_interval():
    with pytest.raises(ValueError, match="poll interval"):
        _wait(object(), 1, 4, interval=-1, timeout=1)


def test_wait_rejects_negative_timeout():
    with pytest.raises(ValueError, match="timeout"):
        _wait(object(), 1, 4, interval=1, timeout=-1)
