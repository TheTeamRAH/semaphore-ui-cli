---
type: Feature Specification
title: Trigger Semaphore Tasks by Project and Template Name
description: Add a versioned Python CLI command that resolves a Semaphore UI project and task template by name, triggers the template with supplied variables, and reports task status and output.
tags:
  - semaphore-ui
  - python
  - cli
  - uv
  - automation
sources:
  - https://semaphoreui.com/api-docs
  - https://docs.astral.sh/uv/guides/projects
status: proposed
---

# Trigger Semaphore Tasks by Project and Template Name

## Context

Semaphore UI exposes projects, task templates, task execution, task status, and task output through its API. The current operational workflow requires manually identifying numeric project and template IDs before triggering a task. The first utility feature should provide a human- and agent-friendly name-based interface while remaining independently usable without AI tooling.

The package will be managed with uv using `pyproject.toml` and a committed `uv.lock`. It will be installable as an isolated CLI with `uv tool install`, without requiring a shared virtual environment.

## Goal

Allow a user or AI skill to trigger a Semaphore UI task using a project name and template name, pass named runtime variables, wait for completion when requested, and retrieve a useful status/output result.

## Scope

### In scope

- A Python package with a console entry point named `semaphore-ui`.
- Configuration from `SEMAPHORE_HOST` and `SEMAPHORE_TOKEN`.
- Listing or resolving projects by exact name.
- Resolving task templates by exact name within the selected project.
- Triggering a task with named environment/survey variables.
- Reporting the created task ID and initial status.
- Checking task status by project and task ID.
- Waiting for a terminal task state with a bounded timeout.
- Retrieving task output.
- Human-readable output and stable JSON output for agent/CI use.
- Unit tests using a local fake HTTP transport or test server; tests must not contact the real Semaphore instance.
- uv packaging metadata, lockfile, build validation, and documented installation/use commands.

### Out of scope

- Creating or editing Semaphore projects, repositories, inventories, variables, or templates.
- Changing task-template configuration.
- Cancelling, approving, or retrying tasks.
- Storing Semaphore credentials in files managed by the package.
- A Hermes-native plugin.
- Automatic installation of the utility by `ai-toolkit`.

## Requirements

1. The CLI must require `SEMAPHORE_HOST` and `SEMAPHORE_TOKEN` for API operations and fail with an actionable message when either is absent.
2. Authorization headers and token values must never appear in normal output, exceptions, debug output, or JSON responses.
3. Project name resolution must return a clear error for zero matches and for ambiguous matches.
4. Template name resolution must be scoped to the selected project and must return a clear error for zero or ambiguous matches.
5. Runtime variables must be encoded in the Semaphore API format expected by the selected template, including the existing `target` and `fact` survey variables.
6. The trigger command must display the resolved project/template identity and created task ID.
7. JSON output must use a documented stable schema containing at least project ID/name, template ID/name, task ID, status, supplied variable names/values where safe, and API timestamps when available.
8. `wait` must use a configurable polling interval and timeout, and must terminate for both success and failure terminal states.
9. Task output retrieval must preserve meaningful task lines and provide a plain-output mode that removes ANSI colour escapes.
10. Network failures, non-success HTTP responses, malformed API responses, timeouts, and failed Semaphore tasks must be distinguishable to callers and have non-zero exit codes where appropriate.
11. The package must declare supported Python versions and runtime dependencies in `pyproject.toml`; `requirements.txt` must not be the source of truth.
12. The package must be runnable with `uv run` during development and installable with `uv tool install` after publication.
13. Tests must run without real credentials or network access.
14. Documentation must include installation, environment setup, command examples, JSON output, exit-status behavior, and security guidance.

## Proposed commands

```bash
semaphore-ui projects
semaphore-ui templates --project configuration_management
semaphore-ui run \
  --project configuration_management \
  --template hello_world \
  --var target=hermes-001.iot.home \
  --var fact=firewall_interface
semaphore-ui wait --project configuration_management --task 4
semaphore-ui output --project configuration_management --task 4 --plain
```

The exact command shape may be refined during implementation if tests show that a simpler consistent interface is preferable. Numeric IDs may be accepted as an explicit advanced option, but name-based operation is the required default behavior.

## Proposed package layout

```text
pyproject.toml
uv.lock
src/semaphore_ui/
  __init__.py
  __main__.py
  api.py
  cli.py
  errors.py
  models.py
tests/
  test_api.py
  test_cli.py
README.md
```

## Acceptance criteria

- [ ] A clean checkout can be installed with `uv tool install` after a package artifact or configured package source is available.
- [ ] A local development checkout runs with `uv run`.
- [ ] A project and template can be resolved by exact names.
- [ ] The required Semaphore task can be triggered with `target=hermes-001.iot.home` and `fact=firewall_interface` without manually supplying numeric IDs.
- [ ] The CLI reports the created task ID and status.
- [ ] Status and output can be retrieved for the created task.
- [ ] Ambiguous/missing names, missing credentials, API failures, malformed responses, and timeouts have tested error behavior.
- [ ] Human and JSON output are tested.
- [ ] No test requires network access, real credentials, or a live Semaphore server.
- [ ] `uv.lock` is present and `uv run pytest` passes.
- [ ] Package build validation succeeds with `uv build`.
- [ ] Documentation accurately reflects commands that were actually exercised.

## Implementation notes

- Prefer a small dependency footprint. The HTTP client, CLI framework, and test dependencies must be justified in `pyproject.toml`.
- Keep API transport separate from name resolution and presentation so the API client can be reused by future integrations.
- Use exact matching by default; do not silently select a first result.
- Use explicit terminal-state handling rather than treating every non-success response as a task failure.
- Use uv project commands and commit `uv.lock`; do not commit `.venv`.
- Keep package releases independently versioned from `ai-toolkit`; the Hermes skill will consume the installed CLI rather than owning its dependencies.

## Risks and compatibility

- Semaphore API response shapes may vary between versions; tests should capture the fields relied upon and fail clearly when required fields are missing.
- Name-based lookup introduces ambiguity if administrators reuse names; exact-match validation is required.
- Private package distribution will require package-index authentication outside this feature’s code.
- Task execution is state-changing. The CLI should make the trigger command explicit and avoid implicit execution during lookup or status commands.

## Validation plan

1. Create a failing unit test for resolving a project and template by name.
2. Run the focused test and confirm it fails because the implementation is absent.
3. Implement the smallest resolution path and confirm the focused test passes.
4. Add trigger, status, wait, output, error, JSON, and CLI tests one vertical behavior at a time using the RED/GREEN/REFACTOR cycle.
5. Run the full test suite with `uv run pytest`.
6. Build the package with `uv build`.
7. Install the built artifact into an isolated uv tool environment and exercise `--help` plus the fake-server integration path.
8. Exercise the live Semaphore path only after the local suite is green, using the known non-destructive `hello_world` template and explicit requested variables.
9. Review package contents, secrets handling, documentation, and `git diff --check` before completion.

## Open questions

- Should the default trigger command wait for completion, or should waiting always be a separate explicit command?
- Should the package be published first to GitHub Packages, or should initial releases use a private Git revision while the package interface stabilises?
- Which task states does the deployed Semaphore version expose as terminal states beyond `success` and failure?
