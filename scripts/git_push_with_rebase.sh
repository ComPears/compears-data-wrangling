#!/usr/bin/env bash
# Commit and push scraper output with pull --rebase retries to survive parallel matrix jobs.
set -euo pipefail

MESSAGE="${1:?commit message required}"
shift

if [[ "$#" -lt 1 ]]; then
  echo "Usage: $0 <commit-message> <path> [path...]" >&2
  exit 2
fi

git config user.name "${GIT_USERNAME:-GitHub Actions Bot}"
git config user.email "${GIT_EMAIL:-actions@github.com}"

git add "$@"
if git diff --cached --quiet; then
  echo "No changes to commit"
  exit 0
fi

git commit -m "$MESSAGE"

attempts=8
delay=3
for ((i = 1; i <= attempts; i++)); do
  if git pull --rebase --autostash origin main && git push origin HEAD:main; then
    echo "Pushed successfully on attempt ${i}"
    exit 0
  fi
  echo "Push attempt ${i}/${attempts} failed; retrying in ${delay}s…"
  sleep "$delay"
  delay=$((delay * 2))
  if (( delay > 60 )); then
    delay=60
  fi
done

echo "Failed to push after ${attempts} attempts" >&2
exit 1
