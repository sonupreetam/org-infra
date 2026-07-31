# Code Review Auto-Assignment

How GitHub auto-assignment is configured across ComplyTime teams
to distribute PR review workload fairly.

## Principles

- Auto-assignment is a **supporting tool** for fair workload distribution.
  It does not restrict who can review. Any maintainer or team member is
  free to review any PR at any time, regardless of whether the algorithm
  assigned them.
- The goal is to ensure no single person carries a disproportionate share
  of reviews while keeping the configuration simple to maintain.

## Algorithm Choice

GitHub offers two routing algorithms for auto-assignment: **Round Robin**
and **Load Balance**.

| Algorithm | Selection criteria | Awareness of pending reviews |
|---|---|---|
| Round Robin | Least recent review request | No |
| Load Balance | Total requests in a rolling 30-day window | Yes |

**Load Balance** is used for all teams because it accounts for each
member's outstanding review count, adapting to vacations, busy periods,
and varying review speeds. Round Robin only alternates by recency and does not account for
unfinished reviews, which can lead to uneven backlog accumulation.

For full details on algorithm behavior, see [References](#references).

## Current Configuration

Auto-assignment is enabled only on teams where it adds value. Teams
whose membership is fully covered by another auto-assigned team have
auto-assignment disabled to avoid redundant reviewer selection from
the same pool.

| Team | Auto-assignment | Algorithm | Reviewers | Count existing requests | Notify | Skipped members |
|---|---|---|---|---|---|---|
| `complytime-dev` | Enabled | Load Balance | 2 | Yes | -- | *(onboarding members)* |
| `complytime-approvers` | Enabled | Load Balance | 2 | Yes | -- | -- |
| `ampel-provider-approvers` | Disabled | -- | -- | -- | Requested only | -- |
| `openscap-provider-approvers` | Disabled | -- | -- | -- | Requested only | -- |
| `opa-provider-approvers` | Disabled | -- | -- | -- | Requested only | -- |

**Count existing requests** must be enabled on all auto-assigned teams.
Without it, a member who belongs to multiple requested teams can consume
a reviewer slot in each team independently, reducing the number of
distinct reviewers on a PR.

**Only notify requested team members** must be enabled on provider
teams (shown as "Requested only" above). Without auto-assignment,
CODEOWNERS requests trigger a team-level review request that notifies
all team members by default. Enabling this setting limits notifications
to members who are already individually requested (e.g., those assigned
by `complytime-dev` auto-assignment), preventing duplicate notifications
to the rest of the team.

## Why Provider Teams Don't Use Auto-Assignment

The three provider teams (`ampel-provider-approvers`,
`openscap-provider-approvers`, `opa-provider-approvers`) exist for
organizational identity and repository permissions, but their
auto-assignment is disabled because:

1. **Full membership overlap**: Every technical maintainer in the
   provider teams is also a member of `complytime-dev`.
2. **CODEOWNERS coverage**: All CODEOWNERS files include
   `complytime-dev`, so its auto-assignment already selects reviewers
   for provider paths.
3. **CODEOWNERS satisfaction**: Since any reviewer assigned by
   `complytime-dev` is also a member of the provider teams, their
   review satisfies the CODEOWNERS branch protection requirement for
   both teams simultaneously.
4. **No redundant slots**: Enabling auto-assignment on provider teams
   would draw from the same pool a second (or third) time, wasting
   reviewer slots without adding distinct reviewers.

Since auto-assignment is disabled on these teams, "Only notify
requested team members" must also be enabled to prevent all team
members from being notified on every CODEOWNERS-triggered request.
With this setting, only members already individually assigned (via
`complytime-dev` auto-assignment) receive notifications from the
provider team request.

If provider teams diverge in membership in the future (specialized
reviewers per provider), re-enabling auto-assignment on those teams
should be reassessed.

## CODEOWNERS Interaction

Branch protection rules require CODEOWNERS review. When a team listed
in CODEOWNERS has auto-assignment enabled:

1. GitHub requests the team as a reviewer.
2. Auto-assignment replaces the team with individual members.
3. However, branch protection prevents the team request from being
   removed until a team member approves.
4. Once an assigned individual (who is a member of the team) approves,
   the team request is satisfied and removed.

In practice, the PR shows both the team and the assigned individuals
until the review is completed.

## Onboarding New Members

When a new member joins a team with auto-assignment enabled:

1. **Add them to the skip list**: In the team's code review settings,
   add the member to "Never assign certain team members." This prevents
   the algorithm from overloading them with reviews before they are
   familiar with the codebase.
2. **Voluntary reviews still count**: While on the skip list, the
   member can still review any PR they feel comfortable with. Their
   approval satisfies CODEOWNERS branch protection as long as they are
   a member of the owning team.
3. **Remove from skip list when ready**: Once the member is ramped up,
   remove them from the skip list. Load Balance will gradually include
   them in assignments based on their review history.

## Reassessment Checklist

Revisit this configuration when:

- A new member is added to or removed from a team -- check
  [`peribolos.yaml`](https://github.com/complytime/.github/blob/main/peribolos.yaml)
  for membership overlap and overload risk.
- Provider teams diverge in membership from `complytime-dev` -- consider
  re-enabling auto-assignment on those teams.
- A new team with overlapping members is created -- evaluate whether
  auto-assignment is needed or redundant.
- The effective reviewer pool for any team drops below 4 -- the
  algorithm has limited room to distribute, increasing per-person load.
- Review workload feels uneven despite Load Balance -- verify that
  "Count existing requests" is enabled and check for members in many
  teams.
- Stale review alerts are firing frequently -- see
  [Stale Review Alerts](#stale-review-alerts) for threshold tuning.

## Stale Review Alerts

Even with Load Balance, a review request can silently stall if the assigned
reviewer is overloaded or unavailable. The **Stale Review Alerts** workflow
detects these cases and surfaces them.

### How It Works

A scheduled GitHub Actions workflow runs every weekday at 09:00 UTC. For each
open PR with pending review requests, it calculates how many **business days**
have elapsed since the review was requested (using timeline events to
determine the exact request date). If the threshold is exceeded:

1. A `stale-review` label is applied to the PR.
2. A comment is posted @-mentioning the assigned reviewer(s) with the
   number of business days each has been pending.

Draft PRs and PRs with an existing approval are skipped. To avoid spam,
a reminder is posted at most once every 3 days per PR.

### Implementation

The workflow uses `actions/github-script` (GitHub-maintained) with inline
logic. No third-party actions are involved. This eliminates supply chain
risk from dormant or single-maintainer community actions.

The business-day calculation excludes weekends (Saturday/Sunday). Holiday
awareness is not included — if needed in the future, a holiday calendar
can be added to the script.

### Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `stale-days` | 5 | Business days before flagging |
| `stale-label` | `stale-review` | Label applied to flagged PRs |

Additional behavior (hardcoded, changeable in the script):

- Draft PRs are skipped.
- PRs with at least 1 approval are skipped.
- Reminders are deduplicated (3-day cooldown per PR).
- The `stale-review` label is auto-removed when no pending reviewers remain.

### Workflow Files

| File | Purpose |
|------|---------|
| `.github/workflows/ci_stale_reviews.yml` | Per-repo scheduled caller |
| `.github/workflows/reusable_stale_reviews.yml` | Reusable workflow (org-infra) |

The caller workflow is synced to repositories via `sync-config.yml`. The
reusable workflow remains in org-infra and is referenced cross-repo.

### Rollout

The workflow is deployed in stages:

1. **Phase 1** -- org-infra only (current). Validates that the action fires
   correctly, labels are applied, and comments render properly.
2. **Phase 2** -- Remove repos from the `exclude_repos` list in
   `sync-config.yml` once Phase 1 is confirmed.

### Responding to Alerts

When a PR is flagged:

- **Reviewer available:** Complete the review or leave a status comment
  explaining when review will happen.
- **Reviewer unavailable:** Re-request review from another team member or
  use `/assign-reviewer` to trigger Load Balance rebalancing.
- **PR no longer relevant:** Close the PR or convert to draft.

The `stale-review` label is automatically removed the next time the workflow
runs if the PR has received a review or approval.

### Customization

To override the threshold for a specific repository, pass inputs to the
reusable workflow in the caller:

```yaml
jobs:
  call_reusable_stale_reviews:
    uses: ./.github/workflows/reusable_stale_reviews.yml
    with:
      stale-days: 3
```

### Fallback Plan

If `actions/github-script` introduces a breaking change or the inline
script needs replacement, the logic is self-contained and can be moved to:

1. A standalone script file (`.github/scripts/stale-reviews.mjs`) invoked
   via `node` in a run step.
2. A composite action in this repository (no external dependency).

Both options preserve zero third-party supply chain risk.

## References

- [Managing code review settings for your team](https://docs.github.com/en/organizations/organizing-members-into-teams/managing-code-review-settings-for-your-team) -- GitHub documentation covering auto-assignment configuration, routing algorithms, and team notification settings.
- [#478](https://github.com/complytime/org-infra/issues/478) -- Stale review request alerts task.
