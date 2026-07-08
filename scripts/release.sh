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
#
# "auto" infers the bump from Conventional Commit prefixes since the last tag
# (feat!→major / feat→minor / else→patch; on 0.x, breaking→minor).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_URL="https://github.com/garyduwyanemorgan/DECCA-Lagoons-App"
cd "$(git rev-parse --show-toplevel)"

BUMP="patch"; EXPLICIT=""; DRYRUN=0; NOPUSH=0
while [ $# -gt 0 ]; do
  case "$1" in
    patch|minor|major|auto) BUMP="$1" ;;
    -v|--version)           EXPLICIT="${2:?--version needs a value}"; shift ;;
    --dry-run)              DRYRUN=1 ;;
    --no-push)              NOPUSH=1 ;;
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
else
  git push origin "${BRANCH}" --follow-tags
  echo "pushed ${BRANCH} + tag v${NEW} to origin ✓"
fi
