# semaphore-ui-cli

A versioned Python CLI for running and inspecting Semaphore UI tasks by project and template name. It is independently usable by people and CI systems, and serves as the execution layer for AI-agent skills.

## Repo Structure

```text
.
├── AGENTS.md       # Repository-specific instructions for AI-assisted work
├── docs/features/  # Feature specifications and the exhaustive feature index
├── pyproject.toml  # Package metadata and uv configuration
├── src/            # Python package and CLI implementation
├── tests/          # Automated tests
└── uv.lock         # Reproducible dependency resolution
```

## Getting Started

Install the published CLI into its own uv-managed environment:

```bash
uv tool install semaphore-ui
```

For development from a checkout:

```bash
uv run pytest
uv build
```

Set the Semaphore connection through environment/secret management:

```bash
export SEMAPHORE_HOST="https://semaphore.example"
export SEMAPHORE_TOKEN="<token>"
```

Do not commit or pass the token as a command-line argument. Certificate verification is enabled by default. For a trusted internal endpoint with an untrusted certificate, explicitly add `--insecure` before the subcommand.

### Examples

Check the installed version:

```console
$ semaphore-ui --version
semaphore-ui 1.4.0
```

List projects and inspect one project:

```bash
semaphore-ui project list
semaphore-ui project show --project configuration_management
```

List templates in a project and inspect one template:

```bash
semaphore-ui template list --project configuration_management
semaphore-ui template show --project configuration_management --template hello_world
```

Manage project-scoped Semaphore repository resources. These commands configure
Semaphore repository records; they do not create or modify remote Git
repositories:

```bash
semaphore-ui repository list --project configuration_management
semaphore-ui repository show --project configuration_management --repository configuration_management
semaphore-ui repository create \
  --project configuration_management \
  --name fb_configuration_management \
  --git-url git@bitbucket.org:adamhills/configuration_management.git \
  --git-branch master
semaphore-ui repository copy \
  --project configuration_management \
  --repository configuration_management \
  --name fb_configuration_management \
  --git-branch feature_branch_cm
semaphore-ui repository update \
  --project configuration_management \
  --repository fb_configuration_management \
  --git-branch feature_branch_cm
```

Repository copy preserves the source Git URL and access-key reference while
allowing an explicit branch/ref override. Credentials and private key material
are never copied or displayed. Repository creation and copying reject existing
destination names and do not run tasks. Repository update changes only the
configured branch/ref of an existing Semaphore repository resource; it does not
modify the remote Git repository. The CLI reads the resource first, sends the
full required configuration, and verifies the branch after the update.

Discover historical tasks:

```bash
semaphore-ui task list --project configuration_management --limit 20
semaphore-ui task list --project configuration_management \
  --var target=hermes-001.iot.home \
  --var fact=firewall_interface \
  --json

Filter by status, template, or creation time:

```bash
semaphore-ui task list --project configuration_management \
  --status success \
  --template hello_world \
  --since 2026-08-29T00:00:00Z \
  --limit 20 --json
```

Trigger a task by name:

```bash
semaphore-ui task run \
  --project configuration_management \
  --template hello_world \
  --var target=hermes-001.iot.home \
  --var fact=firewall_interface
```

The singular resource commands are the supported interface. The former
top-level forms `projects`, `templates`, `tasks`, `run`, `status`, `wait`, and
`output` were removed in the `1.0.0` breaking release; migrate those commands
to the resource forms above.

Create a task template without running it. The project, repository, inventory,
and optional environment/view are resolved by exact name before the one
configuration-changing request is made. Omit `--environment` when the project
has no environments; the CLI sends Semaphore's no-environment value,
`environment_id: 0`:

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

Add survey variables directly with repeatable CLI options. The variable title
defaults to its name when omitted; metadata can be supplied with the matching
`--survey-*` option:

```bash
semaphore-ui template create \
  --project configuration_management \
  --name deploy-web \
  --repository configuration-management \
  --inventory homelab \
  --playbook deploy.yml \
  --survey-var target=web-01 \
  --survey-title target=Target \
  --survey-required target
```

The same options update an existing template without curl:

```bash
semaphore-ui template update \
  --project configuration_management \
  --template fb_deploy_compose \
  --survey-var inbox_repo_version=main \
  --survey-title inbox_repo_version="Inbox repository version" \
  --survey-description inbox_repo_version="Git branch, tag, or commit" \
  --json
```

The legacy inline JSON `--survey-var` and `--vault` forms remain accepted for
backward compatibility. New workflows should use the direct survey options.
The `--file` mode remains an advanced compatibility escape hatch and is not
required for ordinary survey configuration. Secret survey values, vault
passwords, scripts, tokens, and private keys are never accepted or printed.

Template creation persists configuration but does not execute a playbook. The
legacy `--file` mode remains available for compatibility with advanced payloads,
but direct CLI options are the supported workflow for survey variables. The
`--json` result contains the created template and only safe effective
configuration; it omits arguments, survey values/defaults, vault scripts, and
task parameters. A vault's optional `vault_key` is the exact name of an existing
project access key, never credential input. Authorization failures return exit
status `2`. Before creating a template, the CLI checks the target instance's
Swagger schema at `/api/swagger` when that endpoint exists. A missing Swagger
endpoint is supported for older Semaphore instances; malformed or incompatible
schemas and other preflight errors return exit status `2` and prevent the POST.
Semaphore's known `survey_vars[].default_value` and `select` extensions remain
accepted when an otherwise compatible Swagger document has not yet listed them.

Copy an existing template without running it. The source is resolved by exact
name, the destination must be new, and supported non-secret configuration is
preserved:

```bash
semaphore-ui template copy \
  --project configuration_management \
  --template hello_world \
  --name hello_world_copy \
  --json
semaphore-ui template update \
  --project configuration_management \
  --template hello_world \
  --git-branch feature_branch_cm \
  --json
```

Template copying never copies credentials, vault passwords, vault scripts, or
secret survey values. It also never executes a task. Unsupported source
configuration causes a validation error before the create request.

The copy command reports the source and created template identities plus safe
effective configuration.

Update changes the configured branch/ref of an existing template in place. The
CLI preserves the other supported template configuration, reads the resource
back after the update, and verifies the persisted result.

Discover project inventories and access-key identities without exposing
inventory content or credentials:

```bash
semaphore-ui inventory list --project configuration_management --json
semaphore-ui inventory show --project configuration_management \
  --inventory configuration_management --json
semaphore-ui access-key list --project configuration_management --json
semaphore-ui access-key show --project configuration_management \
  --access-key "deploy key" --json
```

Create, copy, and update inventories using explicit CLI options. `--path` maps
to Semaphore's inventory path/content field, while access-key and repository
options resolve exact project-scoped names:

```bash
semaphore-ui inventory create \
  --project configuration_management \
  --name homelab --type file --path inventories/homelab \
  --ssh-key "deploy key" --repository configuration_management
semaphore-ui inventory copy \
  --project configuration_management \
  --inventory configuration_management --name homelab-copy
semaphore-ui inventory update \
  --project configuration_management \
  --inventory homelab --path inventories/homelab-new
```

Inventory mutations verify the persisted resource after the request and return
identity and safe metadata only. Inventory content and credential material are
never displayed. Access-key commands never return private keys, passwords,
tokens, or equivalent secret material.

Wait for completion and retrieve output:

```bash
semaphore-ui task wait --project configuration_management --task 4
semaphore-ui task output --project configuration_management --task 4 --plain
```

Check a task:

```bash
semaphore-ui task status --project NAME --task ID
```

Use `--json` on commands that return structured data for CI and agent integrations. Canonical resource commands are `project`, `repository`, `template`, `inventory`, `access-key`, and `task`; the former top-level commands were removed in `1.0.0`. List/show commands resolve project-scoped resources by exact name. `task run`, `task status`, and `task wait` return an envelope with `project`, `template` (for `run`), `task`, and `variables` (for `run`); template and repository mutations return safe identity/configuration envelopes and verify read-back state. Inventory and access-key output is metadata-only. `task output --json` returns output entries with `time`, `task_id`, and `output`. Successful commands exit `0`; task failures exit `1`; configuration, validation, lookup, network, authorization, malformed-response, and other API errors exit `2`.

## Recent Features

| Date | Purpose | Spec | Author |
| --- | --- | --- | --- |
| 2026-09-19-15-24 | Add direct CLI attribute options for Semaphore template surveys | [Specification](docs/features/2026-09-19-15-24-template-cli-attribute-options.md) | whose-footprints-are-these |
| 2026-09-08-20-18 | Add inventory create, copy, and update commands | [Specification](docs/features/2026-09-08-20-18-inventory-resource-commands.md) | whose-footprints-are-these |
| 2026-09-06-18-47 | Add template update and project resource discovery commands | [Specification](docs/features/2026-09-06-18-47-template-inventory-access-key-resources.md) | whose-footprints-are-these |
| 2026-09-06-17-32 | Add Semaphore repository resource commands | [Specification](docs/features/2026-09-06-17-32-repository-resource-commands.md) | whose-footprints-are-these |
| 2026-09-05-20-55 | Normalize semaphore-ui CLI command conventions | [Specification](docs/features/2026-09-05-20-55-cli-command-conventions.md) | whose-footprints-are-these |
| 2026-09-04-23-00 | Add safe Semaphore template copy command | [Specification](docs/features/2026-09-04-23-00-template-copy.md) | whose-footprints-are-these |
| 2026-08-31-21-20 | Support survey defaults and vaults in template creation | [Specification](docs/features/2026-08-31-21-20-template-survey-defaults-and-vaults.md) | Jibba Jabber |
| 2026-08-31-14-28 | Document v0.2.0 release candidate CLI usage | [Specification](docs/features/2026-08-31-14-28-document-release-candidate-usage.md) | jibbajabber |
| 2026-08-29-21-02 | Create Semaphore task templates | [Specification](docs/features/2026-08-29-21-02-create-task-templates.md) | whose-footprints-are-these |
| 2026-08-29-11-28 | Discover and filter Semaphore task history | [Specification](docs/features/2026-08-29-11-28-task-discovery.md) | whose-footprints-are-these |

See [all feature specifications](docs/features/README.md).

## Contributing

This is an AI-first development repository. Point your agent or model at [AGENTS.md](AGENTS.md) before contributing.

- Create and have a feature specification reviewed before implementation.
- Use a focused feature branch and test-driven development for code changes.
- Use uv with `pyproject.toml` and commit `uv.lock`; do not commit `.venv`.
- Follow the documentation structure, filename conventions, and OKF requirements in `AGENTS.md`.
- Keep credentials, generated environments, and temporary artifacts out of Git.
