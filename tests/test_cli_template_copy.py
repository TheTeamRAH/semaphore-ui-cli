"""Tests for copying Semaphore task templates safely."""

import json

from semaphore_ui import cli


class CopyClient:
    def __init__(self, templates=None):
        self.templates = templates or []
        self.created = []
        self.ran = False
        self.schema_checked = False

    def find_project(self, name):
        return {"id": 1, "name": name}

    def find_template(self, project_id, name):
        matches = [template for template in self.templates if template["name"] == name]
        assert len(matches) == 1
        return matches[0]

    def list_templates(self, project_id):
        return self.templates

    def assert_template_create_supported(self, payload):
        self.schema_checked = True

    def create_template(self, project_id, payload):
        assert self.schema_checked
        self.created.append(payload)
        return {"id": 7, "project_id": project_id, "name": payload["name"]}

    def create_task(self, project_id, template_id, variables):
        self.ran = True
        raise AssertionError("template copy must not run a task")


def source_template(**overrides):
    template = {
        "id": 1,
        "project_id": 1,
        "name": "hello_world",
        "repository_id": 1,
        "inventory_id": 1,
        "environment_id": 0,
        "playbook": "playbooks/hello_world.yml",
        "type": "",
        "arguments": "[]",
        "survey_vars": [
            {"name": "target", "title": "Target to run on", "required": True},
            {"name": "fact", "title": "Fact/Var ", "description": "Fact/Inventory var name to show"},
        ],
    }
    template.update(overrides)
    return template


def test_template_copy_help_and_success(monkeypatch, capsys):
    client = CopyClient([source_template()])
    monkeypatch.setattr(cli, "_client", lambda insecure=False: client)

    try:
        cli.main(["template", "copy", "--help"])
    except SystemExit as exc:
        assert exc.code == 0
    assert "source template" in capsys.readouterr().out

    assert cli.main(
        [
            "template",
            "copy",
            "--project",
            "configuration_management",
            "--template",
            "hello_world",
            "--name",
            "hello_world_copy",
            "--json",
        ]
    ) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["template"] == {"id": 7, "project_id": 1, "name": "hello_world_copy"}
    assert client.created == [
        {
            "name": "hello_world_copy",
            "repository_id": 1,
            "inventory_id": 1,
            "environment_id": 0,
            "playbook": "playbooks/hello_world.yml",
            "type": "",
            "arguments": "[]",
            "survey_vars": source_template()["survey_vars"],
            "project_id": 1,
            "app": "ansible",
        }
    ]
    assert client.ran is False


def test_template_copy_rejects_same_or_existing_destination(monkeypatch, capsys):
    client = CopyClient([source_template(), source_template(id=2, name="existing")])
    monkeypatch.setattr(cli, "_client", lambda insecure=False: client)

    for destination in ("hello_world", "existing"):
        assert cli.main(
            [
                "template",
                "copy",
                "--project",
                "configuration_management",
                "--template",
                "hello_world",
                "--name",
                destination,
            ]
        ) == 2
        assert "template" in capsys.readouterr().err

    assert client.created == []


def test_template_copy_preserves_supported_environment_vault_and_task_configuration(monkeypatch):
    client = CopyClient(
        [
            source_template(
                environment_id=4,
                vaults=[{"name": "production", "type": "password", "vault_key_id": 6}],
                task_params={"params": {"dry_run": True, "tags": ["firewall"]}},
            )
        ]
    )
    monkeypatch.setattr(cli, "_client", lambda insecure=False: client)

    assert cli.main(
        [
            "template",
            "copy",
            "--project",
            "configuration_management",
            "--template",
            "hello_world",
            "--name",
            "copy",
            "--json",
        ]
    ) == 0

    payload = client.created[0]
    assert payload["environment_id"] == 4
    assert payload["vaults"] == [{"name": "production", "type": "password", "vault_key_id": 6}]
    assert payload["task_params"] == {"params": {"dry_run": True, "tags": ["firewall"]}}


def test_template_copy_rejects_secret_survey_values_before_creation(monkeypatch, capsys):
    client = CopyClient([source_template(survey_vars=[{"name": "password", "title": "Password", "type": "secret", "default_value": "x"}])])
    monkeypatch.setattr(cli, "_client", lambda insecure=False: client)

    assert cli.main(
        [
            "template",
            "copy",
            "--project",
            "configuration_management",
            "--template",
            "hello_world",
            "--name",
            "copy",
        ]
    ) == 2
    assert "secret" in capsys.readouterr().err.lower()
    assert client.created == []
