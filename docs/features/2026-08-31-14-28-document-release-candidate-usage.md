---
type: Feature Specification
title: Document v0.2.0 Release Candidate CLI Usage
description: Add verified README examples for version reporting and checking an existing Semaphore UI task.
tags:
  - documentation
  - release-candidate
  - cli
status: completed
sources:
  - README.md
  - pyproject.toml
  - src/semaphore_ui/cli.py
  - tests/test_version.py
  - AGENTS.md
---

# Document v0.2.0 Release Candidate CLI Usage

## Context

The v0.2.0 release candidate needs two concise, copyable CLI examples in the root README: version reporting and task-status retrieval. The package metadata declares version `0.2.0`; the CLI registers `semaphore-ui` as its executable and formats `--version` as `semaphore-ui <version>`.[^pyproject][^cli][^version-test]

## Goal

Make the README accurately demonstrate the v0.2.0 version output and the required syntax for checking a named project's task.

## Scope

### In scope

- Add a `semaphore-ui --version` command example and its expected output, exactly `semaphore-ui 0.2.0`.
- Add a `semaphore-ui status --project NAME --task ID` command example.
- Update `AGENTS.md` release-closeout validation guidance to require review of release-facing README and documentation version references.
- Retain existing README content unless the added examples need a minimal surrounding label or placement adjustment for clarity.
- Run the requested validation commands after the approved documentation change: `uv run pytest` and `uv build`.

### Out of scope

- Changing the CLI's version implementation, package version, command behavior, or tests.
- Adding live Semaphore credentials, endpoints, task data, or a real task-status output example.
- Publishing, tagging, pushing, or creating a hosted release or pull request.

## Requirements

1. The version example must use the installed command name `semaphore-ui` and show the precise expected output `semaphore-ui 0.2.0`.
2. The task-check example must be exactly `semaphore-ui status --project NAME --task ID`, using neutral placeholders rather than user-specific values.
3. The examples must be consistent with the existing `argparse` interface: `--version` is a top-level option; `status` requires `--project` and an integer `--task`.[^cli]
4. Do not modify implementation or tests unless the documentation review identifies a contradiction with the checked source and test evidence. The review has identified none.[^pyproject][^cli][^version-test]
5. Preserve non-generated README content and do not include secrets or build artifacts.[^agents]
6. Add the following narrow rule to the release-closeout validation guidance: “Review README.md and release-facing documentation for version-specific references. Update them when they state, display, or otherwise depend on the released version; do not add or change version references that are not already release-facing.”

## Acceptance Criteria

- `README.md` contains a fenced shell example for `semaphore-ui --version` followed by the expected output `semaphore-ui 0.2.0`.
- `README.md` contains a fenced shell example for `semaphore-ui status --project NAME --task ID`.
- The README examples agree with `pyproject.toml`, `src/semaphore_ui/cli.py`, and `tests/test_version.py`.
- `AGENTS.md` explicitly requires the targeted review of release-facing version references during release closeout.
- `uv run pytest` succeeds.
- `uv build` succeeds; generated build outputs are not included in the final change.
- `git diff --check` succeeds.

## Constraints

- This is documentation-only work, so its release-closeout decision is `no-release`; the request documents an existing release candidate and does not change supported behavior.[^agents]
- Implementation starts only after the user reviews and approves this specification.[^agents]
- Before implementation, create a branch from up-to-date local `main` named `feature/document-release-candidate-usage`, then update the README's recent-features table and the exhaustive feature index as required by `AGENTS.md`.[^agents]

## Implementation Notes

- Place the two additions in the existing `## Getting Started` / `### Examples` area, where task lifecycle examples already appear.
- Use a command fence plus a separate output indication for the version example so the expected output is unambiguous.
- README table/index maintenance is required by the repository workflow upon implementation; obtain the feature author from Git metadata and use the full timestamp prefix from this specification filename.
- Place the new `AGENTS.md` rule in the existing release-closeout validation-and-evidence guidance without changing the declared release decision, authoritative artifacts, command procedure, or external-operation boundaries.

## Risks

- Documentation could drift from the implementation if the CLI's package version or argument parser differs. This is mitigated by checking the authoritative package metadata, parser registration, and version test before editing.[^pyproject][^cli][^version-test]
- `uv build` creates validation-only artifacts. They must be excluded from the final diff.[^agents]

## Validation

Run from the repository root after implementation:

```bash
uv run pytest
uv build
git diff --check
```

Confirm the displayed `--version` output remains exactly `semaphore-ui 0.2.0` and that the status command's arguments exactly match the parser.

## Release Closeout

- **Status:** `no-release` (passed).
- **Decision and classification:** The change documents existing CLI behavior and adds release-documentation review guidance; it does not change supported behavior, the public interface, compatibility, or architecture. SemVer classification is not applicable.
- **Version evidence:** The authoritative `[project].version` in `pyproject.toml` was `0.2.0` before and after closeout. The editable `semaphore-ui` record in `uv.lock` remains `0.2.0`. No version-bearing artifact changed.
- **Synchronization:** Local `main` was already up to date with the feature branch (`git merge --no-edit main` returned `Already up to date`), and `main` is an ancestor of `HEAD`.
- **Commands and outcomes:** `uv lock --check` passed; `uv run pytest` passed with 23 tests; `uv build` passed and produced validation-only distributions; `git diff --check` and `git diff --cached --check` passed. `uv` used the temporary cache `/tmp/semaphore-ui-cli-uv-cache` because the default cache path is read-only in this environment.
- **Review:** The README version output matches `pyproject.toml`, the CLI parser, and `tests/test_version.py`. The change is documentation-only; no dependency, security-sensitive source, secret, or generated build artifact is included in the feature diff.

## Amendments

### 2026-08-31 — Release-facing version-reference guidance

The user requested that the specification include an `AGENTS.md` update ensuring release closeout keeps README and other release-facing documentation version references in sync. The settled rule is intentionally narrow: review and update only references that state, display, or depend on the released version; it does not require unrelated documentation changes or introduce a new authoritative version source.

[^agents]: [Repository development and release workflow](../../AGENTS.md)
[^pyproject]: [Project metadata](../../pyproject.toml)
[^cli]: [CLI parser and handlers](../../src/semaphore_ui/cli.py)
[^version-test]: [Version CLI test](../../tests/test_version.py)
