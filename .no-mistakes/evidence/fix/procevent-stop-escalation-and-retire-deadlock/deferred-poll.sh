#!/bin/bash
marker=$1
input=$2
trap 'printf "TERM trap handled\n" >> "$marker.trap"' TERM
/bin/sh -c 'trap "" TERM; printf "%s\n" "$$" > "$1.child"; exec /usr/bin/tail -f "$2"' _ "$marker" "$input"
printf 'foreground child returned\n' >> "$marker.returned"
