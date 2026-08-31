"""Client for the Semaphore UI HTTP API.

The client keeps transport, resource lookup, and task operations separate so it
can be used by the command-line interface or another Python application.

Examples:
    >>> client = SemaphoreClient("https://semaphore.example", "TOKEN")
    >>> project = client.find_project("configuration_management")
    >>> client.find_template(project["id"], "hello_world")["id"]
    1

A successful task response typically resembles::

    {"id": 4, "status": "waiting", "project_id": 1, "template_id": 1}

Credentials should come from ``SEMAPHORE_HOST`` and ``SEMAPHORE_TOKEN`` in
normal use; they must not be committed or printed.
"""

from __future__ import annotations

import json
import os
import ssl
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .validators import require_nonempty_string, require_positive_int


class SemaphoreError(RuntimeError):
    """Base error for Semaphore client failures."""


class ConfigurationError(SemaphoreError):
    """Required configuration is absent."""


class LookupError(SemaphoreError):
    """A named resource cannot be resolved uniquely."""


class APIError(SemaphoreError):
    """The Semaphore API returned an error or unusable response."""


class TaskTimeoutError(SemaphoreError):
    """A task did not reach a terminal state in time."""


TERMINAL_STATES = {"success", "error", "failed", "stopped", "canceled", "cancelled"}


def _require_list_of_objects(value: Any, resource: str) -> list[dict[str, Any]]:
    """Validate and return a resource collection.

    Args:
        value: Decoded API response.
        resource: Human-readable resource name for the error message.

    Returns:
        The response as a list of dictionaries.

    Raises:
        APIError: If the response is not a list of dictionaries.
    """
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise APIError(f"Semaphore {resource} response was not a list of objects")
    return value


def _require_task_id(task: dict[str, Any]) -> int:
    """Validate and return a positive task identifier.

    Args:
        task: Decoded task response.

    Returns:
        The task's positive integer ID.

    Raises:
        APIError: If the task ID is missing or invalid.
    """
    if not isinstance(task, dict):
        raise APIError("Semaphore task response did not contain a positive integer id")
    return require_positive_int(
        task.get("id"), APIError, "Semaphore task response did not contain a positive integer id"
    )


def _require_task_status(task: dict[str, Any]) -> str:
    """Validate and return a task status.

    Args:
        task: Decoded task response.

    Returns:
        The task status string.

    Raises:
        APIError: If the task status is missing or invalid.
    """
    if not isinstance(task, dict):
        raise APIError("Semaphore task response did not contain a string status")
    status = task.get("status")
    if not isinstance(status, str):
        raise APIError("Semaphore task response did not contain a string status")
    return status


def _require_positive_id(value: Any, field: str, resource: str) -> int:
    """Validate a positive integer field in an API resource.

    Args:
        value: Candidate resource-field value.
        field: Field name for an actionable error message.
        resource: Human-readable Semaphore resource type.

    Returns:
        The validated positive integer.

    Raises:
        APIError: If the value is boolean, non-integer, or not positive.
    """
    return require_positive_int(
        value, APIError, f"Semaphore {resource} response did not contain a positive integer {field}"
    )


def _require_template(template: Any, project_id: int) -> dict[str, Any]:
    """Validate a created template response and return it.

    Args:
        template: Decoded create-template response, for example
            ``{"id": 17, "project_id": 3, "name": "deploy-web"}``.
        project_id: Positive ID of the project used for the create request.

    Returns:
        The original template dictionary after its identity fields are checked.

    Raises:
        APIError: If the response is not an object, its identity is malformed,
            or its project ID does not match the request.

    Examples:
        ``_require_template({"id": 17, "project_id": 3, "name": "deploy-web"}, 3)``
        returns the supplied template dictionary.
    """
    if not isinstance(template, dict):
        raise APIError("Semaphore template response was not an object")
    _require_positive_id(template.get("id"), "id", "template")
    response_project_id = _require_positive_id(
        template.get("project_id"), "project_id", "template"
    )
    if response_project_id != project_id:
        raise APIError("Semaphore template response project_id did not match the requested project")
    require_nonempty_string(
        template.get("name"), APIError, "Semaphore template response did not contain a non-empty name"
    )
    return template


def _schema_properties(document: dict[str, Any], schema: Any) -> dict[str, Any]:
    """Return the merged properties declared by a Swagger schema fragment.

    Args:
        document: Complete Swagger document used to resolve local references.
        schema: Schema fragment that may contain a reference or composition.

    Returns:
        Properties accepted by the schema fragment.

    Raises:
        APIError: If the fragment has an invalid local definition reference.

    Examples:
        A Swagger document stores the template schema under
        ``document["definitions"]["TemplateRequest"]``. In this miniature
        document, ``TemplateRequest`` uses ``allOf`` to combine a reusable base
        with template-specific fields::

            document = {"definitions": {
                "TemplateBase": {"properties": {"name": {"type": "string"}}},
                "TemplateRequest": {"allOf": [
                    {"$ref": "#/definitions/TemplateBase"},
                    {"properties": {"type": {"enum": ["build", "deploy"]}}},
                ]},
            }}

        ``allOf`` is Swagger's schema-composition list: the effective schema
        includes the properties from every listed fragment. Calling this helper
        with ``document`` and ``document["definitions"]["TemplateRequest"]``
        returns properties for both ``name`` and ``type``. Only local
        ``#/definitions/...`` references resolve; later components replace
        duplicate property names.
    """
    if not isinstance(schema, dict):
        return {}
    reference = schema.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/definitions/"):
        definitions = document.get("definitions")
        if not isinstance(definitions, dict):
            raise APIError("Semaphore API schema definitions were not an object")
        definition = definitions.get(reference.rsplit("/", 1)[-1])
        if not isinstance(definition, dict):
            raise APIError(f"Semaphore API schema has an invalid reference: {reference}")
        return _schema_properties(document, definition)
    properties = schema.get("properties", {})
    result = dict(properties) if isinstance(properties, dict) else {}
    for component in schema.get("allOf", []):
        result.update(_schema_properties(document, component))
    return result


def _is_known_template_schema_extension(field: str, value: Any) -> bool:
    """Return whether a missing Swagger constraint is a supported extension.

    Semaphore versions can support survey defaults and multi-select variables
    before their generated Swagger document includes the corresponding nested
    property or enum value. This intentionally recognizes only those two
    precise paths; all other absent schema elements remain validation errors.
    """
    return field.startswith("survey_vars[") and field.endswith(".type") and value == "select"


def _validate_schema_value(document: dict[str, Any], schema: Any, value: Any, field: str) -> None:
    """Confirm that a value's nested fields and enums match a Swagger schema.

    Args:
        document: Complete Swagger document used to resolve local references.
        schema: Schema fragment for the value.
        value: JSON-compatible value that will be submitted to Semaphore.
        field: Dot-separated field name for actionable error messages.

    Raises:
        APIError: If a submitted field or enum value is unsupported.

    Examples:
        For a template-create payload, first select the schema stored at
        ``document["definitions"]["TemplateRequest"]``::

            schema = document["definitions"]["TemplateRequest"]
            value = {"name": "deploy-web", "type": "build"}
            _validate_schema_value(document, schema, value, "template")

        If the ``TemplateRequest`` schema allows only ``"build"`` and
        ``"deploy"`` for ``type``, this succeeds; changing it to ``"delete"``
        raises ``APIError``. For list fields, the helper applies the schema's
        ``items`` fragment to each element. Passing the complete document is
        necessary when ``TemplateRequest`` uses a local reference or ``allOf``.
    """
    if (
        isinstance(schema, dict)
        and isinstance(schema.get("enum"), list)
        and value not in schema["enum"]
        and not _is_known_template_schema_extension(field, value)
    ):
        raise APIError(f"Semaphore API schema does not support {field}={value!r}")
    if isinstance(value, dict):
        properties = _schema_properties(document, schema)
        for key, item in value.items():
            property_schema = properties.get(key)
            if property_schema is None:
                if field.startswith("survey_vars[") and key == "default_value":
                    continue
                raise APIError(f"Semaphore API schema does not support template field {field}.{key}")
            _validate_schema_value(document, property_schema, item, f"{field}.{key}")
    elif isinstance(value, list) and isinstance(schema, dict) and "items" in schema:
        for index, item in enumerate(value):
            _validate_schema_value(document, schema["items"], item, f"{field}[{index}]")


def _decode_environment(task: dict[str, Any]) -> dict[str, Any]:
    """Decode and validate a task's environment object.

    Args:
        task: Decoded task response containing an environment value.

    Returns:
        The environment as a dictionary.

    Raises:
        APIError: If the environment is invalid JSON or not an object.
    """
    environment = task.get("environment", {})
    if isinstance(environment, str):
        try:
            environment = json.loads(environment)
        except json.JSONDecodeError as exc:
            raise APIError(f"Semaphore task {task['id']} environment was invalid JSON") from exc
    if not isinstance(environment, dict):
        raise APIError(f"Semaphore task {task['id']} environment was not an object")
    return environment


def _normalize_task(item: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize one task-list response item.

    Args:
        item: Raw task dictionary returned by Semaphore.

    Returns:
        A stable task dictionary for callers.

    Raises:
        APIError: If required task fields or the environment are invalid.
    """
    _require_task_id(item)
    _require_task_status(item)
    task = {key: item[key] for key in ("id", "status", "created", "start", "end") if key in item}
    task["template"] = {"id": item["template_id"]} if isinstance(item.get("template_id"), int) else {}
    if isinstance(item.get("tpl_alias"), str):
        task["template"]["name"] = item["tpl_alias"]
    task["environment"] = _decode_environment(item)
    return task


class SemaphoreClient:
    """Small HTTP client for the Semaphore UI project/task API.

    Args:
        host: Semaphore base URL. Defaults to ``SEMAPHORE_HOST``.
        token: Bearer token. Defaults to ``SEMAPHORE_TOKEN``.
        insecure: Disable TLS certificate verification when explicitly enabled.
        opener: Optional urllib-compatible opener used by tests.
        responses: Optional fake response map keyed by ``(method, path)``.

    Raises:
        ConfigurationError: If host or token is missing.
    """

    def __init__(
        self,
        host: str | None = None,
        token: str | None = None,
        *,
        insecure: bool = False,
        opener: Callable[..., Any] | None = None,
        responses: dict[tuple[str, str], Any] | None = None,
    ) -> None:
        """Initialise a client from explicit or environment configuration.

        Args:
            host: Semaphore base URL, or ``SEMAPHORE_HOST`` when omitted.
            token: Bearer token, or ``SEMAPHORE_TOKEN`` when omitted.
            insecure: Whether to disable TLS certificate verification.
            opener: Optional urllib-compatible opener for tests.
            responses: Optional fake response map for tests.
        """
        self.host = (host or os.getenv("SEMAPHORE_HOST", "")).rstrip("/")
        self.token = token or os.getenv("SEMAPHORE_TOKEN", "")
        self.insecure = insecure
        self._opener = opener or urlopen
        self._responses = responses
        if not self.host or not self.token:
            raise ConfigurationError("SEMAPHORE_HOST and SEMAPHORE_TOKEN are required")

    def _request(self, method: str, path: str, payload: Any = None) -> Any:
        """Send one JSON API request and decode its response.

        Args:
            method: HTTP method.
            path: API path beginning with ``/``.
            payload: JSON-serializable request body, if applicable.

        Returns:
            The decoded JSON response.

        Raises:
            APIError: If the request fails or the response is invalid JSON.
        """
        if self._responses is not None:
            try:
                return self._responses[(method, path)]
            except KeyError as exc:
                raise APIError(f"No fake response configured for {method} {path}") from exc

        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.host}{path}",
            data=body,
            method=method,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
        )
        try:
            kwargs = {"timeout": 30}
            if self._opener is urlopen:
                kwargs["context"] = ssl._create_unverified_context() if self.insecure else None
            with self._opener(request, **kwargs) as response:
                raw = response.read()
        except HTTPError as exc:
            raise APIError(f"Semaphore API returned HTTP {exc.code} for {method} {path}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", str(exc))
            raise APIError(f"Unable to reach Semaphore API: {reason}") from exc
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise APIError(f"Semaphore API returned invalid JSON for {method} {path}") from exc

    @staticmethod
    def _filter_exact(items: list[dict[str, Any]], name: str, resource: str) -> dict[str, Any]:
        """Return the uniquely named item from a resource collection.

        Args:
            items: Resource dictionaries to search.
            name: Exact resource name.
            resource: Human-readable resource type for errors.

        Returns:
            The single matching resource.

        Raises:
            LookupError: If zero or multiple items match.
        """
        matches = [item for item in items if item.get("name") == name]
        if not matches:
            raise LookupError(f"No Semaphore {resource} named {name!r}")
        if len(matches) > 1:
            plural = {"repository": "repositories"}.get(resource, f"{resource}s")
            raise LookupError(f"Multiple Semaphore {plural} named {name!r}")
        return matches[0]

    def list_projects(self) -> list[dict[str, Any]]:
        """Return all projects.

        Returns:
            A list of project dictionaries.
        """
        return _require_list_of_objects(self._request("GET", "/api/projects"), "projects")

    def find_project(self, name: str) -> dict[str, Any]:
        """Resolve a project by exact name.

        Args:
            name: Exact Semaphore project name.

        Returns:
            The uniquely matching project dictionary.
        """
        return self._filter_exact(self.list_projects(), name, "project")

    def _list_project_resources(self, project_id: int, path: str, resource: str) -> list[dict[str, Any]]:
        """Return one project-scoped named resource collection."""
        return _require_list_of_objects(self._request("GET", f"/api/project/{project_id}/{path}"), resource)

    def list_repositories(self, project_id: int) -> list[dict[str, Any]]:
        """Return repositories available within a project."""
        return self._list_project_resources(project_id, "repositories", "repositories")

    def find_repository(self, project_id: int, name: str) -> dict[str, Any]:
        """Resolve a repository by exact project-scoped name."""
        return self._filter_exact(self.list_repositories(project_id), name, "repository")

    def list_inventories(self, project_id: int) -> list[dict[str, Any]]:
        """Return inventories available within a project."""
        return self._list_project_resources(project_id, "inventory", "inventories")

    def find_inventory(self, project_id: int, name: str) -> dict[str, Any]:
        """Resolve an inventory by exact project-scoped name."""
        return self._filter_exact(self.list_inventories(project_id), name, "inventory")

    def list_environments(self, project_id: int) -> list[dict[str, Any]]:
        """Return environment variable groups available within a project."""
        return self._list_project_resources(project_id, "environment", "environments")

    def find_environment(self, project_id: int, name: str) -> dict[str, Any]:
        """Resolve an environment by exact project-scoped name."""
        return self._filter_exact(self.list_environments(project_id), name, "environment")

    def list_views(self, project_id: int) -> list[dict[str, Any]]:
        """Return views available within a project."""
        return self._list_project_resources(project_id, "views", "views")

    def find_view(self, project_id: int, name: str) -> dict[str, Any]:
        """Resolve a view by exact project-scoped name."""
        return self._filter_exact(self.list_views(project_id), name, "view")

    def list_access_keys(self, project_id: int) -> list[dict[str, Any]]:
        """Return access keys available within a project."""
        return _require_list_of_objects(
            self._request("GET", f"/api/project/{project_id}/keys?sort=name&order=asc"), "access keys"
        )

    def find_access_key(self, project_id: int, name: str) -> dict[str, Any]:
        """Resolve an access key by exact project-scoped name."""
        return self._filter_exact(self.list_access_keys(project_id), name, "access key")

    def list_templates(self, project_id: int) -> list[dict[str, Any]]:
        """Return all task templates in a project.

        Args:
            project_id: Numeric Semaphore project ID.

        Returns:
            A list of task-template dictionaries.
        """
        return _require_list_of_objects(
            self._request("GET", f"/api/project/{project_id}/templates"), "templates"
        )

    def find_template(self, project_id: int, name: str) -> dict[str, Any]:
        """Resolve a task template by exact name within a project.

        Args:
            project_id: Numeric Semaphore project ID.
            name: Exact task-template name.

        Returns:
            The uniquely matching task-template dictionary.
        """
        return self._filter_exact(self.list_templates(project_id), name, "template")

    def create_template(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a template in a project and validate the returned identity.

        Args:
            project_id: Positive numeric project identifier.
            payload: Schema-preflighted JSON body for the template.

        Returns:
            The validated created-template object.

        Raises:
            APIError: If Semaphore rejects the request or returns malformed data.
        """
        return _require_template(
            self._request("POST", f"/api/project/{project_id}/templates", payload), project_id
        )

    def assert_template_create_supported(self, payload: dict[str, Any]) -> None:
        """Check that the deployed API supports the pending template request.

        The preflight reads the instance's Swagger document and never changes
        Semaphore state. It must run immediately before template creation so a
        version mismatch cannot result in a guessed create request.

        Args:
            payload: Fully resolved JSON payload that will be posted.

        Raises:
            APIError: If the schema is unavailable, malformed, or incompatible.
        """
        schema = self._request("GET", "/api/swagger")
        if not isinstance(schema, dict):
            raise APIError("Semaphore API schema was not a JSON object")
        paths = schema.get("paths")
        path = "/project/{project_id}/templates"
        if not isinstance(paths, dict) or not isinstance(paths.get(path), dict) or "post" not in paths[path]:
            raise APIError("Semaphore API schema does not support template creation")
        definitions = schema.get("definitions")
        if not isinstance(definitions, dict):
            raise APIError("Semaphore API schema definitions were not an object")
        template_schema = definitions.get("TemplateRequest")
        properties = _schema_properties(schema, template_schema)
        if not properties:
            raise APIError("Semaphore API schema does not define TemplateRequest properties")
        for field, value in payload.items():
            field_schema = properties.get(field)
            if field_schema is None:
                raise APIError(f"Semaphore API schema does not support template field {field}")
            _validate_schema_value(schema, field_schema, value, field)

    def create_task(self, project_id: int, template_id: int, variables: dict[str, str]) -> dict[str, Any]:
        """Queue a task with Semaphore survey/environment variables.

        Args:
            project_id: Numeric Semaphore project ID.
            template_id: Numeric task-template ID.
            variables: Survey variables such as ``target`` and ``fact``.

        Returns:
            The created task dictionary.

        Raises:
            APIError: If the response lacks a valid ID or status.
        """
        result = self._request(
            "POST",
            f"/api/project/{project_id}/tasks",
            {"template_id": template_id, "environment": json.dumps(variables, separators=(",", ":"))},
        )
        _require_task_id(result)
        _require_task_status(result)
        return result

    def list_tasks(self, project_id: int, limit: int = 20) -> list[dict[str, Any]]:
        """Return a bounded list of normalized tasks for a project.

        Args:
            project_id: Numeric Semaphore project ID.
            limit: Maximum number of tasks to return.

        Returns:
            Task dictionaries with parsed environment and template identity.

        Raises:
            ValueError: If limit is not positive.
            APIError: If the response or a task environment is malformed.
        """
        if limit <= 0:
            raise ValueError("task limit must be positive")
        result = _require_list_of_objects(
            self._request("GET", f"/api/project/{project_id}/tasks"), "tasks"
        )
        return [_normalize_task(item) for item in result[:limit]]

    def get_task(self, project_id: int, task_id: int) -> dict[str, Any]:
        """Retrieve one task by numeric ID.

        Args:
            project_id: Numeric Semaphore project ID.
            task_id: Numeric task ID.

        Returns:
            The task dictionary, including its status.
        """
        result = self._request("GET", f"/api/project/{project_id}/tasks/{task_id}")
        if not isinstance(result, dict):
            raise APIError("Semaphore task response was not an object")
        _require_task_status(result)
        return result

    def get_output(self, project_id: int, task_id: int) -> list[dict[str, Any]]:
        """Retrieve structured output lines for one task.

        Args:
            project_id: Numeric Semaphore project ID.
            task_id: Numeric task ID.

        Returns:
            Output entries containing at least an ``output`` string.
        """
        result = self._request("GET", f"/api/project/{project_id}/tasks/{task_id}/output")
        if not isinstance(result, list) or not all(
            isinstance(item, dict) and isinstance(item.get("output"), str) for item in result
        ):
            raise APIError("Semaphore task output response was not a list of objects with output")
        return result
