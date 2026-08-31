# Repository Purpose

This repository provides a versioned Python CLI for running and inspecting Semaphore UI tasks, independently usable by people, CI systems, and AI-agent skills.

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
- `docs/decisions`: Create ADRs here using the timestamp filename convention. Use Nygard style: `Title`, `Context`, `Decision`, `Status`, and `Consequences`. See Michael Nygard, [Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).
- `docs/discovery`: Record reusable lessons by area or technology; do not use the timestamp filename convention. Consult this directory before related work. Keep it current and non-duplicative. When a mistake teaches a reusable lesson, document it here so it is not repeated.
- `docs/debugging`: Record investigations and outcomes using the timestamp filename convention. Consult `docs/discovery` before starting an investigation. If the outcome yields a reusable lesson, add or update the relevant discovery document after checking for existing coverage.

## Development Flow

1. Before implementation, create a complete, self-contained feature specification in `docs/features`. Include context, goal, scope, requirements, acceptance criteria, constraints, implementation notes, risks, validation, and source links. Give a new context window, using only the specification and its cited repository sources, every fact, decision, constraint, dependency, relevant path, interface expectation, validation command or procedure, and source needed to implement, validate, and determine completion without prior conversation or unstated assumptions.
2. While drafting, resolve missing information, conflicting requirements, and choices that could materially change scope, externally visible behavior, architecture, risk, validation, or acceptance. Use authoritative repository evidence when available; otherwise ask the user focused clarifying questions. Do not invent material requirements or silently select among materially different interpretations. Clearly label non-material implementation discretion.
3. After drafting and before human review, review the specification from the perspective of an agent with only the specification and its cited repository sources. Confirm it says what to change and not change, why, the expected behavior, settled decisions, executable validation, and completion conditions. Remove unresolved placeholders, ambiguous references, hidden conversational context, unsupported assumptions, missing edge cases, incomplete acceptance criteria, and unusable validation steps. Revise to close every gap. If a material gap requires user input, ask and keep the specification in a draft or proposed state. Present it as ready for human review only when no material assumptions or required information remain unresolved.
4. Ask the user to review the specification. Do not implement until they ask to continue.
5. When the user asks to continue, create a new branch from up-to-date `main` before implementation. Name it `<category>/<purpose>`, where category is `feature`, `fix`, or `explore` and purpose is succinct and lowercase-hyphenated. Immediately after branch creation, update the root `README.md` `Recent Features` table and `docs/features/README.md`, the exhaustive feature index. Keep both tables newest first and use the root README's `Date`, `Purpose`, `Spec`, and `Author` column format for each. Every `Date` cell must use the complete `YYYY-MM-DD-HH-MM` prefix from its linked feature specification filename, never a date-only value. Keep only the ten most recent features in the root README table and derive authors from Git metadata.
6. When creating code, use test-driven development: write and run a test first, and confirm it fails because the implementation does not exist; then create the implementation and rerun the tests to confirm they pass. Prefer Python unless the user specifies another language. Use Bash only for simple work, mindful that it has no native testing capabilities; use an appropriately testable language for substantive code.
7. Implement and validate the approved specification on that branch. Keep implementation, documentation, and debugging changes focused.
8. After implementation and validation succeed, review all changed content. Review changed code for safe, worthwhile improvements to clarity, maintainability, duplication, and consistency; make and validate those improvements. Document newly created repository content in its appropriate location. If content was renamed, update relevant existing documentation and references. Assess whether the work produced a reusable lesson and, when it did, add or update the appropriate documentation, normally `docs/discovery`, without duplication. Check the root `README.md` `Repo Structure` section and update it when necessary. Maintain relevant repository documentation as a current source of knowledge.
9. If work stops before completion, perform the applicable quality, documentation, and reusable-learning review. Preserve the active feature specification's truthful lifecycle state and do not declare the feature complete.
10. If the user asks for a small change outside the current specification while its work is underway, record it in a new `## Amendments` section of that active feature specification before or alongside making the change. Before completion or a stopped-work handoff, ensure all such user requests are recorded there, including requests not implemented because work stopped. Keep the exact heading `Amendments`. Do not automatically amend a specification already marked `completed`. The sole exception is correcting a prematurely `completed` specification when it is the current work. If it is unclear whether a specification is active, completed, or was prematurely marked complete, consult the user before changing it.
11. Before marking the active specification `completed` or declaring the feature complete, merge the current `main` branch into the feature branch. Resolve conflicts caused by parallel work, rerun affected validation, and preserve ordering and completeness in shared documentation indexes, including root README and feature-index tables.
12. After the completion review and branch synchronization succeed, run every applicable mandatory declared closeout stage under `Feature Closeout Workflow`. Mark the active feature specification's frontmatter status as `completed` only after implementation, validation, review, branch synchronization, and all applicable mandatory declared closeout stages reach a repository-permitted successful outcome.

## Feature Closeout Workflow

### 1. Local release-version decision and update (mandatory when a releasable change is completed)

- **Trigger and prerequisite:** Run after the quality, documentation, reusable-learning, and security reviews; after merging current local `main` into the feature branch; and only after resolving every textual and semantic conflict. Before starting, confirm `main` is an ancestor of `HEAD` and no merge, rebase, cherry-pick, or revert is in progress.
- **Executor and authority:** An agent follows this declared local command procedure. It may make only the local version and derived-lockfile changes described here. It has no authority to fetch, install or update tooling, access credentials, push, tag, publish, create a hosted release or pull request, or merge the feature branch into `main`.
- **Inputs and context:** The active feature specification, the post-merge `HEAD`, the synchronized local `main` commit, the feature diff, this policy, and any user decisions allowed by this policy. Read the current version only from the resulting post-merge `pyproject.toml`.
- **Release decision:** A completed change warrants a release when it changes the CLI's supported behavior, public interface, compatibility, or architecture. Documentation-only, test-only, tooling-only, and internal changes with no such effect are `no-release` unless the active specification declares otherwise. Do not invent a release for a no-release change.
- **Classification and precedence:** Use Semantic Versioning. A breaking CLI/API compatibility change or fundamental architecture change is **major**. A backward-compatible feature or improvement is **minor**; minor is the default for releasable work. A bug fix, or a missed scope item or amendment completing an existing feature, is **patch**. When the evidence could fit more than one category, apply the highest applicable category. Ask the user if the evidence leaves the release decision or classification materially ambiguous.
- **Authoritative and derived artifacts:** `pyproject.toml` `[project].version` is the sole authoritative version. `uv.lock`'s editable `semaphore-ui` package record is a required derived artifact and must match it. `src/semaphore_ui/__init__.py` derives its value from installed package metadata and must not be manually versioned.
- **Idempotence and procedure:** Before calculating or writing a version, compare the working-tree versions in `pyproject.toml` and `uv.lock` with the synchronized local `main` versions. If a valid, matching version update is already present for this feature's recorded release decision, preserve it and do not increment again; rerun validation and final review. If an existing version update cannot be attributed confidently to this feature and decision, stop for user direction. Otherwise, update the authoritative version only when the decision is `updated`, then run `uv lock` to regenerate `uv.lock`; do not manually edit the lockfile or change unrelated dependency versions. For `no-release`, leave both version-bearing files unchanged. Record the decision, classification, previous and resulting versions, artifact changes, commands, and validation evidence in a `## Release Closeout` section of the active feature specification so a resumed closeout can establish this evidence durably.
- **Validation and evidence:** Run `uv lock --check`, `uv run pytest` (including `tests/test_version.py`), `uv build`, and all checks affected by the release update. Build outputs are validation-only generated artifacts: do not stage or include them in the final diff. Review every post-merge version or lockfile mutation again for quality, documentation, reusable-learning, and security implications. Return to feature completion: status (`updated`, `no-release`, or `blocked`); decision reason; classification (or not applicable); previous and resulting versions; authoritative source; regenerated artifacts; commands and outcomes; validation and drift evidence; and any user-resolved ambiguity or permitted exception.
- **Outcomes, retry, and resume:** `passed` is an `updated` result with all required artifacts and checks successful, or a substantiated `no-release` result with required checks successful. `failed` means a required command or check failed; retry after correcting the cause. `unavailable` is blocking for this mandatory stage unless this policy explicitly permits an exception; it does not. `skipped` and `not-applicable` apply only to the classification field for a no-release result, never to the stage. Resume only after the post-merge branch remains synchronized, no Git operation is in progress, and the failure or ambiguity has been resolved.
- **Separate authorization:** Any remote operation or external mutation requires separate user authorization. A local version update never authorizes publication.

This repository is intentionally a bootstrap repository at present. Proposed directories and commands must not be described as implemented or passing until they exist and have been exercised.

## Safety and Secrets

- Never commit API tokens, credentials, private exports, caches, generated environments, or local configuration.
- Read Semaphore credentials from environment/secret management; never accept tokens in ordinary command arguments or print authorization headers.
- Treat task execution as a state-changing operation and make destructive or broad operations explicit.
- Validate user-provided project, template, task, and variable inputs before making API calls.

## Definition of Done

A change is complete only when the approved scope is implemented, tests and applicable checks pass, the mandatory release-version closeout has reached its permitted successful outcome, documentation is current, `git diff --check` is clean, no secrets or generated artifacts are included, and the branch is pushed for review rather than merged directly into `main` without explicit authorization.
