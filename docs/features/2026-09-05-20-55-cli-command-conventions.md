---
type: feature
title: Normalize semaphore-ui CLI command conventions
description: Introduce singular resource subcommands and preserve existing commands as compatibility aliases.
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
status: proposed
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

The migration must not break existing scripts or the documented exit-status and
JSON contracts. Existing command names therefore remain compatibility aliases
while the singular resource commands become canonical.

## Goal

Adopt a consistent singular-resource-plus-verb CLI convention before adding
repository management actions, while preserving existing commands as tested
compatibility aliases.

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

## Compatibility aliases

The following existing commands must continue to work and dispatch to the same
underlying behavior:

```text
projects                         -> project list
templates --project PROJECT    -> template list --project PROJECT
tasks --project PROJECT ...     -> task list --project PROJECT ...
run --project PROJECT ...       -> task run --project PROJECT ...
status --project PROJECT ...    -> task status --project PROJECT ...
wait --project PROJECT ...      -> task wait --project PROJECT ...
output --project PROJECT ...    -> task output --project PROJECT ...
```

Aliases must preserve accepted options, output shape, exit statuses, and
credential-safety behavior. They may share parser builders and handlers with
the canonical commands; they must not duplicate business logic.

## Scope

### In scope

- Add the `project`, `template`, and `task` namespaces with explicit nested
  subcommands listed above.
- Add `project show` using exact project-name lookup and read-only retrieval.
- Add `template list` as the canonical form of the existing `templates`
  command.
- Add `template show` using exact project/template-name lookup and read-only
  retrieval.
- Move task listing, execution, status, waiting, and output operations under
  the `task` namespace while retaining top-level aliases.
- Preserve existing `template create` and `template copy` under the canonical
  template namespace.
- Share argument definitions, handlers, validation, API calls, output
  rendering, and error handling between canonical commands and aliases.
- Document canonical commands first and label old forms as compatibility
  aliases.
- Add parser, handler, API, output, and compatibility regression tests.

### Out of scope

- Repository commands or repository API changes.
- Project creation, editing, deletion, or administration.
- Removing or changing existing aliases.
- Changing JSON envelopes, human-readable output semantics, exit statuses, or
  authentication behavior.
- Adding shell completion, configuration files, or a global alias system.
- Renaming Python API methods solely to mirror CLI spelling when existing names
  are already clear and tested.

## Command behavior

### Project commands

`project list` must behave exactly like the current `projects` command.
`project show --project PROJECT` must resolve the project by exact name and
return the project object without mutation. Its `--json` and human-readable
output behavior must follow existing conventions.

### Template commands

`template list` must behave exactly like the current `templates --project`
command. `template show` must resolve the project and template by exact name
and return the template object without mutation. Existing `template create` and
`template copy` behavior must remain unchanged.

### Task commands

`task list` must behave exactly like the current `tasks` command, including
filters and pagination metadata. `task run` must behave exactly like the
current `run` command and retain its explicit task-execution semantics.
`task status`, `task wait`, and `task output` must preserve the current task
lookup and output behavior, including task failure exit status `1` and
configuration, lookup, API, and validation failure status `2`.

## Implementation contract

1. Use argparse namespaces and `set_defaults(handler=...)` dispatch, following
   the existing CLI architecture.
2. Factor reusable parser-option builders so aliases and canonical commands
   cannot drift.
3. Keep handlers thin and reuse existing client methods and validation helpers.
4. Add exact-name project/template lookup methods only where the current client
   does not already provide them.
5. Ensure read-only `show` commands issue only GET requests.
6. Ensure aliases and canonical commands produce equivalent parsed inputs and
   invoke equivalent handlers.
7. Keep `--json` available on every command that currently supports it.
8. Keep credentials and secret task variables out of errors, logs, and normal
   output.
9. Add Google-style docstrings and type hints for new public methods and
   important private helpers.
10. Do not add deprecation warnings that alter normal output or break scripts;
    if warnings are desired later, specify them separately.

## Acceptance criteria

- `semaphore-ui --help` shows the canonical resource namespaces and clearly
  identifies retained compatibility commands.
- The following help commands succeed:
  - `semaphore-ui project --help`
  - `semaphore-ui template --help`
  - `semaphore-ui task --help`
  - each canonical nested subcommand's `--help`.
- `project list` and `projects` are behaviorally equivalent.
- `project show` performs exact project lookup and no mutation.
- `template list` and `templates` are behaviorally equivalent.
- `template show` performs exact project/template lookup and no mutation.
- `task list` and `tasks` are behaviorally equivalent for every existing filter.
- `task run` and `run` are behaviorally equivalent and retain task execution
  confirmation boundaries in the caller/skill workflow.
- `task status`, `task wait`, and `task output` are behaviorally equivalent to
  their existing top-level forms.
- Existing `template create` and `template copy` tests continue to pass.
- Tests prove aliases do not duplicate or alter API requests and that show
  commands do not issue POST, PUT, PATCH, or DELETE requests.
- JSON output, human-readable output, error messages, and exit statuses remain
  compatible for existing commands.
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
4. Implement one canonical vertical slice, then test its legacy alias against
   the same behavior.
5. Repeat red-green cycles for project show, template show, task namespace
   commands, and the remaining aliases.
6. Run focused tests, then the full test suite, build, CLI help smoke tests, and
   diff hygiene checks.
7. Review output and request equivalence programmatically, including failure
   paths and no-mutation guarantees.
8. Merge current local `main` into the feature branch before completion and
   perform the repository's mandatory release-version closeout.

## Risks and decisions

- Adding nested commands increases help depth, but the resource grouping makes
  the interface predictable and prevents future top-level verb proliferation.
- Aliases can drift if parsers or handlers are copied. Shared builders and
  equivalence tests are required to prevent that failure mode.
- `project show` and `template show` are read-only additions and should not be
  confused with future create/update operations.
- The migration changes the public interface by addition, not removal. Existing
  automation remains supported while documentation guides new users toward the
  canonical form.

## Sources and repository paths

- `src/semaphore_ui/cli.py`: current parser, handlers, and command behavior.
- `src/semaphore_ui/api.py`: current resource lookup and task client methods.
- `README.md`: current public command examples and output/exit-status contract.
- `docs/features/2026-09-05-20-34-repository-management.md`: follow-on
  repository feature that depends on a settled CLI convention.
