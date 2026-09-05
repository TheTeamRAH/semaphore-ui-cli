---
type: feature
title: Normalize semaphore-ui CLI command conventions
description: Introduce singular resource subcommands and remove the superseded top-level commands.
tags:
  - semaphore-ui
  - cli
  - command-design
  - compatibility
sources:
  - id: cli-parser
    resource: ../../src/semaphore_ui/cli.py
    title: Existing argparse commands and handler dispatch
  - id: cli-readme
    resource: ../../README.md
    title: Existing CLI usage and documented commands
  - id: api-client
    resource: ../../src/semaphore_ui/api.py
    title: Existing client resource and task method boundaries
  - id: repository-management
    resource: 2026-09-05-20-34-repository-management.md
    title: Follow-on repository management feature
status: completed
author: whose-footprints-are-these
---

# Context

The CLI currently mixes command styles. Collection retrieval uses top-level
plural nouns (`projects`, `templates`, and `tasks`), while template mutations
use a singular resource followed by a verb (`template create` and
`template copy`). Task execution and inspection use top-level verbs (`run`,
`status`, `wait`, and `output`). Internal API methods consistently use
resource-oriented names such as `list_projects`, `find_project`,
`list_templates`, and `find_template`, but that consistency is not visible in
the public CLI.

The next planned feature adds project-scoped repository actions. Adding those
actions before settling the command convention would extend the inconsistency
and make future project, repository, template, and task operations harder to
discover. A singular resource namespace with explicit verbs is familiar to CLI
users and provides a stable place for future CRUD-style actions.

This migration intentionally removes the old top-level command forms. The
canonical resource commands become the only supported public interface. This
is a deliberate breaking change because the CLI is still pre-1.0 and the
repository has accepted a major-version release for the cleanup.

## Goal

Adopt a consistent singular-resource-plus-verb CLI convention before adding
repository management actions, with the old top-level forms removed as a
deliberate breaking change.

## Canonical command model

The canonical command hierarchy is:

```text
semaphore-ui project list
semaphore-ui project show --project PROJECT

semaphore-ui template list --project PROJECT
semaphore-ui template show --project PROJECT --template TEMPLATE
semaphore-ui template create ...
semaphore-ui template copy ...

semaphore-ui task list --project PROJECT
semaphore-ui task run --project PROJECT --template TEMPLATE ...
semaphore-ui task status --project PROJECT --task ID
semaphore-ui task wait --project PROJECT --task ID
semaphore-ui task output --project PROJECT --task ID
```

`repository list`, `repository show`, `repository create`, and `repository
copy` are deliberately reserved for the separate repository-management feature
and must not be implemented by this specification.

`project create` is not included. Project creation has separate API, required
fields, permissions, and lifecycle considerations and must receive its own
specification if needed.

## Breaking-change policy

The old top-level forms are removed rather than retained as aliases:

```text
projects, templates, tasks, run, status, wait, output
```

Users must migrate to the canonical resource commands. The removal is part of
the `1.0.0` major release and must be clearly documented in the README and
release-facing change summary.

## Scope

### In scope

- Add the `project`, `template`, and `task` namespaces with explicit nested
  subcommands listed above.
- Add `project show` using exact project-name lookup and read-only retrieval.
- Add `template list` as the canonical template collection command.
- Add `template show` using exact project/template-name lookup and read-only
  retrieval.
- Move task listing, execution, status, waiting, and output operations under
  the `task` namespace and remove their top-level forms.
- Preserve `template create` and `template copy` under the canonical
  template namespace.
- Share argument definitions, handlers, validation, API calls, output
   rendering, and error handling within the canonical command hierarchy.
- Document the removed top-level commands and migration mapping.
- Add parser, handler, API, output, and removal regression tests.

### Out of scope

- Repository commands or repository API changes.
- Project creation, editing, deletion, or administration.
- Preserving compatibility aliases for the removed top-level commands.
- Changing JSON envelopes, human-readable output semantics, exit statuses, or
  authentication behavior.
- Adding shell completion, configuration files, or a global alias system.
- Renaming Python API methods solely to mirror CLI spelling when existing names
  are already clear and tested.

## Command behavior

### Project commands

`project list` must preserve the behavior of the previous `projects`
implementation.
`project show --project PROJECT` must resolve the project by exact name and
return the project object without mutation. Its `--json` and human-readable
output behavior must follow existing conventions.

### Template commands

`template list` must preserve the behavior of the previous `templates
--project` implementation. `template show` must resolve the project and template by exact name
and return the template object without mutation. Existing `template create` and
`template copy` behavior must remain unchanged.

### Task commands

`task list` must preserve the behavior of the previous `tasks` implementation, including
filters and pagination metadata. `task run` must behave exactly like the
current `run` command and retain its explicit task-execution semantics.
`task status`, `task wait`, and `task output` must preserve the current task
lookup and output behavior, including task failure exit status `1` and
configuration, lookup, API, and validation failure status `2`.

## Implementation contract

1. Use argparse namespaces and `set_defaults(handler=...)` dispatch, following
   the existing CLI architecture.
2. Factor reusable parser-option builders so canonical commands cannot drift.
3. Keep handlers thin and reuse existing client methods and validation helpers.
4. Add exact-name project/template lookup methods only where the current client
   does not already provide them.
5. Ensure read-only `show` commands issue only GET requests.
6. Keep `--json` available on every command that currently supports it.
7. Keep credentials and secret task variables out of errors, logs, and normal
   output.
8. Add Google-style docstrings and type hints for new public methods and
   important private helpers.
9. Do not add compatibility shims or deprecation warnings for removed commands.

## Acceptance criteria

- `semaphore-ui --help` shows only the canonical resource namespaces.
- The following help commands succeed:
  - `semaphore-ui project --help`
  - `semaphore-ui template --help`
  - `semaphore-ui task --help`
  - each canonical nested subcommand's `--help`.
- `project show` performs exact project lookup and no mutation.
- `template show` performs exact project/template lookup and no mutation.
- Removed top-level forms fail with argparse's unsupported-command behavior.
- Canonical task commands retain task execution confirmation boundaries in the
  caller/skill workflow.
- Existing `template create` and `template copy` tests continue to pass.
- Tests prove removed top-level forms are unavailable and show commands do not
  issue POST, PUT, PATCH, or DELETE requests.
- JSON output, human-readable output, and exit statuses remain unchanged for
  commands that remain supported.
- `uv run pytest` passes.
- `uv build` passes.
- `uv run semaphore-ui --help` and canonical nested help smoke tests pass.
- `git diff --check` passes.
- README and the feature index document the canonical convention and aliases.
- No credentials, generated artifacts, or unrelated changes are added.

## Validation procedure

1. Review this specification before implementation.
2. Create a feature branch from up-to-date local `main` after authorization.
3. Add a focused failing parser/handler test for one canonical command before
   changing production code, and confirm it fails for the missing command.
4. Implement one canonical vertical slice, then add an explicit unsupported
   command test for the removed forms.
5. Repeat red-green cycles for project show, template show, and task namespace
   commands.
6. Run focused tests, then the full test suite, build, CLI help smoke tests, and
   diff hygiene checks.
7. Review output and no-mutation guarantees programmatically, including
   failure paths and unsupported-command behavior.
8. Merge current local `main` into the feature branch before completion and
   perform the repository's mandatory release-version closeout.

## Risks and decisions

- Adding nested commands increases help depth, but the resource grouping makes
  the interface predictable and prevents future top-level verb proliferation.
- Removing aliases creates a migration burden for existing callers. The
  `1.0.0` release and README migration mapping make that break explicit.
- `project show` and `template show` are read-only additions and should not be
  confused with future create/update operations.
- The migration removes the old public forms. Existing automation must migrate
  before using `1.0.0`.

## Sources and repository paths

- `src/semaphore_ui/cli.py`: current parser, handlers, and command behavior.
- `src/semaphore_ui/api.py`: current resource lookup and task client methods.
- `README.md`: current public command examples and output/exit-status contract.
- `docs/features/2026-09-05-20-34-repository-management.md`: follow-on
  repository feature that depends on a settled CLI convention.

## Amendments

### 2026-09-05 — Remove compatibility aliases

The user approved removing the legacy top-level commands rather than retaining
them as compatibility aliases. This changes the migration from additive to a
deliberate breaking change. The canonical singular resource commands remain;
`projects`, `templates`, `tasks`, `run`, `status`, `wait`, and `output` are
removed. The release classification changes from minor `0.6.0` to major
`1.0.0`.

## Release Closeout

- Decision: updated
- Reason: This feature removes superseded public CLI commands and changes the
  supported interface incompatibly.
- Classification: major
- Previous version: `0.6.0`
- Resulting version: `1.0.0`
- Authoritative version source: `pyproject.toml` `[project].version`
- Derived artifact: `uv.lock` editable `semaphore-ui` package record updated
  to `1.0.0`
- Branch synchronization: current `origin/main` is an ancestor of the feature
  branch; no merge conflicts remained.
- Validation: `uv lock --check`, `uv run pytest -q` (63 passed), `uv build`,
  canonical CLI help smoke tests, and `git diff --check` all passed.
- Release-facing documentation: README version example updated to `1.0.0`.
