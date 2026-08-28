"""Semaphore UI API client."""

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


class SemaphoreClient:
    def __init__(
        self,
        host: str | None = None,
        token: str | None = None,
        *,
        insecure: bool = False,
        opener: Callable[..., Any] | None = None,
        responses: dict[tuple[str, str], Any] | None = None,
    ) -> None:
        self.host = (host or os.getenv("SEMAPHORE_HOST", "")).rstrip("/")
        self.token = token or os.getenv("SEMAPHORE_TOKEN", "")
        self.insecure = insecure
        self._opener = opener or urlopen
        self._responses = responses
        if not self.host or not self.token:
            raise ConfigurationError("SEMAPHORE_HOST and SEMAPHORE_TOKEN are required")

    def _request(self, method: str, path: str, payload: Any = None) -> Any:
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

    def list_projects(self) -> list[dict[str, Any]]:
        result = self._request("GET", "/api/projects")
        if not isinstance(result, list) or not all(isinstance(item, dict) for item in result):
            raise APIError("Semaphore projects response was not a list of objects")
        return result

    def find_project(self, name: str) -> dict[str, Any]:
        matches = [item for item in self.list_projects() if item.get("name") == name]
        if not matches:
            raise LookupError(f"No Semaphore project named {name!r}")
        if len(matches) > 1:
            raise LookupError(f"Multiple Semaphore projects named {name!r}")
        return matches[0]

    def list_templates(self, project_id: int) -> list[dict[str, Any]]:
        result = self._request("GET", f"/api/project/{project_id}/templates")
        if not isinstance(result, list) or not all(isinstance(item, dict) for item in result):
            raise APIError("Semaphore templates response was not a list of objects")
        return result

    def find_template(self, project_id: int, name: str) -> dict[str, Any]:
        matches = [item for item in self.list_templates(project_id) if item.get("name") == name]
        if not matches:
            raise LookupError(f"No Semaphore template named {name!r} in project {project_id}")
        if len(matches) > 1:
            raise LookupError(f"Multiple Semaphore templates named {name!r} in project {project_id}")
        return matches[0]

    def create_task(self, project_id: int, template_id: int, variables: dict[str, str]) -> dict[str, Any]:
        result = self._request(
            "POST",
            f"/api/project/{project_id}/tasks",
            {"template_id": template_id, "environment": json.dumps(variables, separators=(",", ":"))},
        )
        if not isinstance(result, dict) or "id" not in result:
            raise APIError("Semaphore task response did not contain an id")
        return result

    def get_task(self, project_id: int, task_id: int) -> dict[str, Any]:
        result = self._request("GET", f"/api/project/{project_id}/tasks/{task_id}")
        if not isinstance(result, dict) or not isinstance(result.get("status"), str):
            raise APIError("Semaphore task response did not contain a string status")
        return result

    def get_output(self, project_id: int, task_id: int) -> list[dict[str, Any]]:
        result = self._request("GET", f"/api/project/{project_id}/tasks/{task_id}/output")
        if not isinstance(result, list) or not all(isinstance(item, dict) for item in result):
            raise APIError("Semaphore task output response was not a list of objects")
        return result
