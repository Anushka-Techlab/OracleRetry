#!/usr/bin/env bash
set -euo pipefail

marker="<!-- orecle-retry:${JOB_MARKER} -->"
# Page through closed issues too. A closed notification still counts.
existing=$(gh api --paginate "repos/${GITHUB_REPOSITORY}/issues?state=all&per_page=100" |
  jq -r --arg marker "$marker" '.[] | select(.user.login == "github-actions[bot]" and ((.body // "") | contains($marker))) | .number')
if [[ -n "$existing" ]]; then
  echo "Success notification already exists."
  exit 0
fi

# An organization cannot be assigned or mentioned, so notify a user account.
# Set the NOTIFY_USER repository variable when the owner is an organization.
user="${NOTIFY_USER:-$GITHUB_REPOSITORY_OWNER}"
run_url="${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}"
gh issue create --repo "$GITHUB_REPOSITORY" --title 'OCI instance created' \
  --assignee "$user" \
  --body "@${user} The Oracle Resource Manager stack apply succeeded. [View the workflow run](${run_url}).

${marker}"
