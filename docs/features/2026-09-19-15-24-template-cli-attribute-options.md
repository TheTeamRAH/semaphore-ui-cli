---
type: Feature Specification
title: Add direct CLI attribute options for Semaphore template surveys
description: Close the template mutation gap that required curl by exposing safe survey-variable changes through explicit CLI arguments, and audit adjacent resource commands for the same file-JSON dependency.
tags:
  - semaphore
  - cli
  - templates
  - survey-vars
  - python
sources:
  - id: repository-agents
    resource: ../../AGENTS.md
    title: Repository development workflow
  - id: cli
    resource: ../../src/semaphore_ui/cli.py
    title: Current CLI parser, survey validation, and template handlers
  - id: api
    resource: ../../src/semaphore_ui/api.py
    title: Current Semaphore API client and full-object update path
  - id: prior-template-feature
    resource: 2026-09-06-18-47-template-inventory-access-key-resources.md
    title: Existing template update contract
  - id: prior-survey-feature
    resource: 2026-08-31-21-20-template-survey-defaults-and-vaults.md
    title: Existing survey and vault validation contract
status: proposed
author: whose-footprints-are-these
---

# Add direct CLI attribute options for Semaphore template surveys

## Context

The current `semaphore-ui template update` command supports only
`--git-branch`. The API requires a full template object for updates, but the
client already has the safe read-existing, construct-whitelisted-payload, PUT,
and read-back verification path. Because the CLI has no survey-variable update
arguments, adding the `inbox_repo_version` survey variable to the
`fb_deploy_compose` template required a direct curl request.

The current `template create` command also accepts repeated inline JSON objects
for `--survey-var` and `--vault`, and retains a JSON request-file mode for
complex requests. Inventory and repository commands use explicit options for
supported attributes, so template operations are inconsistent with the rest of
the CLI.

An audit of the current commands found:

- Repository create/copy/update already expose explicit options for their
  supported fields; no equivalent file-JSON gap was found.
- Inventory create/copy/update already expose explicit options for their
  supported fields; no equivalent file-JSON gap was found.
- Template create/update are the remaining project-resource commands needing
  direct attribute coverage.
- Access-key commands are intentionally read-only because credential mutation
  and secret retrieval are out of scope.
- Task commands already use repeatable `--var NAME=VALUE` arguments.

## Goal

Make normal Semaphore template survey configuration possible through CLI
arguments, without curl and without requiring a JSON request file. Preserve the
existing safe full-object update behavior and extend it to both template create
and template update where practical.

## Command contract

Use the existing singular resource namespace:

```text
semaphore-ui template create
semaphore-ui template update
```

Add repeatable direct survey options. The exact option names and help text must
remain stable once implemented:

```text
--survey-var NAME[=DEFAULT]
--survey-title NAME=TITLE
--survey-description NAME=DESCRIPTION
--survey-type NAME=TYPE
--survey-target NAME=TARGET
--survey-required NAME
--survey-optional NAME
--survey-option NAME=VALUE
```

`--survey-var` creates or selects a survey variable. An omitted `=DEFAULT`
means that no default is configured. The metadata options apply to the named
variable and may be repeated for different variables. `--survey-option` adds a
named option for enum/select variables and may be repeated. Values are split
only at the first `=` so branch names and descriptions retain subsequent `=`
characters.

Examples:

```bash
semaphore-ui template update \
  --project configuration_management \
  --template fb_deploy_compose \
  --survey-var inbox_repo_version=main \
  --survey-title inbox_repo_version="Inbox repository version" \
  --survey-description inbox_repo_version="Git branch, tag, or commit for the Inbox repository" \
  --json
```

A create example:

```bash
semaphore-ui template create \
  --project configuration_management \
  --name fb_deploy_compose \
  --repository fb_configuration_management \
  --inventory fb_configuration_management \
  --playbook playbooks/compose.yml \
  --survey-var target=docker-001.rah.home \
  --survey-required target \
  --survey-var inbox_repo_version=main
```

The existing `template create --file` mode may remain as a backward-compatible
escape hatch for payloads not yet represented by direct options. This feature
must not add a file requirement or use file JSON in its implementation,
examples, tests, or operational validation. Removing the legacy file mode is a
separate breaking-change decision and is out of scope here.

## Scope

### In scope

- Add explicit survey-variable options to `template create`.
- Add explicit survey-variable add/update options to `template update`.
- Merge requested survey changes by variable name while preserving unrelated
  existing survey variables and safe metadata.
- Permit a simple string default such as `inbox_repo_version=main`.
- Support the existing validated survey types, targets, required flag, titles,
  descriptions, and enum/select option values through direct arguments.
- Reuse the existing survey validation and secret-safety rules.
- Keep full-object template update payload construction and read-back
  verification in the API client.
- Inspect all neighboring resource commands and document that repository and
  inventory commands already have explicit supported-attribute options.
- Add parser, transformation, API, handler, help, error, preservation, and
  secret-safety tests.
- Update README, CLI help, feature index, and this specification.

### Out of scope

- JSON request files as a new interface or as the implementation mechanism.
- Removing the existing backward-compatible `template create --file` mode.
- Secret survey values, secret survey defaults, vault passwords, private keys,
  tokens, or authorization data in arguments or output.
- Creating, rotating, or retrieving access-key credentials.
- Arbitrary template-field mutation without an explicit validated CLI option.
- Template deletion, project mutation, repository deletion, inventory deletion,
  task mutation, or release automation.
- Validating whether a branch, tag, or commit exists in the remote Git provider.

## Requirements

1. `template update` must accept one or more supported update attributes and must
   continue to reject an invocation that requests no change.
2. Survey-variable changes must be identified by exact variable name. Missing
   names, duplicate contradictory definitions, malformed `NAME=VALUE` strings,
   and unknown survey types/targets must fail before mutation.
3. A survey variable supplied only as `--survey-var NAME=DEFAULT` must receive a
   deterministic title derived from its name unless an explicit title is also
   supplied. Existing title, description, type, target, required state, and
   options must be preserved when updating only its default.
4. `--survey-option` is valid only for enum/select variables and must preserve
   existing options unless the request explicitly changes that variable's
   options. Secret variables must reject options and defaults.
5. Direct CLI arguments must be converted to the same validated survey object
   shape currently accepted by template creation. No raw JSON fragments may be
   required in the new interface.
6. Template updates must read the existing template, apply only requested
   changes, send all fields required by the deployed full-object update schema,
   handle an empty successful response, read the template back, and verify the
   requested survey state plus preserved safe fields.
7. Template creation must retain its current explicit options and gain the same
   direct survey-variable representation. Existing `--survey-var` inline JSON
   behavior must either be removed with an explicitly documented breaking
   decision or retained as a compatibility alias; the implementation must not
   silently reinterpret existing inputs.
8. Human and JSON output must not expose secret survey values, vault key IDs,
   vault passwords, private keys, tokens, or authorization headers.
9. Repository and inventory commands must remain behaviorally unchanged. Their
   current explicit options are the reference pattern for supported resource
   attributes.
10. Help output must show concise syntax and at least one example for the new
    survey options.
11. The existing exit contract remains: `0` success, `1` task execution
    failure, and `2` validation, lookup, network, authorization, malformed
    response, or other API errors.
12. The feature remains backward-compatible for existing commands unless the
    implementation identifies an unavoidable ambiguity and records it in an
    amendment before changing behavior.

## Implementation notes

- Keep argument parsing, survey-argument normalization, survey merge logic,
  validation, transport, and output projection as separate helpers.
- Use a small named parser for `NAME[=VALUE]` and `NAME=VALUE`; split once and
  preserve the value literally.
- Build a mapping keyed by survey name from the existing template, apply direct
  updates in argument order, then run the existing complete survey validator.
- Use the existing `SemaphoreClient.update_template` method rather than adding
  a curl/API fallback.
- Preserve unrelated template fields through the existing safe full-object
  payload builder. Do not copy secret survey values or vault credential data.
- Treat direct survey metadata as configuration, not as task variables. Task
  execution continues to use `task run --var NAME=VALUE`.

## Risks and compatibility

- Survey definitions can contain type-dependent fields, so incomplete direct
  arguments must fail with actionable messages rather than producing a partial
  server object.
- Updating an existing survey variable must not accidentally erase fields that
  the user did not mention.
- A user could put a secret in a default or description; validation must prevent
  secret survey defaults and never echo sensitive values in error/output paths.
- Retaining the old inline JSON and file modes avoids an unnecessary breaking
  release, but the direct options must be the documented path for ordinary
  survey configuration.

## Acceptance criteria

- `semaphore-ui template update --help` lists all direct survey options.
- A focused test proves that `--survey-var inbox_repo_version=main` adds the
  variable without changing unrelated template fields.
- A focused test proves that changing only the default preserves title,
  description, type, target, required state, and options.
- A focused test proves that template create can build a survey definition using
  only CLI arguments.
- Validation rejects malformed assignments, duplicate contradictory values,
  invalid type-specific combinations, and secret defaults/options.
- Repository and inventory command help/tests confirm their existing explicit
  attribute interfaces remain intact.
- API tests verify the full-object PUT request, empty response handling, and
  read-back verification.
- No test or implementation step requires curl or a JSON request file.
- `uv run pytest`, lint/compile checks, `uv build`, and `git diff --check` pass.
- The specification and feature indexes accurately identify the feature as
  proposed until implementation and review are complete.

## Validation plan

Before implementation, validate this specification and index changes only:

```bash
git diff --check
```

After implementation, run focused parser/merge/API tests first, then:

```bash
uv run pytest -q
uv run python -m compileall -q src tests
uv build
git diff --check
semaphore-ui template update --help
semaphore-ui repository update --help
semaphore-ui inventory update --help
```

Live Semaphore validation must use the installed CLI against an explicitly
authorized trusted endpoint, read the target template before mutation, perform a
bounded harmless update or test-template operation, wait for completion where a
task is run, and read the exact template back. No live task is required for the
local feature acceptance criteria.

## Open questions

- Should the legacy inline JSON form of `template create --survey-var` remain as
  a compatibility alias, or should it be rejected in the next major release?
  The default for this feature is to retain it while adding direct options.
- Should direct vault metadata options be added in a later feature? This feature
  deliberately does not expose vault credential fields through arguments.

## Amendments

None.
