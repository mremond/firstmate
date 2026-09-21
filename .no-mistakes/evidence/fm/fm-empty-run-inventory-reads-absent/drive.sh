#!/usr/bin/env bash
# usage: drive.sh <lib> <branch> <overview-file> <worktree>
. "$1"; fm_nm_select_run "$2" "$(cat "$3")" "$4"
