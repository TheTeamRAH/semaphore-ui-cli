import json

import pytest

from semaphore_ui import cli


class ProjectClient:
    def list_projects(self):
        return [{"id": 1, "name": "configuration_management"}]

    def find_project(self, name):
        return {"id": 1, "name": name, "description": "Configuration management"}

    def list_templates(self, project_id):
        assert project_id == 1
        return [{"id": 7, "project_id": 1, "name": "hello_world"}]

    def find_template(self, project_id, name):
        assert project_id == 1
        return {"id": 7, "project_id": 1, "name": name}

    def create_task(self, project_id, template_id, variables):
        assert (project_id, template_id, variables) == (1, 7, {"target": "host"})
        return {"id": 4, "status": "waiting"}


def test_project_show_resolves_and_prints_one_project(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_client", lambda insecure=False: ProjectClient())

    result = cli.main(["project", "show", "--project", "configuration_management", "--json"])

    assert result == 0
    assert json.loads(capsys.readouterr().out) == {
        "id": 1,
        "name": "configuration_management",
        "description": "Configuration management",
    }


def test_project_list_prints_projects(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_client", lambda insecure=False: ProjectClient())

    assert cli.main(["project", "list", "--json"]) == 0

    assert json.loads(capsys.readouterr().out) == [{"id": 1, "name": "configuration_management"}]


def test_template_show_resolves_project_and_template(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_client", lambda insecure=False: ProjectClient())

    result = cli.main([
        "template", "show", "--project", "configuration_management", "--template", "hello_world", "--json"
    ])

    assert result == 0
    assert json.loads(capsys.readouterr().out) == {
        "id": 7,
        "name": "hello_world",
        "project_id": 1,
    }


def test_template_list_prints_templates(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_client", lambda insecure=False: ProjectClient())

    assert cli.main(["template", "list", "--project", "configuration_management", "--json"]) == 0

    assert json.loads(capsys.readouterr().out) == [{"id": 7, "project_id": 1, "name": "hello_world"}]


def test_canonical_task_run_resolves_names_and_passes_variables(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_client", lambda insecure=False: ProjectClient())

    assert cli.main([
        "task", "run", "--project", "configuration_management", "--template", "hello_world",
        "--var", "target=host", "--json"
    ]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["task"] == {"id": 4, "status": "waiting"}
    assert output["variables"] == {"target": "host"}


@pytest.mark.parametrize("command", ["projects", "templates", "tasks", "run", "status", "wait", "output"])
def test_removed_top_level_commands_are_unavailable(command):
    with pytest.raises(SystemExit) as exc_info:
        cli.build_parser().parse_args([command])

    assert exc_info.value.code == 2
