import pytest

from semaphore_ui.api import APIError, SemaphoreClient


def test_resolves_project_and_template_by_exact_name():
    responses = {
        ("GET", "/api/projects"): [{"id": 1, "name": "configuration_management"}],
        ("GET", "/api/project/1/templates"): [{"id": 7, "project_id": 1, "name": "hello_world"}],
    }
    client = SemaphoreClient("https://semaphore.example", "secret", responses=responses)
    project = client.find_project("configuration_management")
    template = client.find_template(project["id"], "hello_world")
    assert project == {"id": 1, "name": "configuration_management"}
    assert template == {"id": 7, "project_id": 1, "name": "hello_world"}


def test_creates_repository_and_validates_project_identity():
    responses = {
        ("POST", "/api/project/1/repositories"): {
            "id": 2, "project_id": 1, "name": "feature_branch_cm",
            "git_url": "git@example/repository.git", "git_branch": "master", "ssh_key_id": 3,
        }
    }
    client = SemaphoreClient("https://semaphore.example", "secret", responses=responses)
    repository = client.create_repository(1, {
        "name": "feature_branch_cm", "git_url": "git@example/repository.git",
        "git_branch": "master", "ssh_key_id": 3,
    })
    assert repository["id"] == 2
    assert repository["project_id"] == 1


def test_rejects_repository_response_from_wrong_project():
    responses = {("POST", "/api/project/1/repositories"): {
        "id": 2, "project_id": 9, "name": "feature_branch_cm",
        "git_url": "git@example/repository.git", "git_branch": "master",
    }}
    client = SemaphoreClient("https://semaphore.example", "secret", responses=responses)
    with pytest.raises(APIError, match="project_id"):
        client.create_repository(1, {
            "name": "feature_branch_cm", "git_url": "git@example/repository.git", "git_branch": "master",
        })


def test_rejects_repository_response_that_does_not_match_request():
    responses = {("POST", "/api/project/1/repositories"): {
        "id": 2, "project_id": 1, "name": "unexpected",
        "git_url": "git@example/repository.git", "git_branch": "master",
    }}
    client = SemaphoreClient("https://semaphore.example", "secret", responses=responses)
    with pytest.raises(APIError, match="name"):
        client.create_repository(1, {
            "name": "feature_branch_cm", "git_url": "git@example/repository.git", "git_branch": "master",
        })


def test_updates_repository_with_full_payload_and_reads_back():
    responses = {
        ("PUT", "/api/project/1/repositories/2"): None,
        ("GET", "/api/project/1/repositories"): [{
            "id": 2, "project_id": 1, "name": "feature_branch_cm",
            "git_url": "git@example/repository.git", "git_branch": "feature_branch_cm", "ssh_key_id": 3,
        }],
    }
    client = SemaphoreClient("https://semaphore.example", "secret", responses=responses)
    repository = client.update_repository(1, 2, {
        "id": 2, "project_id": 1, "name": "feature_branch_cm",
        "git_url": "git@example/repository.git", "git_branch": "feature_branch_cm", "ssh_key_id": 3,
    })
    assert repository["git_branch"] == "feature_branch_cm"
