import pytest

from semaphore_ui.api import APIError, SemaphoreClient, _normalize_task, _require_list_of_objects, _require_task_id, _require_task_status
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


def test_list_tasks_rejects_non_positive_limit():
    client = SemaphoreClient("https://semaphore.example", "secret", responses={})

    with pytest.raises(ValueError, match="task limit"):
        client.list_tasks(1, limit=0)


def test_list_tasks_rejects_malformed_environment():
    client = SemaphoreClient(
        "https://semaphore.example",
        "secret",
        responses={("GET", "/api/project/1/tasks"): [{"id": 4, "status": "success", "environment": "not-json"}]},
    )

    with pytest.raises(APIError, match="environment was invalid JSON"):
        client.list_tasks(1)


def test_shared_validators_normalize_valid_task():
    task = {"id": 4, "status": "success", "environment": '{"target":"host"}', "tpl_alias": "hello_world"}

    assert _require_task_id(task) == 4
    assert _require_task_status(task) == "success"
    assert _require_list_of_objects([task], "tasks") == [task]
    assert _normalize_task(task)["environment"] == {"target": "host"}
