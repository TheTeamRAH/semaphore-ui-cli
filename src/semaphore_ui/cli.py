from __future__ import annotations

import argparse
import json
import re
import sys
import time
from typing import Any

from .api import SemaphoreClient, SemaphoreError, TERMINAL_STATES, TaskTimeoutError


def _variables(values: list[str]) -> dict[str, str]:
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
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)


def _print(value: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, indent=2, sort_keys=True))
    elif isinstance(value, list):
        for item in value:
            print(f"{item.get('id', '')}\t{item.get('name', item.get('status', ''))}")
    else:
        print(value)


def _client(insecure: bool = False) -> SemaphoreClient:
    return SemaphoreClient(insecure=insecure)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="semaphore-ui", description="Run and inspect Semaphore UI tasks")
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="disable TLS certificate verification (explicitly opt in; use only for trusted internal endpoints)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    projects = sub.add_parser("projects", help="list projects")
    projects.add_argument("--json", action="store_true", dest="as_json")

    templates = sub.add_parser("templates", help="list templates in a project")
    templates.add_argument("--project", required=True)
    templates.add_argument("--json", action="store_true", dest="as_json")

    run = sub.add_parser("run", help="trigger a task template by project and template name")
    run.add_argument("--project", required=True)
    run.add_argument("--template", required=True)
    run.add_argument("--var", action="append", default=[], metavar="NAME=VALUE")
    run.add_argument("--wait", action="store_true")
    run.add_argument("--poll-interval", type=float, default=2.0)
    run.add_argument("--timeout", type=float, default=300.0)
    run.add_argument("--json", action="store_true", dest="as_json")

    for name in ("status", "output"):
        item = sub.add_parser(name, help=f"retrieve task {name}")
        item.add_argument("--project", required=True)
        item.add_argument("--task", required=True, type=int)
        item.add_argument("--plain", action="store_true")
        item.add_argument("--json", action="store_true", dest="as_json")

    wait = sub.add_parser("wait", help="wait for a task to reach a terminal state")
    wait.add_argument("--project", required=True)
    wait.add_argument("--task", required=True, type=int)
    wait.add_argument("--poll-interval", type=float, default=2.0)
    wait.add_argument("--timeout", type=float, default=300.0)
    wait.add_argument("--json", action="store_true", dest="as_json")
    return parser


def _wait(client: SemaphoreClient, project_id: int, task_id: int, interval: float, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        task = client.get_task(project_id, task_id)
        if task["status"].lower() in TERMINAL_STATES:
            return task
        if time.monotonic() >= deadline:
            raise TaskTimeoutError(f"Task {task_id} did not finish within {timeout:g} seconds")
        time.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        client = _client(args.insecure)
        if args.command == "projects":
            _print(client.list_projects(), args.as_json)
        elif args.command == "templates":
            project = client.find_project(args.project)
            _print(client.list_templates(project["id"]), args.as_json)
        elif args.command == "run":
            project = client.find_project(args.project)
            template = client.find_template(project["id"], args.template)
            variables = _variables(args.var)
            task = client.create_task(project["id"], template["id"], variables)
            result: dict[str, Any] = {"project": project, "template": template, "task": task, "variables": variables}
            if args.wait:
                result["task"] = _wait(client, project["id"], task["id"], args.poll_interval, args.timeout)
            _print(result, args.as_json)
            if result["task"].get("status", "").lower() in {"failed", "error", "stopped", "canceled", "cancelled"}:
                return 1
        elif args.command == "status":
            task = client.find_project(args.project)
            _print(client.get_task(task["id"], args.task), args.as_json)
        elif args.command == "wait":
            project = client.find_project(args.project)
            task = _wait(client, project["id"], args.task, args.poll_interval, args.timeout)
            _print(task, args.as_json)
            return 0 if task["status"].lower() == "success" else 1
        elif args.command == "output":
            project = client.find_project(args.project)
            output = client.get_output(project["id"], args.task)
            if args.as_json:
                _print(output, True)
            else:
                for line in output:
                    text = _plain(line.get("output", "")) if args.plain else line.get("output", "")
                    print(text, end="" if text.endswith("\n") else "\n")
        return 0
    except (SemaphoreError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
