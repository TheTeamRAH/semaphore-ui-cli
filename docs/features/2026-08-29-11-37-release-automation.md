---
type: Feature Specification
title: Automate CI Versioning Tagging and Python Package Releases
description: Add a protected GitHub Actions release workflow that validates main, determines package versions, creates tags and releases, and publishes verified Python distributions without manual merge follow-up.
tags:
  - github-actions
  - ci
  - release-automation
  - python
  - uv
  - pypi
sources:
  - https://docs.github.com/en/actions/concepts/billing-and-usage
  - https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-pypi
  - https://docs.astral.sh/uv/guides/package/
status: proposed
---

# Automate CI Versioning Tagging and Python Package Releases

## Context

The package is now merged into `main`, but publishing each release tag manually is repetitive and creates opportunities for inconsistent versions, missed builds, or tags that do not correspond to validated artifacts. The repository is public, so standard GitHub-hosted runner usage is currently free; this makes GitHub Actions the simplest initial CI/release platform while a self-hosted runner would add operational maintenance.

The release process must be more than an unconditional tag-on-merge job. It needs a reviewable version policy, protected release permissions, reproducible package builds, duplicate-release safeguards, and a publish mechanism that does not require a long-lived package-index token where trusted publishing is available.

## Goal

Make a successful merge to `main` produce a predictable, validated, and auditable Python package release with minimal manual intervention, while retaining an explicit human approval boundary for the first production rollout and exceptional releases.

## Scope

### In scope

- A GitHub Actions CI workflow for pull requests and pushes to `main`.
- Automated validation with `uv run pytest`, `uv build`, and package/install smoke checks.
- A documented version-source and increment policy.
- Automated creation of a version tag using the selected policy.
- Creation of a GitHub Release with generated or maintained release notes.
- Publishing built distributions to the selected package index after validation.
- Least-privilege workflow permissions, protected environments, and concurrency controls.
- Duplicate-tag, duplicate-release, failed-build, and rerun behavior.
- Release auditability through workflow summaries, artifact retention, and tag/release links.
- Tests or dry-run validation for the versioning and release scripts where applicable.
- Documentation for maintainers covering setup, trusted publisher configuration, recovery, and manual release override.

### Out of scope

- Changing application or CLI functionality.
- Replacing the task-history discovery feature.
- Self-hosted runner provisioning or fleet management.
- Publishing private dependencies or container images.
- Automatically merging pull requests.
- Unreviewed production publishing from arbitrary branches, forks, or pull requests.
- Supporting multiple package indexes in the first implementation unless required by the selected distribution strategy.

## Requirements

1. Pull requests and pushes to `main` must run the same core quality gates before release logic can proceed.
2. Release jobs must run only from the protected default branch or an explicitly approved manual dispatch; pull requests and forks must never publish.
3. The version source must be single and authoritative, with a documented mapping from change type to version increment.
4. A release must build distributions once, validate them, and publish those exact artifacts rather than rebuilding an unverified second time.
5. Tags must use a documented format, such as `vMAJOR.MINOR.PATCH`, and must point to the validated `main` commit.
6. Re-running a workflow must not silently create a different version or overwrite an existing release.
7. Workflow permissions must default to read-only and grant write access only to the release job for the required contents/releases operation.
8. Package publishing must use trusted publishing/OIDC where supported; long-lived tokens must not be committed or exposed in logs.
9. The release workflow must use a protected environment or equivalent approval control for the first production rollout and any manually selected release.
10. CI and release workflows must use standard GitHub-hosted Ubuntu runners initially and document the current free-tier assumptions.
11. Release failures must leave an actionable state: failed validation must create no tag; failed publication must identify the existing tag/release and provide a safe retry or recovery path.
12. The repository must document how to preview, manually dispatch, recover, and roll back a release without deleting history casually.
13. Workflow changes must be testable with static YAML validation and local version/build checks; no live publication is required for unit tests.
14. Existing package commands and supported Python versions must remain compatible.

## Proposed workflow

```text
pull request -> CI: tests, build, install smoke test
merge to main -> CI: repeat quality gates
             -> release: calculate next version
             -> release: build and validate distributions
             -> release: create vX.Y.Z tag and GitHub Release
             -> publish: upload the validated artifacts using OIDC
```

The implementation may use Release Please, `python-semantic-release`, or a small repository-native script. The choice must be justified against the repository's version source, desired review flow, and operational complexity before implementation.

## Acceptance criteria

- [ ] Pull requests receive automated test/build feedback through GitHub Actions.
- [ ] A qualifying merge to `main` can produce exactly one predictable version tag and GitHub Release.
- [ ] The tag points to the validated commit and the release references the same version.
- [ ] The published package is built from the validated source and can be installed in an isolated uv tool environment.
- [ ] Version calculation is deterministic, documented, and tested for patch/minor/major cases.
- [ ] Duplicate runs and existing tags/releases are handled safely and tested.
- [ ] No release is published from a pull request, fork, or unapproved branch.
- [ ] Workflow permissions are least-privilege and reviewed explicitly.
- [ ] Trusted publishing or an equivalently safe short-lived credential path is configured without exposing secrets.
- [ ] Failure and recovery behavior is documented and exercised in a dry run.
- [ ] CI remains within the chosen GitHub Actions runner/storage budget under normal development volume.
- [ ] `uv run pytest`, `uv build`, package smoke checks, YAML validation, and `git diff --check` pass.

## Implementation notes

- First inspect the current version metadata and whether the package is intended for PyPI, GitHub Packages, or another index.
- Compare Release Please and `python-semantic-release` with a minimal custom workflow; avoid adding a bot whose policy is less transparent than the repository needs.
- Prefer a release PR or explicit release command if direct tag-on-merge would make version review insufficient. The final choice belongs in an ADR or implementation amendment.
- Pin third-party Actions to reviewed major versions or immutable commits according to repository policy.
- Set workflow-level `permissions: contents: read`, then grant the release job only the write permissions it actually needs.
- Use `id-token: write` only on the package-publish job when using PyPI trusted publishing.
- Keep build artifacts between build and publish jobs using the supported artifact mechanism, with retention limits.
- Add concurrency protection so two release runs cannot calculate and publish the same version simultaneously.

## Risks and compatibility

- Incorrect version policy can create skipped versions or incompatible package metadata.
- A workflow with contents write permission can modify tags/releases and therefore requires careful review and branch protection.
- Package publishing is difficult to undo; yanking or deprecating a release is preferable to rewriting tags or deleting history.
- Third-party Action compromise or mutable tags can affect the supply chain; pinning and minimal permissions reduce this risk.
- Free-tier limits may change; the workflow should remain efficient and report usage rather than assuming unlimited private-runner minutes.

## Validation plan

1. Inspect current version metadata, package build output, repository visibility, and existing tags/releases.
2. Compare candidate versioning tools and document the recommendation before implementation.
3. Add static workflow validation and failing tests for version calculation and duplicate-release handling.
4. Implement CI first and verify it on a pull request without release permissions.
5. Implement release/tag creation behind a dry-run or protected environment.
6. Build once, inspect the distributions, and verify package installation from the retained artifacts.
7. Exercise rerun, duplicate, validation failure, and publication failure paths without publishing a second package.
8. Configure trusted publishing only after workflow identity and permissions are reviewed.
9. Run the full local checks and review workflow permissions, action pins, logs, and documentation.

## Open questions

- Should version increments be driven by Conventional Commits, a reviewed release PR, or manual dispatch input?
- Is PyPI the target index, or should the first release target GitHub Packages/private distribution?
- Should every merge to `main` release, or should releases be created only when a release PR is merged?
- Should the first implementation use Release Please, `python-semantic-release`, or a minimal custom workflow?
- Which GitHub environment and approver policy should protect production publishing?

## Amendments

None.
