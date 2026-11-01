#!/usr/bin/env python3
"""U2 step 1: one row per deduplicated API response from Claude Code transcripts.

Stdlib only, Python 3.9 compatible. Reads only the usage fields the brief names (timestamp,
requestId, isSidechain, sessionId, requestedModel, message.id, message.model, message.usage.*).
Never writes message text, content or tool output anywhere.

Full run (inside a PBS job; the transcript tree is about 6 GB):
  python3 -I extract.py --out "$MEASURE_DIR/claude/out"

Probe run (a few files, for checking the code):
  python3 -I extract.py --out /tmp/u2probe FILE [FILE ...]      (files must sit under --root)

Outputs in --out:
  events.csv.gz        one row per deduplicated response (ts_utc, kind, model, token types, ...)
  extract_report.json  counts for the data-quality section of REPORT.md
"""
import argparse
import collections
import csv
import gzip
import json
import os
import time

PREFILTER = b'"type":"assistant"'
SYNTHETIC = "<synthetic>"
COLUMNS = ["ts_utc", "file_kind", "depth", "is_sidechain", "model", "requested_model",
           "speed", "service_tier", "input", "cw5m", "cw1h", "cache_read", "output",
           "server_tool_calls", "session_id", "n_lines"]


def tok(v):
    """A token count. Anything missing or not a plain integer counts as 0."""
    return v if isinstance(v, int) and not isinstance(v, bool) else 0


def classify(rel):
    """(file_kind, depth) for a path relative to the projects root.

    depth 2 = <project>/<session>.jsonl                        -> main
    depth 4 = <project>/<session>/subagents/agent-*.jsonl      -> subagent
    depth 6 = <project>/<session>/subagents/workflows/wf_*/... -> subagent (workflow)
    anything else                                              -> other
    """
    parts = rel.split("/")
    if len(parts) == 2:
        return "main", 2
    if "subagents" in parts[:-1]:
        return "subagent", len(parts)
    return "other", len(parts)


def find_jsonl(root):
    found = []
    for dp, _dirs, names in os.walk(root):
        for name in names:
            if name.endswith(".jsonl"):
                found.append(os.path.join(dp, name))
    return sorted(found)


def main():
    ap = argparse.ArgumentParser(description="U2 extract: deduplicated API responses")
    ap.add_argument("--root", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-files", type=int, default=0, help="probe only: keep the first N files")
    ap.add_argument("files", nargs="*", help="probe only: explicit transcript files under --root")
    args = ap.parse_args()

    t0 = time.time()
    root = os.path.abspath(os.path.expanduser(args.root))
    files = [os.path.abspath(p) for p in args.files] or find_jsonl(root)
    if args.max_files:
        files = files[: args.max_files]
    os.makedirs(args.out, exist_ok=True)

    rep = collections.Counter()
    kinds = collections.Counter()           # (file_kind, depth) -> files
    seen = {}                               # (message.id, requestId) -> record
    anon = []                               # rows with no message.id: kept, not deduplicable

    for path in files:
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        kind, depth = classify(rel)
        kinds[(kind, depth)] += 1
        rep["files"] += 1
        try:
            fh = open(path, "rb")
        except OSError:
            rep["open_errors"] += 1
            continue
        stem = os.path.basename(path)[: -len(".jsonl")]
        with fh:
            for raw in fh:
                rep["lines"] += 1
                if PREFILTER not in raw:
                    continue
                rep["assistant_candidates"] += 1
                try:
                    obj = json.loads(raw)
                except ValueError:
                    rep["parse_errors"] += 1
                    continue
                if not isinstance(obj, dict) or obj.get("type") != "assistant":
                    rep["prefilter_false_positive"] += 1
                    continue
                msg = obj.get("message")
                usage = msg.get("usage") if isinstance(msg, dict) else None
                if not isinstance(usage, dict):
                    rep["no_usage"] += 1
                    continue
                model = msg.get("model") or "(none)"
                if model == SYNTHETIC:
                    rep["synthetic_excluded"] += 1
                    continue

                ts = obj.get("timestamp")
                if not isinstance(ts, str) or not ts:
                    rep["no_timestamp"] += 1
                    ts = ""
                speed = usage.get("speed")
                if not isinstance(speed, str):
                    speed = "(absent)"
                    rep["speed_absent"] += 1
                tier = usage.get("service_tier")
                tier = tier if isinstance(tier, str) else "(absent)"
                req_model = obj.get("requestedModel")
                req_model = req_model if isinstance(req_model, str) else "(absent)"

                inp = tok(usage.get("input_tokens"))
                cr = tok(usage.get("cache_read_input_tokens"))
                out = tok(usage.get("output_tokens"))
                cc_total = tok(usage.get("cache_creation_input_tokens"))
                cc = usage.get("cache_creation")
                if isinstance(cc, dict) and ("ephemeral_5m_input_tokens" in cc
                                             or "ephemeral_1h_input_tokens" in cc):
                    cw5 = tok(cc.get("ephemeral_5m_input_tokens"))
                    cw1 = tok(cc.get("ephemeral_1h_input_tokens"))
                    if cw5 + cw1 != cc_total:
                        rep["cache_creation_split_mismatch"] += 1
                else:
                    cw5, cw1 = cc_total, 0
                    if cc_total:
                        rep["cache_creation_unsplit_assumed_5m"] += 1

                its = usage.get("iterations")
                if isinstance(its, list) and its:
                    rep["iterations_lines"] += 1
                    dicts = [i for i in its if isinstance(i, dict)]
                    if len(dicts) > 1:
                        rep["iterations_multi"] += 1
                    sums = [sum(tok(i.get(k)) for i in dicts) for k in
                            ("input_tokens", "output_tokens",
                             "cache_read_input_tokens", "cache_creation_input_tokens")]
                    if sums != [inp, out, cr, cc_total]:
                        rep["iterations_sum_mismatch"] += 1
                if usage.get("fallback_credit") is not None:
                    rep["fallback_credit_nonnull"] += 1
                stu = usage.get("server_tool_use")
                srv = sum(tok(v) for v in stu.values()) if isinstance(stu, dict) else 0
                if srv:
                    rep["server_tool_calls_lines"] += 1

                sid = obj.get("sessionId")
                sid = sid if isinstance(sid, str) and sid else stem
                # Everything except output_tokens and speed, which are merged separately below.
                nonout = (inp, cw5, cw1, cr, cc_total, srv, tier, model, req_model)
                rec = {
                    "ts": ts, "kind": kind, "depth": depth,
                    "side": int(bool(obj.get("isSidechain"))),
                    "model": model, "req": req_model, "speed": speed, "tier": tier,
                    "input": inp, "cw5m": cw5, "cw1h": cw1, "cache_read": cr, "output": out,
                    "srv": srv, "session": sid, "n_lines": 1, "file": path, "nonout": nonout,
                }

                mid = msg.get("id")
                if not isinstance(mid, str) or not mid:
                    rep["no_message_id"] += 1
                    anon.append(rec)
                    continue
                key = (mid, obj.get("requestId") or "")
                prev = seen.get(key)
                if prev is None:
                    seen[key] = rec
                    continue
                # A streamed response is logged once per content block, and the copies repeat
                # the message's usage. Only the final copy carries the final output_tokens, so
                # keep the copy with the most output (ties: the latest line) and take speed from
                # any copy that reports it.
                rep["duplicate_lines_removed"] += 1
                prev["n_lines"] += 1
                if prev["file"] != path:
                    rep["duplicate_cross_file"] += 1
                if prev["nonout"] != nonout:
                    rep["duplicate_nonoutput_differs"] += 1
                if prev["output"] != out:
                    rep["duplicate_output_differs"] += 1
                if prev["speed"] != speed:
                    rep["duplicate_speed_differs"] += 1
                if (out, ts) > (prev["output"], prev["ts"]):
                    keep, other = rec, prev
                else:
                    keep, other = prev, rec
                if keep["speed"] == "(absent)":
                    keep["speed"] = other["speed"]
                keep["n_lines"] = prev["n_lines"]
                seen[key] = keep

        if rep["files"] % 100 == 0:
            print("progress: files=%d lines=%d elapsed=%.0fs" %
                  (rep["files"], rep["lines"], time.time() - t0), flush=True)

    rows = list(seen.values()) + anon
    rows.sort(key=lambda r: (r["ts"] == "", r["ts"], r["file"]))

    agg = {k: collections.Counter() for k in
           ("rows_by_kind", "rows_by_model", "rows_by_requested_model", "rows_by_speed",
            "rows_by_service_tier")}
    tokens = collections.defaultdict(collections.Counter)   # model -> token-type sums
    tokens_nonstd = collections.defaultdict(collections.Counter)
    out_csv = os.path.join(args.out, "events.csv.gz")
    with gzip.open(out_csv, "wt", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(COLUMNS)
        for r in rows:
            w.writerow([r["ts"], r["kind"], r["depth"], r["side"], r["model"], r["req"],
                        r["speed"], r["tier"], r["input"], r["cw5m"], r["cw1h"],
                        r["cache_read"], r["output"], r["srv"], r["session"], r["n_lines"]])
            agg["rows_by_kind"][r["kind"]] += 1
            agg["rows_by_model"][r["model"]] += 1
            agg["rows_by_requested_model"][r["req"]] += 1
            agg["rows_by_speed"][r["speed"]] += 1
            agg["rows_by_service_tier"][r["tier"]] += 1
            tgt = tokens if r["speed"] in ("standard", "(absent)") else tokens_nonstd
            t = tgt[r["model"]]
            t["input"] += r["input"]
            t["cw5m"] += r["cw5m"]
            t["cw1h"] += r["cw1h"]
            t["cache_read"] += r["cache_read"]
            t["output"] += r["output"]

    stamps = [r["ts"] for r in rows if r["ts"]]
    report = {
        "root": root,
        "files": rep["files"],
        "files_by_kind_depth": {"%s@depth%d" % kd: n for kd, n in sorted(kinds.items())},
        "lines": rep["lines"],
        "assistant_candidates": rep["assistant_candidates"],
        "parse_errors": rep["parse_errors"],
        "prefilter_false_positive": rep["prefilter_false_positive"],
        "no_usage": rep["no_usage"],
        "synthetic_excluded_lines": rep["synthetic_excluded"],
        "keyed_responses": len(seen),
        "unkeyed_rows_no_message_id": len(anon),
        "duplicates_removed": rep["duplicate_lines_removed"],
        "duplicates_cross_file": rep["duplicate_cross_file"],
        "duplicates_output_differs": rep["duplicate_output_differs"],
        "duplicates_speed_differs": rep["duplicate_speed_differs"],
        "duplicates_nonoutput_differs": rep["duplicate_nonoutput_differs"],
        "rows_written": len(rows),
        "no_timestamp_rows": rep["no_timestamp"],
        "ts_min": min(stamps) if stamps else None,
        "ts_max": max(stamps) if stamps else None,
        "speed_absent_rows_before_dedupe": rep["speed_absent"],
        "cache_creation_split_mismatch": rep["cache_creation_split_mismatch"],
        "cache_creation_unsplit_assumed_5m": rep["cache_creation_unsplit_assumed_5m"],
        "iterations_lines": rep["iterations_lines"],
        "iterations_multi": rep["iterations_multi"],
        "iterations_sum_mismatch": rep["iterations_sum_mismatch"],
        "fallback_credit_nonnull_lines": rep["fallback_credit_nonnull"],
        "server_tool_calls_lines": rep["server_tool_calls_lines"],
        "rows_by_kind": dict(agg["rows_by_kind"]),
        "rows_by_model": dict(agg["rows_by_model"]),
        "rows_by_requested_model": dict(agg["rows_by_requested_model"]),
        "rows_by_speed": dict(agg["rows_by_speed"]),
        "rows_by_service_tier": dict(agg["rows_by_service_tier"]),
        "token_sums_standard_by_model": {m: dict(c) for m, c in sorted(tokens.items())},
        "token_sums_nonstandard_by_model": {m: dict(c) for m, c in sorted(tokens_nonstd.items())},
        "elapsed_s": round(time.time() - t0, 1),
    }
    with open(os.path.join(args.out, "extract_report.json"), "w") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
    print("wrote %s (%d rows) and extract_report.json in %.0fs" %
          (out_csv, len(rows), time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
