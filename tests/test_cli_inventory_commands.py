import json

import pytest

from semaphore_ui import cli


class InventoryClient:
    def __init__(self):
        self.inventories = [{
            "id": 1,
            "project_id": 1,
            "name": "configuration_management",
            "inventory": "inventory",
            "ssh_key_id": 2,
            "password": "secret",
            "type": "static",
        }]
        self.created = []
        self.updated = []

    def find_project(self, name):
        assert name == "configuration_management"
        return {"id": 1, "name": name}

    def list_inventories(self, project_id):
        assert project_id == 1
        return self.inventories

    def find_inventory(self, project_id, name):
        matches = [item for item in self.list_inventories(project_id) if item["name"] == name]
        assert len(matches) == 1
        return matches[0]

    def find_access_key(self, project_id, name):
        assert (project_id, name) == (1, "deploy key")
        return {"id": 3, "name": name}

    def find_repository(self, project_id, name):
        assert (project_id, name) == (1, "configuration_management")
        return {"id": 2, "project_id": 1, "name": name}

    def create_inventory(self, project_id, payload):
        self.created.append((project_id, payload))
        created = {"id": 8, "project_id": project_id, **payload}
        self.inventories.append(created)
        return created

    def update_inventory(self, project_id, inventory_id, payload):
        self.updated.append((project_id, inventory_id, payload))
        self.inventories = [
            {**item, **payload} if item["id"] == inventory_id else item
            for item in self.inventories
        ]
        return next(item for item in self.inventories if item["id"] == inventory_id)


def test_inventory_create_uses_explicit_options(monkeypatch, capsys):
    client = InventoryClient()
    monkeypatch.setattr(cli, "_client", lambda insecure=False: client)

    assert cli.main([
        "inventory", "create", "--project", "configuration_management",
        "--name", "production", "--type", "file", "--path", "inventories/production",
        "--ssh-key", "deploy key", "--become-key", "deploy key",
        "--repository", "configuration_management", "--json",
    ]) == 0

    assert client.created == [(1, {
        "name": "production", "type": "file", "inventory": "inventories/production",
        "ssh_key_id": 3, "become_key_id": 3, "repository_id": 2,
    })]
    output = json.loads(capsys.readouterr().out)
    assert output["inventory"]["name"] == "production"
    assert "inventories/production" not in json.dumps(output)


def test_inventory_copy_preserves_configuration_without_secret_output(monkeypatch, capsys):
    client = InventoryClient()
    monkeypatch.setattr(cli, "_client", lambda insecure=False: client)

    assert cli.main([
        "inventory", "copy", "--project", "configuration_management",
        "--inventory", "configuration_management", "--name", "production", "--json",
    ]) == 0

    assert client.created == [(1, {
        "name": "production", "inventory": "inventory", "ssh_key_id": 2,
        "type": "static",
    })]
    output = json.loads(capsys.readouterr().out)
    assert output["inventory"]["name"] == "production"
    assert "secret" not in json.dumps(output)


def test_inventory_update_changes_explicit_options_and_reads_back(monkeypatch, capsys):
    client = InventoryClient()
    monkeypatch.setattr(cli, "_client", lambda insecure=False: client)

    assert cli.main([
        "inventory", "update", "--project", "configuration_management",
        "--inventory", "configuration_management", "--path", "inventories/new", "--json",
    ]) == 0

    assert client.updated == [(1, 1, {
        "id": 1, "project_id": 1, "name": "configuration_management",
        "inventory": "inventories/new", "ssh_key_id": 2, "type": "static",
    })]
    output = json.loads(capsys.readouterr().out)
    assert output["configuration"]["name"] == "configuration_management"
    assert "secret" not in json.dumps(output)


def test_inventory_create_help_exposes_explicit_attributes(capsys):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["inventory", "create", "--help"])
    help_text = capsys.readouterr().out
    assert "--name" in help_text
    assert "--path" in help_text
    assert "--type" in help_text
    assert "--ssh-key" in help_text
    assert "--become-key" in help_text
    assert "--repository" in help_text
