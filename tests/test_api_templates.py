"""Tests for creating Semaphore task templates without a live server."""

import json

import pytest

from semaphore_ui.api import APIError, LookupError, SemaphoreClient


def test_create_template_resolves_project_resources_and_posts_safe_payload():
    responses = {
        ("GET", "/api/projects"): [{"id": 1, "name": "configuration_management"}],
        ("GET", "/api/project/1/repositories"): [{"id": 2, "name": "configuration-management"}],
        ("GET", "/api/project/1/inventory"): [{"id": 3, "name": "homelab"}],
        ("GET", "/api/project/1/environment"): [{"id": 4, "name": "default"}],
        ("POST", "/api/project/1/templates"): {
            "id": 5,
            "project_id": 1,
            "name": "show-firewall-interface",
        },
    }
    client = SemaphoreClient("https://semaphore.example", "secret", responses=responses)

    project = client.find_project("configuration_management")
    repository = client.find_repository(project["id"], "configuration-management")
    inventory = client.find_inventory(project["id"], "homelab")
    environment = client.find_environment(project["id"], "default")
    created = client.create_template(
        project["id"],
        {
            "name": "show-firewall-interface",
            "repository_id": repository["id"],
            "inventory_id": inventory["id"],
            "environment_id": environment["id"],
            "playbook": "site.yml",
            "git_branch": "main",
            "type": "",
        },
    )

    assert created == {"id": 5, "project_id": 1, "name": "show-firewall-interface"}


def test_create_template_sends_payload_and_rejects_malformed_response():
    seen = {}

    def opener(request, timeout):
        seen["body"] = request.data
        raise AssertionError("not used in this test")

    client = SemaphoreClient("https://semaphore.example", "secret", opener=opener)
    with pytest.raises(AssertionError):
        client.create_template(1, {"name": "template", "repository_id": 2})

    assert json.loads(seen["body"]) == {"name": "template", "repository_id": 2}

    malformed = SemaphoreClient(
        "https://semaphore.example",
        "secret",
        responses={("POST", "/api/project/1/templates"): {"id": 5, "name": "template"}},
    )
    with pytest.raises(APIError, match="project_id"):
        malformed.create_template(1, {"name": "template"})

    boolean_id = SemaphoreClient(
        "https://semaphore.example",
        "secret",
        responses={("POST", "/api/project/1/templates"): {"id": True, "project_id": 1, "name": "template"}},
    )
    with pytest.raises(APIError, match="positive integer id"):
        boolean_id.create_template(1, {"name": "template"})


def test_template_resource_lookup_rejects_ambiguous_names():
    client = SemaphoreClient(
        "https://semaphore.example",
        "secret",
        responses={
            ("GET", "/api/project/1/repositories"): [
                {"id": 2, "name": "same"},
                {"id": 3, "name": "same"},
            ]
        },
    )

    with pytest.raises(LookupError, match="Multiple Semaphore repositories"):
        client.find_repository(1, "same")


def test_template_resource_lookup_rejects_missing_inventory():
    client = SemaphoreClient(
        "https://semaphore.example",
        "secret",
        responses={("GET", "/api/project/1/inventory"): []},
    )

    with pytest.raises(LookupError, match="No Semaphore inventory"):
        client.find_inventory(1, "missing")


def test_access_key_lookup_uses_exact_name_and_required_sorting():
    client = SemaphoreClient(
        "https://semaphore.example",
        "secret",
        responses={
            ("GET", "/api/project/1/keys?sort=name&order=asc"): [
                {"id": 6, "name": "Production vault password"}
            ]
        },
    )

    assert client.find_access_key(1, "Production vault password") == {
        "id": 6,
        "name": "Production vault password",
    }


def test_template_create_schema_preflight_requires_supported_path_and_payload_fields():
    schema = {
        "paths": {"/project/{project_id}/templates": {"post": {}}},
        "definitions": {
            "TemplateRequest": {
                "properties": {
                    "project_id": {},
                    "repository_id": {},
                    "inventory_id": {},
                    "environment_id": {},
                    "name": {},
                    "playbook": {},
                    "git_branch": {},
                }
            }
        },
    }
    client = SemaphoreClient(
        "https://semaphore.example",
        "secret",
        responses={("GET", "/api/swagger"): schema},
    )
    payload = {
        "project_id": 1,
        "repository_id": 2,
        "inventory_id": 3,
        "environment_id": 4,
        "name": "template",
        "playbook": "site.yml",
        "git_branch": "main",
    }

    client.assert_template_create_supported(payload)

    schema["definitions"]["TemplateRequest"]["properties"].pop("git_branch")
    with pytest.raises(APIError, match="git_branch"):
        client.assert_template_create_supported(payload)


def test_template_create_schema_preflight_rejects_malformed_definitions():
    client = SemaphoreClient(
        "https://semaphore.example",
        "secret",
        responses={
            ("GET", "/api/swagger"): {
                "paths": {"/project/{project_id}/templates": {"post": {}}},
                "definitions": [],
            }
        },
    )

    with pytest.raises(APIError, match="definitions"):
        client.assert_template_create_supported({"name": "template"})


def test_template_create_schema_preflight_accepts_known_survey_extensions():
    schema = {
        "paths": {"/project/{project_id}/templates": {"post": {}}},
        "definitions": {
            "TemplateRequest": {
                "properties": {
                    "name": {},
                    "survey_vars": {"type": "array", "items": {"$ref": "#/definitions/TemplateSurveyVar"}},
                }
            },
            "TemplateSurveyVar": {
                "properties": {
                    "name": {},
                    "title": {},
                    "type": {"enum": ["", "int", "enum", "secret", "text"]},
                    "values": {"type": "array", "items": {"$ref": "#/definitions/TemplateSurveyVarValue"}},
                }
            },
            "TemplateSurveyVarValue": {"properties": {"name": {}, "value": {}}},
        },
    }
    client = SemaphoreClient(
        "https://semaphore.example", "secret", responses={("GET", "/api/swagger"): schema}
    )

    client.assert_template_create_supported(
        {
            "name": "template",
            "survey_vars": [
                {
                    "name": "target",
                    "title": "Target",
                    "type": "select",
                    "values": [{"name": "Web 1", "value": "web-01"}],
                    "default_value": ["web-01"],
                }
            ],
        }
    )
