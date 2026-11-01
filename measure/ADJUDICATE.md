# Adjudicate findings and extend a suite key

Use this procedure when precision looks low, or when a suite comes from real code that may contain bugs nobody planted. Adjudication classifies findings against code evidence, adds confirmed unplanted defects to an extended key, and lets later runs be graded without repeating the review.

## Procedure

Use one adjudication group per set of items. One adjudicator must see every finding on the items in that group so that duplicate findings can be clustered consistently. Use the briefs in `measure/adjudicate/`; each brief defines its inputs, outputs, and checks.

1. **Export the findings.** First grade the existing runs if there is no current summary, then export:

   ```sh
   lane-bench grade --suite <suite> [--arm NAME]... [--results-dir DIR]
   lane-bench export-findings --suite <suite> --summary <summary.json> [--arm NAME]... --out <findings.jsonl>
   jq -c . <findings.jsonl> > /dev/null
   ```

   Confirm the export row count against the findings represented by the selected runs and summary. `strict: false` marks salvaged rows from output files the strict parser rejected; retain those rows and their flag.

2. **Adjudicate in item groups** with [`adjudicate.md`](adjudicate/adjudicate.md). Each adjudicator sees every exported finding on their assigned items. Check that every finding has exactly one assignment, every new issue has an item-local id, and all JSONL outputs pass their listed `jq -c .` validators.

3. **Audit location matches** with [`matched-audit.md`](adjudicate/matched-audit.md). Audit findings initially matched by file and line. Check that every non-null `matched_defect` in the export has exactly one audit row, and that the `fid` and defect id agree.

4. **Blind-check the judgments** with a second model family using [`blind-check.md`](adjudicate/blind-check.md). Give it each adjudicator's own claim text and code evidence, but not the adjudicator's verdict, rationale, issue classification, or other judge's work. Check that its verdict rows cover the claim ids exactly once and validate its JSONL.

5. **Tie-break every real-versus-not-real dispute** with [`tiebreak.md`](adjudicate/tiebreak.md). The tie-breaker examines the issue and both judgments and uses a minimal reproducer for disputes about behavior or trigger reachability. Check that every disputed issue has one decision and a real reproducer result, or a specific reason reproduction cannot be run. A third opinion alone does not settle a dispute.

6. **Assemble final issue rows.** Combine the adjudicator's `issues.jsonl`, blind `verdicts.jsonl`, and tie-break `decisions.jsonl` by `issue_id`. The adjudicator's verdict is final when both families agree on whether the issue is `real`; when one says `real` and the other does not, use the tie-break's `final_verdict`. A compact `jq` recipe, with those files in the current directory, is:

   ```sh
   jq -s -c --slurpfile B verdicts.jsonl --slurpfile T decisions.jsonl '
     ($B | INDEX(.claim_id)) as $b | ($T | INDEX(.issue_id)) as $t
     | .[] | . as $x | $t[$x.issue_id] as $d
     | (if (($x.verdict == "real") == ($b[$x.issue_id].verdict == "real"))
        then $x.verdict else $d.final_verdict end) as $v
     | $x + {final_verdict:$v,
       scope:(if $v != "real" then null
              elif $x.verdict == "real" then $x.scope else $d.scope end),
       severity_judged:(if $v != "real" then null
                        elif $x.verdict == "real" then $x.severity_judged else $d.severity end)}
     | del(.verdict)' issues.jsonl > issues-final.jsonl
   jq -c . issues-final.jsonl > /dev/null
   ```

   Require a tie-break decision for every disagreement on real versus not real; there must be no missing blind rows, missing decisions, or unresolved issues. Keep the adjudicator's issue fields. For a tie-broken `real` issue, use the tie-break scope and severity if the adjudicator did not supply them. Validate the JSONL and confirm issue ids are unique.

7. **Rescore** using all finding exports for the suite, final assignments, final issues, matched audit, and any outcome files:

   ```sh
   lane-bench rescore --suite <suite> --findings <findings.jsonl> [--findings F]... \
     --assignments <assignments.jsonl> --issues <issues-final.jsonl> \
     --matched-audit <matched-audit.jsonl> [--outcomes O]... [--by-arm B] \
     [--seed N] [--resamples N] --out-dir <dir>
   ```

   Check that the command completes, generated JSON and JSONL parse, every finding is represented once, every assignment points to a new issue or planted defect, and every matched finding has one audit label. When `--by-arm` is supplied, confirm the v1 reproduction gate passes. Review `per-run.jsonl`, `by-arm-v2.json`, `by-arm-v2.md`, `cheapest.md`, `key-v2/`, and `outcomes-v2.jsonl`.

8. **Grade future runs with the extended key.** Copy the suite before changing its key. In that copy, replace each item's `defects.json` with the corresponding `key-v2/<item>.json`, then grade the future runs:

   ```sh
   lane-bench grade --suite <suite-copy> [--arm NAME]... [--results-dir DIR]
   jq -e 'all(.[]; has("origin"))' <suite-copy>/items/<item>/defects.json > /dev/null
   ```

   Each extended key entry has `origin: planted` or `origin: unplanted`; omitted origin means planted. Check `summary.json`: recall is over planted entries only; a finding matched to an unplanted entry is correct for precision and appears in `real_found`.

## Command and data contract

- `grade --suite <suite> [--arm NAME]... [--results-dir DIR]` writes `summary.json`. A key entry may set `origin` to `planted` or `unplanted`; recall counts planted entries only. Matching an unplanted entry is correct for precision and is listed in `real_found`.
- `export-findings` emits one JSONL row per finding with `{fid, arm, lane, effort, rep, item, kind, finding_index, file, line, severity, description, matched_defect, strict}`. `fid` is `<arm>:<item>:<finding_index>`. Rows salvaged from a file rejected by the strict parser have `strict: false`.
- `rescore` reads issues `{issue_id, file, line, line_end, final_verdict, scope, severity_judged}`, where `final_verdict` is `real`, `speculative`, `wrong`, or `not_a_defect`; assignments `{fid, issue_id}`, where `issue_id` is a new `<item>:U<n>` or planted `<item>:D<k>`; and matched audit `{fid, label}`, where `label` is `describes`, `partial`, or `other_issue`.
- `rescore` writes `per-run.jsonl`, `by-arm-v2.json`, `by-arm-v2.md`, `cheapest.md`, `key-v2/<item>.json` (the extended key with planted and real unplanted bugs, each with `origin`), and `outcomes-v2.jsonl`. `--by-arm` checks that the old scoring reproduces the supplied v1 table; make that table from the same outcome files (`lane-bench summary --outcomes …`), because every arm in the outcomes must appear in it.
- To calculate usable priors from the new outcome flag, run `lane-bench priors --outcomes <outcomes-v2.jsonl> --score v2`.

## Verdicts and matched-audit labels

- `real`: a correctness defect with a concrete, reachable trigger that produces a wrong result, crash, data loss, silently skipped step, wrong file, or broken caller/test contract. Cite the relevant post-change file and line and state the trigger.
- `speculative`: the concern depends on an assumption unsupported by code, callers, tests, or docs, or has no reachable trigger.
- `wrong`: the finding's factual claim about the code is false; cite the line that refutes it.
- `not_a_defect`: the description is accurate, but behavior is acceptable, such as a style, naming, documentation, missing-test, performance-without-result-effect, or design preference concern.

For a `real` issue, record `scope` as `in_diff`, `touched_unchanged`, or `untouched_file`; give the smallest `line`–`line_end` range a fix would change, any additional sites in `also_at`, and `severity_judged` as `high`, `medium`, or `low`. Assign findings that describe a planted defect to its planted id, even when outside the matching window or reported more than once. Cluster new findings into one issue when one fix resolves them.

For each location-matched finding, use exactly one label:

- `describes`: names the planted defect's wrong behavior or cause, including in different words or with a different suggested fix.
- `partial`: points at the defective line or symptom but misstates what is wrong.
- `other_issue`: describes a different problem that happens to be within the location window.

## Cost and lessons from one adjudication

- This one took about 17% of a Codex Pro Lite week and $5.50 at Claude list price for 867 findings.
- A location match can describe another problem: this happened 23 times among 2,245 matches.
- The blind checker was overruled by reproducers 23 of 26 times; settle disputes by running code, not by taking a third opinion.
- If the tie-breaker shares the adjudicator's model family, require every decision to rest on a reproducer's output.
- Grading with the extended key agreed with adjudication on 93.4% of findings, so later runs need no new adjudication.
