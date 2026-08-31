---
type: Feature Specification
title: Create Semaphore Task Templates
description: Add an explicit CLI command for creating Semaphore UI task templates from validated project and resource configuration.
tags:
  - semaphore-ui
  - python
  - cli
  - templates
  - automation
sources:
  - https://raw.githubusercontent.com/semaphoreui/semaphore/develop/api-docs.yml
  - https://semaphoreui.com/docs/admin-guide/api
  - https://semaphoreui.com/docs/user-guide/task-templates
status: in_progress
---

# Create Semaphore Task Templates

## Context

The CLI can discover existing Semaphore projects and templates and trigger tasks from a template. Creating a new template still requires the Semaphore web UI or a hand-built API request, making repeatable setup harder for operators and AI-agent integrations.

Semaphore exposes a project-scoped template creation endpoint, `POST /api/project/{project_id}/templates`. Its `TemplateRequest` model includes the template name, repository, inventory, environment, playbook, task type, branch, arguments, survey variables, and task parameters.[^1] Templates define how tasks run, while tasks are individual executions of those templates.[^3]

Template creation must remain distinct from task execution: creating a template changes Semaphore configuration but does not run a playbook.

## Goal

Allow an operator or automation client to create a Semaphore task template by project name, resolving referenced resources by name where practical, validating the request locally, and reporting the created template without exposing credentials.

## Scope

### In scope

- An explicit `template create` CLI command.
- Exact project-name resolution, consistent with existing commands.
- Exact name resolution for referenced repository, inventory, and environment resources within the selected project.
- Required initial fields: template name, repository, inventory, environment, and playbook path.
- Optional fields: description, Git branch, task type (default, `build`, or `deploy`), arguments, survey variables, task parameters, and view name where supported.
- A file-based request format for advanced or version-sensitive fields, with a documented JSON example/schema.
- Human-readable and stable JSON output containing the created template identity and selected safe configuration.
- Local validation before the mutating API request.
- Unit tests using fake/local HTTP responses only.
- Documentation covering authentication, examples, validation, permissions, and the non-executing nature of the command.

### Out of scope

- Running the newly created template or any playbook.
- Updating, cloning, deleting, or importing templates.
- Creating or editing projects, repositories, inventories, environments, variable groups, vaults, keys, views, schedules, or integrations.
- Automatically creating missing referenced resources.
- Copying secrets, API tokens, SSH keys, vault passwords, or environment secrets into request files or output.
- Live end-to-end mutation during initial unit-test validation.

## Requirements

1. Require `SEMAPHORE_HOST` and `SEMAPHORE_TOKEN` for API operations; never accept the token as an ordinary command-line argument.
2. Make the state-changing action explicit; discovery and resolution commands must not create a template.
3. Resolve the project by exact name and fail clearly for zero or multiple matches.
4. Resolve repository, inventory, and environment references within the selected project by exact name. Missing or ambiguous references must fail before the POST request.
5. Validate required strings, positive resource IDs, supported task types, and mutually compatible options before making the API call.
6. Send the selected project/resource IDs, template name, playbook, and explicitly supplied optional values. Do not rely on unsafe provider defaults for execution-affecting fields.
7. Preserve survey-variable name, title, type, required flag, and supported default/options fields without silently dropping values.
8. Validate the create response as a template object with a positive ID, project ID, and name, and report malformed responses or non-success HTTP responses clearly.
9. Keep bearer tokens, authorization headers, secret values, and private key material out of normal and JSON output.
10. Use a documented stable JSON envelope containing project identity, created template identity, and effective non-secret configuration.
11. Distinguish network, authorization, validation, lookup, malformed-response, and successful-creation outcomes through actionable messages and documented exit statuses.
12. Preserve existing read-only, task-triggering, and task-history behavior.
13. Run tests without real credentials, network access, or a live Semaphore server.
14. Document required Semaphore permissions and state that successful creation persists configuration but does not execute the template.

## Proposed interface

Simple templates should be creatable from options:

```bash
semaphore-ui template create \
  --project configuration_management \
  --name show-firewall-interface \
  --repository configuration-management \
  --inventory homelab \
  --environment default \
  --playbook site.yml \
  --git-branch main
```

Advanced templates should use a request file:

```bash
semaphore-ui template create \
  --project configuration_management \
  --file template.json \
  --json
```

Conflicting direct options and file fields must be rejected rather than silently choosing one. Final option names and request-file shape may be refined during implementation, but the command must retain an explicit create action and exact-name safety checks.

## Proposed API flow

1. Resolve the project using the existing project lookup behavior.
2. List project repositories, inventories, and environments.
3. Resolve each requested resource by exact name within the project.
4. Parse and validate direct options or the request file.
5. Build a project-scoped `POST /api/project/{project_id}/templates` request using resolved IDs.
6. Validate the returned template object.
7. Print the created template ID/name and effective safe configuration, or the documented JSON envelope.

The API documentation identifies `TemplateRequest` fields including `project_id`, `inventory_id`, `repository_id`, `environment_id`, `name`, `playbook`, `description`, `git_branch`, `survey_vars`, `type`, and `task_params`.[^1] The implementation must verify accepted fields against the deployed instance's `/api-docs` before production mutation; unsupported fields must be omitted or reported, not guessed.

## Acceptance criteria

- [x] A clean checkout can invoke `semaphore-ui template create --help`.
- [x] A fake-server scenario resolves the project/resources, sends one project-scoped create request, and reports the created template.
- [x] The request uses resolved resource IDs and preserves supported optional configuration.
- [x] Missing and ambiguous names fail before the POST request.
- [x] Invalid fields, IDs, task types, survey data, and conflicting input modes fail before the POST request.
- [x] Malformed success responses and non-success HTTP responses produce documented errors without secret leakage.
- [x] Human-readable and stable JSON output are tested.
- [x] Existing project, template, task-run, status, output, and task-history tests remain green.
- [x] No test requires real credentials, network access, or a live Semaphore server.
- [x] README documents direct-option and request-file examples, permissions, exit statuses, and non-executing behavior.
- [x] `uv run pytest`, `uv build`, and `git diff --check` pass after implementation.
- [x] No live mutation was performed; the command requires separate explicit approval before any such validation.

## Implementation notes

- Reuse existing transport, authentication, response-validation, exact-name lookup, and output abstractions where their contracts fit.
- Keep request construction separate from CLI parsing so payload validation is independently testable.
- Prefer JSON request files for nested survey/task-parameter structures and direct options for common Ansible templates.
- Never print raw request headers or full payloads by default; redact secret-bearing fields in diagnostics and examples.
- Do not add automatic POST retries unless idempotency is understood; a timeout after server acceptance could create duplicates.
- Keep creation compatible with `run`: creation configures a template, while `run` remains the explicit action that starts a task.

## Risks and compatibility

- API fields and validation rules vary by Semaphore release; the checked-in API specification reports version `2.16.14`, while deployments may differ.[^1]
- Resource names may be duplicated or change between discovery and creation. Exact matching and clear failure are safer than selecting the first result.
- A request may be accepted yet create a template that cannot run if its resources or playbook are incompatible. Execution remains a separate operation.
- Retrying after an ambiguous network failure could create duplicates; operators should reconcile state before retrying.
- Template creation requires project permissions; a valid token may still receive a 403 response.[^2]

## Validation plan

1. Add a failing unit test for creating a template from resolved project and resource names.
2. Run the focused test and confirm it fails because the command/API method is absent.
3. Implement the smallest request-building/create path and confirm the focused test passes.
4. Add vertical tests for file input, optional fields, validation, ambiguity, malformed responses, HTTP errors, JSON output, and redaction.
5. Run `uv run pytest`, build with `uv build`, and exercise the installed artifact's help and fake-server paths.
6. Review the final payload against the deployed `/api-docs` before any live mutation.
7. Perform live creation only after specification review and explicit approval, recording the template ID and rollback procedure outside version control.

## Settled decisions

- The initial command supports the default, build, and deploy template types.
- Advanced request files use name-based references for project resources; the CLI
  resolves them into positive IDs before creation.
- The initial supported survey and task-parameter shapes are the documented
  fields accepted by local validation. The runtime Swagger preflight is the
  authority for the target instance and rejects unavailable nested fields before
  POSTing.
- Template deletion remains out of scope. Live validation, if separately
  approved, must use an intentionally named template and an operator-managed
  rollback procedure.

## Sources

[^1]: Semaphore UI, `api-docs.yml`, `TemplateRequest` and template endpoints, https://raw.githubusercontent.com/semaphoreui/semaphore/develop/api-docs.yml
[^2]: Semaphore UI, “API”, authentication and API usage, https://semaphoreui.com/docs/admin-guide/api
[^3]: Semaphore UI, “Task Templates”, template purpose and task types, https://semaphoreui.com/docs/user-guide/task-templates

## Release Closeout

- Status: updated and passed (minor, backward-compatible public CLI feature).
- Version: `0.2.0` to `0.3.0`; authoritative source: `pyproject.toml`; derived artifact: `uv.lock`.
- Idempotence: the post-synchronization feature version and editable lockfile record
  match `0.3.0`, while local `main` remains at `0.2.0`; this established update
  is attributable to this feature and was preserved without a second increment.
- Synchronization: local `main` was already an ancestor of the feature branch;
  `git merge --no-edit main` reported `Already up to date.`
- Validation: `uv lock --check`, `uv run pytest` (37 passed, including two
  version checks), `uv build`, `uv run semaphore-ui template create --help`, and
  `git diff --check` passed. Build distributions were validation-only and are
  ignored by Git.

## Amendments

- Preserve helper-first function order throughout the Python package: a
  module-level private helper must appear before any other module-level function
  that calls it, except for direct recursion. Add a structural regression test
  covering the package modules and reorder the existing CLI validation helpers
  without changing their public behavior, validation rules, error messages, or
  output. Continue to reserve `validators.py` for context-free contracts shared
  across layers; CLI request-shape validation and API response/schema validation
  remain in their owning modules because their dependencies, error domains, and
  policy are layer-specific.
- Correct the prematurely completed release closeout: update the README's
  release-facing `--version` output to `0.3.0` and add regression coverage that
  compares that documented output with the authoritative package version.
- Before feature completion, add Google-style contract docstrings to new public
  APIs and important private helpers where their parameters, returns, errors, or
  safety guarantees are not self-evident. Refactor the new request-validation
  code into small named predicates or helpers so that compound conditionals do
  not obscure supported fields and error behaviour. Preserve CLI behaviour and
  stable output while making this structural change.
- Expand test coverage for every template-create acceptance criterion: invalid
  resolved project and resource IDs; missing and ambiguous project resources;
  optional view resolution; request validation failures that must occur before a
  POST; create-request HTTP and malformed-response failures; and preservation of
  supported optional configuration. Tests must assert that rejected input does
  not issue the create request.
- Reconcile the compatibility contract before implementation is marked complete.
  The CLI performs an authenticated runtime preflight against the target
  instance's machine-readable Swagger schema endpoint, `/api/swagger`, before a
  template-create POST. `/api-docs` is the human-facing Swagger UI and must not
  be parsed as a schema. The preflight must confirm that the creation path and
  every emitted payload field are supported by the instance schema. An
  unavailable, malformed, or incompatible schema is a validation failure (exit
  status `2`) and must prevent the POST. Tests must demonstrate the compatible
  path and each no-POST failure mode. The parser remains implementation
  discretion, provided no new runtime dependency is introduced without separate
  approval.
- Extract duplicated validation behavior from `api.py` and `cli.py` into a new
  `validators.py` module. Keep transport-specific response/schema validation and
  CLI-specific request-shape validation in their owning modules; only move
  shared positive-ID and non-empty-string checks. Add focused tests for the
  shared contracts and preserve existing CLI/API error wording where practical.
