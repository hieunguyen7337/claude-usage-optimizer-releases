#!/bin/bash
# Claude meter probes: C0 to C4
# C0: 150 direct claude calls (null test)
# C1: haiku (low), 40 sessions
# C2: sonnet (low), 60 sessions
# C3: opus (medium), 40 sessions
# C4: sonnet (low), 2 parallel cached sessions
set -u
export RUNS_DIR="${RUNS_DIR:-$HOME/.local/state/lanes/runs}"

L="${LANE_BIN:-$HOME/.claude/usage-optimizer/bin/lane}"
P="${MEASURE_DIR:-$HOME/.local/state/lanes/measure}"
C=$P/claude
SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" && pwd)
export CLAUDE_BIN="${CLAUDE_BIN:-claude}"
REFERENCE_FILE=""
MARKS=$C/marks.tsv

mark() { printf '%s\t%s\n' "$(date -u +%FT%TZ)" "$1" >> "$MARKS"; }

# Prep function: generate directories and briefs idempotently
prep() {
  mkdir -p "$C/meter-cwd"
  mkdir -p "$C/c0/cwd" "$C/c0/out" "$C/c0/logs"
  mkdir -p "$C/c1/briefs" "$C/c1/out" "$C/c1/logs"
  mkdir -p "$C/c2/briefs" "$C/c2/out" "$C/c2/logs"
  mkdir -p "$C/c3/briefs" "$C/c3/out" "$C/c3/logs"
  mkdir -p "$C/c4/logs" "$C/c4/out"

  # Generic topics keep preparation independent of Codex runs.
  local -a topics=()
  for i in $(seq 1 40); do topics+=("public libraries, topic $i"); done

  # Generate C1 briefs (40 sessions)
  for i in $(seq -w 1 40); do
    local idx=$((10#$i - 1))
    local topic="${topics[$idx]}"
    cat <<EOF > "$C/c1/briefs/$i.md"
# Probe C1-$i (meter calibration: output tokens)

Write THREE new files, each containing about 6,000 words of original English prose about **$topic**:
\`$C/c1/out/$i-a.txt\` (its history), \`$C/c1/out/$i-b.txt\` (how it works today), \`$C/c1/out/$i-c.txt\` (its future).
Use numbered paragraphs. Do not repeat paragraphs.
Write each file with a single tool call (one shell heredoc, one apply_patch, or one Write call).
Do not read any other file, do not run any other command, do not check or re-read the results.
When the three files are written, reply with the single word DONE.
EOF
  done

  # Generate C2 briefs (60 sessions: topics 1..40, then 1..20)
  for i in $(seq -w 1 60); do
    local n=$((10#$i))
    local idx=$(( (n - 1) % 40 ))
    local topic="${topics[$idx]}"
    cat <<EOF > "$C/c2/briefs/$i.md"
# Probe C2-$i (meter calibration: output tokens)

Write THREE new files, each containing about 6,000 words of original English prose about **$topic**:
\`$C/c2/out/$i-a.txt\` (its history), \`$C/c2/out/$i-b.txt\` (how it works today), \`$C/c2/out/$i-c.txt\` (its future).
Use numbered paragraphs. Do not repeat paragraphs.
Write each file with a single tool call (one shell heredoc, one apply_patch, or one Write call).
Do not read any other file, do not run any other command, do not check or re-read the results.
When the three files are written, reply with the single word DONE.
EOF
  done

  # Generate C3 briefs (40 sessions)
  for i in $(seq -w 1 40); do
    local idx=$((10#$i - 1))
    local topic="${topics[$idx]}"
    cat <<EOF > "$C/c3/briefs/$i.md"
# Probe C3-$i (meter calibration: output tokens)

Write THREE new files, each containing about 6,000 words of original English prose about **$topic**:
\`$C/c3/out/$i-a.txt\` (its history), \`$C/c3/out/$i-b.txt\` (how it works today), \`$C/c3/out/$i-c.txt\` (its future).
Use numbered paragraphs. Do not repeat paragraphs.
Write each file with a single tool call (one shell heredoc, one apply_patch, or one Write call).
Do not read any other file, do not run any other command, do not check or re-read the results.
When the three files are written, reply with the single word DONE.
EOF
  done

  # Generate C4 brief
  {
    printf '# Probe C4 (meter calibration: cached input)\n\n'
    printf 'Read the reference text below; you do not need to analyse it. Then follow the INSTRUCTIONS at the end exactly.\n\n'
    printf '<reference>\n'; head -c 400000 "$REFERENCE_FILE"; printf '\n</reference>\n\n'
    printf 'INSTRUCTIONS: make exactly 120 tool calls, strictly one at a time. Call k (k = 1 to 120) runs the shell command `echo %s` with k in place of %%s. Never combine commands, never run anything else, never write files. After call 120, reply with the single word DONE.\n' 'k'
  } > "$C/c4/brief.md"

  # Generate C5 briefs (Fable, 10 sessions): C3's first 10 briefs with C5 paths
  mkdir -p "$C/c5/briefs" "$C/c5/out" "$C/c5/logs"
  for i in $(seq -w 1 10); do
    sed -e "s|/c3/out/|/c5/out/|g" -e "s|Probe C3-|Probe C5-|" "$C/c3/briefs/$i.md" > "$C/c5/briefs/$i.md"
  done
}

# Worker function for running a lane session
run_session() {
  local lane="$1"
  local workdir="$2"
  local brief="$3"
  local effort="$4"
  local block="$5"
  local tag="$6"
  local timeout="$7"
  local logdir="$8"
  local model="${9:-}"

  local nn
  nn=$(basename "$brief" .md)
  local run_id
  run_id="$(date -u +%Y%m%d-%H%M%S)-${lane}-${block}-${nn}"
  local rundir="$RUNS_DIR/$run_id"
  local -a mflag=()
  [ -n "$model" ] && mflag=(-m "$model")

  "$L" "$lane" -C "$workdir" -b "$brief" -e "$effort" "${mflag[@]}" -o "$rundir" --class research --tag "$tag" --off-catalog --timeout "$timeout" > "$logdir/$nn.log" 2>&1 || true
}

# Worker function for C4 lane session
run_c4_session() {
  local nn="$1"
  local run_id
  run_id="$(date -u +%Y%m%d-%H%M%S)-sonnet-c4-${nn}"
  local rundir="$RUNS_DIR/$run_id"

  "$L" sonnet -C "$C/c4" -b "$C/c4/brief.md" -e low -o "$rundir" --class research --tag cprobe-c4 --off-catalog --timeout 3600 > "$C/c4/logs/$nn.log" 2>&1 || true
}

# Worker function for C0 direct claude call
run_c0_call() {
  local nnn="$1"
  (
    cd "$C/c0/cwd" || exit 1
    timeout 180 "$CLAUDE_BIN" -p --model claude-haiku-5-5 --setting-sources project,local --strict-mcp-config --output-format json --max-turns 1 "Reply with the single word OK." > "$C/c0/out/$nnn.json" 2>&1
  ) || true
}

# Guard check against rate limits
guard() {
  local blk="$1"
  local reading
  reading=$("$SCRIPT_DIR/meter_read.sh" "guard-$blk") || true
  local fh sd
  fh=$(echo "$reading" | sed -n 's/.*five_hour=\([0-9.]*\).*/\1/p')
  sd=$(echo "$reading" | sed -n 's/.*seven_day=\([0-9.]*\).*/\1/p')
  if [ -z "$fh" ] || [ -z "$sd" ]; then
    mark "STOP-$blk-noreading"
    printf '# Stopped at block %s: no meter reading at %s\n' "$blk" "$(date -u +%FT%TZ)" > "$C/STATUS.md"
    exit 0
  fi
  if awk -v f="$fh" -v s="$sd" 'BEGIN { exit !((f != "" && f >= 0.75) || (s != "" && s >= 0.40)) }'; then
    mark "STOP-$blk"
    {
      printf '# Stopped at block %s\n\n' "$blk"
      printf 'Guard condition met at %s: five_hour=%s (threshold 0.75), seven_day=%s (threshold 0.40).\n' "$(date -u +%FT%TZ)" "$fh" "$sd"
    } > "$C/STATUS.md"
    echo "Guard triggered for $blk: five_hour=$fh, seven_day=$sd. Exiting." >&2
    exit 0
  fi
}

# Parse options
START_AFTER=""
PREP_ONLY=false

while [ $# -gt 0 ]; do
  case "$1" in
    --start-after)
      START_AFTER="$2"
      shift 2
      ;;
    --reference)
      REFERENCE_FILE="$2"
      shift 2
      ;;
    --prep-only)
      PREP_ONLY=true
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

[ -r "$REFERENCE_FILE" ] || { echo "--reference FILE is required (any large text file)" >&2; exit 2; }
prep

if [ "$PREP_ONLY" = true ]; then
  echo "Block C0:"
  echo "  (direct claude CLI calls, null test)"
  echo "  first: (cd $C/c0/cwd && timeout 180 "$CLAUDE_BIN" -p --model claude-haiku-5-5 --setting-sources project,local --strict-mcp-config --output-format json --max-turns 1 \"Reply with the single word OK.\" > $C/c0/out/001.json)"
  echo "  last:  (cd $C/c0/cwd && timeout 180 "$CLAUDE_BIN" -p --model claude-haiku-5-5 --setting-sources project,local --strict-mcp-config --output-format json --max-turns 1 \"Reply with the single word OK.\" > $C/c0/out/150.json)"
  echo "Block C1:"
  echo "first: $L haiku -C $C/c1 -b $C/c1/briefs/01.md -e low -o $RUNS_DIR/\$(date -u +%Y%m%d-%H%M%S)-haiku-c1-01 --class research --tag cprobe-c1 --off-catalog --timeout 1800 --dry-run"
  echo "last:  $L haiku -C $C/c1 -b $C/c1/briefs/40.md -e low -o $RUNS_DIR/\$(date -u +%Y%m%d-%H%M%S)-haiku-c1-40 --class research --tag cprobe-c1 --off-catalog --timeout 1800 --dry-run"
  echo "Block C2:"
  echo "first: $L sonnet -C $C/c2 -b $C/c2/briefs/01.md -e low -o $RUNS_DIR/\$(date -u +%Y%m%d-%H%M%S)-sonnet-c2-01 --class research --tag cprobe-c2 --off-catalog --timeout 2400 --dry-run"
  echo "last:  $L sonnet -C $C/c2 -b $C/c2/briefs/60.md -e low -o $RUNS_DIR/\$(date -u +%Y%m%d-%H%M%S)-sonnet-c2-60 --class research --tag cprobe-c2 --off-catalog --timeout 2400 --dry-run"
  echo "Block C3:"
  echo "first: $L opus -C $C/c3 -b $C/c3/briefs/01.md -e medium -o $RUNS_DIR/\$(date -u +%Y%m%d-%H%M%S)-opus-c3-01 --class research --tag cprobe-c3 --off-catalog --timeout 3000 --dry-run"
  echo "last:  $L opus -C $C/c3 -b $C/c3/briefs/40.md -e medium -o $RUNS_DIR/\$(date -u +%Y%m%d-%H%M%S)-opus-c3-40 --class research --tag cprobe-c3 --off-catalog --timeout 3000 --dry-run"
  echo "Block C4:"
  echo "first: $L sonnet -C $C/c4 -b $C/c4/brief.md -e low -o $RUNS_DIR/\$(date -u +%Y%m%d-%H%M%S)-sonnet-c4-01 --class research --tag cprobe-c4 --off-catalog --timeout 3600 --dry-run"
  echo "last:  $L sonnet -C $C/c4 -b $C/c4/brief.md -e low -o $RUNS_DIR/\$(date -u +%Y%m%d-%H%M%S)-sonnet-c4-02 --class research --tag cprobe-c4 --off-catalog --timeout 3600 --dry-run"
  exit 0
fi


# Resolve the binary without starting it, then scope lane selection to this run.
CLAUDE_BIN=$(command -v -- "$CLAUDE_BIN") || { echo "claude executable not found" >&2; exit 2; }
export CLAUDE_BIN
export LANES_CONFIG="$C/lane-config"
mkdir -p "$LANES_CONFIG/bin"
ln -sf -- "$CLAUDE_BIN" "$LANES_CONFIG/bin/claude"

# Optional sleep until start-after
if [ -n "$START_AFTER" ]; then
  target_ts=$(date -u -d "$START_AFTER" +%s)
  while true; do
    now_ts=$(date -u +%s)
    if [ "$now_ts" -ge "$target_ts" ]; then
      break
    fi
    sleep 60
  done
fi

# Block C0
guard c0
"$SCRIPT_DIR/meter_read.sh" pre-c0
mark c0-start
seq -f '%03g' 1 150 | xargs -P 4 -I{} bash -c "$(declare -f run_c0_call); C='$C'; run_c0_call '{}'"
mark c0-end
sleep 30
"$SCRIPT_DIR/meter_read.sh" post-c0

# Block C1
guard c1
"$SCRIPT_DIR/meter_read.sh" pre-c1
mark c1-start
for b in "$C"/c1/briefs/*.md; do echo "$b"; done | xargs -P 6 -I{} bash -c "$(declare -f run_session); L='$L'; HOME='$HOME'; run_session haiku '$C/c1' '{}' low c1 cprobe-c1 1800 '$C/c1/logs'"
mark c1-end
sleep 30
"$SCRIPT_DIR/meter_read.sh" post-c1

# Block C2
guard c2
"$SCRIPT_DIR/meter_read.sh" pre-c2
mark c2-start
for b in "$C"/c2/briefs/*.md; do echo "$b"; done | xargs -P 6 -I{} bash -c "$(declare -f run_session); L='$L'; HOME='$HOME'; run_session sonnet '$C/c2' '{}' low c2 cprobe-c2 2400 '$C/c2/logs'"
mark c2-end
sleep 30
"$SCRIPT_DIR/meter_read.sh" post-c2

# Block C3
guard c3
"$SCRIPT_DIR/meter_read.sh" pre-c3
mark c3-start
for b in "$C"/c3/briefs/*.md; do echo "$b"; done | xargs -P 6 -I{} bash -c "$(declare -f run_session); L='$L'; HOME='$HOME'; run_session opus '$C/c3' '{}' medium c3 cprobe-c3 3000 '$C/c3/logs'"
mark c3-end
sleep 30
"$SCRIPT_DIR/meter_read.sh" post-c3

# Block C4
guard c4
"$SCRIPT_DIR/meter_read.sh" pre-c4
mark c4-start
printf '%s\n' 01 02 | xargs -P 2 -I{} bash -c "$(declare -f run_c4_session); L='$L'; HOME='$HOME'; C='$C'; run_c4_session '{}'"
mark c4-end
sleep 30
"$SCRIPT_DIR/meter_read.sh" post-c4

# Block C5: Fable 5.1 through the opus lane, to see whether seven_day_overage_included moves
guard c5
"$SCRIPT_DIR/meter_read.sh" pre-c5
mark c5-start
for b in "$C"/c5/briefs/*.md; do echo "$b"; done | xargs -P 5 -I{} bash -c "$(declare -f run_session); L='$L'; HOME='$HOME'; run_session opus '$C/c5' '{}' medium c5 cprobe-c5 3000 '$C/c5/logs' claude-fable-5-1"
mark c5-end
sleep 30
"$SCRIPT_DIR/meter_read.sh" post-c5

# Finish
"$SCRIPT_DIR/meter_read.sh" final
mark CPROBES-end
echo "cprobes done"
