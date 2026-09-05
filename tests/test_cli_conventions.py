import json

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
    client = ProjectClient()
    monkeypatch.setattr(cli, "_client", lambda insecure=False: client)

    result = cli.main(["project", "show", "--project", "configuration_management", "--json"])

    assert result == 0
    assert json.loads(capsys.readouterr().out) == {
        "id": 1,
        "name": "configuration_management",
        "description": "Configuration management",
    }


def test_canonical_project_list_matches_legacy_projects(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_client", lambda insecure=False: ProjectClient())

    assert cli.main(["project", "list", "--json"]) == 0
    canonical = capsys.readouterr().out
    assert cli.main(["projects", "--json"]) == 0
    legacy = capsys.readouterr().out

    assert json.loads(canonical) == json.loads(legacy)


def test_template_show_resolves_project_and_template(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_client", lambda insecure=False: ProjectClient())

    result = cli.main(["template", "show", "--project", "configuration_management", "--template", "hello_world", "--json"])

    assert result == 0
    assert json.loads(capsys.readouterr().out) == {
        "id": 7,
        "name": "hello_world",
        "project_id": 1,
    }


def test_canonical_template_list_matches_legacy_templates(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_client", lambda insecure=False: ProjectClient())

    assert cli.main(["template", "list", "--project", "configuration_management", "--json"]) == 0
    canonical = capsys.readouterr().out
    assert cli.main(["templates", "--project", "configuration_management", "--json"]) == 0
    legacy = capsys.readouterr().out

    assert json.loads(canonical) == json.loads(legacy)


def test_canonical_task_run_matches_legacy_run(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_client", lambda insecure=False: ProjectClient())

    assert cli.main(["task", "run", "--project", "configuration_management", "--template", "hello_world", "--var", "target=host", "--json"]) == 0
    canonical = json.loads(capsys.readouterr().out)
    assert cli.main(["run", "--project", "configuration_management", "--template", "hello_world", "--var", "target=host", "--json"]) == 0
    legacy = json.loads(capsys.readouterr().out)

    assert canonical == legacy


def test_canonical_and_legacy_parsers_share_task_options_and_handlers():
    parser = cli.build_parser()
    canonical = parser.parse_args([
        "task", "list", "--project", "configuration_management", "--limit", "5",
        "--status", "success", "--template", "hello_world", "--var", "target=host",
        "--since", "2026-01-01T00:00:00Z", "--until", "2026-01-02T00:00:00Z", "--json",
    ])
    legacy = parser.parse_args([
        "tasks", "--project", "configuration_management", "--limit", "5",
        "--status", "success", "--template", "hello_world", "--var", "target=host",
        "--since", "2026-01-01T00:00:00Z", "--until", "2026-01-02T00:00:00Z", "--json",
    ])

    for field in ("project", "limit", "status", "template", "var", "since", "until", "as_json"):
        assert getattr(canonical, field) == getattr(legacy, field)
    assert canonical.handler is legacy.handler
