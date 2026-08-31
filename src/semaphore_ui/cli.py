"""Command-line interface for Semaphore UI task automation.

Examples:
    List projects as JSON::

        semaphore-ui --insecure projects --json

    Run a template by exact project and template names::

        semaphore-ui --insecure run \\
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
from typing import Any, Callable

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


def _handle_projects(args: argparse.Namespace, client: SemaphoreClient) -> int:
    """Handle the ``projects`` command."""
    _print(client.list_projects(), args.as_json)
    return 0


def _handle_templates(args: argparse.Namespace, client: SemaphoreClient) -> int:
    """Handle the ``templates`` command."""
    project = client.find_project(args.project)
    _print(client.list_templates(project["id"]), args.as_json)
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
}
_TEMPLATE_REQUIRED_FIELDS = {"name", "repository", "inventory", "environment", "playbook"}
_SURVEY_TYPES = {"", "int", "enum", "secret", "text"}
_SURVEY_TARGETS = {"", "env"}
_SURVEY_FIELDS = {"name", "title", "description", "type", "target", "required", "values"}


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


def _are_named_string_values(value: Any) -> bool:
    """Return whether survey values have the supported name/value object shape.

    Args:
        value: Candidate survey-variable options from the request file.

    Returns:
        True when every option has only non-empty string ``name`` and ``value`` fields.
    """
    return isinstance(value, list) and all(_is_named_string_value(option) for option in value)


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


def _validate_task_params(value: Any) -> dict[str, Any]:
    """Validate task parameters accepted by the published Semaphore API schema.

    Args:
        value: Task parameter object from a template request.

    Returns:
        The validated task parameter object.

    Raises:
        ValueError: If a parameter field or value has an unsupported shape.
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


def _validate_template_request(request: dict[str, Any]) -> dict[str, Any]:
    """Validate a name-based template request before resource lookup or POST.

    Args:
        request: Template fields supplied directly or loaded from JSON.

    Returns:
        A validated copy of the request, with the default template type included.

    Raises:
        ValueError: If required fields, types, or nested settings are invalid.
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
    template_type = result.get("type", "")
    if template_type not in {"", "build", "deploy"}:
        raise ValueError("template type must be one of: default, build, deploy")
    result["type"] = template_type
    if "survey_vars" in result:
        result["survey_vars"] = _validate_survey_vars(result["survey_vars"])
    if "task_params" in result:
        result["task_params"] = _validate_task_params(result["task_params"])
    return result


def _template_request_from_args(args: argparse.Namespace) -> dict[str, Any]:
    """Load one exclusive direct-option or JSON-file template request.

    Args:
        args: Parsed template-create command arguments.

    Returns:
        A locally validated name-based request.

    Raises:
        ValueError: If modes conflict or the request file cannot be used safely.
    """
    direct = {
        field: getattr(args, field)
        for field in _TEMPLATE_FIELDS
        if getattr(args, field, None) is not None
    }
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


def _safe_template_configuration(request: dict[str, Any], resources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Return stable, non-secret configuration safe for command output.

    Args:
        request: Validated request before name-to-ID conversion.
        resources: Successfully resolved project resources by request field.

    Returns:
        An output-safe configuration envelope without sensitive request values.
    """
    configuration = {
        key: {"id": resources[key]["id"], "name": resources[key]["name"]}
        for key in ("repository", "inventory", "environment")
    }
    for field in ("playbook", "description", "git_branch", "type"):
        if field in request:
            configuration[field] = request[field]
    if "view" in resources:
        configuration["view"] = {"id": resources["view"]["id"], "name": resources["view"]["name"]}
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
        "environment": client.find_environment(project_id, request["environment"]),
    }
    if "view" in request:
        resources["view"] = client.find_view(project_id, request["view"])
    payload = {
        key: value
        for key, value in request.items()
        if key not in {"repository", "inventory", "environment", "view"}
    }
    payload.update(
        {f"{key}_id": _resource_id(resource, key) for key, resource in resources.items()}
    )
    payload["project_id"] = project_id
    client.assert_template_create_supported(payload)
    created = client.create_template(project_id, payload)
    result = {
        "project": project,
        "template": {key: created[key] for key in ("id", "project_id", "name")},
        "configuration": _safe_template_configuration(request, resources),
    }
    if args.as_json:
        _print(result, True)
    else:
        print(f"Created template {created['id']}: {created['name']}")
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

    projects = sub.add_parser("projects", help="list projects")
    _add_json_argument(projects)
    projects.set_defaults(handler=_handle_projects)

    templates = sub.add_parser("templates", help="list templates in a project")
    templates.add_argument("--project", required=True)
    _add_json_argument(templates)
    templates.set_defaults(handler=_handle_templates)

    template = sub.add_parser("template", help="manage a task template")
    template_sub = template.add_subparsers(dest="template_command", required=True)
    create = template_sub.add_parser("create", help="create a template without running it")
    create.add_argument("--project", required=True, help="exact project name")
    create.add_argument("--file", help="JSON request file; cannot be combined with template options")
    create.add_argument("--name")
    create.add_argument("--repository", help="exact repository name in the project")
    create.add_argument("--inventory", help="exact inventory name in the project")
    create.add_argument("--environment", help="exact environment name in the project")
    create.add_argument("--playbook", help="playbook path in the selected repository")
    create.add_argument("--description")
    create.add_argument("--git-branch")
    create.add_argument("--type", choices=("default", "build", "deploy"), dest="type")
    create.add_argument("--arguments", help="Semaphore arguments string")
    create.add_argument("--view", help="exact view name in the project")
    _add_json_argument(create)
    create.set_defaults(handler=_handle_template_create)

    run = sub.add_parser("run", help="trigger a task template by project and template name")
    run.add_argument("--project", required=True)
    run.add_argument("--template", required=True)
    run.add_argument("--var", action="append", default=[], metavar="NAME=VALUE")
    run.add_argument("--wait", action="store_true")
    run.add_argument("--poll-interval", type=float, default=2.0)
    run.add_argument("--timeout", type=float, default=300.0)
    _add_json_argument(run)
    run.set_defaults(handler=_handle_run)

    status = sub.add_parser("status", help="retrieve task status")
    status.add_argument("--project", required=True)
    status.add_argument("--task", required=True, type=int)
    _add_json_argument(status)
    status.set_defaults(handler=_handle_status)

    output = sub.add_parser("output", help="retrieve task output")
    output.add_argument("--project", required=True)
    output.add_argument("--task", required=True, type=int)
    output.add_argument("--plain", action="store_true")
    _add_json_argument(output)
    output.set_defaults(handler=_handle_output)

    tasks = sub.add_parser("tasks", help="list historical tasks in a project")
    tasks.add_argument("--project", required=True)
    tasks.add_argument("--limit", type=int, default=20)
    tasks.add_argument("--status")
    tasks.add_argument("--template")
    tasks.add_argument("--since", help="include tasks created at or after this ISO-8601 timestamp")
    tasks.add_argument("--until", help="include tasks created at or before this ISO-8601 timestamp")
    tasks.add_argument("--var", action="append", default=[], metavar="NAME=VALUE")
    _add_json_argument(tasks)
    tasks.set_defaults(handler=_handle_tasks)

    wait = sub.add_parser("wait", help="wait for a task to reach a terminal state")
    wait.add_argument("--project", required=True)
    wait.add_argument("--task", required=True, type=int)
    wait.add_argument("--poll-interval", type=float, default=2.0)
    wait.add_argument("--timeout", type=float, default=300.0)
    _add_json_argument(wait)
    wait.set_defaults(handler=_handle_wait)
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
