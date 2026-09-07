#!/usr/bin/env bash
# Standalone product-level evidence for the two guarded merge entrypoints.
set -eu

ROOT=/Users/mremond/.no-mistakes/worktrees/acf4a767348a/01M1Y6H734EAVDZHYTVT29263Y
TMP_ROOT=$(mktemp -d /tmp/fm-merge-authority-e2e.XXXXXX)
trap 'rm -rf "$TMP_ROOT"' EXIT

make_home() {
  local home=$1
  mkdir -p "$home/data" "$home/state" "$home/config" "$home/projects" "$home/fakebin"
  cp "$ROOT/.tasks.toml" "$home/.tasks.toml"
  printf '%s\n' '## In flight' '' '## Queued' '' '## Done' > "$home/data/backlog.md"
}

write_meta() {
  local home=$1 id=$2 mode=$3 repo=$4 worktree=$5
  printf '%s\n' \
    "window=firstmate:fm-$id" "endpoint_task_id=$id" "worktree=$worktree" \
    "project=$repo" 'harness=codex' 'kind=ship' "mode=$mode" "spawn_gen=e2e-$id" \
    > "$home/state/$id.meta"
}

make_repo_and_branch() {
  local repo=$1 worktree=$2 branch=$3
  git init -q -b main "$repo"
  git -C "$repo" -c user.name=Evidence -c user.email=evidence@example.invalid \
    commit --allow-empty -qm base
  git -C "$repo" worktree add -q -b "$branch" "$worktree"
  printf 'e2e local delivery\n' > "$worktree/delivery.txt"
  git -C "$worktree" add delivery.txt
  git -C "$worktree" -c user.name=Evidence -c user.email=evidence@example.invalid \
    commit -qm delivery
}

local_home="$TMP_ROOT/local-home"
local_id=e2e-local
local_repo="$local_home/projects/sample"
local_wt="$local_home/projects/$local_id"
make_home "$local_home"
make_repo_and_branch "$local_repo" "$local_wt" "fm/$local_id"
write_meta "$local_home" "$local_id" local-only "$local_repo" "$local_wt"

printf '%s\n' 'LOCAL-ONLY MERGE: absent authority record'
rm "$local_home/data/backlog.md"
set +e
FM_ROOT_OVERRIDE="$ROOT" FM_HOME="$local_home" FM_STATE_OVERRIDE="$local_home/state" \
  FM_DATA_OVERRIDE="$local_home/data" FM_CONFIG_OVERRIDE="$local_home/config" \
  "$ROOT/bin/fm-merge-local.sh" "$local_id" > "$TMP_ROOT/local-absent.out" 2> "$TMP_ROOT/local-absent.err"
local_absent_rc=$?
set -e
printf 'exit=%s\n' "$local_absent_rc"
grep -F 'captain-hold authority record is unavailable' "$TMP_ROOT/local-absent.err"
printf 'main=%s\n' "$(git -C "$local_repo" rev-parse --short main)"

printf '%s\n' 'LOCAL-ONLY MERGE: readable backlog with no task row'
printf '%s\n' '## In flight' '' '## Queued' '' '## Done' > "$local_home/data/backlog.md"
FM_ROOT_OVERRIDE="$ROOT" FM_HOME="$local_home" FM_STATE_OVERRIDE="$local_home/state" \
  FM_DATA_OVERRIDE="$local_home/data" FM_CONFIG_OVERRIDE="$local_home/config" \
  "$ROOT/bin/fm-merge-local.sh" "$local_id"

pr_home="$TMP_ROOT/pr-home"
pr_id=e2e-pr
pr_url=https://github.com/sample/sample/pull/43
make_home "$pr_home"
write_meta "$pr_home" "$pr_id" no-mistakes "$pr_home/projects/sample" "$pr_home/projects/missing"
cat > "$pr_home/fakebin/gh" <<'SH'
#!/usr/bin/env bash
case "${1:-} ${2:-}" in
  'api graphql') printf '%s\n' 'state=MERGED' 'merged=true' 'queued=false' 'base=main' ;;
  'api '*) : ;;
  'pr view') printf '%s\n' 1111111111111111111111111111111111111111 ;;
esac
SH
cat > "$pr_home/fakebin/gh-axi" <<'SH'
#!/usr/bin/env bash
printf 'FORGE_CALLED %s\n' "$*" >> "$FM_E2E_FORGE_LOG"
case "${1:-} ${2:-}" in
  'pr merge') printf 'merged: %s\n' "${3:-}" ;;
  'pr view') printf 'pull_request: %s\n' "${3:-}" ;;
esac
SH
chmod +x "$pr_home/fakebin/gh" "$pr_home/fakebin/gh-axi"
: > "$TMP_ROOT/forge.log"

printf '%s\n' 'PR MERGE: absent authority record'
rm "$pr_home/data/backlog.md"
set +e
PATH="$pr_home/fakebin:$PATH" FM_E2E_FORGE_LOG="$TMP_ROOT/forge.log" \
  FM_ROOT_OVERRIDE="$ROOT" FM_HOME="$pr_home" FM_STATE_OVERRIDE="$pr_home/state" \
  FM_DATA_OVERRIDE="$pr_home/data" FM_CONFIG_OVERRIDE="$pr_home/config" \
  "$ROOT/bin/fm-pr-merge.sh" "$pr_id" "$pr_url" > "$TMP_ROOT/pr-absent.out" 2> "$TMP_ROOT/pr-absent.err"
pr_absent_rc=$?
set -e
printf 'exit=%s\n' "$pr_absent_rc"
grep -F 'captain-hold authority record is unavailable' "$TMP_ROOT/pr-absent.err"
if [ -s "$TMP_ROOT/forge.log" ]; then cat "$TMP_ROOT/forge.log"; else printf 'FORGE_NOT_CALLED\n'; fi

printf '%s\n' 'PR MERGE: readable backlog with no task row'
printf '%s\n' '## In flight' '' '## Queued' '' '## Done' > "$pr_home/data/backlog.md"
PATH="$pr_home/fakebin:$PATH" FM_E2E_FORGE_LOG="$TMP_ROOT/forge.log" \
  FM_ROOT_OVERRIDE="$ROOT" FM_HOME="$pr_home" FM_STATE_OVERRIDE="$pr_home/state" \
  FM_DATA_OVERRIDE="$pr_home/data" FM_CONFIG_OVERRIDE="$pr_home/config" \
  "$ROOT/bin/fm-pr-merge.sh" "$pr_id" "$pr_url"
tail -n 1 "$TMP_ROOT/forge.log"
