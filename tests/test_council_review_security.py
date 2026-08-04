"""Tests for council review security gate logic.

Mirrors workflow bash logic as Python functions and tests them with pytest,
following the established pattern from TestWorkflowInputValidation in
test_crapload_package_resolution.py.

Refs: #429 (security hardening for council review workflows)
"""

import pytest


class TestCouncilReviewGateLogic:
    """Tests for the gate-check job logic in ci_council_review_collect.yml."""

    @staticmethod
    def _check_gate(pr_draft, pr_author):
        """Mirror: ci_council_review_collect.yml "Evaluate gate conditions" step.

        Returns True if the PR should proceed to org membership check,
        False if it should be skipped.
        """
        if pr_draft:
            return False
        if pr_author == "dependabot[bot]":
            return False
        return True

    def test_draft_pr_skipped(self):
        assert self._check_gate(pr_draft=True, pr_author="someone") is False

    def test_dependabot_pr_skipped(self):
        assert self._check_gate(pr_draft=False, pr_author="dependabot[bot]") is False

    def test_normal_pr_proceeds(self):
        assert self._check_gate(pr_draft=False, pr_author="orgmember") is True

    def test_draft_dependabot_pr_skipped(self):
        """Draft check takes precedence over dependabot check."""
        assert self._check_gate(pr_draft=True, pr_author="dependabot[bot]") is False

    def test_renovate_bot_not_skipped(self):
        """Only dependabot[bot] is explicitly skipped, not other bots."""
        assert self._check_gate(pr_draft=False, pr_author="renovate[bot]") is True


class TestOrgMembershipCheck:
    """Tests for the org membership verification in ci_council_review_collect.yml."""

    @staticmethod
    def _check_org_membership(http_status):
        """Mirror: ci_council_review_collect.yml "Verify org membership" step.

        Returns True if the commenter is an org member (HTTP 204),
        False otherwise.
        """
        return http_status == 204

    def test_member_returns_204(self):
        assert self._check_org_membership(204) is True

    def test_non_member_returns_302(self):
        """Public membership check returns 302 for non-members."""
        assert self._check_org_membership(302) is False

    def test_non_member_returns_404(self):
        """Private membership returns 404 when using GITHUB_TOKEN."""
        assert self._check_org_membership(404) is False

    def test_forbidden_returns_403(self):
        assert self._check_org_membership(403) is False

    def test_server_error_returns_500(self):
        assert self._check_org_membership(500) is False

    def test_zero_status_rejected(self):
        assert self._check_org_membership(0) is False

    def test_200_not_member(self):
        """200 is not the membership confirmation code — only 204 is."""
        assert self._check_org_membership(200) is False


class TestCooldownCalculation:
    """Tests for the cooldown logic in reusable_council_review.yml."""

    @staticmethod
    def _check_cooldown(last_review_epoch, now_epoch, cooldown_seconds=300):
        """Mirror: reusable_council_review.yml "Check cooldown" step.

        Returns True if the review should proceed (cooldown elapsed or
        no previous review), False if cooldown is active.

        A last_review_epoch of 0 means no previous review was found or
        the timestamp could not be parsed.
        """
        if last_review_epoch == 0:
            return True
        elapsed = now_epoch - last_review_epoch
        return elapsed >= cooldown_seconds

    def test_no_previous_review(self):
        """No previous review found — proceed."""
        assert self._check_cooldown(0, 1000000) is True

    def test_cooldown_active(self):
        """Review within cooldown window — block."""
        now = 1000300
        last = 1000100  # 200s ago, less than 300s cooldown
        assert self._check_cooldown(last, now) is False

    def test_cooldown_elapsed(self):
        """Review outside cooldown window — proceed."""
        now = 1000600
        last = 1000000  # 600s ago, more than 300s cooldown
        assert self._check_cooldown(last, now) is True

    def test_cooldown_exact_boundary(self):
        """Review exactly at cooldown boundary (300s) — proceed."""
        now = 1000300
        last = 1000000  # exactly 300s ago
        assert self._check_cooldown(last, now) is True

    def test_cooldown_one_second_before_boundary(self):
        """Review 1 second before cooldown expires — block."""
        now = 1000299
        last = 1000000  # 299s ago
        assert self._check_cooldown(last, now) is False

    def test_custom_cooldown_period(self):
        """Custom cooldown period of 60s."""
        now = 1000061
        last = 1000000  # 61s ago, cooldown is 60s
        assert self._check_cooldown(last, now, cooldown_seconds=60) is True

    def test_custom_cooldown_period_blocked(self):
        """Custom cooldown period of 600s — still within window."""
        now = 1000500
        last = 1000000  # 500s ago, cooldown is 600s
        assert self._check_cooldown(last, now, cooldown_seconds=600) is False


class TestCommentTriggerFilter:
    """Tests for the /council-review comment trigger filter."""

    @staticmethod
    def _is_council_review_command(comment_body):
        """Mirror: ci_council_review_collect.yml job-level if condition.

        The workflow uses startsWith(github.event.comment.body, '/council-review').
        """
        return comment_body.startswith("/council-review")

    def test_exact_command(self):
        assert self._is_council_review_command("/council-review") is True

    def test_command_with_trailing_text(self):
        assert self._is_council_review_command("/council-review please") is True

    def test_command_with_newline(self):
        assert self._is_council_review_command("/council-review\nsome context") is True

    def test_not_a_command(self):
        assert self._is_council_review_command("please run /council-review") is False

    def test_empty_comment(self):
        assert self._is_council_review_command("") is False

    def test_similar_but_wrong_command(self):
        assert self._is_council_review_command("/council-reviews") is True  # startsWith matches prefix

    def test_case_sensitive(self):
        """GitHub Actions startsWith is case-insensitive, but our mirror is case-sensitive.
        This test documents the Python behavior. In production, GitHub Actions
        would match '/Council-Review' too."""
        assert self._is_council_review_command("/Council-Review") is False


class TestPRStateGate:
    """Tests for the PR state check in ci_council_review_collect.yml."""

    @staticmethod
    def _check_pr_state(pr_state):
        """Mirror: ci_council_review_collect.yml "Evaluate gate conditions" step.

        Returns True only if the PR is open.
        """
        return pr_state == "open"

    def test_open_pr_proceeds(self):
        assert self._check_pr_state("open") is True

    def test_closed_pr_skipped(self):
        assert self._check_pr_state("closed") is False

    def test_merged_pr_skipped(self):
        """GitHub API returns 'closed' for merged PRs, not 'merged'."""
        assert self._check_pr_state("closed") is False

    def test_empty_state_skipped(self):
        assert self._check_pr_state("") is False


class TestOrgCheckTokenErrorHandling:
    """Tests for ORG_CHECK_TOKEN error code handling."""

    @staticmethod
    def _is_token_error(http_status):
        """Mirror: ci_council_review_collect.yml token error check.

        Returns True if the HTTP status indicates a token configuration
        problem (401/403) rather than a membership check result.
        """
        return http_status in (401, 403)

    def test_401_is_token_error(self):
        assert self._is_token_error(401) is True

    def test_403_is_token_error(self):
        assert self._is_token_error(403) is True

    def test_404_is_not_token_error(self):
        """404 is a valid non-member response, not a token error."""
        assert self._is_token_error(404) is False

    def test_204_is_not_token_error(self):
        assert self._is_token_error(204) is False

    def test_302_is_not_token_error(self):
        assert self._is_token_error(302) is False


class TestCooldownFilterLogic:
    """Tests that the cooldown filter distinguishes review comments from notices.

    The cooldown check must only count actual review summary comments (containing
    '## AI Council Review'), not cooldown notices or non-member notices. Otherwise
    the cooldown timer resets on every notice, creating an infinite loop.
    """

    SENTINEL = "<!-- council-review-bot -->"
    REVIEW_MARKER = "## AI Council Review"

    @staticmethod
    def _is_review_comment(body):
        """Mirror: reusable_council_review.yml cooldown jq filter.

        Returns True if the comment is an actual review (not a notice).
        """
        return ("<!-- council-review-bot -->" in body
                and "## AI Council Review" in body)

    def test_review_summary_matches(self):
        body = "<!-- council-review-bot -->\n## AI Council Review\n\nFindings..."
        assert self._is_review_comment(body) is True

    def test_cooldown_notice_excluded(self):
        body = ("<!-- council-review-bot -->\n"
                "> Council review cooldown active")
        assert self._is_review_comment(body) is False

    def test_non_member_notice_excluded(self):
        body = ("<!-- council-review-bot -->\n"
                "> `/council-review` is available to org members.")
        assert self._is_review_comment(body) is False

    def test_plain_comment_excluded(self):
        body = "LGTM, looks good to me!"
        assert self._is_review_comment(body) is False

    def test_sentinel_without_review_header_excluded(self):
        body = "<!-- council-review-bot -->\nSome other bot message"
        assert self._is_review_comment(body) is False

    def test_review_header_in_reusable_workflow(self):
        """The review summary step must include the review header marker."""
        with open(".github/workflows/reusable_council_review.yml") as f:
            content = f.read()
        assert self.REVIEW_MARKER in content, (
            "Review marker '## AI Council Review' not found in "
            "reusable_council_review.yml — cooldown filter will never match"
        )


class TestSentinelConsistency:
    """Tests that the bot comment sentinel is consistent across workflow files.

    The sentinel <!-- council-review-bot --> is used by:
    - ci_council_review_collect.yml (non-member notice reply)
    - reusable_council_review.yml (cooldown search, cleanup, review summary, inline comments)

    If the sentinel drifts between files, cooldown and cleanup will silently break.
    """

    SENTINEL = "<!-- council-review-bot -->"

    def test_sentinel_in_collect_workflow(self):
        """The collect workflow must include the sentinel in the non-member notice."""
        with open(".github/workflows/ci_council_review_collect.yml") as f:
            content = f.read()
        assert self.SENTINEL in content, (
            "Sentinel not found in ci_council_review_collect.yml — "
            "non-member notice reply won't be cleaned up by the reusable workflow"
        )

    def test_sentinel_in_reusable_workflow(self):
        """The reusable workflow must include the sentinel in multiple locations."""
        with open(".github/workflows/reusable_council_review.yml") as f:
            content = f.read()
        # Must appear in: cooldown search, cleanup selectors, review summary,
        # cooldown notice, inline comments
        occurrences = content.count(self.SENTINEL)
        assert occurrences >= 3, (
            f"Expected sentinel to appear at least 3 times in reusable_council_review.yml "
            f"(cooldown, cleanup, summary), found {occurrences}"
        )
