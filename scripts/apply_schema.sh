#!/usr/bin/env bash
# Applies the whole schema to a Postgres running in a Supabase container.
#
# The repo has no migration runner and no schema_migrations table — the order in
# db/migrations/README.md is the only record of what goes where, and it has only
# ever been executed by hand in the Supabase dashboard. That is why no migration
# in this repository has ever been parsed by a real Postgres. This script exists
# to change that.
#
#   scripts/apply_schema.sh --dry-run        # print the order, touch nothing
#   scripts/apply_schema.sh                  # apply, stopping at the first error
#   scripts/apply_schema.sh --container db   # non-default container name
#
# ON_ERROR_STOP=1 is not optional. Without it psql reports failures and carries
# on, and a migration that half-applied is worse than one that did not run —
# `IF NOT EXISTS` means the next attempt succeeds quietly over a schema that is
# subtly wrong, which is exactly what README.md warns about.
set -euo pipefail

CONTAINER="${SUPABASE_DB_CONTAINER:-supabase-db}"
DB_USER="${SUPABASE_DB_USER:-postgres}"
DB_NAME="${SUPABASE_DB_NAME:-postgres}"
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)   DRY_RUN=1 ;;
    --container) CONTAINER="$2"; shift ;;
    --user)      DB_USER="$2"; shift ;;
    --database)  DB_NAME="$2"; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

cd "$(dirname "$0")/.."

# The order is load-bearing and is NOT plain alphabetical:
#   000 first — it creates `readings` and `predictions`, which schema.sql ALTERs
#               and schema_rls.sql attaches policies to. Neither table is created
#               anywhere else in the repo.
#   then schema.sql (organizations, sites, adds site_id to both)
#   then schema_rls.sql (user_profiles, get_user_organization/get_user_role)
#   then 001..023 in numeric order.
# The 002 and 006 prefixes are each shared by two independent files; either order
# within a pair is fine, and `sort` gives a stable one.
FILES=(db/migrations/000_base.sql db/schema.sql db/schema_rls.sql)
while IFS= read -r f; do FILES+=("$f"); done < <(
  find db/migrations -name '*.sql' ! -name '*_down.sql' ! -name '000_base.sql' | sort
)

if [ "$DRY_RUN" -eq 1 ]; then
  printf 'Would apply %d files to %s (container %s), in this order:\n\n' \
    "${#FILES[@]}" "$DB_NAME" "$CONTAINER"
  i=1; for f in "${FILES[@]}"; do printf '  %2d. %s\n' "$i" "$f"; i=$((i+1)); done
  exit 0
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "error: no running container named '$CONTAINER'." >&2
  echo "Running containers:" >&2
  docker ps --format '  {{.Names}}' >&2
  echo "Start the stack first, or pass --container <name>." >&2
  exit 1
fi

echo "Applying ${#FILES[@]} files to $DB_NAME in $CONTAINER"
echo

for f in "${FILES[@]}"; do
  [ -f "$f" ] || { echo "error: $f not found" >&2; exit 1; }
  printf '  %-52s ' "$f"
  if docker exec -i "$CONTAINER" \
       psql -v ON_ERROR_STOP=1 -q -U "$DB_USER" -d "$DB_NAME" < "$f" >/dev/null 2>/tmp/pgerr; then
    echo "ok"
  else
    echo "FAILED"
    echo
    sed 's/^/    /' /tmp/pgerr >&2
    echo >&2
    echo "Stopped at $f. Nothing after it was applied." >&2
    echo "Each migration is wrapped in BEGIN/COMMIT, so this file itself rolled" >&2
    echo "back — but earlier files are committed. Fix, then re-run: every file" >&2
    echo "uses IF NOT EXISTS and is safe to repeat." >&2
    exit 1
  fi
done

echo
echo "Verifying:"
docker exec -i "$CONTAINER" psql -q -U "$DB_USER" -d "$DB_NAME" <<'SQL'
\pset border 2
SELECT
  (SELECT count(*) FROM information_schema.tables
     WHERE table_schema = 'public') AS public_tables,
  (SELECT deployment FROM public.deployment_identity LIMIT 1) AS deployment,
  (SELECT count(*) FROM public.standards)           AS standards,
  (SELECT count(*) FROM public.specification_sets)  AS spec_sets,
  (SELECT count(*) FROM public.spec_limits)         AS spec_limits,
  (SELECT count(*) FROM public.guideline_modules)   AS modules,
  (SELECT count(*) FROM public.obligations)         AS obligations;
SQL

echo
echo "Schema applied. The registry tables are empty by design — 022 and 023 seed"
echo "nothing. Next: python -m db.seed_standards --dry-run"
