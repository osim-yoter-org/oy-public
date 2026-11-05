#!/usr/bin/env bash
# One run of .github/workflows/short-link-request.yml, on a fresh checkout of main.
# Env: ISSUE_NUMBER, ISSUE_BODY (issue text, used only as data), RUNNER_TEMP, GH_TOKEN,
#      GITHUB_SERVER_URL, GITHUB_REPOSITORY, GITHUB_RUN_ID.
# Each issue has its own branch short-link/issue-<n> and at most one open PR, so an edited issue
# updates its branch and PR, and a branch left without a PR gets one on the next run.
# On failure the reason goes to $RUNNER_TEMP/failure-reason.txt for comment_failure.sh.
set -euo pipefail

reason_file="$RUNNER_TEMP/failure-reason.txt"
fail() {
  printf '%s\n' "$1" > "$reason_file"
  exit 1
}

result=$(python3 scripts/short_link_request.py links.json) || fail "$result"
slug=${result#slug=}
branch="short-link/issue-$ISSUE_NUMBER"
title="Add short link /$slug"
run_url="$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID"

# Only PRs whose head branch lives in this repository count: a fork PR can reuse any branch name or title.
# Both lookups page through every open PR (100 per page), so nothing is cut off.
pulls_api="repos/$GITHUB_REPOSITORY/pulls?state=open&per_page=100"
own_pulls="$RUNNER_TEMP/own-pulls.json"
open_pulls="$RUNNER_TEMP/open-pulls.json"
gh api --paginate --slurp "$pulls_api&head=${GITHUB_REPOSITORY%%/*}:$branch" > "$own_pulls" \
  || fail "could not look up the pull request of $branch"
gh api --paginate --slurp "$pulls_api" > "$open_pulls" || fail "could not list the open pull requests"
pr_refs=$(OWN_PULLS="$own_pulls" OPEN_PULLS="$open_pulls" BRANCH="$branch" TITLE="$title" python3 -c '
import json, os
repo, branch, title = os.environ["GITHUB_REPOSITORY"], os.environ["BRANCH"], os.environ["TITLE"]
def same_repo_pulls(path):
    with open(path, encoding="utf-8") as pages:
        return [p for page in json.load(pages) for p in page if (p["head"]["repo"] or {}).get("full_name") == repo]
own = next((p["html_url"] for p in same_repo_pulls(os.environ["OWN_PULLS"]) if p["head"]["ref"] == branch), "-")
other = next((p["html_url"] for p in same_repo_pulls(os.environ["OPEN_PULLS"]) if p["title"] == title and p["head"]["ref"] != branch), "-")
print(own, other)') || fail "could not read the open pull requests"
read -r own_pr other_pr <<< "$pr_refs"
if [ "$other_pr" != "-" ]; then
  fail "/$slug is already requested in $other_pr"
fi

# PRs opened with the workflow token do not run validate.yml until someone with write access selects
# "Approve workflows to run", so this run of the same validator is checked before anything is pushed.
validation=$(python3 scripts/validate_links.py) || fail "validator failed on the request branch: $validation"

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git switch -q -c "$branch"
git add links.json
git commit -q -m "$title" -m "Closes #$ISSUE_NUMBER"

remote_sha=$(git ls-remote --heads origin "refs/heads/$branch" | cut -f1) || fail "could not read $branch from origin"
if [ -n "$remote_sha" ] && git fetch -q origin "refs/heads/$branch" && git diff --quiet FETCH_HEAD HEAD -- links.json; then
  echo "$branch already holds this links.json"
else
  # The branch belongs to this issue alone; the lease refuses the push if it moved since ls-remote.
  git push -q --force-with-lease="refs/heads/$branch:$remote_sha" origin "HEAD:refs/heads/$branch" \
    || fail "push to $branch was rejected (the branch changed during this run)"
fi

body_file="$RUNNER_TEMP/pr-body.md"
{
  printf 'Closes #%s\n\nAdds /%s to links.json.\n\n' "$ISSUE_NUMBER" "$slug"
  printf 'Validation (scripts/validate_links.py on this branch, run %s):\n\n```text\n%s\n```\n\n' "$run_url" "$validation"
  printf 'This PR comes from the request workflow, so GitHub holds its Validate check until someone with write access selects "Approve workflows to run".\n'
} > "$body_file"

if [ "$own_pr" = "-" ]; then
  pr_url=$(gh pr create --base main --head "$branch" --title "$title" --body-file "$body_file") \
    || fail "could not open the pull request (is \"Allow GitHub Actions to create and approve pull requests\" on?)"
  done_word="נפתח"
else
  gh pr edit "$own_pr" --title "$title" --body-file "$body_file" || fail "could not update $own_pr"
  pr_url=$own_pr
  done_word="עודכן"
fi
gh issue comment "$ISSUE_NUMBER" --body "$done_word Pull Request: $pr_url - הקישור עולה לאוויר כ-5 דקות אחרי האישור."
