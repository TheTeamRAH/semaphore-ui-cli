---
type: Feature Specification
title: Discover and Filter Semaphore Task History
description: Add CLI commands for listing, inspecting, and filtering historical Semaphore UI tasks without requiring a curl fallback.
tags:
  - semaphore-ui
  - python
  - cli
  - task-history
  - discovery
sources:
  - https://semaphoreui.com/api-docs
  - https://docs.github.com/en/actions/concepts/billing-and-usage
status: proposed
---

# Discover and Filter Semaphore Task History

## Context

The initial `semaphore-ui` feature can list projects and templates, trigger tasks by project and template name, retrieve a known task by numeric ID, wait for completion, and retrieve output. It cannot enumerate historical tasks or search them by their submitted variables.

During end-to-end validation, identifying two previous successful tasks with different `target` and `fact` values required a direct read-only request to Semaphore's task collection endpoint. This fallback is inconvenient for users and prevents scripts and agent integrations from using the CLI as the single interface.

## Goal

Provide a safe, human-readable, and JSON-friendly task-history interface that can list and filter historical tasks by project, task identity, status, host, template, variable name/value, and time range where the deployed Semaphore API supports those fields.

## Scope

### In scope

- Add a command for listing historical tasks in a named project.
- Resolve projects by exact name, consistent with existing commands.
- Support bounded pagination or an explicit maximum result count.
- Support filtering by task status, template name, target/host, variable name, and variable value.
- Support time-range filtering using task creation time where available.
- Provide stable JSON output containing task IDs, project/template identity, status, timestamps, and parsed environment variables.
- Provide concise human-readable output suitable for terminal use.
- Reuse the existing API transport, error handling, TLS behavior, and secret-handling rules.
- Add unit tests using fake responses; tests must not contact a real Semaphore instance.
- Document the command, filters, pagination/limits, output schema, and API compatibility behavior.

### Out of scope

- Triggering, cancelling, approving, retrying, or modifying tasks.
- Changing Semaphore projects, templates, inventories, repositories, or variables.
- Replacing the existing `status`, `wait`, or `output` commands.
- Automatic release versioning, tagging, package publishing, or GitHub Actions release workflows. Those should be specified separately because they introduce repository permissions, publishing credentials, and release rollback decisions.
- Guaranteeing filters that the deployed Semaphore API cannot express server-side; client-side filtering may be used only within a documented bounded result set.

## Requirements

1. The task-list command must require a project name and resolve it by exact name.
2. The command must never print `SEMAPHORE_TOKEN`, authorization headers, or other credentials.
3. The command must offer an explicit maximum result count and must not perform an unbounded crawl by default.
4. The command must support filtering by status and template name.
5. The command must support filtering on parsed environment values, including the existing `target` and `fact` variables.
6. The command must distinguish an empty result from configuration, lookup, API, malformed-response, and pagination errors.
7. JSON output must use a documented stable schema and preserve task IDs, status, timestamps, template identity, and environment values where safe.
8. Human-readable output must show enough identity to select a task for existing `status`, `wait`, or `output` commands.
9. API responses with malformed task objects or malformed environment JSON must fail clearly or be represented according to a documented compatibility policy; they must not be silently misinterpreted.
10. Pagination and server-side filtering behavior must be covered by tests for the supported Semaphore API response shapes.
11. Existing commands and their exit-status behavior must remain compatible.
12. The feature must be usable without `curl` for supported task-discovery workflows.

## Proposed commands

```bash
semaphore-ui tasks --project configuration_management --limit 20
semaphore-ui tasks --project configuration_management --status success --json
semaphore-ui tasks --project configuration_management \
  --var target=hermes-001.iot.home \
  --var fact=firewall_interface \
  --limit 20 --json
```

The exact command and filter names may be refined during implementation, but discovery must remain read-only and project-scoped by default.

## Proposed JSON shape

```json
{
  "project": {"id": 1, "name": "configuration_management"},
  "tasks": [
    {
      "id": 4,
      "template": {"id": 1, "name": "hello_world"},
      "status": "success",
      "created": "2026-08-28T09:28:39.967141Z",
      "start": "2026-08-28T09:28:40.989545Z",
      "end": "2026-08-28T09:28:58.799261Z",
      "environment": {
        "target": "hermes-001.iot.home",
        "fact": "firewall_interface"
      }
    }
  ],
  "pagination": {"limit": 20, "has_more": false}
}
```

The final schema must reflect the actual deployed API and clearly document omitted or unavailable fields.

## Acceptance criteria

- [ ] A user can list recent tasks for a project by name using only `semaphore-ui`.
- [ ] A user can find tasks matching a host and `fact` variable without using `curl`.
- [ ] Status, template, variable, and bounded time-range filters work and are tested.
- [ ] Results can be consumed as stable JSON and identify task IDs for follow-up commands.
- [ ] Empty results, malformed responses, API failures, and pagination limits have tested behavior.
- [ ] Existing tests and commands remain passing.
- [ ] No test requires network access, real credentials, or a live Semaphore server.
- [ ] Documentation accurately describes the supported API behavior and limits.
- [ ] A live end-to-end test against the deployed Semaphore instance lists or filters the required task history using only `semaphore-ui` after installation from the feature branch.
- [ ] The PR contains redacted evidence of that end-to-end test, including the install, discovery/filter, and follow-up task retrieval commands and captured results; real hostnames/targets, tokens, and other sensitive values are replaced with safe placeholders.
- [ ] `uv run pytest`, `uv build`, and `git diff --check` pass.

## Implementation notes

- Inspect the deployed Semaphore API response and pagination conventions before finalizing the client method.
- Keep task-environment parsing separate from presentation and filtering so it can be tested independently.
- Prefer server-side filtering where the API supports it; otherwise enforce a finite client-side bound and disclose it in output/documentation.
- Preserve the existing exact-name project resolution and shared `_request` transport.
- Treat discovery as read-only and avoid implicit task execution.
- Add a separate release-automation specification before introducing GitHub Actions permissions, package-index credentials, version-bump policy, or tag protection.

## Risks and compatibility

- Semaphore versions may return different task-list shapes, pagination metadata, or environment encodings.
- Large task histories can make client-side filtering expensive or incomplete if the API has no server-side filters.
- Environment values may contain sensitive operational data even when they are not credentials; document output handling and avoid logging request headers.
- A task-history command may expose more operational history than some users should see; project-level API permissions remain authoritative.

## Validation plan

1. Capture representative task-list responses, including pagination, empty results, malformed task objects, and malformed environment values.
2. Add failing unit tests for project-scoped task listing and exact variable filtering.
3. Implement the API method and CLI command in small vertical increments.
4. Add tests for human/JSON output, limits, filters, errors, and backward compatibility.
5. Run `uv run pytest`, `uv build`, and `git diff --check`.
6. Install from the branch with `uv tool install --from` and exercise read-only discovery against the deployed Semaphore instance.

## Open questions

- Which pagination and filtering parameters are supported by the deployed Semaphore version?
- Should the command be named `tasks`, `history`, or `task-list`?
- Should variable filtering accept repeated `--var NAME=VALUE` arguments, separate `--target`/`--fact` options, or both?
- What default and maximum limits are appropriate for interactive use and automation?

## Amendments

- Correct the package version after the task-discovery release by deriving
  `semaphore_ui.__version__` from installed package metadata and exposing the
  same value through `semaphore-ui --version`. A regression test compares both
  values with the version declared in `pyproject.toml`.
