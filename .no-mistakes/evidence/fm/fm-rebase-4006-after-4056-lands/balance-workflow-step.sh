set -eu
shopt -s nullglob
serial=("$RUNNER_TEMP"/fm-test-aggregate/fm-test-timing-portable-serial-*.json)
if [ "${#serial[@]}" -eq 0 ]; then
  echo "::warning::no portable serial timing JSON found; shard balance unchecked"
  exit 0
fi
# The runner owns the cap this share is taken against; the suite parses
# this workflow and refuses when that record and the
# tests-portable-serial timeout-minutes disagree, so the cap cannot
# move in one place only.
bin/fm-test-run.sh --check-shard-balance "${serial[@]}"
