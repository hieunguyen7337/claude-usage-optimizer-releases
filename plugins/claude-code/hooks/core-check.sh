#!/bin/sh
# SessionStart: say when the kit core is missing or older than this plugin.
# Any error prints nothing and exits 0, so the session still starts.

exec 2>/dev/null
trap 'exit 0' EXIT

emit() {
  printf '%s\n' "{\"hookSpecificOutput\":{\"hookEventName\":\"SessionStart\",\"additionalContext\":\"$1\"}}"
  exit 0
}

if [ -z "${HOME:-}" ]; then
  exit 0
fi

# $0 may be a Windows path (C:\...\core-check.sh). Normalize before taking its directory.
script=$(printf '%s' "$0" | tr '\\' '/')
case $script in
  */*) dir=${script%/*} ;;
  *) dir=. ;;
esac
plugin_dir=$(CDPATH= cd "$dir/.." && pwd) || exit 0
plugin_file=$plugin_dir/kit-version
if [ ! -f "$plugin_file" ]; then
  exit 0
fi
plugin=$(awk 'NR==1 { sub(/\r$/, ""); print; exit }' "$plugin_file") || exit 0
case $plugin in
  [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].[0-9]*) ;;
  *) exit 0 ;;
esac

policy=$HOME/.claude/usage-optimizer/POLICY.md
if [ ! -f "$policy" ]; then
  emit "The Coding Tool Optimizer core is not installed. Use the kit-setup skill to install it."
fi

# Prefer the current version line. Fall back to the name the kit used before 2026-11-16.3.
line=$(awk '
  /^Coding Tool Optimizer version: / { print; found = "new"; exit }
  /^Claude Usage Optimizer version: / { if (found == "") found = $0 }
  END { if (found != "" && found != "new") print found }
' "$policy") || exit 0
case $line in
  *": "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].[0-9]*) ;;
  *) emit "The Coding Tool Optimizer core is not installed. Use the kit-setup skill to install it." ;;
esac

rest=${line#*: }
token=${rest%% *}
case $token in
  *.) token=${token%.} ;;
esac
case $token in
  [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].[0-9]*) ;;
  *) exit 0 ;;
esac

result=$(awk -v core="$token" -v plugin="$plugin" 'BEGIN {
  n = split(core, a, /[-.]/)
  m = split(plugin, b, /[-.]/)
  if (n < 4 || m < 4) { print "bad"; exit }
  for (i = 1; i <= 4; i++) {
    if (a[i] + 0 < b[i] + 0) { print "older"; exit }
    if (a[i] + 0 > b[i] + 0) { print "newer"; exit }
  }
  print "same"
}') || exit 0

if [ "$result" = "older" ]; then
  emit "The installed Coding Tool Optimizer core ($token) is older than this plugin ($plugin). Use the kit-setup skill to update it."
fi
exit 0
