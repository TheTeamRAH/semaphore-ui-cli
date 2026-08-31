---
type: Feature Specification
title: Support Survey Defaults and Vaults in Template Creation
description: Extend Semaphore template creation to preserve non-secret survey defaults and configure project vault associations safely.
tags:
  - semaphore-ui
  - python
  - cli
  - templates
  - survey-vars
  - vaults
sources:
  - https://raw.githubusercontent.com/semaphoreui/semaphore/develop/api-docs.yml
  - https://raw.githubusercontent.com/semaphoreui/semaphore/develop/db/Template.go
  - https://semaphoreui.com/docs/user-guide/task-templates
  - https://semaphoreui.com/docs/admin-guide/api
status: completed
---

# Support Survey Defaults and Vaults in Template Creation

## Context

`semaphore-ui template create` currently rejects the `default_value` member of
each `survey_vars` item and rejects the top-level `vaults` member. This blocks
faithful creation of templates that use pre-filled prompts or Ansible Vault
configuration.

Semaphore's published `TemplateRequest` model accepts a `vaults` array, whose
entries use a vault name, a `password` or `script` type, an optional access-key
ID, and an optional script path.[^api] Its public Swagger model currently omits
`survey_vars[].default_value` and the newer `select` survey type. Semaphore's
survey-variable model nevertheless supports a default as either a string or an
array of strings, with type-specific validation.[^source] The CLI must therefore
recognize both as narrow, known Semaphore extensions while preserving the
existing runtime schema preflight for every other field.

Task templates define task execution; creating one persists configuration and
does not run a task.[^templates]

## Goal

Let a user create a template containing non-secret survey defaults and vault
associations, with local validation, exact project-local access-key resolution,
safe output, and no secret material in request files or command output.

## Scope

### In scope

- The `survey_vars[].default_value` field and `select` type in JSON template
  request files.
- Top-level `vaults` in JSON template request files.
- Exact-name resolution of a vault's referenced project access key.
- Runtime schema-preflight support for the known default-value and `select`
  extensions.
- Safe JSON and human-readable output, documentation, and fake-server tests.

### Out of scope

- Direct command-line flags for nested survey or vault objects; request files
  remain the interface for these structured settings.
- Creating, modifying, deleting, exporting, or revealing vault passwords,
  scripts, or access keys.
- Setting a default value for a `secret` survey variable.
- Updating, deleting, cloning, or executing templates.
- Relaxing schema validation for fields other than the two known extensions.
- Live Semaphore mutation during development or validation.

## Request-file interface

The existing name-based JSON request file gains these fields:

```json
{
  "name": "deploy-web",
  "repository": "web",
  "inventory": "production",
  "environment": "default",
  "playbook": "deploy.yml",
  "survey_vars": [
    {
      "name": "target",
      "title": "Target host",
      "type": "select",
      "required": false,
      "values": [
        {"name": "Web 1", "value": "web-01"},
        {"name": "Web 2", "value": "web-02"}
      ],
      "default_value": ["web-01", "web-02"]
    }
  ],
  "vaults": [
    {
      "name": "production",
      "type": "password",
      "vault_key": "Production vault password"
    },
    {
      "name": "legacy",
      "type": "script",
      "vault_key": "Vault client credential",
      "script": "scripts/vault-client.py"
    }
  ]
}
```

`default_value` must be a string or an array of strings. A scalar is accepted
for every non-secret type; an array is accepted only for `select`. For `enum`
and `select`, every default must match one of the declared option values. An
explicitly supplied empty string is preserved. Defaults are allowed only when
the survey-variable type is not `secret`, and are submitted unchanged. The CLI
must reject secret survey defaults before any lookup or POST; it must not print
default values in normal or JSON output.

Each vault object has a non-empty `name`, `type` (`password` or `script`), and
may contain a non-empty `vault_key` exact name and a non-empty `script` path.
`script` is valid only for a `script` vault. `vault_key` is a CLI-only,
name-based reference: it is resolved through the selected project's access-key
collection and converted to `vault_key_id` in the API payload. The submitted
vault object must contain only Semaphore API fields (`name`, `type`, optional
`vault_key_id`, and optional `script`); it must never contain `vault_key`.

An omitted `vault_key` is permitted because Semaphore models `vault_key_id` as
optional.[^api] A missing or ambiguous supplied key name is a validation error
and prevents the create request.

## Requirements

1. Extend the accepted request-file fields with `vaults`, and the accepted
   survey-variable fields with `default_value`.
2. Support survey types `""`, `int`, `enum`, `secret`, `text`, and `select`.
   Require every supplied `default_value` to be a string or an array of strings,
   with arrays permitted only for `select`. Preserve its JSON shape and values
   exactly in the template-create payload, including `""`.
3. Reject any `default_value` on a `secret` survey variable before client
   creation, resource lookup, Swagger retrieval, or POST.
4. Validate vault objects and their type-dependent fields locally before API
   access. Reject unknown fields, non-list `vaults`, malformed entries,
   unsupported types, blank names, blank key references, and a script on a
   password vault.
5. Add a client lookup for project access keys that uses existing exact-name
   lookup semantics: zero and multiple matches are failures, and returned IDs
   must be positive integers before the POST.
6. Resolve every supplied `vault_key` only after project resolution and before
   the preflight or create POST. Convert it to `vault_key_id` and omit the
   client-only name reference.
7. Continue to preflight the target instance's `/api/swagger` before POSTing
   when the endpoint exists.
   Permit `survey_vars[].default_value` and `survey_vars[].type="select"` as
   the only documented Semaphore extensions when that nested property or enum
   value is absent from Swagger; validate all other payload fields and nested
   values normally. If Swagger explicitly defines either extension, validate its
   declared constraints normally.
8. Do not generalize these exceptions: an unrecognized survey field, unrecognized
   vault field, unsupported parent `survey_vars`/`vaults` field, malformed
   schema, or non-404 preflight failure remains an exit-status-2 failure with no
   POST. A 404 from exactly `GET /api/swagger` is the documented compatibility
   case for instances that do not expose the schema endpoint.
9. Preserve redaction: neither human output nor the stable JSON envelope may
   include survey default values, survey values, arguments, task parameters,
   access-key secret material, or vault scripts. Safe output may include each
   configured vault's name, type, and resolved access-key identity.
10. Preserve all existing commands and all supported template-create behavior.

## Implementation notes

- Extend the CLI request-shape validators in `src/semaphore_ui/cli.py` and keep
  the existing direct-option/file exclusivity unchanged.
- Add project access-key list/find support in `src/semaphore_ui/api.py`, using
  `GET /api/project/{project_id}/keys` and the repository's existing safe HTTP,
  list-response, exact-name, and positive-ID validation patterns. Semaphore's
  API documents project access keys and bearer-token authentication.[^api][^auth]
- Isolate the known-extension handling in the schema validator so it cannot
  accidentally permit arbitrary absent Swagger fields.
- Build the final payload only after all local validation and named-resource
  resolution succeed; then preflight and POST once. Do not retry a potentially
  accepted create request.
- Update the README's template request-file example and field list. It must
  state that survey defaults cannot be secret values and that vault access keys
  are references to existing project keys, not credential input.

## Acceptance criteria

- [x] Request files with non-secret scalar and `select`-array
  `survey_vars[].default_value` values create payloads preserving their exact
  JSON shapes and values.
- [x] The same request succeeds when a compatible fake Swagger schema omits
  `default_value` and the `select` enum value; every other unsupported field
  still fails preflight without a POST.
- [x] A Swagger schema that explicitly constrains either extension is respected.
- [x] An invalid default shape/type combination and a default on a secret survey
  variable fail before lookup, preflight, or POST, without displaying the value.
- [x] A request file with password and script vaults resolves each supplied
  `vault_key` by exact project-local name and POSTs `vault_key_id`, never the
  reference name.
- [x] Missing, ambiguous, or invalid resolved access keys fail before preflight
  or POST.
- [x] Vault validation rejects every malformed/type-incompatible shape before
  API use.
- [x] Safe JSON output reports only the allowed vault identities and does not
  reveal defaults, scripts, arguments, task parameters, or credentials.
- [x] Existing template-create tests remain green and no test requires network,
  credentials, or a live Semaphore instance.
- [x] `uv run pytest`, `uv build`, and `git diff --check` pass.

## Validation plan

1. Add focused failing tests for default-value validation/payload preservation,
   extension-aware Swagger validation, vault validation, access-key resolution,
   safe output, and each no-POST failure path.
2. Run the focused tests and confirm they fail before implementation.
3. Implement the smallest CLI/client/schema changes, rerunning the focused
   tests until they pass.
4. Run `uv run pytest`, `uv build`, `uv run semaphore-ui template create --help`,
   and `git diff --check`.
5. Review the final request paths and output fixtures for accidental secret
   exposure. Do not perform live creation without separate user approval.

## Risks and constraints

- Different Semaphore releases may not persist the extensions documented by the
  current upstream source. The narrow extensions are intentional because the
  user selected full upstream-compatible defaults; the target schema remains
  authoritative for all other fields.
- Vault names and access-key names can change between lookup and POST. Exact
  matching prevents selecting the first similarly named resource but cannot
  eliminate this server-side race.
- An ambiguous network failure after POST can still create a template; automatic
  retries remain unsafe.
- A vault script path and a default value can be operationally sensitive even
  when not credentials. Output redaction therefore omits both.

## Completion conditions

The work is ready for closeout only after the approved scope is implemented on
a feature branch, tests and declared validation pass, documentation is current,
the feature branch is synchronized with local `main`, mandatory release-closeout
policy succeeds, and the branch is pushed for review. This specification starts
as `proposed` and must not be implemented until user approval.

## Release Closeout

- Status: updated and passed. This is a backward-compatible public CLI feature,
  so the release classification is minor.
- Version: `0.3.0` to `0.4.0`. `pyproject.toml` is the authoritative source and
  `uv.lock` was regenerated as the required derived artifact.
- Synchronization: `git merge --no-edit main` reported `Already up to date.`;
  local `main` is an ancestor of the feature branch and no Git operation is in
  progress.
- Validation: `uv lock --check`, `uv run pytest` (43 passed), `uv build`,
  `uv run semaphore-ui --version` (reported `0.4.0`), and `git diff --check`
  passed. Build distributions are validation-only ignored artifacts.
- Amendment release: updated and passed (patch). The completed amendment adds
  optional no-environment creation and direct nested CLI options, completing
  the existing feature scope. Version: `0.4.0` to `0.4.1`; `pyproject.toml`
  remains authoritative and `uv.lock` was regenerated. After local-main
  synchronization reported `Already up to date.`, `uv lock --check`, `uv run
  pytest` (45 passed), `uv build`, `uv run semaphore-ui --version` (reported
  `0.4.1`), and `git diff --check` passed.
- Swagger compatibility amendment release: updated and passed (patch). The
  missing-`/api/swagger` compatibility fix changes version `0.4.1` to `0.4.2`.
  `pyproject.toml` remains authoritative and `uv.lock` was regenerated. After
  local-main synchronization, `uv lock --check`, `uv run pytest` (46 passed),
  `uv run semaphore-ui template create --help`, `uv build`,
  `uv run semaphore-ui --version` (reported `0.4.2`), and `git diff --check`
  passed. Build distributions are validation-only ignored artifacts.

## Amendments

- Add discoverable `template create --help` guidance for nested survey and
  vault configuration. Add regression coverage for the help text and preserve
  all command behavior.
- Correct the environment dependency: `--environment` is optional. When it is
  omitted, do not look up an environment and submit Semaphore's no-environment
  representation, `environment_id: 0`. Preserve exact-name resolution when the
  option is supplied.
- Replace the request-file-only restriction for nested template configuration
  with repeatable `--survey-var JSON` and `--vault JSON` options. These objects
  use the documented `survey_vars` and name-based vault shapes, may be combined
  with normal create options, and must have the same validation, vault-key
  resolution, preflight, redaction, help, and README documentation as file
  input. A request file remains available for reproducible advanced requests
  but cannot be combined with direct options.
- Support Semaphore instances that do not expose `GET /api/swagger`. When that
  exact preflight endpoint returns HTTP 404, continue to the create request
  after local validation and named-resource resolution. Preserve schema
  validation when Swagger is available and preserve failures for all other
  preflight errors, including malformed schemas and non-404 HTTP responses.

## Sources

[^api]: Semaphore UI, `api-docs.yml`: `TemplateRequest`, `TemplateVault`, project access-key endpoint, and API base path, https://raw.githubusercontent.com/semaphoreui/semaphore/develop/api-docs.yml
[^source]: Semaphore UI, `db/Template.go`: `SurveyVarDefaultValue`, survey-type validation, and `SurveyVar` JSON field, https://raw.githubusercontent.com/semaphoreui/semaphore/develop/db/Template.go
[^templates]: Semaphore UI, “Task Templates”, https://semaphoreui.com/docs/user-guide/task-templates
[^auth]: Semaphore UI, “API”, bearer-token authentication, https://semaphoreui.com/docs/admin-guide/api
