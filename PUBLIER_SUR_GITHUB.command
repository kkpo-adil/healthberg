#!/bin/bash
# Publish a committed review branch. Never rename, force-push or write main.
set -Eeuo pipefail
cd "$(dirname "$0")"
EXPECTED_REMOTE='https://github.com/kkpo-adil/healthberg.git'
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo 'Ce script doit être lancé depuis un clone Git du dépôt.'; exit 2; }
BRANCH="$(git branch --show-current)"
[[ -n "$BRANCH" && "$BRANCH" != main && "$BRANCH" != master ]] || { echo 'Publication réservée à une branche de travail, pas à main.'; exit 2; }
[[ -z "$(git status --porcelain)" ]] || { echo 'Des modifications ne sont pas commitées. Vérifiez-les avant publication.'; exit 2; }
REMOTE="$(git remote get-url origin)"
[[ "$REMOTE" == "$EXPECTED_REMOTE" || "$REMOTE" == 'git@github.com:kkpo-adil/healthberg.git' ]] || { echo 'Dépôt distant différent de kkpo-adil/healthberg : arrêt.'; exit 2; }
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push -u origin "$BRANCH"
else
  git push -u origin "$BRANCH"
fi
printf '\nBranche publiée. Tests : https://github.com/kkpo-adil/healthberg/actions\n'
