---
type: Feature Specification
title: Add Semaphore repository resource commands
description: Add consistent project-scoped repository list, show, create, copy, and update commands to semaphore-ui, including safe branch overrides and secret-free configuration handling.
tags:
  - semaphore
  - cli
  - repositories
  - copy
  - configuration
  - python
sources:
  - id: repository-agents
    resource: ../AGENTS.md
    title: Repository development workflow
  - id: command-conventions
    resource: 2026-09-05-20-55-cli-command-conventions.md
    title: Canonical CLI command conventions
  - id: cli
    resource: ../../src/semaphore_ui/cli.py
    title: Current CLI parser and command handlers
  - id: api
    resource: ../../src/semaphore_ui/api.py
    title: Current Semaphore API client and project resources
  - id: template-copy
    resource: 2026-09-04-23-00-template-copy.md
    title: Existing template copy feature and safety boundaries
  - id: semaphore-api
    resource: https://docs.semaphoreui.com/reference/api
    title: Semaphore API reference
status: in-progress
author: whose-footprints-are-these
---

# Add Semaphore repository resource commands

## Context

The `semaphore-ui` CLI now uses singular project-scoped resource namespaces:
`project`, `template`, and `task`. Its API client already lists and resolves
project repositories by exact name, but the CLI has no repository namespace and
cannot create or copy repository resources. That gap forces callers to build
raw API requests when preparing an isolated feature-branch configuration.

A Semaphore repository resource is a configuration record inside an existing
Semaphore project. It is not a new GitHub or Bitbucket repository. A repository
record contains a name, Git URL, branch/ref, and an optional access-key
reference. Copying it should preserve the source configuration while allowing
an explicit branch override such as `feature_branch_cm`.

## Goal

Add safe, consistent repository resource operations that allow callers to list,
inspect, create, copy, and update project-scoped Semaphore repositories without
exposing credentials or silently changing source configuration.

## Command convention

The complete repository namespace is:

```text
semaphore-ui repository list
semaphore-ui repository show
semaphore-ui repository create
semaphore-ui repository copy
semaphore-ui repository update
```

This mirrors the existing resource-plus-verb convention:
`project list/show`, `template list/show/create/copy`, and
`task list/run/status/wait/output`.

## Scope

### In scope

- `repository list --project PROJECT [--json]` as read-only discovery.
- `repository show --project PROJECT --repository NAME [--json]` as exact-name
  read-only inspection.
- `repository create --project PROJECT --name NAME --git-url URL
  --git-branch BRANCH [--access-key ACCESS_KEY] [--json]`.
- `repository copy --project PROJECT --repository SOURCE --name DESTINATION
  [--git-branch BRANCH] [--json]`.
- `repository update --project PROJECT --repository NAME --git-branch BRANCH
  [--json]` to change the configured branch/ref in place.
- Exact project, source repository, access-key, and destination collision
  handling.
- Secret-free human-readable and JSON output.
- API client methods and fake-client/unit coverage.
- CLI help, README, and feature documentation.
- Safe use of the existing global `--insecure` option.

### Out of scope

- Creating, cloning, branching, or pushing to GitHub, Bitbucket, or any other
  Git provider repository.
- Copying access-key secrets, private keys, passwords, vault material, or
  tokens.
- Creating or changing Semaphore projects, inventories, environments,
  templates, tasks, permissions, schedules, or variables.
- Deleting or overwriting repositories.
- Updating arbitrary repository fields beyond the supported branch/ref update.
- Updating or changing the existing repository API/server.
- Retaining removed pre-1.0.0 top-level command aliases.

## Requirements

1. All four commands must live under the singular `repository` namespace and
   use the existing exit-status contract: `0` success, `1` only for task
   execution failure, and `2` for configuration, validation, lookup, API, or
   input errors.
2. `--project`, repository names, URLs, and branch values must be validated as
   required non-empty strings where applicable. Preserve branch/ref values
   literally; do not normalize or rewrite them.
3. `repository list` must resolve the project by exact name and return the
   project-scoped repository collection without mutation.
4. `repository show` must resolve both project and repository by exact name,
   issue no mutation, and return the complete non-secret repository detail
   available from the API.
5. `repository create` must require project, destination name, Git URL, and
   branch/ref. It may optionally resolve an access-key name exactly within the
   project. It must reject a same-project name collision before POST.
6. `repository copy` must require project, source repository name, and
   destination name. It must reject identical source/destination names and an
   existing destination before POST. It must read the source repository first,
   preserve its Git URL and access-key reference, and use the source branch
   unless `--git-branch` explicitly supplies a non-empty override.
7. Copying must not copy secret key material. An access-key reference may be
   reused by ID only after exact source/read validation; output must show safe
   access-key identity or reference metadata, never secret content.
8. `repository update` must resolve the existing repository exactly, preserve
   its name, project, Git URL, and access-key reference, and change only its
   explicitly requested branch/ref.
9. The create and update payloads must set every field explicitly rather than relying on
   provider defaults. The implementation must inspect the current Semaphore
   API/schema behavior before finalizing field names and payload shape.
10. A successful mutation must create exactly one repository and must return the
   project plus safe created-resource identity/configuration. It must not create
   Git-provider state or run a task.
11. After creation, the implementation must validate the returned repository’s
    ID, project, name, URL, branch, and safe access-key reference. A mismatched
    response is an error, not a successful operation.
12. `--json` output must be stable and must not include access-key secrets,
    authorization values, private key material, or untrusted instructions.
13. The default must retain TLS verification. `--insecure` is honored only as
    the existing global option before the namespace.
14. Update README, CLI help, and feature documentation with the five commands,
    the distinction between Semaphore resources and Git-provider repositories,
    branch-override behavior, and safety boundaries.

## Acceptance criteria

- `semaphore-ui repository --help` lists `list`, `show`, `create`, `copy`, and `update`.
- Every nested command’s help shows the required arguments and JSON option.
- List and show use exact project/repository lookup and issue only GET requests.
- Create produces one explicit valid API payload and rejects collisions before
  any POST.
- Copy preserves the source Git URL and access-key reference, uses the source
  branch by default, and uses the explicit branch override when supplied.
- Update sends the full server-required repository object with only the branch
  changed, accepts the server's 204 response, reads the repository back, and
  verifies that the requested branch persisted while all other safe fields are
  unchanged.
- Same-name source/destination and existing destinations are rejected before
  POST.
- Missing or ambiguous projects, repositories, and access keys fail safely.
- Returned resource identity and parent/configuration are verified after each
  mutation.
- Tests prove no Git-provider operation, task execution, deletion, or overwrite
  occurs.
- Tests prove no secret values appear in output or error messages.
- `uv run pytest` passes.
- `uv build` passes.
- `uv lock --check` passes.
- Canonical repository help smoke tests pass.
- `git diff --check` passes.
- README and feature indexes accurately document the completed feature.

## Implementation notes

- Inspect the current Semaphore API responses and, when available, its Swagger
  schema before implementing the POST payload. The known read endpoint is
  `/api/project/{project_id}/repositories`; do not invent an alternative path.
- Extend `SemaphoreClient` with narrowly scoped repository creation and
  response-validation methods. Reuse `_filter_exact`, project resource
  resolution, positive-ID validation, and the existing request/error handling.
- Keep source-to-create transformation in a pure helper so branch override,
  access-key handling, and field preservation are testable without a network.
- Prefer access-key names in CLI input and numeric references in API payloads;
  never expose raw key data beyond safe identity metadata.
- Human-readable output should identify the project, repository, branch, and
  safe access-key identity without printing credentials.
- The CLI should not validate Git-provider reachability or branch existence;
  Semaphore or the Git provider owns that behavior. A configured branch may be
  created later, and a missing branch should be reported by task execution.
- Follow TDD: add failing parser/client/handler tests first, observe RED,
  implement the smallest vertical slice, then run focused and full suites.

## Risks and mitigations

- **Ambiguous resource meaning:** document that commands manage Semaphore
  repository records, not remote Git repositories.
- **Secret leakage:** whitelist output fields, reuse only access-key references,
  and add output/error redaction tests.
- **Provider schema drift:** perform read-only schema/API inspection before
  mutation and validate the response after POST.
- **Accidental overwrite:** perform exact destination collision checks before
  every create request.
- **Branch surprise:** default to the source branch and require an explicit
  `--git-branch` override for feature-branch use; preserve the value literally.
- **Partial remote mutation:** do not retry a timed-out POST automatically;
  require a follow-up exact-name read to determine whether creation occurred.

## Validation procedure

1. Inspect current `main`, API responses, and available Swagger/schema behavior.
2. Add focused failing tests for parser/help, list/show reads, create payload,
   copy transformation, collisions, branch overrides, response validation, and
   secret-safe output, plus update payload and read-back verification.
3. Implement the client and CLI vertical slices, confirming focused tests move
   from RED to GREEN.
4. Run focused tests, then `uv run pytest`, `uv lock --check`, `uv build`, all
   repository help commands, and `git diff --check`.
5. In a disposable or explicitly authorized Semaphore project, perform live
   list/show and, only with explicit mutation authorization, create/copy a
   harmless repository resource. Read back every mutation and record redacted
   evidence. Do not run a task as part of this feature’s live validation.
6. Before completion, synchronize with local `main`, repeat affected checks,
   and perform the repository’s documented release closeout/version decision.

## Release and compatibility

This feature adds five public commands under an existing resource convention.
It is additive to the `1.0.0` CLI and should normally receive a minor version
increment from the current release. The removed pre-1.0.0 top-level commands
remain unsupported. The authoritative version and lockfile changes must be
handled during the repository’s release closeout after implementation.

## Amendments

2026-09-06: Amend the feature to add `repository update`. Semaphore's update
endpoint requires a full repository object and returns `204 No Content`; the
CLI therefore resolves the existing record, changes only `git_branch`, submits
the complete non-secret configuration, and verifies the persisted record by
reading it back. Arbitrary field editing remains out of scope.
