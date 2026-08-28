# Repository Purpose

This repository will provide a versioned Python CLI for running and inspecting Semaphore UI tasks, independently usable by people, CI systems, and AI-agent skills.

## Communication and Research

- Give brief, direct answers that address the request.
- Source factual statements. When research is needed, use multiple independent, relevant sources, cross-check their claims, and link the sources used. Prefer primary sources where practical.
- Be explicit when information is unknown, when more research is needed, or when user input is required. Ask clarifying questions whenever a material requirement is unclear.

## Repository Documentation

Use and maintain this structure:

```text
docs/
├── architecture/  # Architecture documentation, organized by area or technology.
├── features/      # Self-contained feature specifications.
├── decisions/     # Architecture decision records (ADRs).
├── discovery/     # Reusable lessons learned, organized by area or technology.
└── debugging/     # Debugging investigations and outcomes.
```

Every Markdown documentation artifact under `docs/` must conform to Open Knowledge Format (OKF) v0.2: [OKF specification](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md). Create normal documentation files as OKF concept documents: begin with YAML frontmatter containing at least a descriptive `type`. Also include `title`, `description`, `tags`, and provenance `sources` where applicable. Attribute source-specific claims with Markdown footnotes keyed to `sources` entries. Preserve unknown OKF frontmatter keys when updating a document. Use `index.md` and `log.md` only in their defined OKF roles and formats.

For timestamped documents, obtain the timestamp when creating the file. Do not calculate it manually:

```bash
date +"%Y-%m-%d-%H-%M"
```

Use the resulting prefix in this format: `YYYY-MM-DD-HH-MM-<purpose>.md`, where `<purpose>` is concise and lowercase-hyphenated.

- `docs/architecture`: Document architecture by area or technology. Do not use the timestamp filename convention.
- `docs/features`: Create feature specifications here. Use the timestamp filename convention.
- `docs/decisions`: Create architecture decision records using the timestamp filename convention and Nygard-style `Title`, `Context`, `Decision`, `Status`, and `Consequences` sections.
- `docs/discovery`: Record reusable lessons by area or technology; do not use the timestamp filename convention. Consult this directory before related work. Keep it current and non-duplicative.
- `docs/debugging`: Record investigations and outcomes using the timestamp filename convention. Consult `docs/discovery` first.

## Development Flow

1. Before implementation, create a complete, self-contained feature specification in `docs/features`. Include context, goal, scope, requirements, acceptance criteria, constraints, implementation notes, risks, validation, and source links. Ask the user to review it before implementation.
2. When the user asks to continue, create a new branch from up-to-date `main`, named `<category>/<purpose>` using a lowercase, hyphenated purpose.
3. When creating code, use test-driven development: write and run a failing test first, then implement and rerun the tests. Prefer Python unless the user specifies another language.
4. Implement and validate the approved specification on that branch. Keep implementation, documentation, and debugging changes focused.
5. Maintain `docs/features/README.md` as the exhaustive feature index and the root README's `Recent Features` table as the newest-ten index. Keep both newest first, use complete `YYYY-MM-DD-HH-MM` dates, and derive authors from Git metadata.
6. Before completion, review every changed item, update documentation and references, run the applicable validation, and mark the active feature specification `completed` only after implementation, validation, and review succeed.
7. Record small out-of-scope changes in an exact `## Amendments` section of the active specification. Do not amend completed specifications unless correcting a premature completion of the current work.

This repository is intentionally a bootstrap repository at present. Proposed directories and commands must not be described as implemented or passing until they exist and have been exercised.

## Safety and Secrets

- Never commit API tokens, credentials, private exports, caches, generated environments, or local configuration.
- Read Semaphore credentials from environment/secret management; never accept tokens in ordinary command arguments or print authorization headers.
- Treat task execution as a state-changing operation and make destructive or broad operations explicit.
- Validate user-provided project, template, task, and variable inputs before making API calls.

## Definition of Done

A change is complete only when the approved scope is implemented, tests and applicable checks pass, documentation is current, `git diff --check` is clean, no secrets or generated artifacts are included, and the branch is pushed for review rather than merged directly into `main` without explicit authorization.
