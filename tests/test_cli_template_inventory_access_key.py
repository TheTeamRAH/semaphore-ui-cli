import json

from semaphore_ui import cli


class ResourceClient:
    def __init__(self):
        self.updated_templates = []
        self.templates = [{
            "id": 7, "project_id": 1, "name": "hello_world", "repository_id": 2,
            "inventory_id": 1, "environment_id": 0, "playbook": "playbooks/hello_world.yml",
            "git_branch": "master", "type": "", "app": "ansible",
            "allow_override_branch_in_task": True,
        }]
        self.inventories = [{
            "id": 1, "project_id": 1, "name": "configuration_management",
            "inventory": "inventory", "ssh_key_id": 2, "password": "secret",
        }]
        self.access_keys = [{
            "id": 3, "project_id": 1, "name": "deploy key", "type": "ssh",
            "login": "git", "private_key": "secret",
        }]
        self.created_inventories = []
        self.updated_inventories = []

    def find_project(self, name):
        assert name == "configuration_management"
        return {"id": 1, "name": name}

    def list_templates(self, project_id):
        assert project_id == 1
        return self.templates

    def find_template(self, project_id, name):
        return next(item for item in self.list_templates(project_id) if item["name"] == name)

    def update_template(self, project_id, template_id, payload):
        self.updated_templates.append((project_id, template_id, payload))
        self.templates = [{**item, **payload} if item["id"] == template_id else item for item in self.templates]
        return next(item for item in self.templates if item["id"] == template_id)

    def list_inventories(self, project_id):
        assert project_id == 1
        return self.inventories

    def find_inventory(self, project_id, name):
        return next(item for item in self.list_inventories(project_id) if item["name"] == name)

    def list_access_keys(self, project_id):
        assert project_id == 1
        return self.access_keys

    def find_access_key(self, project_id, name):
        return next(item for item in self.list_access_keys(project_id) if item["name"] == name)

    def find_repository(self, project_id, name):
        assert (project_id, name) == (1, "configuration_management")
        return {"id": 2, "project_id": 1, "name": name}

    def create_inventory(self, project_id, payload):
        self.created_inventories.append((project_id, payload))
        created = {"id": 8, "project_id": project_id, **payload}
        self.inventories.append(created)
        return created

    def update_inventory(self, project_id, inventory_id, payload):
        self.updated_inventories.append((project_id, inventory_id, payload))
        self.inventories = [
            {**item, **payload} if item["id"] == inventory_id else item
            for item in self.inventories
        ]
        return next(item for item in self.inventories if item["id"] == inventory_id)


def test_template_update_changes_only_branch_and_reads_back(monkeypatch, capsys):
    client = ResourceClient()
    monkeypatch.setattr(cli, "_client", lambda insecure=False: client)

    assert cli.main([
        "template", "update", "--project", "configuration_management",
        "--template", "hello_world", "--git-branch", "feature_branch_cm", "--json",
    ]) == 0

    payload = client.updated_templates[0][2]
    assert payload["git_branch"] == "feature_branch_cm"
    assert payload["repository_id"] == 2
    assert payload["inventory_id"] == 1
    assert payload["allow_override_branch_in_task"] is True
    assert json.loads(capsys.readouterr().out)["configuration"]["git_branch"] == "feature_branch_cm"


def test_inventory_list_and_show_are_safe(monkeypatch, capsys):
    client = ResourceClient()
    monkeypatch.setattr(cli, "_client", lambda insecure=False: client)

    assert cli.main(["inventory", "list", "--project", "configuration_management", "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output == [{"id": 1, "project_id": 1, "name": "configuration_management"}]

    assert cli.main([
        "inventory", "show", "--project", "configuration_management",
        "--inventory", "configuration_management", "--json",
    ]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["name"] == "configuration_management"
    assert "ssh_key_id" not in output
    assert "password" not in json.dumps(output)


def test_access_key_list_and_show_expose_only_safe_identity(monkeypatch, capsys):
    client = ResourceClient()
    monkeypatch.setattr(cli, "_client", lambda insecure=False: client)

    assert cli.main(["access-key", "list", "--project", "configuration_management", "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output == [{"id": 3, "project_id": 1, "name": "deploy key", "type": "ssh", "login": "git"}]

    assert cli.main([
        "access-key", "show", "--project", "configuration_management",
        "--access-key", "deploy key", "--json",
    ]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["name"] == "deploy key"
    assert "private_key" not in json.dumps(output)
