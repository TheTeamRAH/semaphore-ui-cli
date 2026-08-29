import pytest

from semaphore_ui.api import TaskTimeoutError
from semaphore_ui.cli import _wait


class SequencedClient:
    def __init__(self, statuses):
        self.statuses = iter(statuses)

    def get_task(self, project_id, task_id):
        return {"id": task_id, "status": next(self.statuses)}


def test_wait_returns_when_task_reaches_success():
    client = SequencedClient(["waiting", "success"])

    result = _wait(client, 1, 4, interval=0, timeout=1)

    assert result["status"] == "success"


def test_wait_times_out_for_non_terminal_task():
    client = SequencedClient(["waiting", "waiting", "waiting"])

    with pytest.raises(TaskTimeoutError):
        _wait(client, 1, 4, interval=0, timeout=0)
