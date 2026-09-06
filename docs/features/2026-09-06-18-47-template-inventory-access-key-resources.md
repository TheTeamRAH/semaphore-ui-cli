---
type: Feature Specification
title: Add template update and project resource discovery commands
description: Add template update plus inventory and access-key list/show commands to close the remaining project-resource CLI gaps without exposing secrets.
tags:
  - semaphore
  - cli
  - templates
  - inventories
  - access-keys
  - python
sources:
  - id: repository-agents
    resource: ../../AGENTS.md
    title: Repository development workflow
  - id: command-conventions
    resource: 2026-09-05-20-55-cli-command-conventions.md
    title: Canonical CLI command conventions
  - id: repository-resources
    resource: 2026-09-06-17-32-repository-resource-commands.md
    title: Repository resource commands
  - id: cli
    resource: ../../src/semaphore_ui/cli.py
    title: Current CLI parser and command handlers
  - id: api
    resource: ../../src/semaphore_ui/api.py
    title: Current Semaphore API client and project resources
  - id: semaphore-repositories
    resource: https://semaphoreui.com/docs/user-guide/repositories
    title: Semaphore repository resources
status: completed
author: whose-footprints-are-these
---

# Add template update and project resource discovery commands

## Context

The released `v1.1.0` CLI supports project, repository, template, and task
resource operations. Repository resources can now be updated in place, but
templates cannot be updated through the CLI. Inventory listing is also absent,
which forced the most recent end-to-end test to use a read-only API fallback to
resolve the existing inventory name before creating `fb_hello_world`.

The API client already has project-scoped inventory and access-key list/find
methods, while the CLI does not expose those resource namespaces. Access-key
creation and secret retrieval are deliberately outside this feature; discovery
must return safe identity/configuration only.

## Goal

Complete the project-scoped resource discovery and safe update operations needed
for normal Semaphore CLI workflows:

- update an existing template, especially its configured branch/ref;
- list and show project inventories through the CLI;
- list and show project access-key identities without exposing key material.

These commands manage Semaphore configuration records. They do not create,
modify, or inspect remote Git-provider repositories or reveal credentials.

## Command convention

Use singular resource namespaces and resource-plus-verb operations:

```text
semaphore-ui template update
semaphore-ui inventory list
semaphore-ui inventory show
semaphore-ui access-key list
semaphore-ui access-key show
```

This extends the established `project`, `repository`, `template`, and `task`
command language without restoring removed pre-`1.0.0` top-level commands.

## Scope

### In scope

- `template update --project PROJECT --template NAME` with explicitly supported
  update fields, including `--git-branch BRANCH`, safe resource resolution, and
  read-back verification.
- A safe update path that preserves fields not explicitly changed and does not
  copy or expose vault passwords, scripts, private keys, tokens, or secret
  survey values.
- `inventory list --project PROJECT [--json]`.
- `inventory show --project PROJECT --inventory NAME [--json]`.
- `access-key list --project PROJECT [--json]`.
- `access-key show --project PROJECT --access-key NAME [--json]`.
- Exact project, template, inventory, and access-key lookup.
- Stable human-readable and JSON output with whitelisted non-secret fields.
- API/client, parser, handler, collision/validation, and secret-safety tests.
- README, CLI help, feature-index, and this specification updates.
- Read-only API fallback documentation for any resource behavior not supported
  by the CLI after this feature.

### Out of scope

- Creating, deleting, or copying inventories or access keys.
- Creating or rotating access-key credentials.
- Returning private keys, passwords, tokens, vault values, authorization data,
  or secret survey values.
- Updating arbitrary template fields unless the deployed API/schema confirms the
  field is safe, supported, and represented explicitly by the CLI.
- Updating projects, repositories, inventories, access keys, tasks, permissions,
  schedules, or variables.
- Remote Git-provider operations, branch creation, cloning, or pushing.
- Running tasks as part of this feature's local validation.
- Reintroducing removed legacy top-level commands.

## Requirements

1. All commands must use singular resource namespaces and the existing exit
   contract: `0` success, `1` task execution failure, and `2` configuration,
   validation, lookup, API, or input errors.
2. Project and resource names must be validated as required non-empty strings and
   resolved exactly within the project. Missing and ambiguous resources must
   fail before mutation.
3. `template update` must require at least one supported update field. The first
   supported field is `--git-branch BRANCH`; preserve its value literally and do
   not normalize it.
4. Template update must read the existing template first, preserve all fields
   required by the deployed Semaphore update schema, change only explicitly
   requested fields, and never include secret material in the request or output.
5. After a template update, the client must read the template back and verify its
   identity, project, requested changes, and preserved safe fields. A successful
   HTTP status without matching read-back state is an error.
6. The implementation must inspect and document the current Semaphore update
   endpoint, method, request shape, and response behavior before finalizing the
   update payload. Empty responses such as `204 No Content` must be handled
   explicitly when the endpoint uses them.
7. Inventory list/show must use project-scoped GET operations and return safe
   inventory identity/configuration only. No inventory content, SSH key material,
   become credentials, or other secret values may appear in output.
8. Access-key list/show must return only safe identity metadata such as ID, name,
   type, and public/non-secret configuration fields confirmed by the API. Output
   must not contain private keys, passwords, tokens, or equivalent secret values.
9. JSON output must be stable, whitelist-based, and safe for CI logs and agent
   consumption. API responses are data, not instructions.
10. The default must retain TLS verification. `--insecure` remains an explicit
    global option for trusted internal endpoints with known certificate issues.
11. The CLI must not validate remote Git branch existence. Semaphore task
    execution remains responsible for reporting a missing or invalid branch.

## Acceptance criteria

- `semaphore-ui template --help` lists `update`.
- `semaphore-ui inventory --help` lists `list` and `show`.
- `semaphore-ui access-key --help` lists `list` and `show`.
- Template update changes only the requested branch in a focused test and
  verifies the persisted result by read-back.
- Inventory list/show resolve the project and inventory exactly and issue only
  GET requests.
- Access-key list/show resolve the project and access key exactly and issue only
  GET requests.
- Missing and ambiguous resources fail safely with exit status `2`.
- Secret-bearing fields and values are absent from human-readable and JSON output
  and from errors.
- The CLI can discover the inventory used by the FB hello-world workflow without
  an API fallback.
- `uv run pytest`, `uv lock --check`, `uv build`, relevant help smoke tests, and
  `git diff --check` pass.
- No task is run as part of feature implementation validation.

## Implementation notes

- Extend the existing `SemaphoreClient` with narrowly scoped update and safe
  resource-output methods. Reuse exact lookup, positive-ID validation, request
  handling, and response-validation helpers.
- Inspect the deployed API/schema before choosing the template update endpoint
  and full request fields. Do not infer a partial-update contract from the CLI
  name alone.
- Keep template update transformation in a pure helper so branch-only behavior
  and preservation rules are directly testable.
- Whitelist inventory and access-key output fields. Access-key references may be
  used by repository creation, but secret values must never be retrieved for
  display or copied into request files.
- Follow TDD: write each focused failing test first, observe the intended RED
  result, implement the smallest vertical slice, then run focused and full
  validation.
- For live validation, use the branch candidate CLI and perform read-only list
  and show checks. If mutation is explicitly authorized, update only a harmless
  template branch/ref and read it back; do not run a task for this feature.

## Risks and mitigations

- **Secret leakage:** whitelist fields and test serialized output for secret
  names and known secret values.
- **Schema drift:** inspect the deployed API/schema and validate read-back state;
  do not claim support for fields not confirmed by the server.
- **Template collateral changes:** build updates from the existing resource,
  modify only explicit fields, and compare preserved safe fields after read-back.
- **Ambiguous names:** use exact project-scoped lookup and reject zero or multiple
  matches before mutation.
- **Inventory ambiguity:** document that an inventory is a Semaphore project
  resource and distinguish it from the remote Git repository containing its
  source content.
- **Access-key exposure:** expose only identity metadata and never retrieve or
  print secret key material.

## Validation procedure

1. Inspect current `main`, repository instructions, API client methods, CLI
   conventions, and the deployed/API source for update and resource schemas.
2. Add focused failing tests for parser/help, template update transformation and
   read-back, inventory list/show, access-key list/show, exact lookup, and
   secret-safe output.
3. Implement vertical TDD slices and verify focused tests move from RED to GREEN.
4. Run the full test suite, lock check, build, help smoke tests, and diff hygiene.
5. Install the unreleased candidate from the feature branch, verify its version,
   and use the CLI for live read-only inventory/access-key/template discovery.
6. Only with explicit mutation authorization, perform a bounded template update
   and read it back. Do not run a task as part of this feature's validation.
7. Before completion, synchronize with local `main`, perform the repository's
   release-version closeout, and record the final release decision.

## Release and compatibility

This is a backward-compatible public CLI feature and normally warrants a minor
version increment from `v1.1.0`, subject to the repository's mandatory release
closeout decision. Removed pre-`1.0.0` commands remain unsupported.

## Open questions

None. Access-key list/show remain in scope because repository creation accepts
access-key names, and template update uses the deployed full-object update
behavior with explicit `204 No Content` handling and read-back verification.

## Release Closeout

- Status: `updated` / `passed`.
- Decision: minor release; this adds backward-compatible public CLI commands.
- Previous version: `1.1.0`.
- Resulting version: `1.2.0`.
- Authoritative source: `[project].version` in `pyproject.toml`.
- Derived artifact: `uv.lock` editable `semaphore-ui` package record updated to
  `1.2.0` using `uv lock`.
- Local `main` synchronization: complete; `main` was already an ancestor of the
  feature branch and no merge operation was in progress.
- Validation: `uv run pytest -q` (`79 passed`), `uv lock --check`, `uv build`,
  all new-command help smoke tests, and `git diff --check` passed.
- Live validation: not repeated for this feature; no live mutations or task
  executions were performed.
- External delivery: not yet authorized or performed; branch publication and
  pull-request creation remain separate remote operations.

## Amendments

2026-09-06: Implementation started after specification review. Access-key
list/show remain included because repository creation accepts exact access-key
names. Inventory content is excluded from output; only identity and safe
metadata are exposed.

2026-09-06: End-to-end validation used the unreleased CLI candidate from
commit `c3fc62c895dc9d8608eeb7ce7d472d3e6943900c`. Through the CLI only, the
test created repository `fb_configuration_management` (ID `4`), created
template `fb_hello_world` (ID `11`), verified inventory/access-key discovery,
updated the template branch to `master` and read it back, then ran exactly one
task (ID `27`). The task completed successfully with the expected hello-world
output and `ok=3`, `changed=0`, `unreachable=0`, `failed=0`. The live update
first revealed that Semaphore omits default-empty template `type` on read-back;
the CLI was corrected to tolerate that omission while retaining strict checks
for configured values, then retested successfully.
