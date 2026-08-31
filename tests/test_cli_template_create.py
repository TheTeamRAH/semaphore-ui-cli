"""CLI tests for explicit Semaphore template creation."""

import json

from semaphore_ui import cli


class FakeClient:
    schema_checked = False

    def find_project(self, name):
        assert name == "configuration_management"
        return {"id": 1, "name": name}

    def find_repository(self, project_id, name):
        assert (project_id, name) == (1, "configuration-management")
        return {"id": 2, "name": name}

    def find_inventory(self, project_id, name):
        assert (project_id, name) == (1, "homelab")
        return {"id": 3, "name": name}

    def find_environment(self, project_id, name):
        assert (project_id, name) == (1, "default")
        return {"id": 4, "name": name}

    def find_view(self, project_id, name):
        assert (project_id, name) == (1, "operations")
        return {"id": 5, "name": name}

    def find_access_key(self, project_id, name):
        assert (project_id, name) == (1, "Production vault password")
        return {"id": 6, "name": name}

    def create_template(self, project_id, payload):
        assert self.schema_checked
        assert project_id == 1
        expected = {
            "name": "show-firewall-interface",
            "repository_id": 2,
            "inventory_id": 3,
            "environment_id": 4,
            "playbook": "site.yml",
            "type": "",
        }
        assert payload.items() >= expected.items()
        return {
            "id": 5,
            "project_id": 1,
            "name": payload["name"],
            "survey_vars": [{"name": "password", "value": "secret"}],
        }

    def assert_template_create_supported(self, payload):
        assert payload["project_id"] == 1
        self.schema_checked = True


def test_template_create_resolves_names_and_prints_safe_json(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_client", lambda insecure=False: FakeClient())

    result = cli.main(
        [
            "template",
            "create",
            "--project",
            "configuration_management",
            "--name",
            "show-firewall-interface",
            "--repository",
            "configuration-management",
            "--inventory",
            "homelab",
            "--environment",
            "default",
            "--playbook",
            "site.yml",
            "--git-branch",
            "main",
            "--json",
        ]
    )

    assert result == 0
    output = json.loads(capsys.readouterr().out)
    assert output == {
        "configuration": {
            "environment": {"id": 4, "name": "default"},
            "git_branch": "main",
            "inventory": {"id": 3, "name": "homelab"},
            "playbook": "site.yml",
            "repository": {"id": 2, "name": "configuration-management"},
            "type": "",
        },
        "project": {"id": 1, "name": "configuration_management"},
        "template": {"id": 5, "name": "show-firewall-interface", "project_id": 1},
    }


def test_template_create_reads_advanced_request_file(monkeypatch, capsys, tmp_path):
    request_file = tmp_path / "template.json"
    request_file.write_text(
        json.dumps(
            {
                "name": "show-firewall-interface",
                "repository": "configuration-management",
                "inventory": "homelab",
                "environment": "default",
                "playbook": "site.yml",
                "git_branch": "main",
                "survey_vars": [
                    {"name": "target", "title": "Target", "type": "", "required": True}
                ],
                "task_params": {"params": {"dry_run": True, "tags": ["firewall"]}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "_client", lambda insecure=False: FakeClient())

    result = cli.main(
        ["template", "create", "--project", "configuration_management", "--file", str(request_file)]
    )

    assert result == 0
    assert capsys.readouterr().out == "Created template 5: show-firewall-interface\n"


def test_template_create_resolves_an_optional_view(monkeypatch, tmp_path):
    request_file = tmp_path / "template.json"
    request_file.write_text(
        json.dumps(
            {
                "name": "show-firewall-interface",
                "repository": "configuration-management",
                "inventory": "homelab",
                "environment": "default",
                "playbook": "site.yml",
                "view": "operations",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "_client", lambda insecure=False: FakeClient())

    assert cli.main(["template", "create", "--project", "configuration_management", "--file", str(request_file)]) == 0


def test_template_create_preserves_defaults_and_resolves_vault_keys(monkeypatch, capsys, tmp_path):
    request_file = tmp_path / "template.json"
    request_file.write_text(
        json.dumps(
            {
                "name": "show-firewall-interface",
                "repository": "configuration-management",
                "inventory": "homelab",
                "environment": "default",
                "playbook": "site.yml",
                "survey_vars": [
                    {
                        "name": "target",
                        "title": "Target",
                        "type": "select",
                        "values": [
                            {"name": "Web 1", "value": "web-01"},
                            {"name": "Web 2", "value": "web-02"},
                        ],
                        "default_value": ["web-01", "web-02"],
                    }
                ],
                "vaults": [
                    {
                        "name": "production",
                        "type": "password",
                        "vault_key": "Production vault password",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    class VaultClient(FakeClient):
        def create_template(self, project_id, payload):
            assert project_id == 1
            assert payload["survey_vars"][0]["default_value"] == ["web-01", "web-02"]
            assert payload["vaults"] == [
                {"name": "production", "type": "password", "vault_key_id": 6}
            ]
            return {"id": 5, "project_id": 1, "name": payload["name"]}

    monkeypatch.setattr(cli, "_client", lambda insecure=False: VaultClient())

    assert cli.main(["template", "create", "--project", "configuration_management", "--file", str(request_file), "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["configuration"]["vaults"] == [
        {"key": {"id": 6, "name": "Production vault password"}, "name": "production", "type": "password"}
    ]
    assert "default_value" not in json.dumps(output)


def test_template_create_rejects_secret_survey_default_before_api_lookup(monkeypatch, tmp_path):
    request_file = tmp_path / "template.json"
    request_file.write_text(
        json.dumps(
            {
                "name": "template",
                "repository": "repository",
                "inventory": "inventory",
                "environment": "environment",
                "playbook": "site.yml",
                "survey_vars": [
                    {"name": "password", "title": "Password", "type": "secret", "default_value": "secret"}
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "_client", lambda insecure=False: object())

    assert cli.main(["template", "create", "--project", "project", "--file", str(request_file)]) == 2


def test_template_create_rejects_an_invalid_project_id_before_resource_lookup(monkeypatch):
    class InvalidProjectClient:
        def find_project(self, name):
            return {"id": True, "name": name}

        def find_repository(self, project_id, name):
            raise AssertionError("resource lookup must not occur")

    monkeypatch.setattr(cli, "_client", lambda insecure=False: InvalidProjectClient())

    result = cli.main(
        [
            "template", "create", "--project", "configuration_management", "--name", "template",
            "--repository", "repository", "--inventory", "inventory", "--environment", "environment",
            "--playbook", "site.yml",
        ]
    )

    assert result == 2


def test_template_create_rejects_conflicting_or_secret_request_before_api_lookup(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "_client", lambda insecure=False: object())
    request_file = tmp_path / "template.json"
    request_file.write_text("{}", encoding="utf-8")

    result = cli.main(
        [
            "template",
            "create",
            "--project",
            "configuration_management",
            "--file",
            str(request_file),
            "--name",
            "conflict",
        ]
    )

    assert result == 2

    secret_request = tmp_path / "secret-template.json"
    secret_request.write_text(
        json.dumps(
            {
                "name": "template",
                "repository": "repo",
                "inventory": "inventory",
                "environment": "environment",
                "playbook": "site.yml",
                "survey_vars": [
                    {"name": "password", "title": "Password", "type": "secret", "values": [{"name": "x", "value": "secret"}]}
                ],
            }
        ),
        encoding="utf-8",
    )

    assert cli.main(["template", "create", "--project", "project", "--file", str(secret_request)]) == 2
