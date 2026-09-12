"""Command-line interface for Semaphore UI task automation.

Examples:
    List projects as JSON::

        semaphore-ui --insecure project list --json

    Run a template by exact project and template names::

        semaphore-ui --insecure task run \\
            --project configuration_management \\
            --template hello_world \\
            --var target=hermes-001.iot.home \\
            --var fact=firewall_interface \\
            --wait --json

Typical JSON output is an envelope containing ``project``, ``template``,
``task``, and ``variables``. Credentials come from ``SEMAPHORE_HOST`` and
``SEMAPHORE_TOKEN``.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
import re
import sys
import time
from typing import Any

from . import __version__
from .api import SemaphoreClient, SemaphoreError, TERMINAL_STATES, TaskTimeoutError
from .validators import require_nonempty_string, require_positive_int


def _variables(values: list[str]) -> dict[str, str]:
    """Parse repeated ``NAME=VALUE`` arguments.

    Args:
        values: Raw variable arguments from argparse.

    Returns:
        A mapping suitable for Semaphore's environment payload.

    Raises:
        ValueError: If an argument does not contain a non-empty name.
    """
    result = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"variable must use NAME=VALUE: {value!r}")
        name, item = value.split("=", 1)
        if not name:
            raise ValueError("variable name cannot be empty")
        result[name] = item
    return result


def _plain(text: str) -> str:
    """Remove ANSI CSI escape sequences from task output.

    Args:
        text: A task-output fragment.

    Returns:
        The fragment without terminal colour/control sequences.
    """
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)


def _print(value: Any, as_json: bool) -> None:
    """Print a JSON value or a compact human-readable representation.

    Args:
        value: Value returned by the API or a command handler.
        as_json: Whether to render indented JSON.
    """
    if as_json:
        print(json.dumps(value, indent=2, sort_keys=True))
    elif isinstance(value, list):
        for item in value:
            print(f"{item.get('id', '')}\t{item.get('name', item.get('status', ''))}")
    else:
        print(value)


def _client(insecure: bool = False) -> SemaphoreClient:
    """Create the configured Semaphore client.

    Args:
        insecure: Whether to disable TLS certificate verification explicitly.

    Returns:
        A configured :class:`SemaphoreClient`.
    """
    return SemaphoreClient(insecure=insecure)


def _add_json_argument(parser: argparse.ArgumentParser) -> None:
    """Add the common JSON-output option to a subcommand parser.

    Args:
        parser: Parser receiving the option.
    """
    parser.add_argument("--json", action="store_true", dest="as_json")


def _wait(client: SemaphoreClient, project_id: int, task_id: int, interval: float, timeout: float) -> dict[str, Any]:
    """Poll a task until it reaches a terminal state or times out.

    Args:
        client: Configured Semaphore client.
        project_id: Numeric Semaphore project ID.
        task_id: Numeric task ID.
        interval: Seconds between status requests.
        timeout: Maximum total wait in seconds.

    Returns:
        The terminal task dictionary.

    Raises:
        ValueError: If interval or timeout is negative.
        TaskTimeoutError: If the task remains non-terminal before the deadline.
    """
    if interval < 0:
        raise ValueError("poll interval cannot be negative")
    if timeout < 0:
        raise ValueError("timeout cannot be negative")
    deadline = time.monotonic() + timeout
    while True:
        task = client.get_task(project_id, task_id)
        if task["status"].lower() in TERMINAL_STATES:
            return task
        if time.monotonic() >= deadline:
            raise TaskTimeoutError(f"Task {task_id} did not finish within {timeout:g} seconds")
        time.sleep(interval)


def _handle_project_list(args: argparse.Namespace, client: SemaphoreClient) -> int:
    """List all Semaphore projects."""
    _print(client.list_projects(), args.as_json)
    return 0


def _handle_project_show(args: argparse.Namespace, client: SemaphoreClient) -> int:
    """Show one Semaphore project resolved by exact name."""
    _print(client.find_project(args.project), args.as_json)
    return 0


def _safe_repository_configuration(repository: dict[str, Any]) -> dict[str, Any]:
    """Return non-secret repository configuration for command output."""
    return {
        key: repository[key]
        for key in ("id", "project_id", "name", "git_url", "git_branch", "ssh_key_id")
        if key in repository
    }


def _handle_repository_list(args: argparse.Namespace, client: SemaphoreClient) -> int:
    """List repositories in a project."""
    project = client.find_project(args.project)
    repositories = client.list_repositories(project["id"])
    _print([_safe_repository_configuration(repository) for repository in repositories], args.as_json)
    return 0


def _handle_repository_show(args: argparse.Namespace, client: SemaphoreClient) -> int:
    """Show one project repository resolved by exact name."""
    project = client.find_project(args.project)
    repository = client.find_repository(project["id"], args.repository)
    _print(_safe_repository_configuration(repository), args.as_json)
    return 0


def _repository_payload(
    source: dict[str, Any], destination: str, branch: str | None = None
) -> dict[str, Any]:
    """Build a repository-create payload from safe source configuration."""
    payload: dict[str, Any] = {
        "name": require_nonempty_string(destination, ValueError, "repository name must be a non-empty string"),
        "git_url": require_nonempty_string(source.get("git_url"), ValueError, "repository git URL must be a non-empty string"),
        "git_branch": require_nonempty_string(
            branch if branch is not None else source.get("git_branch"),
            ValueError,
            "repository git branch must be a non-empty string",
        ),
    }
    if "ssh_key_id" in source and source["ssh_key_id"] is not None:
        payload["ssh_key_id"] = require_positive_int(
            source["ssh_key_id"], ValueError, "repository access key id must be positive"
        )
    return payload


def _create_repository(
    args: argparse.Namespace, client: SemaphoreClient, project: dict[str, Any], payload: dict[str, Any]
) -> int:
    """Create one repository and print safe result details."""
    request = {"project_id": project["id"], **payload}
    created = client.create_repository(project["id"], request)
    result = {
        "project": project,
        "repository": {key: created[key] for key in ("id", "project_id", "name")},
        "configuration": _safe_repository_configuration(created),
    }
    _print(result, args.as_json)
    return 0


def _handle_repository_create(args: argparse.Namespace, client: SemaphoreClient) -> int:
    """Create a repository resource in an existing project."""
    project = client.find_project(args.project)
    repositories = client.list_repositories(project["id"])
    if any(repository.get("name") == args.name for repository in repositories):
        raise ValueError(f"repository already exists: {args.name}")
    source = {"git_url": args.git_url, "git_branch": args.git_branch}
    if args.access_key:
        source["ssh_key_id"] = require_positive_int(
            client.find_access_key(project["id"], args.access_key).get("id"),
            ValueError,
            "resolved access key did not contain a positive id",
        )
    return _create_repository(args, client, project, _repository_payload(source, args.name))


def _handle_repository_copy(args: argparse.Namespace, client: SemaphoreClient) -> int:
    """Copy one repository resource, optionally overriding its branch."""
    if args.repository == args.name:
        raise ValueError("repository copy source and destination names must differ")
    project = client.find_project(args.project)
    repositories = client.list_repositories(project["id"])
    if any(repository.get("name") == args.name for repository in repositories):
        raise ValueError(f"repository already exists: {args.name}")
    source = client.find_repository(project["id"], args.repository)
    payload = _repository_payload(source, args.name, args.git_branch)
    return _create_repository(args, client, project, payload)


def _handle_repository_update(args: argparse.Namespace, client: SemaphoreClient) -> int:
    """Update a repository's branch and verify the persisted configuration."""
    project = client.find_project(args.project)
    repository = client.find_repository(project["id"], args.repository)
    repository_id = require_positive_int(repository.get("id"), ValueError, "repository id must be positive")
    payload = _safe_repository_configuration(repository)
    payload["project_id"] = project["id"]
    payload["git_branch"] = require_nonempty_string(args.git_branch, ValueError, "repository git branch must be a non-empty string")
    updated = client.update_repository(project["id"], repository_id, payload)
    if updated.get("id") != repository_id or updated.get("project_id") != project["id"]:
        raise ValueError("updated repository identity did not match the request")
    persisted = client.find_repository(project["id"], args.repository)
    if _safe_repository_configuration(persisted) != _safe_repository_configuration(updated):
        raise ValueError("updated repository did not match the requested configuration")
    result = {
        "project": project,
        "repository": {key: persisted[key] for key in ("id", "project_id", "name")},
        "configuration": _safe_repository_configuration(persisted),
    }
    _print(result, args.as_json)
    return 0


def _handle_template_list(args: argparse.Namespace, client: SemaphoreClient) -> int:
    """List templates in a project."""
    project = client.find_project(args.project)
    _print(client.list_templates(project["id"]), args.as_json)
    return 0


def _handle_template_show(args: argparse.Namespace, client: SemaphoreClient) -> int:
    """Show one project template resolved by exact name."""
    project = client.find_project(args.project)
    template = client.find_template(project["id"], args.template)
    _print(template, args.as_json)
    return 0


def _safe_inventory_configuration(inventory: dict[str, Any]) -> dict[str, Any]:
    """Return non-secret inventory identity and configuration fields."""
    return {
        key: inventory[key]
        for key in ("id", "project_id", "name", "type", "template_id")
        if key in inventory
    }


def _safe_access_key_identity(access_key: dict[str, Any]) -> dict[str, Any]:
    """Return non-secret access-key identity fields."""
    return {
        key: access_key[key]
        for key in ("id", "project_id", "name", "type", "login", "owner")
        if key in access_key
    }


def _handle_inventory_list(args: argparse.Namespace, client: SemaphoreClient) -> int:
    """List inventories in a project without exposing credentials."""
    project = client.find_project(args.project)
    _print([_safe_inventory_configuration(item) for item in client.list_inventories(project["id"])], args.as_json)
    return 0


def _handle_inventory_show(args: argparse.Namespace, client: SemaphoreClient) -> int:
    """Show one project inventory without exposing credentials."""
    project = client.find_project(args.project)
    inventory = client.find_inventory(project["id"], args.inventory)
    _print(_safe_inventory_configuration(inventory), args.as_json)
    return 0


_INVENTORY_TYPES = ("static", "static-yaml", "file", "terraform-workspace")
_INVENTORY_FIELDS = ("inventory", "type", "ssh_key_id", "become_key_id", "repository_id")


def _inventory_reference_id(
    client: SemaphoreClient, project_id: int, name: str | None, resource: str
) -> int | None:
    """Resolve an optional project resource name to a positive ID."""
    if name is None:
        return None
    if resource == "access key":
        item = client.find_access_key(project_id, name)
    else:
        item = client.find_repository(project_id, name)
    return require_positive_int(item.get("id"), ValueError, f"resolved {resource} id must be positive")


def _inventory_payload(
    client: SemaphoreClient,
    project_id: int,
    *,
    name: str,
    inventory_path: str | None,
    inventory_type: str | None,
    ssh_key: str | None,
    become_key: str | None,
    repository: str | None,
) -> dict[str, Any]:
    """Build an inventory mutation payload from explicit CLI options."""
    payload: dict[str, Any] = {"name": require_nonempty_string(name, ValueError, "inventory name must be a non-empty string")}
    if inventory_path is not None:
        payload["inventory"] = require_nonempty_string(
            inventory_path, ValueError, "inventory path must be a non-empty string"
        )
    if inventory_type is not None:
        payload["type"] = inventory_type
    access_key_id = _inventory_reference_id(client, project_id, ssh_key, "access key")
    if access_key_id is not None:
        payload["ssh_key_id"] = access_key_id
    become_key_id = _inventory_reference_id(client, project_id, become_key, "access key")
    if become_key_id is not None:
        payload["become_key_id"] = become_key_id
    repository_id = _inventory_reference_id(client, project_id, repository, "repository")
    if repository_id is not None:
        payload["repository_id"] = repository_id
    return payload


def _safe_inventory_mutation_result(
    project: dict[str, Any], inventory: dict[str, Any]
) -> dict[str, Any]:
    """Return a safe envelope for an inventory mutation."""
    return {
        "project": project,
        "inventory": {key: inventory[key] for key in ("id", "project_id", "name") if key in inventory},
        "configuration": _safe_inventory_configuration(inventory),
    }


def _handle_inventory_create(args: argparse.Namespace, client: SemaphoreClient) -> int:
    """Create an inventory resource from explicit CLI options."""
    project = client.find_project(args.project)
    inventories = client.list_inventories(project["id"])
    if any(item.get("name") == args.name for item in inventories):
        raise ValueError(f"inventory already exists: {args.name}")
    payload = {"project_id": project["id"], **_inventory_payload(
        client,
        project["id"],
        name=args.name,
        inventory_path=args.inventory_path,
        inventory_type=args.type,
        ssh_key=args.ssh_key,
        become_key=args.become_key,
        repository=args.repository,
    )}
    created = client.create_inventory(project["id"], payload)
    _print(_safe_inventory_mutation_result(project, created), args.as_json)
    return 0


def _inventory_copy_payload(source: dict[str, Any], destination: str) -> dict[str, Any]:
    """Build a safe inventory-create payload from a source resource."""
    payload = {key: source[key] for key in _INVENTORY_FIELDS if key in source}
    payload["name"] = require_nonempty_string(
        destination, ValueError, "inventory name must be a non-empty string"
    )
    return payload


def _handle_inventory_copy(args: argparse.Namespace, client: SemaphoreClient) -> int:
    """Copy an inventory resource without exposing its content."""
    if args.inventory == args.name:
        raise ValueError("inventory copy source and destination names must differ")
    project = client.find_project(args.project)
    inventories = client.list_inventories(project["id"])
    if any(item.get("name") == args.name for item in inventories):
        raise ValueError(f"inventory already exists: {args.name}")
    source = client.find_inventory(project["id"], args.inventory)
    created = client.create_inventory(
        project["id"], {"project_id": project["id"], **_inventory_copy_payload(source, args.name)}
    )
    _print(_safe_inventory_mutation_result(project, created), args.as_json)
    return 0


def _handle_inventory_update(args: argparse.Namespace, client: SemaphoreClient) -> int:
    """Update explicit inventory options and verify persisted state."""
    if all(value is None for value in (args.path, args.type, args.ssh_key, args.become_key, args.repository)):
        raise ValueError("inventory update requires at least one update option")
    project = client.find_project(args.project)
    source = client.find_inventory(project["id"], args.inventory)
    payload = {"id": source["id"], "project_id": project["id"], "name": source["name"]}
    payload.update({key: source[key] for key in _INVENTORY_FIELDS if key in source})
    payload.update(_inventory_payload(
        client,
        project["id"],
        name=source["name"],
        inventory_path=args.path,
        inventory_type=args.type,
        ssh_key=args.ssh_key,
        become_key=args.become_key,
        repository=args.repository,
    ))
    updated = client.update_inventory(project["id"], source["id"], payload)
    persisted = client.find_inventory(project["id"], source["name"])
    for field in ("name", "inventory", "type", "ssh_key_id", "become_key_id", "repository_id"):
        if field in payload and persisted.get(field) != payload[field]:
            raise ValueError(f"updated inventory did not match requested {field}")
    _print(_safe_inventory_mutation_result(project, persisted), args.as_json)
    return 0


def _handle_access_key_list(args: argparse.Namespace, client: SemaphoreClient) -> int:
    """List access-key identities in a project."""
    project = client.find_project(args.project)
    _print([_safe_access_key_identity(item) for item in client.list_access_keys(project["id"])], args.as_json)
    return 0


def _handle_access_key_show(args: argparse.Namespace, client: SemaphoreClient) -> int:
    """Show one access-key identity without exposing key material."""
    project = client.find_project(args.project)
    access_key = client.find_access_key(project["id"], args.access_key)
    _print(_safe_access_key_identity(access_key), args.as_json)
    return 0


_TEMPLATE_FIELDS = {
    "name",
    "repository",
    "inventory",
    "environment",
    "playbook",
    "description",
    "git_branch",
    "type",
    "arguments",
    "survey_vars",
    "task_params",
    "view",
    "vaults",
}
_TEMPLATE_REQUIRED_FIELDS = {"name", "repository", "inventory", "playbook"}
_DEFAULT_TEMPLATE_APP = "ansible"
_SURVEY_TYPES = {"", "int", "enum", "secret", "text", "select"}
_SURVEY_TARGETS = {"", "env"}
_SURVEY_FIELDS = {"name", "title", "description", "type", "target", "required", "values", "default_value"}
_VAULT_FIELDS = {"name", "type", "vault_key", "script"}
_VAULT_TYPES = {"password", "script"}


def _is_named_string_value(value: Any) -> bool:
    """Return whether one survey option has only string name and value fields.

    Args:
        value: Candidate survey-variable option.

    Returns:
        True when the candidate has the supported object shape.
    """
    if not isinstance(value, dict) or set(value) - {"name", "value"}:
        return False
    return isinstance(value.get("name"), str) and isinstance(value.get("value"), str)


def _are_named_string_values(value: Any) -> bool:
    """Return whether survey values have the supported name/value object shape.

    Args:
        value: Candidate survey-variable options from the request file.

    Returns:
        True when every option has only non-empty string ``name`` and ``value`` fields.
    """
    return isinstance(value, list) and all(_is_named_string_value(option) for option in value)


def _validate_survey_values(item: dict[str, Any], index: int) -> None:
    """Validate non-secret named options for one survey variable.

    Args:
        item: Typed survey-variable mapping that contains ``values``.
        index: Zero-based position used in validation messages.

    Raises:
        ValueError: If a secret variable supplies values or the option shape is invalid.
    """
    if item.get("type") == "secret":
        raise ValueError("template secret survey variables cannot include values")
    if not _are_named_string_values(item["values"]):
        raise ValueError(f"template survey_vars[{index}].values must be name/value objects")


def _validate_survey_default(item: dict[str, Any], index: int) -> None:
    """Validate a non-secret survey default and its type-specific constraints."""
    if "default_value" not in item:
        return
    default = item["default_value"]
    if isinstance(default, list):
        if not all(isinstance(value, str) for value in default):
            raise ValueError(f"template survey_vars[{index}].default_value must contain only strings")
        if item.get("type") != "select":
            raise ValueError(f"template survey_vars[{index}].default_value list requires type select")
        defaults = default
    elif isinstance(default, str):
        defaults = [default]
    else:
        raise ValueError(f"template survey_vars[{index}].default_value must be a string or string list")
    if item.get("type") == "secret":
        raise ValueError("template secret survey variables cannot include default_value")
    if item.get("type") in {"enum", "select"}:
        values = item.get("values", [])
        allowed = {value.get("value") for value in values if isinstance(value, dict)}
        if any(default_value not in allowed for default_value in defaults):
            raise ValueError(f"template survey_vars[{index}].default_value must be in values")


def _validate_survey_choice(
    item: dict[str, Any], field: str, supported_values: set[str], index: int
) -> None:
    """Validate one optional survey field against its supported values.

    Args:
        item: Typed survey-variable mapping.
        field: Optional survey field to validate.
        supported_values: Values accepted for the field.
        index: Zero-based position used in validation messages.

    Raises:
        ValueError: If the field is present with an unsupported value.
    """
    if item.get(field, "") not in supported_values:
        raise ValueError(f"template survey_vars[{index}].{field} is unsupported")


def _validate_survey_identity(item: dict[str, Any], index: int) -> None:
    """Validate a survey variable's required identity and descriptive fields.

    Args:
        item: Typed survey-variable mapping.
        index: Zero-based position used in validation messages.

    Raises:
        ValueError: If required strings or description are invalid.
    """
    for field in ("name", "title"):
        require_nonempty_string(
            item.get(field), ValueError, f"template survey_vars[{index}].{field} must be a non-empty string"
        )
    if "description" in item and not isinstance(item["description"], str):
        raise ValueError(f"template survey_vars[{index}].description must be a string")


def _require_survey_object(value: Any, index: int) -> dict[str, Any]:
    """Return a survey-variable mapping with only supported fields.

    Args:
        value: Candidate survey-variable value.
        index: Zero-based position used in validation messages.

    Returns:
        The typed survey-variable mapping.

    Raises:
        ValueError: If the value is not an object or has unknown fields.
    """
    if not isinstance(value, dict):
        raise ValueError(f"template survey_vars[{index}] has unsupported fields")
    if set(value) - _SURVEY_FIELDS:
        raise ValueError(f"template survey_vars[{index}] has unsupported fields")
    return value


def _validate_survey_options(item: dict[str, Any], index: int) -> None:
    """Validate a survey variable's type, target, required flag, and options.

    Args:
        item: Typed survey-variable mapping.
        index: Zero-based position used in validation messages.

    Raises:
        ValueError: If an option is unsupported or could expose a secret value.
    """
    _validate_survey_choice(item, "type", _SURVEY_TYPES, index)
    _validate_survey_choice(item, "target", _SURVEY_TARGETS, index)
    if "required" in item and not isinstance(item["required"], bool):
        raise ValueError(f"template survey_vars[{index}].required must be a boolean")
    if "values" in item:
        _validate_survey_values(item, index)
    _validate_survey_default(item, index)


def _validate_survey_var(value: Any, index: int) -> dict[str, Any]:
    """Validate one survey-variable object.

    Args:
        value: Candidate survey-variable object.
        index: Zero-based position used in validation messages.

    Returns:
        The validated survey-variable object.

    Raises:
        ValueError: If a field is malformed, unsupported, or exposes a secret.
    """
    item = _require_survey_object(value, index)
    _validate_survey_identity(item, index)
    _validate_survey_options(item, index)
    return item


def _validate_survey_vars(value: Any) -> list[dict[str, Any]]:
    """Validate the supported non-secret portion of survey-variable configuration.

    Args:
        value: Survey variable array from a template request.

    Returns:
        The validated survey variable objects.

    Raises:
        ValueError: If a survey variable has an unsupported shape or secret value.
    """
    if not isinstance(value, list):
        raise ValueError("template survey_vars must be a list")
    return [_validate_survey_var(item, index) for index, item in enumerate(value)]


def _validate_vaults(value: Any) -> list[dict[str, Any]]:
    """Validate name-based vault configuration without accepting credentials."""
    if not isinstance(value, list):
        raise ValueError("template vaults must be a list")
    result = []
    for index, vault in enumerate(value):
        if not isinstance(vault, dict) or set(vault) - _VAULT_FIELDS:
            raise ValueError(f"template vaults[{index}] has unsupported fields")
        item = dict(vault)
        item["name"] = require_nonempty_string(
            item.get("name"), ValueError, f"template vaults[{index}].name must be a non-empty string"
        )
        if item.get("type") not in _VAULT_TYPES:
            raise ValueError(f"template vaults[{index}].type is unsupported")
        for field in ("vault_key", "script"):
            if field in item:
                item[field] = require_nonempty_string(
                    item[field], ValueError, f"template vaults[{index}].{field} must be a non-empty string"
                )
        if "script" in item and item["type"] != "script":
            raise ValueError(f"template vaults[{index}].script requires type script")
        result.append(item)
    return result


def _contains_non_boolean(values: dict[str, Any], fields: set[str]) -> bool:
    """Return whether any selected field is present with a non-boolean value.

    Args:
        values: Candidate parameter mapping.
        fields: Keys whose values must be booleans.

    Returns:
        True when a present selected field is not a boolean.
    """
    return any(field in values and not isinstance(values[field], bool) for field in fields)


def _contains_non_string_list(values: dict[str, Any], fields: set[str]) -> bool:
    """Return whether any selected field is present with a non-string-list value.

    Args:
        values: Candidate parameter mapping.
        fields: Keys whose values must be lists of strings.

    Returns:
        True when a present selected field is not a string list.
    """
    return any(
        field in values
        and (not isinstance(values[field], list) or not all(isinstance(item, str) for item in values[field]))
        for field in fields
    )


def _validate_task_params(value: Any) -> dict[str, Any]:
    """Validate task parameters accepted by the published Semaphore API schema.

    Args:
        value: Task parameter object from a template request.

    Returns:
        The validated task parameter object.

    Raises:
        ValueError: If a parameter field or value has an unsupported shape.

    Examples:
        ``{"params": {"dry_run": true, "tags": ["firewall"]}}`` is a
        supported task-parameter object. ``dry_run`` must be boolean, while
        ``tags``, ``limit``, and ``skip_tags`` must be lists of strings.
    """
    allowed_fields = {"environment", "git_branch", "message", "arguments", "params"}
    if not isinstance(value, dict) or set(value) - allowed_fields:
        raise ValueError("template task_params has unsupported fields")
    for field in ("environment", "git_branch", "message", "arguments"):
        if field in value and not isinstance(value[field], str):
            raise ValueError(f"template task_params.{field} must be a string")
    if "params" in value:
        params = value["params"]
        boolean_fields = {"debug", "dry_run", "diff", "skip_galaxy_install", "plan", "destroy", "auto_approve", "upgrade"}
        list_fields = {"limit", "tags", "skip_tags"}
        if not isinstance(params, dict) or set(params) - boolean_fields - list_fields:
            raise ValueError("template task_params.params has unsupported fields")
        if _contains_non_boolean(params, boolean_fields):
            raise ValueError("template task_params.params boolean values must be booleans")
        if _contains_non_string_list(params, list_fields):
            raise ValueError("template task_params.params list values must be string lists")
    return value


def _validate_template_request(request: dict[str, Any]) -> dict[str, Any]:
    """Validate a name-based template request before resource lookup or POST.

    Args:
        request: Template fields supplied directly or loaded from JSON.

    Returns:
        A validated copy of the request, with the default template type included.

    Raises:
        ValueError: If required fields, types, or nested settings are invalid.

    Examples:
        A minimal request is ``{"name": "deploy-web", "repository": "web",
        "inventory": "production", "environment": "default", "playbook":
        "deploy.yml"}``. The returned copy includes ``"type": ""`` when no
        template type is supplied.
    """
    unknown = set(request) - _TEMPLATE_FIELDS
    if unknown:
        raise ValueError(f"template request has unsupported fields: {', '.join(sorted(unknown))}")
    missing = sorted(field for field in _TEMPLATE_REQUIRED_FIELDS if field not in request)
    if missing:
        raise ValueError(f"template request is missing required fields: {', '.join(missing)}")
    result = dict(request)
    for field in _TEMPLATE_REQUIRED_FIELDS:
        result[field] = require_nonempty_string(
            result[field], ValueError, f"template {field} must be a non-empty string"
        )
    for field in ("description", "git_branch", "arguments", "view"):
        if field in result and not isinstance(result[field], str):
            raise ValueError(f"template {field} must be a string")
    if "environment" in result:
        result["environment"] = require_nonempty_string(
            result["environment"], ValueError, "template environment must be a non-empty string"
        )
    template_type = result.get("type", "")
    if template_type not in {"", "build", "deploy"}:
        raise ValueError("template type must be one of: default, build, deploy")
    result["type"] = template_type
    if "survey_vars" in result:
        result["survey_vars"] = _validate_survey_vars(result["survey_vars"])
    if "task_params" in result:
        result["task_params"] = _validate_task_params(result["task_params"])
    if "vaults" in result:
        result["vaults"] = _validate_vaults(result["vaults"])
    return result


def _inline_json_objects(values: list[str], option: str) -> list[dict[str, Any]]:
    """Decode repeated JSON-object command-line options without reading a file."""
    result = []
    for value in values:
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{option} must be valid JSON: {exc.msg}") from exc
        if not isinstance(decoded, dict):
            raise ValueError(f"{option} must contain a JSON object")
        result.append(decoded)
    return result


def _template_request_from_args(args: argparse.Namespace) -> dict[str, Any]:
    """Load one exclusive direct-option or JSON-file template request.

    Args:
        args: Parsed template-create command arguments.

    Returns:
        A locally validated name-based request.

    Raises:
        ValueError: If modes conflict or the request file cannot be used safely.

    Examples:
        Direct parser fields produce a complete request such as
        ``{"name": "deploy-web", "repository": "web", "inventory":
        "production", "environment": "default", "playbook": "deploy.yml"}``.
        When ``args.file`` is set, its JSON object supplies that same complete
        request shape; the file path itself is not included in the request, and
        file and direct-option modes cannot be combined.
    """
    direct = {
        field: getattr(args, field)
        for field in _TEMPLATE_FIELDS
        if getattr(args, field, None) is not None
    }
    for field, option in (("survey_vars", "--survey-var"), ("vaults", "--vault")):
        if field in direct:
            direct[field] = _inline_json_objects(direct[field], option)
    if direct.get("type") == "default":
        direct["type"] = ""
    if args.file:
        if direct:
            raise ValueError("template --file cannot be combined with direct template options")
        try:
            with open(args.file, encoding="utf-8") as request_file:
                loaded = json.load(request_file)
        except OSError as exc:
            raise ValueError(f"unable to read template request file: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"template request file is not valid JSON: {exc.msg}") from exc
        if not isinstance(loaded, dict):
            raise ValueError("template request file must contain a JSON object")
        return _validate_template_request(loaded)
    return _validate_template_request(direct)


def _safe_template_configuration(
    request: dict[str, Any], resources: dict[str, dict[str, Any]], vaults: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return stable, non-secret configuration safe for command output.

    Args:
        request: Validated request before name-to-ID conversion.
        resources: Successfully resolved project resources by request field.

    Returns:
        An output-safe configuration envelope without sensitive request values.

    Examples:
        A validated request containing ``{"name": "deploy-web", "repository":
        "web", "inventory": "production", "environment": "default",
        "playbook": "deploy.yml", "type": "", "arguments": "--limit web"}``
        and resources containing repository ``{"id": 2, "name": "web"}``,
        inventory ``{"id": 3, "name": "production"}``, and environment
        ``{"id": 4, "name": "default"}`` returns their identities, the
        playbook, and type. It deliberately omits ``arguments`` and other
        secret- or execution-sensitive values; an optional view is included only
        when it has been resolved.
    """
    configuration = {
        key: {"id": resources[key]["id"], "name": resources[key]["name"]}
        for key in ("repository", "inventory")
    }
    if "environment" in resources:
        configuration["environment"] = {
            "id": resources["environment"]["id"], "name": resources["environment"]["name"]
        }
    else:
        configuration["environment"] = {"id": 0}
    for field in ("playbook", "description", "git_branch", "type"):
        if field in request:
            configuration[field] = request[field]
    configuration["app"] = _DEFAULT_TEMPLATE_APP
    if "view" in resources:
        configuration["view"] = {"id": resources["view"]["id"], "name": resources["view"]["name"]}
    if vaults:
        configuration["vaults"] = vaults
    return configuration


def _resource_id(resource: dict[str, Any], resource_name: str) -> int:
    """Return a resolved resource's positive ID before a mutating request.

    Args:
        resource: Resource object returned by Semaphore.
        resource_name: Human-readable name for a validation error.

    Returns:
        A positive resource identifier.

    Raises:
        ValueError: If the response does not contain a positive integer ID.
    """
    return require_positive_int(
        resource.get("id"), ValueError, f"resolved {resource_name} did not contain a positive id"
    )


def _resolve_vaults(
    client: SemaphoreClient, project_id: int, vaults: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Resolve vault-key names into API payload and output-safe vault entries."""
    payload_vaults = []
    safe_vaults = []
    for vault in vaults:
        payload_vault = {key: value for key, value in vault.items() if key != "vault_key"}
        safe_vault = {key: vault[key] for key in ("name", "type")}
        if "vault_key" in vault:
            key = client.find_access_key(project_id, vault["vault_key"])
            safe_key = {"id": _resource_id(key, "vault access key"), "name": key["name"]}
            payload_vault["vault_key_id"] = safe_key["id"]
            safe_vault["key"] = safe_key
        payload_vaults.append(payload_vault)
        safe_vaults.append(safe_vault)
    return payload_vaults, safe_vaults


def _handle_template_create(args: argparse.Namespace, client: SemaphoreClient) -> int:
    """Resolve named resources, create one template, and report it safely.

    Args:
        args: Parsed template-create arguments.
        client: Authenticated client used for lookup, preflight, and creation.

    Returns:
        Zero after successful creation.

    Raises:
        SemaphoreError: If Semaphore rejects lookup, preflight, or creation.
        ValueError: If request or resolved-resource validation fails.
    """
    request = _template_request_from_args(args)
    project = client.find_project(args.project)
    project_id = _resource_id(project, "project")
    resources = {
        "repository": client.find_repository(project_id, request["repository"]),
        "inventory": client.find_inventory(project_id, request["inventory"]),
    }
    if "environment" in request:
        resources["environment"] = client.find_environment(project_id, request["environment"])
    if "view" in request:
        resources["view"] = client.find_view(project_id, request["view"])
    payload_vaults, safe_vaults = _resolve_vaults(client, project_id, request.get("vaults", []))
    payload = {
        key: value
        for key, value in request.items()
        if key not in {"repository", "inventory", "environment", "view", "vaults"}
    }
    if payload_vaults:
        payload["vaults"] = payload_vaults
    payload.update(
        {f"{key}_id": _resource_id(resource, key) for key, resource in resources.items()}
    )
    payload.setdefault("environment_id", 0)
    payload["project_id"] = project_id
    payload["app"] = _DEFAULT_TEMPLATE_APP
    client.assert_template_create_supported(payload)
    created = client.create_template(project_id, payload)
    result = {
        "project": project,
        "template": {key: created[key] for key in ("id", "project_id", "name")},
        "configuration": _safe_template_configuration(request, resources, safe_vaults),
    }
    if args.as_json:
        _print(result, True)
    else:
        print(f"Created template {created['id']}: {created['name']}")
    return 0


def _copy_survey_vars(source: Any) -> list[dict[str, Any]]:
    """Return safe, validated survey definitions for a copied template.

    Args:
        source: Survey-variable collection returned by Semaphore.

    Returns:
        Validated survey-variable definitions without secret variables.

    Raises:
        ValueError: If the source is malformed or contains a secret variable.
    """
    survey_vars = _validate_survey_vars(source if source is not None else [])
    if any(item.get("type") == "secret" for item in survey_vars):
        raise ValueError("template copy cannot copy secret survey variables")
    return [dict(item) for item in survey_vars]


def _copy_vault(source: dict[str, Any], index: int) -> dict[str, Any]:
    """Validate and copy one non-secret vault reference."""
    secret_fields = {"script", "password", "value"}.intersection(source)
    if secret_fields:
        raise ValueError(f"template copy vaults[{index}] contain unsupported secret content")
    allowed = {"name", "type", "vault_key_id"}
    if set(source) - allowed:
        raise ValueError(f"template copy vaults[{index}] contain unsupported fields")
    if not isinstance(source.get("name"), str) or not isinstance(source.get("type"), str):
        raise ValueError(f"template copy vaults[{index}] have invalid identity")
    entry = {key: source[key] for key in ("name", "type")}
    if "vault_key_id" in source:
        entry["vault_key_id"] = require_positive_int(
            source["vault_key_id"], ValueError, "copied vault access key did not contain a positive id"
        )
    return entry


def _copy_vaults(source: Any) -> list[dict[str, Any]]:
    """Return safe vault references that can be submitted to template creation.

    Args:
        source: Vault-reference collection returned by Semaphore.

    Returns:
        Vault references containing names, types, and numeric key IDs.

    Raises:
        ValueError: If vault data contains secret content or an invalid key ID.
    """
    vaults = source if source is not None else []
    if not isinstance(vaults, list) or not all(isinstance(item, dict) for item in vaults):
        raise ValueError("template copy vaults must be a list of objects")
    return [_copy_vault(vault, index) for index, vault in enumerate(vaults)]


def _copy_task_params(source: Any) -> dict[str, Any] | None:
    """Validate supported task parameters from an existing template."""
    if source is None:
        return None
    if not isinstance(source, dict):
        raise ValueError("template copy task_params must be an object")
    task_params = dict(source)
    if task_params.pop("allow_override_inventory", False):
        raise ValueError("template copy cannot preserve allow_override_inventory")
    return _validate_task_params(task_params) if task_params else None


def _template_copy_request(source: dict[str, Any], destination: str) -> dict[str, Any]:
    """Build a create payload from a safe, supported source template.

    Args:
        source: Existing template returned by Semaphore.
        destination: New template name.

    Returns:
        A payload suitable for the existing template-create API path.

    Raises:
        ValueError: If required source fields or supported configuration are missing.
    """
    for field in ("repository_id", "inventory_id"):
        _resource_id(source, field.removesuffix("_id"))
    if not isinstance(source.get("playbook"), str) or not source["playbook"]:
        raise ValueError("template copy source has no usable playbook")
    environment_id = source.get("environment_id", 0)
    if not isinstance(environment_id, int) or isinstance(environment_id, bool) or environment_id < 0:
        raise ValueError("template copy source has an invalid environment")
    payload = {
        "name": destination,
        "repository_id": source["repository_id"],
        "inventory_id": source["inventory_id"],
        "environment_id": environment_id,
        "playbook": source["playbook"],
        "type": source.get("type", ""),
        "app": _DEFAULT_TEMPLATE_APP,
        **{
            field: source[field]
            for field in ("description", "git_branch", "arguments", "allow_override_branch_in_task")
            if field in source
        },
    }
    optional = {
        field: copier(source[field])
        for field, copier in {
            "survey_vars": _copy_survey_vars,
            "vaults": _copy_vaults,
            "task_params": _copy_task_params,
        }.items()
        if field in source
    }
    payload.update({key: value for key, value in optional.items() if value is not None})
    if "view_id" in source:
        payload["view_id"] = _resource_id(source, "view")
    return payload


def _safe_template_copy_configuration(payload: dict[str, Any]) -> dict[str, Any]:
    """Return non-secret configuration details for a copied template."""
    configuration = {
        key: payload[key]
        for key in ("repository_id", "inventory_id", "environment_id", "playbook", "type", "app")
        if key in payload
    }
    configuration.update({
        field: payload[field]
        for field in ("description", "git_branch", "allow_override_branch_in_task")
        if field in payload
    })
    configuration.update({field: payload[field] for field in ("survey_vars", "task_params") if field in payload})
    if "vaults" in payload:
        configuration["vaults"] = [
            {key: value for key, value in vault.items() if key != "vault_key_id"}
            for vault in payload["vaults"]
        ]
    return configuration


def _handle_template_copy(args: argparse.Namespace, client: SemaphoreClient) -> int:
    """Copy one existing template without executing it.

    Args:
        args: Parsed template-copy arguments.
        client: Authenticated client used for lookup, preflight, and creation.

    Returns:
        Zero after successful creation.

    Raises:
        SemaphoreError: If Semaphore rejects lookup, preflight, or creation.
        ValueError: If the source or destination is invalid.
    """
    if args.template == args.name:
        raise ValueError("template copy source and destination names must differ")
    project = client.find_project(args.project)
    project_id = _resource_id(project, "project")
    templates = client.list_templates(project_id)
    if any(template.get("name") == args.name for template in templates):
        raise ValueError(f"template already exists: {args.name}")
    source = client.find_template(project_id, args.template)
    payload = _template_copy_request(source, args.name)
    payload["project_id"] = project_id
    client.assert_template_create_supported(payload)
    created = client.create_template(project_id, payload)
    result = {
        "project": project,
        "source_template": {key: source[key] for key in ("id", "project_id", "name")},
        "template": {key: created[key] for key in ("id", "project_id", "name")},
        "configuration": _safe_template_copy_configuration(payload),
    }
    if args.as_json:
        _print(result, True)
    else:
        print(f"Created template {created['id']}: {created['name']} from {source['name']}")
    return 0


def _handle_template_update(args: argparse.Namespace, client: SemaphoreClient) -> int:
    """Update a template's branch and verify its persisted configuration."""
    project = client.find_project(args.project)
    project_id = _resource_id(project, "project")
    source = client.find_template(project_id, args.template)
    template_id = _resource_id(source, "template")
    payload = _template_copy_request(source, source["name"])
    payload.update({"id": template_id, "project_id": project_id, "git_branch": args.git_branch})
    updated = client.update_template(project_id, template_id, payload)
    if updated.get("id") != template_id or updated.get("project_id") != project_id:
        raise ValueError("updated template identity did not match the request")
    expected = _safe_template_copy_configuration(payload)
    actual = _safe_template_copy_configuration(updated)
    # Semaphore omits default-valued fields such as an empty template type
    # from some read-back responses. Treat those omissions as equivalent while
    # still requiring every explicitly configured non-default value to match.
    if any(actual.get(key, "") != value for key, value in expected.items()):
        raise ValueError("updated template did not match the requested configuration")
    result = {
        "project": project,
        "template": {key: updated[key] for key in ("id", "project_id", "name")},
        "configuration": actual,
    }
    _print(result, args.as_json)
    return 0


def _handle_run(args: argparse.Namespace, client: SemaphoreClient) -> int:
    """Resolve and trigger a named template, optionally waiting for completion."""
    project = client.find_project(args.project)
    template = client.find_template(project["id"], args.template)
    variables = _variables(args.var)
    task = client.create_task(project["id"], template["id"], variables)
    result: dict[str, Any] = {"project": project, "template": template, "task": task, "variables": variables}
    if args.wait:
        result["task"] = _wait(client, project["id"], task["id"], args.poll_interval, args.timeout)
    _print(result, args.as_json)
    return 1 if result["task"].get("status", "").lower() in {"failed", "error", "stopped", "canceled", "cancelled"} else 0


def _handle_status(args: argparse.Namespace, client: SemaphoreClient) -> int:
    """Handle the ``status`` command with a stable project/task envelope."""
    project = client.find_project(args.project)
    task = client.get_task(project["id"], args.task)
    _print({"project": project, "task": task}, args.as_json)
    return 0


def _handle_output(args: argparse.Namespace, client: SemaphoreClient) -> int:
    """Handle the ``output`` command in JSON or line-oriented form."""
    project = client.find_project(args.project)
    output = client.get_output(project["id"], args.task)
    if args.as_json:
        _print(output, True)
    else:
        for line in output:
            text = _plain(line["output"]) if args.plain else line["output"]
            print(text, end="" if text.endswith("\n") else "\n")
    return 0


@dataclass(frozen=True)
class TaskFilters:
    """User-selected predicates for historical task discovery.

    Attributes:
        status: Optional case-insensitive task status.
        template: Optional exact template name.
        variables: Environment values that must all match.
        since: Optional inclusive creation-time lower bound.
        until: Optional inclusive creation-time upper bound.
    """

    status: str | None = None
    template: str | None = None
    variables: dict[str, str] | None = None
    since: str | None = None
    until: str | None = None


def _parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp for task-history filtering.

    Args:
        value: ISO-8601 timestamp including a timezone.

    Returns:
        A timezone-aware datetime.

    Raises:
        ValueError: If the timestamp is invalid or has no timezone.
    """
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid timestamp: {value!r}") from exc
    if timestamp.tzinfo is None:
        raise ValueError(f"timestamp must include a timezone: {value!r}")
    return timestamp


def _matches_time_range(task: dict[str, Any], since: datetime | None, until: datetime | None) -> bool:
    """Return whether a task creation time falls within inclusive bounds.

    Args:
        task: Normalized task dictionary.
        since: Optional inclusive lower bound.
        until: Optional inclusive upper bound.

    Returns:
        True when the task is within the supplied bounds.

    Raises:
        ValueError: If a bounded task has no valid creation timestamp.
    """
    if since is None and until is None:
        return True
    if not isinstance(task.get("created"), str):
        raise ValueError(f"task {task.get('id', '')} has no creation timestamp")
    created = _parse_timestamp(task["created"])
    return (since is None or created >= since) and (until is None or created <= until)


def _matches_task(task: dict[str, Any], filters: TaskFilters) -> bool:
    """Return whether a normalized task matches every selected filter.

    Args:
        task: Normalized task dictionary.
        filters: User-selected task predicates.

    Returns:
        True when status, template, variables, and time bounds all match.

    Raises:
        ValueError: If the filter timestamps are invalid or reversed.
    """
    wanted_status = filters.status.lower() if filters.status else None
    since = _parse_timestamp(filters.since) if filters.since else None
    until = _parse_timestamp(filters.until) if filters.until else None
    if since and until and since > until:
        raise ValueError("since timestamp cannot be after until timestamp")
    return all(
        (
            wanted_status is None or task.get("status", "").lower() == wanted_status,
            filters.template is None or task.get("template", {}).get("name") == filters.template,
            not filters.variables
            or all(task.get("environment", {}).get(name) == value for name, value in filters.variables.items()),
            _matches_time_range(task, since, until),
        )
    )


def _filter_tasks(tasks: list[dict[str, Any]], filters: TaskFilters) -> list[dict[str, Any]]:
    """Return normalized tasks matching all selected filters.

    Args:
        tasks: Normalized task dictionaries.
        filters: User-selected task predicates.

    Returns:
        The subset of tasks matching every selected predicate.
    """
    return [task for task in tasks if _matches_task(task, filters)]


def _handle_tasks(args: argparse.Namespace, client: SemaphoreClient) -> int:
    """Handle bounded historical task discovery and filtering.

    Args:
        args: Parsed arguments for the ``tasks`` command.
        client: Configured Semaphore client.

    Returns:
        Zero after printing the matching task results.

    Raises:
        SemaphoreError: If project or task retrieval fails.
        ValueError: If a variable or filter value is invalid.
    """
    project = client.find_project(args.project)
    filters = TaskFilters(
        status=args.status,
        template=args.template,
        variables=_variables(args.var),
        since=getattr(args, "since", None),
        until=getattr(args, "until", None),
    )
    fetched_tasks = client.list_tasks(project["id"], args.limit)
    tasks = _filter_tasks(fetched_tasks, filters)
    _print(
        {"project": project, "tasks": tasks, "pagination": {"limit": args.limit, "has_more": len(fetched_tasks) == args.limit}},
        args.as_json,
    )
    return 0


def _handle_wait(args: argparse.Namespace, client: SemaphoreClient) -> int:
    """Handle the ``wait`` command and return task-based exit status."""
    project = client.find_project(args.project)
    task = _wait(client, project["id"], args.task, args.poll_interval, args.timeout)
    _print({"project": project, "task": task}, args.as_json)
    return 0 if task["status"].lower() == "success" else 1


def _add_project_list_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments shared by project-list commands."""
    _add_json_argument(parser)


def _add_project_show_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments shared by project-show commands."""
    parser.add_argument("--project", required=True, help="exact project name")
    _add_json_argument(parser)


def _add_repository_list_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments shared by repository-list commands."""
    parser.add_argument("--project", required=True, help="exact project name")
    _add_json_argument(parser)


def _add_repository_show_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments shared by repository-show commands."""
    parser.add_argument("--project", required=True, help="exact project name")
    parser.add_argument("--repository", required=True, help="exact repository name")
    _add_json_argument(parser)


def _add_template_list_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments shared by template-list commands."""
    parser.add_argument("--project", required=True, help="exact project name")
    _add_json_argument(parser)


def _add_template_show_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments shared by template-show commands."""
    parser.add_argument("--project", required=True, help="exact project name")
    parser.add_argument("--template", required=True, help="exact template name")
    _add_json_argument(parser)


def _add_run_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments shared by task-run commands."""
    parser.add_argument("--project", required=True)
    parser.add_argument("--template", required=True)
    parser.add_argument("--var", action="append", default=[], metavar="NAME=VALUE")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--timeout", type=float, default=300.0)
    _add_json_argument(parser)


def _add_status_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments shared by task-status commands."""
    parser.add_argument("--project", required=True)
    parser.add_argument("--task", required=True, type=int)
    _add_json_argument(parser)


def _add_output_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments shared by task-output commands."""
    parser.add_argument("--project", required=True)
    parser.add_argument("--task", required=True, type=int)
    parser.add_argument("--plain", action="store_true")
    _add_json_argument(parser)


def _add_task_list_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments shared by task-list commands."""
    parser.add_argument("--project", required=True)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--status")
    parser.add_argument("--template")
    parser.add_argument("--since", help="include tasks created at or after this ISO-8601 timestamp")
    parser.add_argument("--until", help="include tasks created at or before this ISO-8601 timestamp")
    parser.add_argument("--var", action="append", default=[], metavar="NAME=VALUE")
    _add_json_argument(parser)


def _add_wait_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments shared by task-wait commands."""
    parser.add_argument("--project", required=True)
    parser.add_argument("--task", required=True, type=int)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--timeout", type=float, default=300.0)
    _add_json_argument(parser)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser and dispatch table.

    Returns:
        An argparse parser whose subcommands carry their handler functions.
    """
    parser = argparse.ArgumentParser(prog="semaphore-ui", description="Run and inspect Semaphore UI tasks")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="disable TLS certificate verification (explicitly opt in; use only for trusted internal endpoints)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    project = sub.add_parser("project", help="manage projects")
    project_sub = project.add_subparsers(dest="project_command", required=True)
    project_list = project_sub.add_parser("list", help="list projects")
    _add_project_list_arguments(project_list)
    project_list.set_defaults(handler=_handle_project_list)
    project_show = project_sub.add_parser("show", help="show one project")
    _add_project_show_arguments(project_show)
    project_show.set_defaults(handler=_handle_project_show)

    repository = sub.add_parser("repository", help="manage repositories")
    repository_sub = repository.add_subparsers(dest="repository_command", required=True)
    repository_list = repository_sub.add_parser("list", help="list repositories in a project")
    _add_repository_list_arguments(repository_list)
    repository_list.set_defaults(handler=_handle_repository_list)
    repository_show = repository_sub.add_parser("show", help="show one repository")
    _add_repository_show_arguments(repository_show)
    repository_show.set_defaults(handler=_handle_repository_show)
    repository_create = repository_sub.add_parser("create", help="create a repository resource")
    repository_create.add_argument("--project", required=True, help="exact project name")
    repository_create.add_argument("--name", required=True, help="new repository name")
    repository_create.add_argument("--git-url", required=True, help="Git repository URL")
    repository_create.add_argument("--git-branch", required=True, help="Git branch or ref")
    repository_create.add_argument("--access-key", help="exact project access-key name")
    _add_json_argument(repository_create)
    repository_create.set_defaults(handler=_handle_repository_create)
    repository_copy = repository_sub.add_parser("copy", help="copy a repository resource")
    repository_copy.add_argument("--project", required=True, help="exact project name")
    repository_copy.add_argument("--repository", required=True, help="exact source repository name")
    repository_copy.add_argument("--name", required=True, help="new repository name")
    repository_copy.add_argument("--git-branch", help="branch or ref override")
    _add_json_argument(repository_copy)
    repository_copy.set_defaults(handler=_handle_repository_copy)
    repository_update = repository_sub.add_parser("update", help="update a repository resource")
    repository_update.add_argument("--project", required=True, help="exact project name")
    repository_update.add_argument("--repository", required=True, help="exact repository name")
    repository_update.add_argument("--git-branch", required=True, help="new Git branch or ref")
    _add_json_argument(repository_update)
    repository_update.set_defaults(handler=_handle_repository_update)

    inventory = sub.add_parser("inventory", help="manage project inventories")
    inventory_sub = inventory.add_subparsers(dest="inventory_command", required=True)
    inventory_list = inventory_sub.add_parser("list", help="list inventories in a project")
    inventory_list.add_argument("--project", required=True, help="exact project name")
    _add_json_argument(inventory_list)
    inventory_list.set_defaults(handler=_handle_inventory_list)
    inventory_show = inventory_sub.add_parser("show", help="show one inventory")
    inventory_show.add_argument("--project", required=True, help="exact project name")
    inventory_show.add_argument("--inventory", required=True, help="exact inventory name")
    _add_json_argument(inventory_show)
    inventory_show.set_defaults(handler=_handle_inventory_show)
    inventory_create = inventory_sub.add_parser("create", help="create an inventory resource")
    inventory_create.add_argument("--project", required=True, help="exact project name")
    inventory_create.add_argument("--name", required=True, help="new inventory name")
    inventory_create.add_argument("--type", required=True, choices=_INVENTORY_TYPES)
    inventory_create.add_argument("--path", required=True, dest="inventory_path", help="inventory path or content")
    inventory_create.add_argument("--ssh-key", help="exact project access-key name")
    inventory_create.add_argument("--become-key", help="exact project access-key name")
    inventory_create.add_argument("--repository", help="exact repository name in the project")
    _add_json_argument(inventory_create)
    inventory_create.set_defaults(handler=_handle_inventory_create)
    inventory_copy = inventory_sub.add_parser("copy", help="copy an inventory resource")
    inventory_copy.add_argument("--project", required=True, help="exact project name")
    inventory_copy.add_argument("--inventory", required=True, help="exact source inventory name")
    inventory_copy.add_argument("--name", required=True, help="new inventory name")
    _add_json_argument(inventory_copy)
    inventory_copy.set_defaults(handler=_handle_inventory_copy)
    inventory_update = inventory_sub.add_parser("update", help="update an inventory resource")
    inventory_update.add_argument("--project", required=True, help="exact project name")
    inventory_update.add_argument("--inventory", required=True, help="exact inventory name")
    inventory_update.add_argument("--type", choices=_INVENTORY_TYPES)
    inventory_update.add_argument("--path", dest="path", help="new inventory path or content")
    inventory_update.add_argument("--ssh-key", help="exact project access-key name")
    inventory_update.add_argument("--become-key", help="exact project access-key name")
    inventory_update.add_argument("--repository", help="exact repository name in the project")
    _add_json_argument(inventory_update)
    inventory_update.set_defaults(handler=_handle_inventory_update)

    access_key = sub.add_parser("access-key", help="inspect project access-key identities")
    access_key_sub = access_key.add_subparsers(dest="access_key_command", required=True)
    access_key_list = access_key_sub.add_parser("list", help="list access-key identities in a project")
    access_key_list.add_argument("--project", required=True, help="exact project name")
    _add_json_argument(access_key_list)
    access_key_list.set_defaults(handler=_handle_access_key_list)
    access_key_show = access_key_sub.add_parser("show", help="show one access-key identity")
    access_key_show.add_argument("--project", required=True, help="exact project name")
    access_key_show.add_argument("--access-key", required=True, help="exact access-key name")
    _add_json_argument(access_key_show)
    access_key_show.set_defaults(handler=_handle_access_key_show)

    template = sub.add_parser("template", help="manage templates")
    template_sub = template.add_subparsers(dest="template_command", required=True)
    template_list = template_sub.add_parser("list", help="list templates in a project")
    _add_template_list_arguments(template_list)
    template_list.set_defaults(handler=_handle_template_list)
    template_show = template_sub.add_parser("show", help="show one template")
    _add_template_show_arguments(template_show)
    template_show.set_defaults(handler=_handle_template_show)

    create = template_sub.add_parser("create", help="create a template without running it")
    create.add_argument("--project", required=True, help="exact project name")
    create.add_argument(
        "--file",
        help=(
            "JSON request file for nested survey_vars[].default_value, vaults, and task_params; "
            "cannot be combined with template options"
        ),
    )
    create.add_argument("--survey-var", action="append", dest="survey_vars", metavar="JSON", help="survey variable JSON object; repeatable")
    create.add_argument("--vault", action="append", dest="vaults", metavar="JSON", help="vault JSON object; repeatable")
    create.add_argument("--name")
    create.add_argument("--repository", help="exact repository name in the project")
    create.add_argument("--inventory", help="exact inventory name in the project")
    create.add_argument("--environment", help="exact environment name in the project; omit for no environment")
    create.add_argument("--playbook", help="playbook path in the selected repository")
    create.add_argument("--description")
    create.add_argument("--git-branch")
    create.add_argument("--type", choices=("default", "build", "deploy"), dest="type")
    create.add_argument("--arguments", help="Semaphore arguments string")
    create.add_argument("--view", help="exact view name in the project")
    _add_json_argument(create)
    create.set_defaults(handler=_handle_template_create)

    copy = template_sub.add_parser("copy", help="copy a template without running it")
    copy.add_argument("--project", required=True, help="exact project name")
    copy.add_argument("--template", required=True, help="exact source template name")
    copy.add_argument("--name", required=True, help="new template name")
    _add_json_argument(copy)
    copy.set_defaults(handler=_handle_template_copy)
    template_update = template_sub.add_parser("update", help="update a template resource")
    template_update.add_argument("--project", required=True, help="exact project name")
    template_update.add_argument("--template", required=True, help="exact template name")
    template_update.add_argument("--git-branch", required=True, help="new Git branch or ref")
    _add_json_argument(template_update)
    template_update.set_defaults(handler=_handle_template_update)

    task = sub.add_parser("task", help="manage tasks")
    task_sub = task.add_subparsers(dest="task_command", required=True)
    task_run = task_sub.add_parser("run", help="trigger a task template")
    _add_run_arguments(task_run)
    task_run.set_defaults(handler=_handle_run)
    task_status = task_sub.add_parser("status", help="retrieve task status")
    _add_status_arguments(task_status)
    task_status.set_defaults(handler=_handle_status)
    task_output = task_sub.add_parser("output", help="retrieve task output")
    _add_output_arguments(task_output)
    task_output.set_defaults(handler=_handle_output)
    task_list = task_sub.add_parser("list", help="list historical tasks")
    _add_task_list_arguments(task_list)
    task_list.set_defaults(handler=_handle_tasks)
    task_wait = task_sub.add_parser("wait", help="wait for a task to finish")
    _add_wait_arguments(task_wait)
    task_wait.set_defaults(handler=_handle_wait)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, dispatch one command, and convert known errors to status 2.

    Args:
        argv: Optional argument list; defaults to ``sys.argv`` when omitted.

    Returns:
        Process exit status: zero for success, one for task failure, or two for
        configuration, lookup, API, and input errors.
    """
    args = build_parser().parse_args(argv)
    try:
        client = _client(args.insecure)
        return args.handler(args, client)
    except (SemaphoreError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
