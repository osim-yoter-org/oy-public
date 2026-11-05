#!/usr/bin/env bash
# Runs in .github/workflows/short-link-request.yml only when an earlier step failed:
# comments the reason from run_request.sh (or a generic one) and the run link on the issue.
# Env: ISSUE_NUMBER, RUNNER_TEMP, GH_TOKEN, GITHUB_SERVER_URL, GITHUB_REPOSITORY, GITHUB_RUN_ID.
set -euo pipefail

reason=$(cat "$RUNNER_TEMP/failure-reason.txt" 2> /dev/null || true)
run_url="$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID"
comment_file="$RUNNER_TEMP/failure-comment.md"
{
  echo "הבקשה לא עברה:"
  echo
  echo '```text'
  printf '%s\n' "${reason:-unexpected error, see the run log}"
  echo '```'
  echo
  echo "פרטים: $run_url"
  echo "לתיקון: לערוך את הבקשה (Edit) והבדיקה רצה שוב."
} > "$comment_file"
gh issue comment "$ISSUE_NUMBER" --body-file "$comment_file"
