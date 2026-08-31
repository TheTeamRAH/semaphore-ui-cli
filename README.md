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
semaphore-ui 0.3.0
```

List projects and templates:

```bash
semaphore-ui projects
semaphore-ui templates --project configuration_management
```

Discover historical tasks:

```bash
semaphore-ui tasks --project configuration_management --limit 20
semaphore-ui tasks --project configuration_management \
  --var target=hermes-001.iot.home \
  --var fact=firewall_interface \
  --json

Filter by status, template, or creation time:

```bash
semaphore-ui tasks --project configuration_management \
  --status success \
  --template hello_world \
  --since 2026-08-29T00:00:00Z \
  --limit 20 --json
```

Trigger a task by name:

```bash
semaphore-ui run \
  --project configuration_management \
  --template hello_world \
  --var target=hermes-001.iot.home \
  --var fact=firewall_interface
```

Create a task template without running it. The project, repository, inventory,
environment, and optional view are resolved by exact name before the one
configuration-changing request is made:

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

For survey variables or task parameters, use a JSON object with name-based
resource references. Do not put API tokens, SSH keys, vault material, or secret
survey values in this file:

```json
{
  "name": "show-firewall-interface",
  "repository": "configuration-management",
  "inventory": "homelab",
  "environment": "default",
  "playbook": "site.yml",
  "git_branch": "main",
  "type": "",
  "survey_vars": [
    {"name": "target", "title": "Target", "type": "", "required": true}
  ],
  "task_params": {"params": {"dry_run": true, "tags": ["firewall"]}}
}
```

```bash
semaphore-ui template create --project configuration_management --file template.json --json
```

The request file accepts `name`, `repository`, `inventory`, `environment`, and
`playbook` (all required); plus `description`, `git_branch`, `type` (`""`,
`build`, or `deploy`), `arguments`, `survey_vars`, `task_params`, and `view`.
It cannot be combined with direct template options. The `--json` result contains
the created template and only safe effective configuration; it deliberately
omits arguments, survey values, and task parameters. Template creation persists
configuration but does not execute a playbook. The token must have permission to
create templates and read the referenced project resources; authorization
failures return exit status `2`.

Wait for completion and retrieve output:

```bash
semaphore-ui wait --project configuration_management --task 4
semaphore-ui output --project configuration_management --task 4 --plain
```

Check a task:

```bash
semaphore-ui status --project NAME --task ID
```

Use `--json` on commands that return structured data for CI and agent integrations. `projects` and `templates` return API resource arrays. `run`, `status`, and `wait` return an envelope with `project`, `template` (for `run`), `task`, and `variables` (for `run`); `template create --json` returns `project`, `template`, and safe `configuration`; `task` contains the Semaphore task ID, status, timestamps, and environment. `output --json` returns output entries with `time`, `task_id`, and `output`. Successful commands exit `0`; task failures exit `1`; configuration, validation, lookup, network, authorization, malformed-response, and other API errors exit `2`.

## Recent Features

| Date | Purpose | Spec | Author |
| --- | --- | --- | --- |
| 2026-08-31-14-28 | Document v0.2.0 release candidate CLI usage | [Specification](docs/features/2026-08-31-14-28-document-release-candidate-usage.md) | jibbajabber |
| 2026-08-29-21-02 | Create Semaphore task templates | [Specification](docs/features/2026-08-29-21-02-create-task-templates.md) | whose-footprints-are-these |
| 2026-08-29-11-28 | Discover and filter Semaphore task history | [Specification](docs/features/2026-08-29-11-28-task-discovery.md) | whose-footprints-are-these |
| 2026-08-28-19-59 | Trigger Semaphore tasks by project and template name | [Specification](docs/features/2026-08-28-19-59-trigger-task-by-name.md) | whose-footprints-are-these |

See [all feature specifications](docs/features/README.md).

## Contributing

This is an AI-first development repository. Point your agent or model at [AGENTS.md](AGENTS.md) before contributing.

- Create and have a feature specification reviewed before implementation.
- Use a focused feature branch and test-driven development for code changes.
- Use uv with `pyproject.toml` and commit `uv.lock`; do not commit `.venv`.
- Follow the documentation structure, filename conventions, and OKF requirements in `AGENTS.md`.
- Keep credentials, generated environments, and temporary artifacts out of Git.
