import json

import pytest

from semaphore_ui.api import LookupError, SemaphoreClient
from semaphore_ui.cli import _plain, _variables


def test_create_task_encodes_environment_as_semaphore_json():
    responses = {
        ("POST", "/api/project/1/tasks"): {"id": 4, "status": "waiting"},
    }
    client = SemaphoreClient("https://semaphore.example", "secret", responses=responses)

    task = client.create_task(1, 7, {"target": "hermes-001.iot.home", "fact": "firewall_interface"})

    assert task["id"] == 4


def test_create_task_payload_is_available_to_fake_transport():
    seen = {}

    def opener(request, timeout):
        seen["body"] = request.data
        raise AssertionError("not used in this test")

    client = SemaphoreClient("https://semaphore.example", "secret", opener=opener)
    with pytest.raises(AssertionError):
        client.create_task(1, 7, {"target": "host", "fact": "value"})

    payload = json.loads(seen["body"])
    assert payload == {"template_id": 7, "environment": '{"target":"host","fact":"value"}'}


def test_duplicate_project_names_are_rejected():
    responses = {
        ("GET", "/api/projects"): [{"id": 1, "name": "same"}, {"id": 2, "name": "same"}],
    }
    client = SemaphoreClient("https://semaphore.example", "secret", responses=responses)

    with pytest.raises(LookupError, match="Multiple"):
        client.find_project("same")


def test_variables_require_name_and_value():
    with pytest.raises(ValueError, match="NAME=VALUE"):
        _variables(["target"])


def test_plain_output_removes_ansi_escape_sequences():
    assert _plain("\033[0;32mok\033[0m: host") == "ok: host"


def test_list_tasks_parses_environment_and_applies_limit():
    client = SemaphoreClient(
        "https://semaphore.example",
        "secret",
        responses={
            ("GET", "/api/project/1/tasks"): [
                {"id": 4, "status": "success", "tpl_alias": "hello_world", "environment": '{"target":"host-a","fact":"fact_a"}'},
                {"id": 3, "status": "error", "tpl_alias": "hello_world", "environment": '{"target":"host-b","fact":"fact_b"}'},
            ]
        },
    )

    tasks = client.list_tasks(1, limit=1)

    assert tasks == [
        {
            "id": 4,
            "status": "success",
            "template": {"name": "hello_world"},
            "environment": {"target": "host-a", "fact": "fact_a"},
        }
    ]
