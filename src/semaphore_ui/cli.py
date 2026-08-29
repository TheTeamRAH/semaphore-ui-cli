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

from .api import SemaphoreClient, SemaphoreError, TERMINAL_STATES, TaskTimeoutError


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
