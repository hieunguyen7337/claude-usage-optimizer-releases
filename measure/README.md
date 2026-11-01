# Re-running the meter measurements

Python 3.9, stdlib only for extraction and fitting. Probe drivers require Bash, GNU coreutils, jq, the kit's `lane` and `usage-status`, and authenticated provider CLIs. Probe drivers spend real allowance and create files. Never run near a limit. Other devices and cloud sessions on the same account move the meter without creating local evidence. A Fable call opens Fable's capped weekly window.

## Aligning meter readings

An account reading reports `used_percentage`. The statusline records the value from its latest response, so it
freezes between responses from that writing session even while other sessions spend. In the 2026-10-17 data,
the reading stayed at 1% from 13:54 to 14:55 while about 30 other sessions used the account; one generated
201,000 output tokens in that span. It jumped to 10% at 14:56:02 when the writing session responded.

The aligned rule treats a reading as reflecting use up to that session's last response, with 5 seconds of
slack and never earlier than the previous reading. The naive rule treats it as reflecting use up to its write
time. Alignment lowers the five-hour H1 residual sum of squares from 1356.8 to 1169.9 (−14%) and changes the
best model by Akaike information criterion from H3 (separate weights for cache writes, cache reads and output)
to H1 (all token types charged at list price). It changes the cumulative step estimate by under
0.5%. On the weekly meter, H1 residual sum of squares gets slightly worse, 207.1 to 210.5, so that result
does not settle the weekly estimate.

## Method

Run controlled blocks between two meter readings, keeping unrelated account activity idle. Whole-percent readings mean the true rise is in (Δ−1, Δ+1) points for positive Δ and [0,1) for Δ=0. For cost C and positive Δ, cost per 1% is C/Δ, with interval (C/(Δ+1), C/(Δ−1)); the upper bound is unbounded at Δ=1. At Δ=0 there is only a lower bound C and no point estimate. Multiply by 100 for the full window. Reject resets or backwards readings rather than fitting across them. These are rounding bounds, not confidence intervals.

H1 charges every token type at list. H2 sets cache reads free. Compare meter consumed per list dollar to an anchor block: factor = anchor dollars/point divided by model dollars/point. Sonnet C2 anchors Claude; astra P1–P3 anchor Codex. Solve cache weight by interpolating each block's cost as H2+w(H1−H2), equating its ratio to the meter-rise ratio and intersecting the rounding constraints with w in [0,1].

Extractors read usage metadata only and never export transcript content. Their local outputs contain session identifiers; keep all raw outputs private. Only publish reviewed aggregates. Fitting attributes all local traffic between readings, with probe-only attribution shown separately for Claude.

## Paths and commands, in order

Run from the kit root. Defaults: `MEASURE_DIR=~/.local/state/lanes/measure`, `CLAUDE_BIN=claude`, and `CODEX_BIN=~/.config/lanes/bin/codex` (falls back to `codex` on PATH). `LANE_BIN` and `STATUS_BIN` override the installed kit tools. Drivers export `USAGE_OPTIMIZER_CODEX_BIN` for meter reads and create a measurement-local `LANES_CONFIG/bin` symlink for worker binary selection. `RUNS_DIR` selects the run ledger (default `~/.local/state/lanes/runs`). `CLAUDE_USAGE_DIR` selects the meter cache. Use a fresh measurement directory for each run to avoid mixing marks.

```bash
export MEASURE_DIR="$HOME/.local/state/lanes/measure"
export CLAUDE_BIN=claude
export CODEX_BIN="$HOME/.config/lanes/bin/codex"
# Preparation only, then the spending run. P1–P5 run sequentially.
bash measure/codex/run_probes.sh --prep-only
bash measure/codex/run_probes.sh
# C4 requires your own large text file. Any large text file works; none is shipped.
bash measure/claude/run_cprobes.sh --reference "$REFERENCE_FILE" --prep-only
bash measure/claude/run_cprobes.sh --reference "$REFERENCE_FILE"
# Extraction and fits, after the probes finish; run these on a compute node on HPC.
python3 measure/codex/extract.py "${CODEX_HOME:-$HOME/.codex}/sessions" "$MEASURE_DIR/codex/out"
python3 measure/codex/fit_probes.py
python3 measure/codex/fit.py "$MEASURE_DIR/codex/out/events.csv.gz" "$MEASURE_DIR/codex/out"
python3 measure/claude/extract.py --root "$HOME/.claude/projects" --out "$MEASURE_DIR/claude/out"
python3 measure/claude/analyze_cprobes.py
```

Set `REFERENCE_FILE` to a readable large text file before those commands. Do not use private project material if you plan to share probe briefs or logs. A reference of at least 400,000 bytes matches the original cached-input probe.

- Claude `meter_read.sh LABEL`: a tiny Haiku call; appends utilization, cost and usage to `claude/meter.jsonl` (about $0.003 per read; LIMITS.md:50).
- Claude `run_cprobes.sh`: C0 null test, C1 Haiku output, C2 Sonnet output, C3 Opus output, C4 cached input, C5 Fable output. Marks and readings bracket every block. The original guard stops at 75% 5h or 40% weekly; it is not a reservation against concurrent activity. `--start-after` accepts a UTC date.
- Claude `extract.py`: deduplicates response usage into `events.csv.gz` and `extract_report.json`; `--root`, `--out` and optional explicit files select inputs and outputs. `prices.json` carries list prices and Haiku prompt tiers.
- Claude `analyze_cprobes.py`: writes `derived.json` and `REPORT_C.md`, including H1/H2 rates, model factors, cache-weight solve and request-fee bounds. Override `CLAUDE_FIT_OUT`, `CLAUDE_MARKS`, `CLAUDE_METER`, `CLAUDE_PRICES`, `CLAUDE_EVENTS`, `CLAUDE_PROJECTS` as needed. Project attribution derives encoded project-directory suffixes from `MEASURE_DIR`.
- Codex `run_probes.sh`: merges the two original drivers, prepares generic P1/P4/P5 output briefs, builds P2 cached and P3 unique-input briefs from generated P1 prose, records meter readings and `marks.tsv`, then runs P4 sol and P5 luna. Worker parallelism is at most four.
- Codex `extract.py`: usage-only rollout extraction, with per-call versus cumulative token detection and deduplication; accepts sessions root and output directory, optional `--limit` and `--workers`.
- Codex `fit_probes.py`: block summaries, rise intervals and joint token-type fits in `codex/out/`. Override `CODEX_FIT_OUT`, `CODEX_EVENTS`, `CODEX_MARKS`, `CODEX_RATES`. The default rate card is `findings/findings.json`'s `rate_card`; `CODEX_RATES` also accepts the original standalone card format.
- Codex `fit.py`: passive weekly fits in `windows.csv`, `fit_a_b.csv`, `fit_c.csv`, `unknown_models.json`. Inputs are positional; `CODEX_RATES` selects the card.

## Cost and limits

The original C-series local block totals were $0.0475, $1.4781, $30.4989, $45.7066, $4.7409 and $27.1414 H1 list, totaling $109.6134 (about $110), not the task brief's approximate $135. Probe-only spend was smaller. Large output blocks C2/C3/C5 moved 5h by 12/17/22 points and weekly by 2/2/3; C0/C1/C4 moved much less. Budget conservatively: results depend on model verbosity and other traffic. [INFERRED sum; claude/probes_fit/REPORT_C.md:24–29]

P1–P4 cost 1,259.022 card credits; P5 added 14.573, for 1,273.595 overall (about 15% of the 8,400-credit week). The report's roughly 1,260 figure excludes P5. These are card costs, not necessarily the charged meter weights. [INFERRED sum; codex/probes/REPORT.md:53,186; LIMITS.md:14]

Port corrections: Claude's original JSON model factors were inverted relative to its report table; the port records meter weight. Codex's original 0.1-point floor invented finite upper bounds for zero/one-point blocks; the port emits null for an unbounded endpoint. All other estimators and output names are retained. Generic preparation replaces missing external P1 inputs. No reference text or raw account records are shipped.

## Rerunning the fits from the shipped data

`findings/limits/` holds de-identified data (see its README), so the fits can be rerun without the private raw extracts and without spending allowance. Run from the kit root, on a compute node on HPC, with Python 3.9+ and no other dependencies. `OUT` is any empty scratch directory.

```bash
D=findings/limits; OUT=./rerun; mkdir -p "$OUT"/claude "$OUT"/codex_probes

# Claude C0–C5: writes derived.json and REPORT_C.md
CLAUDE_FIT_OUT="$OUT/claude" CLAUDE_MARKS="$D/claude/marks.tsv" CLAUDE_METER="$D/claude/meter_readings.jsonl" \
  CLAUDE_EVENTS="$D/claude/events_cprobes.csv" CLAUDE_EXTRACT_REPORT="$D/claude/extract_report.json" \
  python3 measure/claude/analyze_cprobes.py

# Codex P1–P5: writes block_summary.{csv,json}, intervals.csv, joint_fit.json
CODEX_FIT_OUT="$OUT/codex_probes" CODEX_EVENTS="$D/codex/events_probes.csv" CODEX_MARKS="$D/codex/marks.tsv" \
  python3 measure/codex/fit_probes.py
```

What each reproduces:

- `analyze_cprobes.py` → Claude weekly $1,525 ($1,017–3,050) and 5h $254 ($235–277) from C2; Opus 0.95, Haiku 1.72 and Fable 2.06 on the 5h meter; Fable's $531 ($443–664) sub-cap; cache weight 0.36 (0–1); the request-fee bound. It reproduces the shipped `derived.json` exactly; the regenerated `REPORT_C.md` differs from the lab's only in the analysis job id.
- `fit_probes.py` → Codex Pro Lite block table (P1–P5), `intervals.csv`, `joint_fit.json` and `block_summary.*` identical to the shipped files (P5's cost-per-point range has no upper end, `inf`, since luna moved no whole point). The ≈ 8,400 credits (7,800–9,200) is arithmetic on `block_summary.csv`: P1–P3 card credits (`total_cr`, rows P1–P3, 1,010.711) divided by the 12-point rise (`first_up` 2 → `last_up` 14), with bounds at 13 and 11 points; P1–P4 pooled is 1,259.022 over 16 points = 7,869. The sol factors divide the P1–P3 pooled rate (84.226 credits per point) by P4's block rate `a` (62.078, factor 1.36) or its `b_step_rate` (70.771, factor 1.19).

Needs the private raw extracts (cannot be rerun from the bundle):

- The Codex passive weekly fit (`measure/codex/fit.py`) has no rerun command: the three Plus weeks' event file is 6.4 MB and stays in the lab, so `windows.csv`, `fit_a_b.csv` and `fit_c.csv` ship as tables only.
- The extractors (`measure/claude/extract.py`, `measure/codex/extract.py`) read session transcripts and rollouts.
- The Claude probe/rest split uses the shipped `probe_block` column; recomputing it needs the local project directories (the analyzer does so when `events.csv.gz` has a `session_id` column instead).
- The other 17 passive Codex weeks, `unknown_models.json` and the pooled Plus regression (n = 548 intervals, `pooled:plus` in `fit_c.csv`): the full passive events file is 2.1 MB trimmed and did not fit the size budget. Their results are shipped as tables only.
- The Fable-window reading (0 → 5%) is a recorded input (`claude/fable_window.json`); the analyzer hard-codes it.
- The superseded Claude passive estimate ($21–25 per 1% weekly) came from `claude/fit.py` on the full events file; it is neither shipped nor reproducible.
