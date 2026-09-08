---
type: Feature Specification
title: Add inventory create, copy, and update commands
description: Extend the semaphore-ui inventory namespace with safe project-scoped create, copy, list, show, and update operations, then validate the released candidate against Semaphore and synchronize the downstream ai-toolkit skill.
tags:
  - semaphore
  - cli
  - inventories
  - api
  - python
  - ai-toolkit
sources:
  - id: repository-agents
    resource: ../../AGENTS.md
    title: Repository development and closeout workflow
  - id: current-api-client
    resource: ../../src/semaphore_ui/api.py
    title: Current Semaphore API client and inventory discovery methods
  - id: current-cli
    resource: ../../src/semaphore_ui/cli.py
    title: Current inventory CLI commands and output policy
  - id: current-tests
    resource: ../../tests/test_cli_template_inventory_access_key.py
    title: Current inventory safety and CLI tests
  - id: current-readme
    resource: ../../README.md
    title: Current CLI usage and command documentation
  - id: semaphore-api
    resource: https://raw.githubusercontent.com/semaphoreui/semaphore/develop/api-docs.yml
    title: Semaphore API inventory schema and endpoints
  - id: ai-toolkit-agents
    resource: ../../../ai-toolkit/AGENTS.md
    title: Downstream ai-toolkit development workflow
  - id: ai-toolkit-skill
    resource: ../../../ai-toolkit/skills/semaphore-ui/SKILL.md
    title: Downstream Semaphore skill contract
status: proposed
author: whose-footprints-are-these
---

# Add inventory create, copy, and update commands

## Context

The `semaphore-ui` CLI already exposes project-scoped `inventory list` and
`inventory show` commands. It does not yet provide the configuration operations
needed to create a new inventory, duplicate an existing inventory, or update an
existing inventory. Operators therefore have to use the Semaphore web UI or
hand-built API requests for ordinary project setup.

A Semaphore inventory is a configuration resource inside an existing project,
not a remote Git repository. The API defines `POST /api/project/{project_id}/inventory`
for creation, `GET` on the collection and resource paths, `PUT
/api/project/{project_id}/inventory/{inventory_id}` for updates, and `204` for a
successful update. The API's inventory request includes a name, inventory
content, access-key IDs, an optional repository ID, and an inventory type.[^api]

Inventory content can contain host variables or other sensitive operational
data. Existing list/show output intentionally whitelists metadata and never
prints the content or credential material. The new mutation commands must keep
that boundary: content may be supplied as input or copied as part of an
explicit inventory copy, but it must never be echoed in normal output or error
messages.

The downstream `ai-toolkit` Semaphore skill currently documents inventory as a
read-only discovery resource and pins the reviewed CLI candidate. After the CLI
feature is implemented and live-tested, that skill must document the new
commands and the exact reviewed version/commit to use.

## Goal

Provide a complete, project-scoped inventory command namespace:

```text
semaphore-ui inventory create
semaphore-ui inventory copy
semaphore-ui inventory list
semaphore-ui inventory show
semaphore-ui inventory update
```

Make creation, copying, and updating usable by people, CI, and agent tooling
without exposing inventory content or credentials, and leave the downstream
Semaphore skill accurate after live validation.

## Scope

### In scope

- `inventory create` for a new inventory in an existing project.
- `inventory copy` from one exact source inventory name to a new destination
  name in the same project.
- The existing `inventory list` and `inventory show` commands, including any
  changes required to support stable safe read-back verification.
- `inventory update` for an existing project inventory.
- Project and inventory exact-name lookup, destination collision checks, positive
  ID validation, and the existing exit-status contract.
- API client methods for inventory create, update, and any resource GET needed
  for verification, using the documented endpoint and HTTP methods.
- Secret-safe, whitelist-based human-readable and JSON output for all inventory
  commands. Mutation results must report safe identity/configuration only, not
  inventory content or credential material.
- A secret-free JSON request-file interface for create and update payloads. The
  file may contain only the documented inventory request fields; it must not be
  printed, copied into output, or included in errors.
- Copy transformation that preserves supported source configuration while
  replacing the destination name, without exposing the source content.
- Unit and CLI tests covering parser/help, payload validation, exact lookup,
  collision handling, API methods, read-back verification, 204 responses, and
  secret-safe output.
- README, CLI help, feature index, and feature specification updates.
- After live E2E verification, the corresponding downstream update in
  `/opt/data/ai-toolkit` so `skills/semaphore-ui/SKILL.md` documents the
  reviewed CLI version, inventory commands, safety rules, and installation/use
  procedure.

### Out of scope

- Deleting inventories.
- Changing Semaphore server behavior or API schemas.
- Creating or modifying projects, repositories, access keys, environments,
  templates, tasks, permissions, schedules, or remote Git repositories.
- Displaying inventory content, SSH private keys, passwords, tokens, vault
  values, or other secret-equivalent fields.
- Reading credentials from files or accepting tokens as command arguments.
- Running a task as part of unit validation or inventory command implementation.
- Automatic retries of POST/PUT requests after timeout, because a remote
  mutation may have succeeded.
- Changes to unrelated ai-toolkit skills or release/publishing automation.

## Settled interface

All commands retain singular resource namespaces and require the existing
project-scoped exact-name options:

```bash
semaphore-ui inventory list \
  --project PROJECT --json
semaphore-ui inventory show \
  --project PROJECT --inventory NAME --json
semaphore-ui inventory create \
  --project PROJECT --file inventory.json --json
semaphore-ui inventory copy \
  --project PROJECT --inventory SOURCE --name DESTINATION --json
semaphore-ui inventory update \
  --project PROJECT --inventory NAME --file inventory-update.json --json
```

`create` and `update` use a JSON request file so inventory content is not
placed in shell history or command-line arguments. The accepted top-level
fields are the Semaphore `InventoryRequest` fields: `name`, `inventory`,
`ssh_key_id`, `become_key_id`, `repository_id`, and `type`; `project_id` and
`id` are controlled by the CLI and are not accepted from the file. The CLI
must validate non-empty names/content where applicable, positive numeric IDs,
and the API-supported type values (`static`, `static-yaml`, `file`, and
`terraform-workspace`) before making a mutation. The exact required fields for
each type must follow the deployed API behavior discovered during
implementation; any type-specific requirement not confirmed by the instance
must fail clearly rather than be guessed.

For `update`, the file contains the fields to change and must not permit a
name change. The implementation reads the existing inventory, merges the
explicitly requested supported fields with the required preserved fields, and
sends the documented full update payload. For `copy`, the implementation reads
the source, rejects a same-name or already-existing destination, changes only
`name`, and creates the destination with the source's supported configuration.
The destination name must be supplied separately and must not be taken from
untrusted source content.

Mutation results use the existing safe inventory projection. At minimum this
projection may include `id`, `project_id`, `name`, `type`, and safe resource
identifiers such as `template_id` only when confirmed by the deployed API. It
must exclude `inventory`, `ssh_key_id`, `become_key_id`, private key material,
passwords, tokens, and all unknown fields by default. The final whitelist may
include non-secret IDs needed to identify configuration, but must be justified
by tests and the API response shape.

## Requirements

1. The five inventory subcommands appear in CLI help and use the existing
   `0` success / `1` task failure / `2` configuration, validation, lookup, API,
   network, or input-error contract.
2. Project and inventory names are required non-empty strings and resolve by
   exact match. Missing or ambiguous source resources fail before mutation.
3. Create rejects an existing destination name before POST and validates the
   request-file object and supported fields before POST.
4. Copy reads one exact source, rejects same-name and existing destinations,
   submits a create payload with the destination name, and does not mutate the
   source.
5. Update reads the existing inventory first, changes only explicitly
   supported fields, preserves required fields, rejects name changes, and sends
   one PUT request to the documented resource endpoint.
6. POST responses are validated as inventory objects with positive identity and
   matching project/name. PUT responses, including `204 No Content`, are
   handled explicitly and followed by a GET/read-back.
7. Every successful mutation verifies persisted project identity, destination or
   source identity, and every requested safe field. A successful HTTP status
   without matching persisted state is an error.
8. Request-file contents and API inventory content never appear in human output,
   JSON output, exceptions, logs, or test failure messages. Known secret field
   names and fixture values are covered by regression tests.
9. Existing list/show behavior remains backward compatible and remains safe for
   API responses containing additional or sensitive fields.
10. No mutation is retried automatically after a timeout. Errors identify the
    operation and safe resource identity without including request payloads.
11. The live validation procedure uses only the CLI candidate, environment/
    secret-managed credentials, and a bounded test project/resource. It records
    redacted evidence and does not expose hostnames, tokens, inventory content,
    or credentials.
12. The downstream ai-toolkit skill is updated only after the CLI candidate has
    passed local validation and live inventory command verification. It pins the
    exact reviewed version/commit, lists all five inventory commands, and
    preserves the skill's token and secret-safety rules.

## Acceptance criteria

- `inventory --help` lists `create`, `copy`, `list`, `show`, and `update`.
- Local tests cover all five commands and pass, including malformed request
  files, missing/ambiguous names, destination collisions, safe output, and
  read-back mismatches.
- API tests prove the collection POST, resource PUT, collection/resource GET,
  and explicit empty update response handling.
- Copy preserves the tested supported source configuration and changes only the
  destination name.
- Update persists a harmless supported field and verifies it by read-back.
- No inventory content or credential-equivalent value is emitted by any command
  or error path.
- `uv run pytest`, `uv lock --check`, `uv build`, help smoke tests, and
  `git diff --check` pass.
- The candidate reports the intended version exactly via `semaphore-ui
  --version`.
- Live E2E verification successfully exercises list, show, create, copy, and
  update against the authorized Semaphore host, with redacted evidence and no
  task execution. Cleanup is limited to explicitly authorized non-destructive
  operations; because delete is out of scope, test resources are not silently
  removed.
- The ai-toolkit Semaphore skill names the verified CLI version/commit and
  accurately documents the new inventory operations and safety boundaries.
- The feature specification records implementation, live-test, downstream
  update, release-closeout, and remaining-work evidence truthfully.

## Implementation notes

- Extend `SemaphoreClient` beside the existing inventory list/find methods and
  reuse `_request`, exact lookup, positive-ID validation, and response-shape
  helpers.
- Inspect the deployed instance's API/schema before finalizing validation and
  payload details. The upstream API document is a source for the endpoint and
  model, not proof that every deployed instance has identical behavior.
- Keep request-file parsing and create/copy/update transformations in pure
  helpers so field whitelisting, name rules, and preservation behavior are
  directly testable.
- Keep safe inventory projection separate from mutation payload construction;
  never serialize a raw API object as command output.
- Use TDD: add focused failing tests, observe the intended RED result, implement
  the smallest vertical slice, then run focused and complete validation.
- Do not modify `/opt/data/ai-toolkit` until the CLI implementation and live E2E
  test are complete. The downstream skill update is a separate repository
  mutation and must be verified by reading back its exact file and testing its
  documented installation/version references.

## Risks and mitigations

- **Secret leakage:** never print request bodies or raw inventory responses;
  whitelist output and test known secret values and field names.
- **Schema drift:** inspect the deployed API, validate response identity, and
  fail closed for unsupported fields or type-specific requirements.
- **Collateral changes on update:** merge only supported fields with required
  preserved values and verify read-back field-by-field.
- **Duplicate resources:** list and exact-match before create/copy; reject
  collisions and same-name copies before POST.
- **Partial remote mutation:** do not retry timed-out mutations; require a
  follow-up read-only inspection to determine state.
- **Untracked test resources:** live validation may leave authorized resources
  because deletion is out of scope; record their safe identities and remaining
  cleanup responsibility.
- **Downstream version drift:** update the ai-toolkit skill only from the exact
  verified candidate and verify both the CLI version and documented commit.

## Validation plan

1. Read repository instructions and current source/tests; inspect the upstream
   and deployed API inventory schema and endpoint behavior.
2. Add parser, validation, API, projection, create, copy, update, collision,
   read-back, 204, and secret-safety tests and confirm they fail for the missing
   behavior.
3. Implement vertical slices and rerun focused tests after each slice.
4. Run the complete local suite, lock check, build, help smoke tests, and diff
   hygiene checks.
5. Build/install the candidate from the feature branch and verify the exact
   version without using the live token in output.
6. With explicit authorization immediately before the external operation,
   exercise list/show first, then create/copy/update on bounded harmless
   inventory resources. Verify each mutation by CLI read-back and record only
   redacted safe identities/results. Do not run a task.
7. Update and verify the downstream ai-toolkit Semaphore skill from the tested
   candidate. Run its applicable structural/documentation checks.
8. Complete the semaphore-ui repository's branch synchronization and mandatory
   local release-version closeout, then report external delivery separately.

## Compatibility and release

This is a backward-compatible public CLI feature and normally warrants a minor
version increment from the resulting current version, subject to the
repository's mandatory release closeout procedure. Existing list/show commands,
resource namespaces, TLS defaults, environment credential configuration, and
exit-status behavior remain compatible. The downstream skill must pin the
reviewed candidate rather than an unverified release tag.

## Open questions

None are blocking at specification review. Type-specific required fields and
whether the deployed API accepts collection query parameters are implementation
validation items: they must be discovered from the deployed instance and
recorded before finalizing the payload, not guessed from the command names.

## Amendments

None.

[^api]: [Semaphore API inventory definition and project inventory endpoints](https://raw.githubusercontent.com/semaphoreui/semaphore/develop/api-docs.yml)
