#!/bin/bash
# Codex meter probes on gpt-6-astra (effort low), one token type dominant per block:
#   P1 output-heavy   40 short sessions, each writes ~8k tokens of prose
#   P2 cached-heavy   1 session, ~100k-token brief, then ~120 trivial tool calls (context re-read cached)
#   P3 uncached-heavy 30 sessions, each a unique ~40k-token brief answered with one word
# Dispatch only: every model call goes through lane. Block boundaries go to marks.tsv for the fit,
# which reads tokens and used_percent from the rollouts themselves.
set -u
export RUNS_DIR="${RUNS_DIR:-$HOME/.local/state/lanes/runs}"
L="${LANE_BIN:-$HOME/.claude/usage-optimizer/bin/lane}"
P="${MEASURE_DIR:-$HOME/.local/state/lanes/measure}/codex"
if [ -z "${CODEX_BIN:-}" ]; then
  CODEX_BIN="$HOME/.config/lanes/bin/codex"
  [ -x "$CODEX_BIN" ] || CODEX_BIN=codex
fi
export CODEX_BIN
export USAGE_OPTIMIZER_CODEX_BIN="$CODEX_BIN"
STATUS_BIN="${STATUS_BIN:-$HOME/.claude/usage-optimizer/bin/usage-status}"
export CLAUDE_USAGE_DIR="${CLAUDE_USAGE_DIR:-$HOME/.claude/usage}"
mark() { printf '%s\t%s\n' "$(date -u +%FT%TZ)" "$1" >> "$P/marks.tsv"; }
run() { "$L" astra -C "$1" -b "$2" -e low --class research --tag "$3" --off-catalog --timeout "$4" 2>&1 | head -1; }

# Prep function: generate directories and briefs idempotently
prep() {
  mkdir -p "$P/p4/briefs" "$P/p4/out" "$P/p4/logs"
  mkdir -p "$P/p5/briefs" "$P/p5/out" "$P/p5/logs"

  # Load the 40 topics from p1 briefs
  local -a topics=()
  for i in $(seq -w 1 40); do
    local t
    t=$(grep -o '\*\*[^*]*\*\*' "$P/p1/briefs/$i.md" | tr -d '*')
    topics+=("$t")
  done

  # Generate P4 briefs
  for i in $(seq -w 1 40); do
    local idx=$((10#$i - 1))
    local topic="${topics[$idx]}"
    cat <<EOF > "$P/p4/briefs/$i.md"
# Probe P4-$i (meter calibration: output tokens)

Write THREE new files, each containing about 6,000 words of original English prose about **$topic**:
\`$P/p4/out/$i-a.txt\` (its history), \`$P/p4/out/$i-b.txt\` (how it works today), \`$P/p4/out/$i-c.txt\` (its future).
Use numbered paragraphs. Do not repeat paragraphs.
Write each file with a single tool call (one shell heredoc, one apply_patch, or one Write call).
Do not read any other file, do not run any other command, do not check or re-read the results.
When the three files are written, reply with the single word DONE.
EOF
  done

  # Generate P5 briefs
  for i in $(seq -w 1 40); do
    local idx=$((10#$i - 1))
    local topic="${topics[$idx]}"
    cat <<EOF > "$P/p5/briefs/$i.md"
# Probe P5-$i (meter calibration: output tokens)

Write THREE new files, each containing about 6,000 words of original English prose about **$topic**:
\`$P/p5/out/$i-a.txt\` (its history), \`$P/p5/out/$i-b.txt\` (how it works today), \`$P/p5/out/$i-c.txt\` (its future).
Use numbered paragraphs. Do not repeat paragraphs.
Write each file with a single tool call (one shell heredoc, one apply_patch, or one Write call).
Do not read any other file, do not run any other command, do not check or re-read the results.
When the three files are written, reply with the single word DONE.
EOF
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

  local nn
  nn=$(basename "$brief" .md)
  local run_id
  run_id="$(date -u +%Y%m%d-%H%M%S)-${lane}-${block}-${nn}"
  local rundir="$RUNS_DIR/$run_id"

  "$L" "$lane" -C "$workdir" -b "$brief" -e "$effort" -o "$rundir" --class research --tag "$tag" --off-catalog --timeout "$timeout" > "$logdir/$nn.log" 2>&1 || true
}

# Codex meter read helper
cread() {
  local lbl="$1"
  timeout 60 env USAGE_OPTIMIZER_CODEX_BIN="$CODEX_BIN" "$STATUS_BIN" --codex-refresh >/dev/null 2>&1 || true
  local ts
  ts=$(date -u +%FT%TZ)
  if [ -f "$CLAUDE_USAGE_DIR/codex-latest.json" ]; then
    jq -c -n --arg ts "$ts" --arg lbl "$lbl" --slurpfile codex "$CLAUDE_USAGE_DIR/codex-latest.json" '{ts: $ts, label: $lbl, codex: $codex[0]}' >> "$P/meter-codex.jsonl"
  else
    jq -c -n --arg ts "$ts" --arg lbl "$lbl" '{ts: $ts, label: $lbl, codex: null}' >> "$P/meter-codex.jsonl"
  fi
}


# Generate generic P1 briefs; no external project material is needed.
prep_p1() {
  mkdir -p "$P"/p1/{briefs,out} "$P/p2" "$P/p3/briefs"
  for i in $(seq -w 1 40); do
    cat > "$P/p1/briefs/$i.md" <<EOF
# Probe P1-$i
Write about 6,000 words of original English prose about **the history and future of public libraries, topic $i**.
Use numbered paragraphs and do not repeat paragraphs.
Write it to \`$P/p1/out/$i.txt\` in a single tool call.
Do not read other files, run other commands or re-read the result. Reply DONE.
EOF
  done
}

prep_p1
prep
if [ "${1:-}" = --prep-only ]; then exit 0; fi

# Resolve the binary without starting it, then scope lane selection to this run.
CODEX_BIN=$(command -v -- "$CODEX_BIN") || { echo "codex executable not found" >&2; exit 2; }
export CODEX_BIN
export LANES_CONFIG="$P/lane-config"
mkdir -p "$LANES_CONFIG/bin"
ln -sf -- "$CODEX_BIN" "$LANES_CONFIG/bin/codex"

cread pre-p1
mark P1-start
for b in "$P"/p1/briefs/*.md; do echo "$b"; done | xargs -P 4 -I{} bash -c "$(declare -f run); L='$L'; run '$P/p1' '{}' probe-p1 1800"
mark P1-end
cread post-p1

# P2: ~400 KB (~100k tokens) of P1 text inside the brief, so every later call re-reads it from cache.
cat "$P"/p1/out/*.txt 2>/dev/null > "$P/p1-text.txt"
{
  printf '# Probe P2 (meter calibration: cached input)\n\n'
  printf 'Read the reference text below; you do not need to analyse it. Then follow the INSTRUCTIONS at the end exactly.\n\n'
  printf '<reference>\n'; head -c 400000 "$P/p1-text.txt"; printf '\n</reference>\n\n'
  printf 'INSTRUCTIONS: make exactly 120 tool calls, strictly one at a time. Call k (k = 1 to 120) runs the shell command `echo %s` with k in place of %%s. Never combine commands, never run anything else, never write files. After call 120, reply with the single word DONE.\n' 'k'
} > "$P/p2/brief.md"
cread pre-p2
mark P2-start
run "$P/p2" "$P/p2/brief.md" probe-p2 3600
mark P2-end
cread post-p2

# P3: 30 sessions, each a unique header plus a different ~160 KB (~40k tokens) slice, one-word answer.
size=$(stat -c %s "$P/p1-text.txt")
for k in $(seq -w 1 30); do
  off=$(( (10#$k - 1) * 160000 % (size > 160000 ? size - 160000 : 1) ))
  {
    printf '# Probe P3-%s (meter calibration: uncached input) nonce %s\n\n' "$k" "$(od -An -N8 -tx8 /dev/urandom | tr -d ' ')"
    printf 'Do not run any command and do not write any file. Read the text below, then reply with the single word DONE.\n\n<text>\n'
    tail -c +$((off + 1)) "$P/p1-text.txt" | head -c 160000
    printf '\n</text>\n\nReply with the single word DONE.\n'
  } > "$P/p3/briefs/$k.md"
done
cread pre-p3
mark P3-start
for b in "$P"/p3/briefs/*.md; do echo "$b"; done | xargs -P 4 -I{} bash -c "$(declare -f run); L='$L'; run '$P/p3' '{}' probe-p3 900"
mark P3-end
cread post-p3
echo "probes done: $(wc -l < "$P/marks.tsv") marks"

# Block P4
cread pre-p4
mark P4-start
for b in "$P"/p4/briefs/*.md; do echo "$b"; done | xargs -P 4 -I{} bash -c "$(declare -f run_session); L='$L'; HOME='$HOME'; run_session sol '$P/p4' '{}' low p4 probe-p4 2400 '$P/p4/logs'"
mark P4-end
cread post-p4

# Block P5
cread pre-p5
mark P5-start
for b in "$P"/p5/briefs/*.md; do echo "$b"; done | xargs -P 4 -I{} bash -c "$(declare -f run_session); L='$L'; HOME='$HOME'; run_session luna '$P/p5' '{}' low p5 probe-p5 2400 '$P/p5/logs'"
mark P5-end
cread post-p5

echo "probes2 done"
