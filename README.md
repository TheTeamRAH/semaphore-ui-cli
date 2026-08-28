# semaphore-ui-cli

A versioned Python CLI for running and inspecting Semaphore UI tasks. It is designed to be usable independently by people and CI systems, and as the execution layer for AI-agent skills.

## Repo Structure

```text
.
├── AGENTS.md  # Repository-specific instructions for AI-assisted work
├── docs/      # Architecture, feature, decision, discovery, and debugging records
├── src/       # Python package and CLI implementation (proposed)
└── tests/     # Automated tests (proposed)
```

The implementation directories are proposed only; this bootstrap change contains guidance and repository documentation, not executable code.

## Getting Started

Implementation has not started yet. Review [AGENTS.md](AGENTS.md) for the required specification-first workflow before adding code.

The eventual CLI is expected to use `SEMAPHORE_HOST` and `SEMAPHORE_TOKEN` from environment/secret management. Do not commit or pass those values as ordinary command-line arguments.

## Recent Features

| Date | Purpose | Spec | Author |
| --- | --- | --- | --- |

No implemented features are recorded yet. Feature specifications will be added under `docs/features/` when implementation work begins.

## Contributing

This is an AI-first development repository. Point your agent or model at [AGENTS.md](AGENTS.md) before contributing.

- Create and have a feature specification reviewed before implementation.
- Use a focused feature branch and test-driven development for code changes.
- Follow the documentation structure, filename conventions, and OKF requirements in `AGENTS.md`.
- Keep credentials, generated environments, and temporary artifacts out of Git.
- Keep communication concise, source factual claims, and ask when requirements are unclear.
