#!/bin/bash
# Claude meter reader: queries claude haiku for rate limits and cost, writes to meter.jsonl
set -u

LABEL="${1:-}"
if [ -z "$LABEL" ]; then
  echo "Usage: $0 LABEL" >&2
  exit 1
fi

C="${MEASURE_DIR:-$HOME/.local/state/lanes/measure}/claude"
CLAUDE_BIN="${CLAUDE_BIN:-claude}"
mkdir -p "$C/meter-cwd"

# Run claude haiku in empty meter-cwd
(
  cd "$C/meter-cwd" || exit 1
  timeout 180 "$CLAUDE_BIN" -p --model claude-haiku-5-5 --setting-sources project,local --strict-mcp-config --output-format stream-json --verbose --max-turns 1 "Reply with the single word OK." > "$C/meter-cwd/last.jsonl" 2>&1
) || true

if [ ! -f "$C/meter-cwd/last.jsonl" ]; then
  echo "Error: $C/meter-cwd/last.jsonl not found" >&2
  exit 3
fi

rate_event=$(jq -c -R 'fromjson? | select(.type=="rate_limit_event")' "$C/meter-cwd/last.jsonl" 2>/dev/null | tail -n 1)
if [ -z "$rate_event" ]; then
  echo "Error: rate_limit_event not found in $C/meter-cwd/last.jsonl" >&2
  exit 3
fi

rate_info=$(printf '%s\n' "$rate_event" | jq -c '.rate_limit_info // empty')
if [ -z "$rate_info" ] || [ "$rate_info" = "null" ]; then
  echo "Error: rate_limit_info missing in rate_limit_event" >&2
  exit 3
fi

five_hour=$(printf '%s\n' "$rate_info" | jq -r '.unifiedWindows.five_hour.utilization // empty')
seven_day=$(printf '%s\n' "$rate_info" | jq -r '.unifiedWindows.seven_day.utilization // empty')

if [ -z "$five_hour" ] || [ -z "$seven_day" ]; then
  echo "Error: utilization window data missing in rate_limit_info" >&2
  exit 3
fi

result_event=$(jq -c -R 'fromjson? | select(.type=="result")' "$C/meter-cwd/last.jsonl" 2>/dev/null | tail -n 1)
if [ -n "$result_event" ]; then
  usage=$(printf '%s\n' "$result_event" | jq -c '.usage // null')
  cost=$(printf '%s\n' "$result_event" | jq -r '.total_cost_usd // 0')
else
  usage="null"
  cost="0"
fi

now_iso=$(date -u +%FT%TZ)

jq -c -n \
  --arg ts "$now_iso" \
  --arg lbl "$LABEL" \
  --argjson rli "$rate_info" \
  --argjson usg "$usage" \
  --argjson cost "$cost" \
  '{ts: $ts, label: $lbl, rate_limit_info: $rli, usage: $usg, total_cost_usd: $cost}' >> "$C/meter.jsonl"

printf 'five_hour=%s seven_day=%s\n' "$five_hour" "$seven_day"
