#!/usr/bin/env bash
# Rotate the judge or admin token (ADR 0016, 0017): a new random token, kept in ~/.config/frameteller/, set as the
# GitHub environment secret, then the matching deploy, which hands it to the Container App.
#
#   backend/scripts/rotate_token.sh judge production
#   backend/scripts/rotate_token.sh admin staging
#
# Every pass or admin tab using the old token stops working once the deploy is live. The old token is kept beside
# the new one as <kind>-<env>.token.old. The token is never printed: it goes from the file to `gh` on stdin.
# Production deploys the latest release (a tag), never main, and waits for approval in the GitHub environment.
set -euo pipefail

REPO="${FRAMETELLER_REPO:-njugTumz/frameteller}"
DIR="${HOME}/.config/frameteller"

usage() {
  echo "usage: $0 <judge|admin> <staging|production>" >&2
  exit 2
}

[[ $# -eq 2 ]] || usage
kind="$1"
env="$2"
case "$kind" in
  judge) secret=JUDGE_TOKEN ;;
  admin) secret=ADMIN_TOKEN ;;
  *) usage ;;
esac
case "$env" in
  staging) workflow=deploy-staging.yml ;;
  production) workflow=deploy-production.yml ;;
  *) usage ;;
esac

command -v gh >/dev/null || { echo "gh (the GitHub CLI) is not installed." >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 is needed to make the token." >&2; exit 1; }

umask 077
mkdir -p "$DIR"
file="$DIR/$kind-$env.token"
if [[ -f "$file" ]]; then
  mv -f "$file" "$file.old"
  echo "Kept the old token as $file.old"
fi
python3 -c 'import secrets, sys; sys.stdout.write(secrets.token_urlsafe(32))' > "$file"
echo "Wrote a new token to $file"

gh secret set "$secret" --env "$env" -R "$REPO" < "$file"
echo "Set $secret in the $env environment of $REPO"

if [[ "$env" == production ]]; then
  tag="$(gh release view -R "$REPO" --json tagName --jq .tagName)"
  gh workflow run "$workflow" -R "$REPO" --ref "$tag"
  echo "Started $workflow on $tag: approve it in the production environment, then the new token is live."
else
  gh workflow run "$workflow" -R "$REPO" --ref main
  echo "Started $workflow on main: the new token is live once it finishes."
fi
if [[ "$kind" == judge ]]; then
  echo "Send judges the new link privately: https://app.frameteller.com/judge# followed by the file's contents (staging: the staging studio's /judge#)."
else
  echo "Open the admin page with the new link: /admin# followed by the file's contents."
fi
