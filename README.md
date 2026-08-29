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

List projects and templates:

```bash
semaphore-ui projects
semaphore-ui templates --project configuration_management
```

Trigger a task by name:

```bash
semaphore-ui run \
  --project configuration_management \
  --template hello_world \
  --var target=hermes-001.iot.home \
  --var fact=firewall_interface
```

Wait for completion and retrieve output:

```bash
semaphore-ui wait --project configuration_management --task 4
semaphore-ui output --project configuration_management --task 4 --plain
```

Use `--json` on commands that return structured data for CI and agent integrations. `projects` and `templates` return API resource arrays. `run`, `status`, and `wait` return an envelope with `project`, `template` (for `run`), `task`, and `variables` (for `run`); `task` contains the Semaphore task ID, status, timestamps, and environment. `output --json` returns output entries with `time`, `task_id`, and `output`. Successful tasks exit `0`; task failures exit `1`; configuration, lookup, API, and timeout errors exit `2`.

## Recent Features

| Date | Purpose | Spec | Author |
| --- | --- | --- | --- |
| 2026-08-29-11-37 | Automate CI versioning, tagging, and Python package releases | [Specification](docs/features/2026-08-29-11-37-release-automation.md) | whose-footprints-are-these |
| 2026-08-28-19-59 | Trigger Semaphore tasks by project and template name | [Specification](docs/features/2026-08-28-19-59-trigger-task-by-name.md) | whose-footprints-are-these |

See [all feature specifications](docs/features/README.md).

## Contributing

This is an AI-first development repository. Point your agent or model at [AGENTS.md](AGENTS.md) before contributing.

- Create and have a feature specification reviewed before implementation.
- Use a focused feature branch and test-driven development for code changes.
- Use uv with `pyproject.toml` and commit `uv.lock`; do not commit `.venv`.
- Follow the documentation structure, filename conventions, and OKF requirements in `AGENTS.md`.
- Keep credentials, generated environments, and temporary artifacts out of Git.
