# Council Review — Operational Guide

<!-- Evidence test for #429 security hardening — verifies issue_comment trigger chain -->

AI-assisted PR review using OpenCode on Vertex AI with Divisor persona
discovery. Reviews are posted as inline comments on PR diff lines.
Invoked by posting `/council-review` as a PR comment. Only org members
can invoke.

## Architecture

```text
┌─────────────────────────────────────────────────────────┐
│  Downstream Repo (e.g., complytime, gaze)               │
│                                                         │
│  ci_council_review_collect.yml  (issue_comment trigger) │
│  ├── Gate: only PR comments starting with /council-review│
│  ├── Gate: skip drafts, dependabot PRs                  │
│  ├── Gate: verify commenter is org member (notice if not)│
│  ├── Capture diff: gh pr diff → pr-diff.patch           │
│  ├── Build metadata: pr-meta.json                       │
│  └── Upload artifact: council-review-diff               │
│                                                         │
│  ci_council_review.yml  (workflow_run / workflow_dispatch)│
│  └── calls → reusable_council_review.yml (org-infra)    │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│  org-infra: reusable_council_review.yml                 │
│                                                         │
│  ├── Harden runner (egress blocked, allowlist only)     │
│  ├── Cooldown check (5-minute minimum between reviews)  │
│  ├── Download artifact (pr-diff.patch, pr-meta.json)    │
│  ├── WIF auth → Google Cloud (Vertex AI)                │
│  ├── council-review-action (SHA-pinned composite)       │
│  │   ├── Filter noise → pr-diff-filtered.patch          │
│  │   ├── Annotate lines → pr-diff-annotated.patch       │
│  │   ├── Pre-fetch PR context (CI, reviews, issues)     │
│  │   ├── Discover Divisor personas                      │
│  │   ├── Build prompt + opencode run                    │
│  │   └── Parse + validate → review_output.json          │
│  ├── Clean up previous bot comments                     │
│  ├── Post review summary (issue comment)                │
│  └── Post inline comments (PR review comments)          │
└─────────────────────────────────────────────────────────┘
```

## Workflow files

| File | Synced? | Trigger | Purpose |
|------|---------|---------|---------|
| `ci_council_review_collect.yml` | Yes | `issue_comment` | Comment-triggered diff collection (`/council-review`) |
| `ci_council_review.yml` | Yes | `workflow_run` / `workflow_dispatch` | Thin consumer, passes secrets to the reusable |
| `reusable_council_review.yml` | **No** | `workflow_call` | Core logic: egress blocking, cooldown, WIF auth, action invocation, comment posting |

Consumer workflows have `DO NOT EDIT` provenance headers indicating they
are managed by org-infra. Downstream repos should not modify them directly.

## Required secrets

| Secret | Required | Scope | Purpose |
|--------|----------|-------|---------|
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Yes | Org-level | WIF provider for Vertex AI authentication |
| `GCP_PROJECT_ID` | Yes | Org-level | GCP project containing Vertex AI |
| `ORG_CHECK_TOKEN` | No | Org-level | PAT with `org:read` for private org membership checks |

If `GCP_WORKLOAD_IDENTITY_PROVIDER` is not set, the review is skipped with a
`::notice::` annotation. No tokens are consumed.

If `ORG_CHECK_TOKEN` is not set, the collect workflow falls back to
`GITHUB_TOKEN` which can only check **public** org membership. Private org
members (the GitHub default) will be treated as non-members and skipped.

## Invocation

Post `/council-review` as a comment on a PR to trigger a review.

## Gate conditions

The collect workflow skips council review when:

- The comment does not start with `/council-review`
- The comment is on an issue (not a PR)
- PR is a draft
- PR author is `dependabot[bot]`
- The **commenter** is not a member of the repository's org (a notice
  reply is posted so the commenter knows why it was ignored)

## Composite action

The review logic lives in
[`unbound-force/unbound-force/council-review-action/`](https://github.com/unbound-force/unbound-force/tree/main/council-review-action).
It is pinned by full SHA in `reusable_council_review.yml`.

The action:

1. Installs `opencode-ai@1.2.26` via npm
2. Filters noise files from the diff (lock files, vendor, generated code)
3. Annotates the diff with `[L<N>]` source-file line numbers
4. Pre-fetches PR context (CI status, existing reviews, linked issues)
5. Discovers Divisor personas from `.opencode/agents/divisor-*.md`
6. Builds a constrained review prompt with injection defense
7. Runs `opencode run` on Vertex AI
8. Parses structured JSON output and validates line numbers against the diff

## Rollout

Rollout is staged via `sync-config.yml` `exclude_repos`:

1. **Current**: Only org-infra receives the consumer workflows. Reviews
   are comment-triggered (`/council-review`) only — no automatic runs.
2. **Phase 2**: Remove repos from `exclude_repos` after:
   - Composite action SHA points to a merged `main` commit
   - Security hardening (#429) is in place
   - Token consumption controls (#430) are in place
   - End-to-end chain validated on org-infra
3. **Future graduation**: Once battle-tested, consider re-adding an
   automatic `pull_request` trigger alongside the comment command (#429).

## Manual trigger

The standard way to trigger a review is to post `/council-review` as a PR
comment. The collect workflow runs automatically and the consumer workflow
picks up the artifact via `workflow_run`.

To manually trigger via `workflow_dispatch` (e.g., for debugging):

1. Find the collect workflow run ID from Actions → "Council Review - Collect"
2. Go to Actions → "Council Review" → "Run workflow"
3. Enter the collect run ID

Or via CLI:

```bash
gh workflow run ci_council_review.yml \
  --repo complytime/org-infra \
  --ref <branch> \
  -f triggering_run_id=<collect-run-id>
```

## Security controls

### Network egress blocking

The reusable workflow uses `step-security/harden-runner` with
`egress-policy: block`. Only the following endpoints are allowed:

- GitHub API and CDN (`api.github.com`, `github.com`, etc.)
- Vertex AI (`global-aiplatform.googleapis.com`, regional endpoints)
- GCP auth (`oauth2.googleapis.com`, `iamcredentials.googleapis.com`, etc.)
- npm registry (`registry.npmjs.org`, `nodejs.org`)
- StepSecurity agent (`agent.api.stepsecurity.io`)

To add a new endpoint, update the `allowed-endpoints` list in
`reusable_council_review.yml`.

### Cooldown

A 5-minute (300s) cooldown is enforced between reviews per PR. The
cooldown checks the timestamp of the most recent `<!-- council-review-bot -->`
comment on the PR. If the cooldown is active, the review is skipped and a
notice comment is posted on the PR.

### CODEOWNERS

Council review workflow files require review from `@complytime/complytime-dev`
via CODEOWNERS. This ensures human review of security-sensitive changes.

## Bot comment lifecycle

All bot comments are tagged with `<!-- council-review-bot -->`.

On each new review:
1. Previous issue comments (summary) are **deleted**
2. Previous PR review comments (inline) are **deleted**
3. Previous Reviews API objects are **minimized** (collapsed as "outdated")
4. New summary and inline comments are posted

## Troubleshooting

### Review skipped — "No WIF credentials"

The `GCP_WORKLOAD_IDENTITY_PROVIDER` secret is not configured for this repo.
Set it at the org level or add a repo-level secret.

### Review skipped — "commenter is not a member"

Either the commenter is not an org member, or `ORG_CHECK_TOKEN` is not set
and the commenter's membership is private. A notice reply is posted on the
PR. Configure `ORG_CHECK_TOKEN` with a PAT that has `org:read` scope to
support private membership checks.

### Review skipped — "cooldown active"

A council review was posted on this PR within the last 5 minutes. Wait for
the cooldown to elapse and invoke `/council-review` again. The cooldown
prevents token exhaustion from rapid re-invocations.

### Review produced no inline comments

The model may have returned a summary-only review, or the diff was too small
to warrant inline findings. Check the review summary comment on the PR.

### Inline comments on wrong lines

The `[L<N>]` annotation in the diff helps the model identify correct line
numbers. If comments land on wrong lines, check:
- `filter-diff-lines.py` validation logic in the composite action
- Whether the diff has since been invalidated by new commits

### Credentials error — "Could not load the default credentials"

The WIF authentication succeeded but the credentials were not passed to
OpenCode. Check that `GOOGLE_APPLICATION_CREDENTIALS` is set in the
environment when `opencode run` executes.

## Related issues

- Security hardening: [#429](https://github.com/complytime/org-infra/issues/429)
- Token consumption controls: [#430](https://github.com/complytime/org-infra/issues/430)
- `continue-on-error` removal: [#440](https://github.com/complytime/org-infra/issues/440)
- Error handling hardening: [#454](https://github.com/complytime/org-infra/issues/454)
- Composite action tracking: [unbound-force#253](https://github.com/unbound-force/unbound-force/issues/253)
