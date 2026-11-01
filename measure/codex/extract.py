#!/usr/bin/env python3
"""Extract token_count events from Codex rollouts -> events.csv.gz + extract_report.json.
usage: extract.py SESSIONS_ROOT OUTDIR [--limit N] [--workers N]"""
import sys, os, json, gzip, csv, glob, collections, multiprocessing as mp, argparse

KEYS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
        "output_tokens", "reasoning_output_tokens")
COLS = ["ts_utc", "session_id", "originator", "cli_version", "model", "effort",
        "d_input", "d_cached", "d_cache_write", "d_output", "d_reasoning",
        "plan_type", "used_percent", "window_minutes", "resets_at",
        "sec_used_percent", "sec_window_minutes", "sec_resets_at",
        "limit_id", "delta_src", "cached_gt_input", "reasoning_gt_output"]

def tot(d):
    return tuple(int((d or {}).get(k) or 0) for k in KEYS)

def proc(path):
    c = collections.Counter()
    rows = []
    sid = os.path.basename(path); orig = ver = ""; model = effort = ""
    prev = None; prevkey = None
    try:
        f = open(path, "r", errors="replace")
    except Exception:
        c["skip_unreadable"] += 1
        return rows, c
    with f:
        for line in f:
            if '"token_count"' in line:
                kind = "tc"
            elif '"turn_context"' in line:
                kind = "tx"
            elif '"session_meta"' in line:
                kind = "sm"
            else:
                continue
            try:
                o = json.loads(line)
            except Exception:
                c["bad_json"] += 1
                continue
            p = o.get("payload") or {}
            t = o.get("type")
            if kind == "sm" and t == "session_meta":
                sid = p.get("id") or sid
                orig = p.get("originator") or ""
                ver = p.get("cli_version") or ""
            elif kind == "tx" and t == "turn_context":
                model = p.get("model") or model
                effort = p.get("effort") or effort
            elif kind == "tc" and t == "event_msg" and p.get("type") == "token_count":
                c["tc_events"] += 1
                info = p.get("info"); rl = p.get("rate_limits")
                if not info:
                    c["info_null"] += 1
                if not rl:
                    c["rl_null"] += 1
                    continue          # no meter reading -> useless for fit
                prim = rl.get("primary")
                if not prim:
                    c["primary_null"] += 1
                    continue
                sec = rl.get("secondary") or {}
                d = (0,) * 5; src = "none"; cg = rg = 0
                if info:
                    tt = info.get("total_token_usage"); lt = info.get("last_token_usage")
                    cur = tot(tt) if tt else None
                    if cur is not None:
                        cg = int(cur[1] > cur[0]); rg = int(cur[4] > cur[3])
                    lcur = tot(lt) if lt else None
                    key = (cur, lcur)
                    if cur is not None and key == prevkey:
                        d = (0,) * 5; src = "dup"       # identical re-emission
                    elif cur is not None and lcur is not None and cur == lcur:
                        # total == last: in many files total_token_usage is per-call, not cumulative
                        d = lcur; src = "total_eq_last"; prev = cur
                    elif cur is not None and prev is not None and all(a >= b for a, b in zip(cur, prev)):
                        d = tuple(a - b for a, b in zip(cur, prev)); src = "total"
                        prev = cur
                    elif cur is not None and prev is None:
                        d = cur; src = "total_first"; prev = cur
                    else:
                        c["totals_missing" if cur is None else "totals_backwards"] += 1
                        if lt:
                            d = tot(lt); src = "last"
                        if cur is not None:
                            prev = cur
                    prevkey = key
                    c["src_" + src] += 1
                    c["cached_gt_input"] += cg; c["reasoning_gt_output"] += rg
                    c["n_with_info"] += 1
                    if cur is None and not lt: c["info_no_usage"] += 1
                rows.append((o.get("timestamp"), sid, orig, ver, model, effort, *d,
                             rl.get("plan_type"), prim.get("used_percent"),
                             prim.get("window_minutes"), prim.get("resets_at"),
                             sec.get("used_percent"), sec.get("window_minutes"), sec.get("resets_at"),
                             rl.get("limit_id"), src, cg, rg))
    c["files_ok"] += 1
    if not rows:
        c["files_no_rows"] += 1
    return rows, c

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root"); ap.add_argument("out")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    files = sorted(glob.glob(os.path.join(a.root, "*", "*", "*", "rollout-*.jsonl")))
    if a.limit:
        files = files[-a.limit:]
    tot_c = collections.Counter(); models = collections.Counter(); nrows = 0
    pcts_frac = 0; pcts = 0
    with gzip.open(os.path.join(a.out, "events.csv.gz"), "wt", newline="") as g:
        w = csv.writer(g); w.writerow(COLS)
        with mp.Pool(a.workers) as pool:
            for rows, c in pool.imap_unordered(proc, files, chunksize=16):
                tot_c.update(c)
                for r in rows:
                    w.writerow(r); nrows += 1
                    models[r[4]] += 1
                    if r[12] is not None:
                        pcts += 1; pcts_frac += (float(r[12]) != int(float(r[12])))
    rep = {"files_found": len(files), "events_written": nrows, "counters": dict(tot_c),
           "rows_by_model": dict(models), "used_percent_readings": pcts,
           "used_percent_fractional": pcts_frac}
    json.dump(rep, open(os.path.join(a.out, "extract_report.json"), "w"), indent=1)
    print(json.dumps(rep, indent=1))

if __name__ == "__main__":
    main()
