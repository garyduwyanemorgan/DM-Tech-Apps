#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/release.sh — one-command release automation.
#
# Automates the whole flow:
#   1. generates a CHANGELOG section from commits since the last tag
#   2. bumps VERSION + frontend/package.json (SemVer)
#   3. commits, annotated-tags vX.Y.Z, and pushes with the tag
#
# Usage:
#   scripts/release.sh [patch|minor|major|auto]   # bump type (default: patch)
#   scripts/release.sh -v 1.0.0                    # explicit version
#   scripts/release.sh minor --dry-run             # preview, change nothing
#   scripts/release.sh patch --no-push             # commit + tag locally only
#   scripts/release.sh minor --verify              # poll the live app after push
#
# "auto" infers the bump from Conventional Commit prefixes since the last tag
# (feat!→major / feat→minor / else→patch; on 0.x, breaking→minor).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# Derived from the checkout, never hardcoded. This repo began as a copy of the
# DECCA/LOS build, and these two constants came with it — so every release from
# v1.6.0 onward wrote CHANGELOG compare links pointing at the frozen
# DECCA-Lagoons-App repo, and --verify would have polled that project's
# production host to decide whether THIS release had landed. Deriving the repo
# from `origin` means a future fork cannot inherit the wrong identity again.
REPO_URL="$(git remote get-url origin 2>/dev/null | sed -E 's/\.git$//; s#git@github\.com:#https://github.com/#')"

# The deployed host to poll when --verify is passed. REQUIRED, with no default.
# It briefly defaulted to https://app.gdm-enviro.com, inferred from
# CLERK_AUTHORIZED_PARTIES — that host has no DNS record at all, so the default
# was a guess that could never succeed. The inherited default before that was
# the OTHER project's production host, where a green verify would have been a
# different app answering. Both failure modes are silent, so there is no safe
# default: an unset value must stop the verify, not guess at one.
API_URL="${RELEASE_VERIFY_URL:-}"
# Render service to name in the rollback hint below. Inherited from the
# DECCA/LOS build as srv-d91t1ofavr4c73fv52d0 ("lagoon-saas") — a rollback
# command naming another project's service is worse than no hint at all,
# since it would be pasted during an incident. Set RENDER_SERVICE_ID for
# this app, or the hint says so instead of guessing.
RENDER_SERVICE="${RENDER_SERVICE_ID:-}"
cd "$(git rev-parse --show-toplevel)"

BUMP="patch"; EXPLICIT=""; DRYRUN=0; NOPUSH=0; VERIFY=0
while [ $# -gt 0 ]; do
  case "$1" in
    patch|minor|major|auto) BUMP="$1" ;;
    -v|--version)           EXPLICIT="${2:?--version needs a value}"; shift ;;
    --dry-run)              DRYRUN=1 ;;
    --no-push)              NOPUSH=1 ;;
    --verify)               VERIFY=1 ;;
    -h|--help)              sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "release.sh: unknown argument '$1'" >&2; exit 2 ;;
  esac; shift
done

# ── current version + last tag ───────────────────────────────────────────────
CUR="$(tr -d ' \r\n' < VERSION 2>/dev/null || echo 0.0.0)"
IFS=. read -r MA MI PA <<< "$CUR"
LASTTAG="$(git describe --tags --abbrev=0 2>/dev/null || true)"
RANGE="${LASTTAG:+$LASTTAG..}HEAD"

# ── compute next version ─────────────────────────────────────────────────────
if [ "$BUMP" = "auto" ]; then
  LOG="$(git log $RANGE --no-merges --pretty=%s 2>/dev/null || true)"
  if echo "$LOG" | grep -qiE '(feat|fix|refactor|perf)(\([^)]*\))?!:|BREAKING CHANGE'; then
    [ "$MA" -eq 0 ] && BUMP=minor || BUMP=major
  elif echo "$LOG" | grep -qiE '^feat(\([^)]*\))?:'; then BUMP=minor
  else BUMP=patch; fi
fi
if [ -n "$EXPLICIT" ]; then NEW="$EXPLICIT"
else case "$BUMP" in
  major) NEW="$((MA+1)).0.0" ;;
  minor) NEW="$MA.$((MI+1)).0" ;;
  patch) NEW="$MA.$MI.$((PA+1))" ;;
esac; fi
DATE="$(date +%F)"

# ── changelog section from commits since last tag ────────────────────────────
BULLETS="$(git log $RANGE --no-merges --pretty='- %s' 2>/dev/null | grep -vE 'chore\(release\)' || true)"
[ -z "$BULLETS" ] && BULLETS="- Maintenance release (no itemized changes)."
SECTION="## [$NEW] - $DATE

$BULLETS"

echo "──────────────────────────────────────────"
echo " current : v$CUR   (last tag: ${LASTTAG:-none})"
echo " release : v$NEW   ($BUMP)"
echo "──────────────────────────────────────────"
echo "$SECTION"
echo "──────────────────────────────────────────"

if [ "$DRYRUN" -eq 1 ]; then echo "[dry-run] no files changed, nothing committed."; exit 0; fi

# ── roll CHANGELOG: insert new section above the first existing version heading ─
printf '%s\n\n' "$SECTION" > .release-section.tmp
awk 'FNR==NR { s = s $0 ORS; next }
     !done && /^## \[[0-9]/ { printf "%s", s; done=1 }
     { print }
     END { if (!done) printf "%s", s }' .release-section.tmp CHANGELOG.md > CHANGELOG.new
mv CHANGELOG.new CHANGELOG.md
rm -f .release-section.tmp

# ── link references ──────────────────────────────────────────────────────────
sed -i "s#/compare/v${CUR}\.\.\.HEAD#/compare/v${NEW}...HEAD#" CHANGELOG.md || true
if ! grep -q "^\[${NEW}\]:" CHANGELOG.md; then
  sed -i "/^\[Unreleased\]:/a [${NEW}]: ${REPO_URL}/compare/v${CUR}...v${NEW}" CHANGELOG.md || true
fi

# ── bump version files ───────────────────────────────────────────────────────
printf '%s\n' "$NEW" > VERSION
if [ -f frontend/package.json ]; then
  sed -i -E "0,/\"version\": *\"[^\"]*\"/ s//\"version\": \"${NEW}\"/" frontend/package.json
fi

# ── commit, tag, push ────────────────────────────────────────────────────────
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
git add -A
git commit -q -m "chore(release): v${NEW}"
git tag -a "v${NEW}" -m "Release v${NEW}"
echo "committed + tagged v${NEW} on ${BRANCH}"

if [ "$NOPUSH" -eq 1 ]; then
  echo "[--no-push] local only. Push with:  git push origin ${BRANCH} --follow-tags"
  exit 0
fi

git push origin "${BRANCH}" --follow-tags
echo "pushed ${BRANCH} + tag v${NEW} to origin ✓"

# ── verify the deploy actually landed ────────────────────────────────────────
# Render auto-deploys on push. A green build is not proof the intended build is
# serving traffic — an orphaned worker can hold the port, and an env-var change
# needs a *deploy*, not a restart. So poll /api/version until it reports v$NEW.
if [ "$VERIFY" -eq 1 ]; then
  if [ -z "$API_URL" ]; then
    echo "release.sh: --verify needs RELEASE_VERIFY_URL set to this app's" >&2
    echo "  deployed /api/version endpoint. Refusing to guess: the wrong host" >&2
    echo "  answers for a different deployment and reports a false success." >&2
    exit 1
  fi
  echo "waiting for $API_URL to report $NEW …"
  for i in $(seq 1 60); do
    LIVE="$(curl -fsS --max-time 10 "$API_URL" 2>/dev/null | sed -nE 's/.*"version" *: *"([^"]+)".*/\1/p' || true)"
    if [ "$LIVE" = "$NEW" ]; then
      echo "verified: live app reports v$NEW ✓"
      exit 0
    fi
    printf '  [%3ds] live=%s\n' "$((i*10))" "${LIVE:-unreachable}"
    sleep 10
  done

  PREV_SHA="$(git rev-parse --short "${LASTTAG:-HEAD~1}" 2>/dev/null || echo '<previous-sha>')"
  {
    echo "release.sh: live app never reported v$NEW within 10 minutes."
    echo "Investigate before assuming success. To roll back:"
    if [ -n "$RENDER_SERVICE" ]; then
      echo "  render deploys create ${RENDER_SERVICE} --commit ${PREV_SHA} --wait"
    else
      echo "  set RENDER_SERVICE_ID to this app's Render service, then:"
      echo "  render deploys create <service-id> --commit ${PREV_SHA} --wait"
    fi
    echo "NOTE: an env-var change needs a deploy, not a restart. A code rollback"
    echo "      does NOT revert env vars."
  } >&2
  exit 1
fi
