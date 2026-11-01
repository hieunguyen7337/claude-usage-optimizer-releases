# Review suites for `lane-bench`

A review suite is a set of diffs with known planted defects. `bin/lane-bench` runs every arm of a lane
against it, scores each review, and turns the scores into recall, false-alarm, cost and priors numbers.
The kit ships the tools, not the items. A suite is built and kept by the project that owns the code.

## Layout

```
<suite>/
  suite.json              optional; {"name", "class", "window"}
  review_brief.md         the brief template; must contain {{ITEM_PATH}}
  items/NNN/diff.patch    the change under review (-U20 is what the builds used)
  items/NNN/post/         the full post-change files the reviewer may read
  items/NNN/defects.json  list of {id, file, line, line_end, type, description, origin}; [] marks a control
  items/NNN/meta.json     provenance for the builder; the tools do not read it
  runs/<arm>/NNN/         written by `lane-bench run`
  results/                written by grade, stats, compare and run
  failed_runs/            failed or partial workspaces moved aside by `run --resume`
```

`suite.json` is optional. Without it the name is the folder name, the class is `review` and the window is 5.

- `name` is the ledger tag (`--tag`). It must match `^[a-zA-Z0-9][a-zA-Z0-9._-]*$`.
- `class` is the lane class (`mechanical`, `substantive`, `hard`, `design`, `review`, `research`). Priors are
  written under it.
- `window` is the matching window in lines (default 5).

Only `diff.patch` and `post/` are copied into a run's workspace, with any `__pycache__` removed. `defects.json`
and `meta.json` never reach the reviewer.

`origin` is optional and defaults to `planted`. Use `"origin": "unplanted"` for a real bug added to the answer key
after adjudication. Both origins participate in the same file/window one-to-one matching. Only planted entries count
toward recall; unplanted matches remain matched findings for precision and are reported as `real_found`. How to
find and confirm them: `ADJUDICATE.md`.

## Run layout and records

`runs/<arm>/<NNN>/` holds `diff.patch`, `post/`, `review_brief.md`, `lane.log`, `lane.exit`, `findings.jsonl`
and `run.json`.

- The arm name is `<lane>-<effort>[-<model>][-r<rep>]`. The model is the raw model string with `/` replaced by
  `__`. Replicate 1 has no suffix; replicate 2 is `-r2`.
- `findings.jsonl` has one `{file, line, severity, description}` per line. `severity` is `high`, `medium` or
  `low`. A file with no lines is a review that found nothing. The grader reads it as `utf-8-sig`, so a leading
  byte-order mark is accepted: Windows PowerShell's `Set-Content -Encoding UTF8` writes one, and on 2026-10-28
  103 of terra's 116 files had it and first scored as missing.
- Ask for a read-back in `review_brief.md`: the worker reads `findings.jsonl` back before it finishes. A Codex
  worker on Windows that took a command's early, empty return as done ended its turn before writing, and 4 of
  24 files were lost in terra's first pass (LANES.md, Orchestration lessons). Before you grade, count the items without a file and
  read their `lane.log`: a missing file is a harness question before it is a model score.
- `lane.exit` holds the lane's exit code. `run.json` holds `{lane_run_dir, started_at, ended_at, exit}`.
  `lane_run_dir` is the ledger run, whose `meta.json` carries usage, verdict and duration. A gated skip has
  `exit` 75 and `"skipped": "codex weekly"`.

## Building a suite

Planted defects are the part that needs care. Three rules apply to every key.

**R1. Every key covers an added line.** Each `[line, line_end]` in `defects.json` must overlap at least one `+`
line of `diff.patch`, in post-image line numbers. A planted deletion counts when the `+` or context line where the
deleted code was lies within 2 lines. A key on an unchanged context line describes old code the diff never
touches, so the reviewer cannot be expected to find it from the change. Check every item with a script and
replant any failing key.

**R2. No plant advertised by a comment.** No comment within 5 lines of a key, and no docstring, comment or test
added by the same patch, may state the correct value or describe the defect. Do not edit or delete the commit's
own comments to hide a plant. Move the plant to a different changed line in the same item.

**R3. The matching window is clear of comments that point at the defect.** For each key, the window
`[line - window, line_end + window]` must not contain (a) a comment line that names a defect, bug, fix,
off-by-one, regression or earlier wrong behaviour, or (b) the code line such a comment describes. Check with a
keyword list, then review every hit by hand and record the verdict per key. A reviewer who repeats a comment
should not earn credit for the defect it describes.

Two more constraints keep the scores comparable:

- **Controls.** An item with `defects.json` equal to `[]` is a control. A control has no planted defect, so
  every finding on it is a false alarm. Keep some controls in every suite.
- **Coverage.** Use a spread of defect categories, each at least twice, and keep the number of defects per
  planted item small (one to three). This is guidance for the builder, and nothing in the tools checks it.

Plant on realistic, changed lines. The defect must be findable from the diff and the post-change files, which
are the only context the reviewer gets.

## How findings are scored

- A finding matches a defect when it is in the same file and its line falls in
  `[defect.line - window, defect.line_end + window]`. The file must match exactly, as a repo-relative path.
- Matching is one-to-one and maximal. One finding cannot credit two defects, and one defect cannot take two
  findings. Duplicate reports that cannot match a separate defect are unmatched findings.
- Recall is over every defect in the suite. A missing `findings.jsonl` scores as zero findings. Findings are
  scored whatever the lane exit, and the exit is reported beside them.
- False alarms are unmatched findings. They are reported suite-wide, where a missing review counts as zero,
  and completed-only, which excludes missing reviews and nonzero exits.
- An item is **usable** when a planted item has at least one matched defect and no more than two unmatched
  findings, or a control has at most one unmatched finding. An item with no `findings.jsonl` is never usable.
- Wilson 95% intervals are reported for recall. A per-item bootstrap (2,000 resamples, seed 1) is reported beside
  them.

## Commands

```sh
bin/lane-bench run   --suite DIR --arm luna:high --arm haiku:low:claude-haiku-5-5 [--arms-file F] [--rep 2]
                     [--items 001,002] [--par 4] [--slots 2] [--timeout 1800] [--resume] [--no-grade]
                     [--codex-7d PCT] [--codex-at-limit skip|wait] [--codex-wait-max-h HOURS]
                     --approved NOTE
bin/lane-bench grade --suite DIR [--arm NAME ...] [--results-dir DIR]     # results/summary.{json,md}
bin/lane-bench stats --suite DIR [--arm NAME ...] [--ledger DIR] [--arms-json PATH] [--codex-home DIR] [--results-dir DIR]
bin/lane-bench compare --suite DIR [--arm NAME ...] [--public FILE] [--results-dir DIR]   # results/compare.{json,md}
bin/lane-bench priors --suite DIR [--min-items 30] [--write arms.local.json]
bin/lane-bench export --suite DIR --out FILE [--summary FILE] [--arm NAME ...] [--arms-json PATH]   # de-identified per-run outcomes, JSONL
bin/lane-bench panels --suite DIR [--arm NAME ...] [--arms-json PATH] [--max-size 3] [--results-dir DIR]   # results/panels.{json,md}
bin/lane-bench replicates --suite DIR [--holdout-max-rep 2] [--arm NAME ...] [--arms-json PATH] [--out-dir DIR]   # replicates.{json,md}
bin/lane-bench summary (--suite DIR | --outcomes FILE) [--public FILE] [--arms-json PATH] [--arm NAME ...] [--out-dir DIR]   # by-arm.{json,md}
bin/lane-bench grade --selftest
```

`run` is a capability test: it spends window on items nobody needs. Run it only after the user approves that run, and pass `--approved "<who, when>"`. Without it `run` exits 2 and launches nothing. `grade`, `stats`, `compare`, `priors`, `export`, `panels`, `replicates` and `summary` only read results and spend nothing.

`run` gates every launch. It waits for task headroom under the user's pids slice (150 for codex lanes, 40
otherwise), spaces launches six seconds apart, waits for the Claude 5h and 7d windows to fall below their
ceilings (75% and 65% by default), and checks Codex weekly usage against 96% by default. A high Codex reading
forces a live refresh before either mode acts. `--codex-at-limit skip` (the default) skips if the refreshed
reading is still at the ceiling; `wait` checks every 300 seconds until the weekly reset or a redeemed reset
credit lowers usage. A missing reading counts as zero in skip mode and as at the ceiling in wait mode.
`--codex-wait-max-h HOURS` limits one wait; zero means no limit, and reaching the limit skips the item with the
reason recorded in `run.json`. Every external binary can be replaced with `LANE_BENCH_LANE`,
`LANE_BENCH_USAGE_STATUS` and `LANE_BENCH_CLAUDE`.

`priors --write` updates only arms the catalog already lists, by (lane, model, effort). It never adds
`prior_*` keys, and it keeps every other field in the file.

## Public numbers

`findings/public.json` lists public benchmark values per model and effort, with the source and date. Each row
is `{lane, model, effort, metric, value, source, date, url}`. The shipped file quotes the Artificial Analysis
coding-agent index v1.5 as recorded in `POLICY.md` on 2026-10-17. `compare` reports rank correlations with
our recall, and the arms whose public order differs from ours while their recall intervals do not overlap.
