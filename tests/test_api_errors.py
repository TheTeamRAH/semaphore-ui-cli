import pytest

from semaphore_ui.api import APIError, SemaphoreClient


def test_malformed_project_items_raise_api_error():
    client = SemaphoreClient(
        "https://semaphore.example",
        "secret",
        responses={("GET", "/api/projects"): [{"id": 1}, "not-an-object"]},
    )

    with pytest.raises(APIError, match="list of objects"):
        client.list_projects()


def test_timeout_is_wrapped_as_api_error():
    def opener(request, timeout):
        raise TimeoutError("timed out")

    client = SemaphoreClient("https://semaphore.example", "secret", opener=opener)

    with pytest.raises(APIError, match="Unable to reach"):
        client.list_projects()
