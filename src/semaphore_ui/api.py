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
    task_id = task.get("id")
    if not isinstance(task_id, int) or task_id <= 0:
        raise APIError("Semaphore task response did not contain a positive integer id")
    return task_id


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
            raise LookupError(f"Multiple Semaphore {resource}s named {name!r}")
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
