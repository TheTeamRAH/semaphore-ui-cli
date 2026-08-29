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


from argparse import Namespace
import json
from semaphore_ui.cli import _handle_tasks


def test_tasks_handler_filters_by_variables_and_prints_json(capsys):
    class Client:
        def find_project(self, name):
            return {"id": 1, "name": name}

        def list_tasks(self, project_id, limit):
            return [
                {"id": 4, "status": "success", "template": {"name": "hello_world"}, "environment": {"target": "host-a", "fact": "fact_a"}},
                {"id": 3, "status": "success", "template": {"name": "hello_world"}, "environment": {"target": "host-b", "fact": "fact_b"}},
            ]

    args = Namespace(project="configuration_management", limit=20, status=None, template=None, var=["target=host-b", "fact=fact_b"], as_json=True)

    assert _handle_tasks(args, Client()) == 0
    output = json.loads(capsys.readouterr().out)
    assert [task["id"] for task in output["tasks"]] == [3]


def test_tasks_handler_filters_by_creation_time(capsys):
    class Client:
        def find_project(self, name):
            return {"id": 1, "name": name}

        def list_tasks(self, project_id, limit):
            return [
                {"id": 4, "status": "success", "created": "2026-08-29T10:00:00Z", "template": {"name": "hello_world"}, "environment": {}},
                {"id": 3, "status": "success", "created": "2026-08-29T12:00:00Z", "template": {"name": "hello_world"}, "environment": {}},
            ]

    args = Namespace(project="configuration_management", limit=20, status=None, template=None, var=[], since="2026-08-29T11:00:00Z", until=None, as_json=True)

    assert _handle_tasks(args, Client()) == 0
    output = json.loads(capsys.readouterr().out)
    assert [task["id"] for task in output["tasks"]] == [3]
