from semaphore_ui.api import SemaphoreClient


def test_resolves_project_and_template_by_exact_name():
    responses = {
        ("GET", "/api/projects"): [
            {"id": 1, "name": "configuration_management"},
        ],
        ("GET", "/api/project/1/templates"): [
            {"id": 7, "project_id": 1, "name": "hello_world"},
        ],
    }

    client = SemaphoreClient("https://semaphore.example", "secret", responses=responses)

    project = client.find_project("configuration_management")
    template = client.find_template(project["id"], "hello_world")

    assert project == {"id": 1, "name": "configuration_management"}
    assert template == {"id": 7, "project_id": 1, "name": "hello_world"}
