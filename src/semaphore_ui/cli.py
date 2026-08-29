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
