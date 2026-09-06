import json

from semaphore_ui import cli


class RepositoryClient:
    def __init__(self, repositories=None):
        self.repositories = repositories or []
        self.created = []
        self.updated = []

    def find_project(self, name):
        assert name == "configuration_management"
        return {"id": 1, "name": name}

    def list_repositories(self, project_id):
        assert project_id == 1
        return self.repositories or [
            {"id": 2, "project_id": 1, "name": "configuration_management", "git_branch": "master"}
        ]

    def find_repository(self, project_id, name):
        matches = [item for item in self.list_repositories(project_id) if item["name"] == name]
        assert len(matches) == 1
        return matches[0]

    def find_access_key(self, project_id, name):
        assert (project_id, name) == (1, "deploy key")
        return {"id": 3, "name": name}

    def create_repository(self, project_id, payload):
        self.created.append(payload)
        return {"id": 8, "project_id": project_id, **payload}

    def update_repository(self, project_id, repository_id, payload):
        self.updated.append((project_id, repository_id, payload))
        self.repositories = [{**item, **payload} if item.get("id") == repository_id else item for item in self.repositories]
        return {"id": repository_id, "project_id": project_id, **payload}


def test_repository_list_uses_project_namespace(monkeypatch, capsys):
    client = RepositoryClient([{
        "id": 2, "project_id": 1, "name": "configuration_management",
        "git_branch": "master", "private_key": "should-not-print",
    }])
    monkeypatch.setattr(cli, "_client", lambda insecure=False: client)

    result = cli.main(["repository", "list", "--project", "configuration_management", "--json"])

    assert result == 0
    assert json.loads(capsys.readouterr().out) == [{
        "id": 2, "project_id": 1, "name": "configuration_management", "git_branch": "master"
    }]


def test_repository_show_resolves_project_and_repository(monkeypatch, capsys):
    client = RepositoryClient()
    monkeypatch.setattr(cli, "_client", lambda insecure=False: client)

    result = cli.main(
        ["repository", "show", "--project", "configuration_management", "--repository", "configuration_management", "--json"]
    )

    assert result == 0
    assert json.loads(capsys.readouterr().out)["name"] == "configuration_management"


def test_repository_create_uses_explicit_payload(monkeypatch, capsys):
    client = RepositoryClient()
    monkeypatch.setattr(cli, "_client", lambda insecure=False: client)

    result = cli.main(
        [
            "repository", "create", "--project", "configuration_management",
            "--name", "fb_configuration_management", "--git-url",
            "git@bitbucket.org:adamhills/configuration_management.git", "--git-branch", "master", "--json",
        ]
    )

    assert result == 0
    assert client.created == [{
        "project_id": 1,
        "name": "fb_configuration_management",
        "git_url": "git@bitbucket.org:adamhills/configuration_management.git",
        "git_branch": "master",
    }]
    assert json.loads(capsys.readouterr().out)["repository"]["id"] == 8


def test_repository_copy_overrides_branch_and_reuses_safe_source_configuration(monkeypatch, capsys):
    source = {
        "id": 2,
        "project_id": 1,
        "name": "configuration_management",
        "git_url": "git@bitbucket.org:adamhills/configuration_management.git",
        "git_branch": "master",
        "ssh_key_id": 3,
    }
    client = RepositoryClient([source])
    monkeypatch.setattr(cli, "_client", lambda insecure=False: client)

    result = cli.main(
        [
            "repository", "copy", "--project", "configuration_management",
            "--repository", "configuration_management", "--name", "fb_configuration_management",
            "--git-branch", "feature_branch_cm", "--json",
        ]
    )

    assert result == 0
    assert client.created == [{
        "project_id": 1,
        "name": "fb_configuration_management",
        "git_url": source["git_url"],
        "git_branch": "feature_branch_cm",
        "ssh_key_id": 3,
    }]
    output = json.loads(capsys.readouterr().out)
    assert output["repository"]["name"] == "fb_configuration_management"
    assert "private_key" not in json.dumps(output)
    assert "password" not in json.dumps(output)
    assert "token" not in json.dumps(output)


def test_repository_create_rejects_existing_name_before_creation(monkeypatch, capsys):
    client = RepositoryClient([{"id": 2, "project_id": 1, "name": "existing"}])
    monkeypatch.setattr(cli, "_client", lambda insecure=False: client)

    result = cli.main(
        [
            "repository", "create", "--project", "configuration_management",
            "--name", "existing", "--git-url", "https://example.invalid/repo.git", "--git-branch", "master",
        ]
    )

    assert result == 2
    assert client.created == []
    assert "already exists" in capsys.readouterr().err


def test_repository_create_resolves_access_key_name(monkeypatch):
    client = RepositoryClient()
    monkeypatch.setattr(cli, "_client", lambda insecure=False: client)

    assert cli.main(
        [
            "repository", "create", "--project", "configuration_management",
            "--name", "secured", "--git-url", "git@example/repository.git",
            "--git-branch", "master", "--access-key", "deploy key",
        ]
    ) == 0
    assert client.created[0]["ssh_key_id"] == 3


def test_repository_update_changes_only_branch_and_reads_back(monkeypatch, capsys):
    source = {
        "id": 2,
        "project_id": 1,
        "name": "fb_configuration_management",
        "git_url": "git@bitbucket.org:adamhills/configuration_management.git",
        "git_branch": "master",
        "ssh_key_id": 3,
    }
    client = RepositoryClient([source])
    monkeypatch.setattr(cli, "_client", lambda insecure=False: client)

    assert cli.main([
        "repository", "update", "--project", "configuration_management",
        "--repository", "fb_configuration_management", "--git-branch", "feature_branch_cm", "--json",
    ]) == 0

    assert client.updated == [(1, 2, {
        "id": 2, "project_id": 1, "name": source["name"],
        "git_url": source["git_url"], "git_branch": "feature_branch_cm", "ssh_key_id": 3,
    })]
    assert json.loads(capsys.readouterr().out)["configuration"]["git_branch"] == "feature_branch_cm"
