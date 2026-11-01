#!/usr/bin/env python3
"""fit_probes.py - Fit the Codex weekly meter on controlled probe blocks P1-P5.
Stdlib python only. Rerun with: ~/bin/hpc-py fit_probes.py
"""
import sys
import os
import csv
import gzip
import json
import math
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.expanduser(os.environ.get("MEASURE_DIR", "~/.local/state/lanes/measure"))
OUT_DIR = os.environ.get("CODEX_FIT_OUT", BASE + "/codex/out")
RATES_PATH = os.environ.get("CODEX_RATES", os.path.join(HERE, "..", "..", "findings", "findings.json"))
MARKS_PATH = os.environ.get("CODEX_MARKS", BASE + "/codex/marks.tsv")
EVENTS_PATH = os.environ.get("CODEX_EVENTS", OUT_DIR + "/events.csv.gz")
R = json.load(open(RATES_PATH))
R = R.get("rate_card", R)
RATES = R["models"]
USD_PER_CREDIT = R.get("usd_per_credit", 0.04)

BLOCK_MODELS = {
    "P1": "gpt-6-astra",
    "P2": "gpt-6-astra",
    "P3": "gpt-6-astra",
    "P4": "gpt-6.1-sol",
    "P5": "gpt-6-luna",
}


def quantization(cost, delta):
    """Rise bracket and cost/point endpoints; None is an unbounded upper end."""
    if cost < 0 or delta < 0:
        raise ValueError("negative cost, meter reset or backwards reading")
    lower, upper = max(0.0, delta - 1.0), delta + 1.0
    return (lower, upper), (cost / upper, cost / lower if lower > 0 else None)

def ols_no_intercept(X, y):
    """OLS with no intercept: y = X * beta.
    Returns (beta, se, n, dof) or None.
    """
    n, k = len(y), len(X[0])
    if n <= k:
        return None
    A = [[sum(X[i][a] * X[i][b] for i in range(n)) for b in range(k)] for a in range(k)]
    B = [sum(X[i][a] * y[i] for i in range(n)) for a in range(k)]
    
    # Invert A via Gauss-Jordan
    M = [r[:] + [1.0 if i == j else 0.0 for j in range(k)] for i, r in enumerate(A)]
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-18:
            return None
        M[c], M[p] = M[p], M[c]
        d = M[c][c]
        M[c] = [v / d for v in M[c]]
        for r in range(k):
            if r != c:
                f = M[r][c]
                M[r] = [a - f * b for a, b in zip(M[r], M[c])]
    inv = [r[k:] for r in M]
    coef = [sum(inv[a][b] * B[b] for b in range(k)) for a in range(k)]
    rss = sum((y[i] - sum(coef[a] * X[i][a] for a in range(k))) ** 2 for i in range(n))
    s2 = rss / (n - k)
    se = [math.sqrt(max(s2 * inv[a][a], 0.0)) for a in range(k)]
    return coef, se, n, n - k

def ols_with_intercept(x, y):
    """Simple 1D linear regression with intercept: y = slope * x + intercept.
    Returns (slope, intercept, se_slope, r2)
    """
    n = len(x)
    if n < 2:
        return None
    mx = sum(x) / n
    my = sum(y) / n
    sxx = sum((xi - mx) ** 2 for xi in x)
    syy = sum((yi - my) ** 2 for yi in y)
    sxy = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    if sxx < 1e-18:
        return None
    slope = sxy / sxx
    intercept = my - slope * mx
    rss = sum((yi - (slope * xi + intercept)) ** 2 for xi, yi in zip(x, y))
    s2 = rss / (n - 2) if n > 2 else 0.0
    se = math.sqrt(s2 / sxx) if sxx > 0 and s2 >= 0 else 0.0
    r2 = (sxy ** 2) / (sxx * syy) if sxx * syy > 0 else 1.0
    return slope, intercept, se, r2

def parse_iso(ts):
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("=== Codex Probe Calibration Analysis ===")
    
    # 1. Read marks
    marks = {}
    with open(MARKS_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) == 2:
                ts, label = parts
                marks[label] = ts
    
    print(f"Loaded {len(marks)} marks from {MARKS_PATH}:")
    for k, v in sorted(marks.items()):
        print(f"  {k}: {v}")
        
    available_blocks = []
    for b in ["P1", "P2", "P3", "P4", "P5"]:
        if f"{b}-start" in marks and f"{b}-end" in marks:
            available_blocks.append(b)
        else:
            print(f"Block {b} incomplete: start={f'{b}-start' in marks}, end={f'{b}-end' in marks}")
            
    print(f"Active blocks to fit: {available_blocks}")
    
    # 2. Read events
    with (gzip.open if EVENTS_PATH.endswith(".gz") else open)(EVENTS_PATH, "rt") as f:
        events = list(csv.DictReader(f))
    events.sort(key=lambda r: r["ts_utc"])
    print(f"Loaded {len(events)} events from {EVENTS_PATH}")
    
    # 3. Process each block
    block_results = []
    block_events = {}
    
    for b in available_blocks:
        model = BLOCK_MODELS[b]
        start_ts = marks[f"{b}-start"]
        end_ts = marks[f"{b}-end"]
        start_dt = parse_iso(start_ts)
        end_dt = parse_iso(end_ts)
        # Upper bound: block end mark window (do not attribute post-block rollouts)
        cutoff = end_dt.timestamp()
        
        # Events before block start
        prior_events = [e for e in events if parse_iso(e["ts_utc"]).timestamp() < start_dt.timestamp() and e["used_percent"] != ""]
        reading_before = float(prior_events[-1]["used_percent"]) if prior_events else None
        
        bevs = []
        for e in events:
            e_ts = parse_iso(e["ts_utc"]).timestamp()
            if start_dt.timestamp() <= e_ts <= cutoff:
                if e["model"] == model:
                    bevs.append(e)
        block_events[b] = bevs
        
        # Token counts
        n_ev = len(bevs)
        sids = set(e["session_id"] if "session_id" in e else e["session_seq"] for e in bevs)
        n_sess = len(sids)
        
        u_tok = sum(max(int(e["d_input"]) - int(e["d_cached"]), 0) for e in bevs)
        c_tok = sum(int(e["d_cached"]) for e in bevs)
        o_tok = sum(int(e["d_output"]) for e in bevs)
        r_tok = sum(int(e["d_reasoning"]) for e in bevs)
        
        # Card credits
        ri, rc, ro = RATES[model]
        u_cr = u_tok * ri / 1e6
        c_cr = c_tok * rc / 1e6
        o_cr = o_tok * ro / 1e6
        tot_cr = u_cr + c_cr + o_cr
        
        # Readings
        ups = [float(e["used_percent"]) for e in bevs]
        first_up = ups[0]
        last_up = ups[-1]
        delta_p = last_up - first_up
        
        # Estimator (a): credits / delta_p
        a_all = tot_cr / delta_p if delta_p > 0 else None
        
        tail_cr = 0.0
        for ev in bevs[1:]:
            inp, ca, out = int(ev["d_input"]), int(ev["d_cached"]), int(ev["d_output"])
            unc = max(inp - ca, 0)
            tail_cr += (unc * ri + ca * rc + out * ro) / 1e6
        a_tail = tail_cr / delta_p if delta_p > 0 else None
        
        # Estimator (b): least-squares slope of cumulative credits against readings at rise points
        pts_all = []
        cum = 0.0
        mx = first_up
        for ev in bevs:
            inp, ca, out = int(ev["d_input"]), int(ev["d_cached"]), int(ev["d_output"])
            unc = max(inp - ca, 0)
            cum += (unc * ri + ca * rc + out * ro) / 1e6
            up = float(ev["used_percent"])
            if up > mx:
                mx = up
                pts_all.append((mx - first_up, cum, up))
                
        # Fit b (no intercept, fit.py style on rise points)
        b_no_int = None
        b_no_int_se = None
        if len(pts_all) >= 1:
            res_b = ols_no_intercept([[p[0]] for p in pts_all], [p[1] for p in pts_all])
            if res_b:
                b_no_int, b_no_int_se = res_b[0][0], res_b[1][0]
                
        # Fit b with intercept
        b_with_int = None
        b_int_se = None
        b_intercept = None
        if len(pts_all) >= 2:
            res_int = ols_with_intercept([p[0] for p in pts_all], [p[1] for p in pts_all])
            if res_int:
                b_with_int, b_intercept, b_int_se, _ = res_int
                
        # Step rate between first and last rise points in block
        if len(pts_all) >= 2:
            step_rate = (pts_all[-1][1] - pts_all[0][1]) / (pts_all[-1][0] - pts_all[0][0])
        else:
            step_rate = None
            
        # Quantization bracket (+-1 point on delta_p)
        (dp_low, dp_high), (cr_per_pct_low, cr_per_pct_high) = quantization(tot_cr, delta_p)
        
        block_results.append({
            "block": b,
            "model": model,
            "sessions": n_sess,
            "events": n_ev,
            "uncached_tok": u_tok,
            "cached_tok": c_tok,
            "output_tok": o_tok,
            "reasoning_tok": r_tok,
            "uncached_cr": round(u_cr, 3),
            "cached_cr": round(c_cr, 3),
            "output_cr": round(o_cr, 3),
            "total_cr": round(tot_cr, 3),
            "first_up": first_up,
            "last_up": last_up,
            "reading_before": reading_before,
            "delta_p": delta_p,
            "a": round(a_all, 3) if a_all else None,
            "a_tail": round(a_tail, 3) if a_tail else None,
            "b": round(b_no_int, 3) if b_no_int else None,
            "b_se": round(b_no_int_se, 3) if b_no_int_se else None,
            "b_with_intercept": round(b_with_int, 3) if b_with_int else None,
            "b_intercept": round(b_intercept, 3) if b_intercept else None,
            "b_step_rate": round(step_rate, 3) if step_rate else None,
            "quant_dp_bracket": f"[{dp_low:.0f}, {dp_high:.0f}]",
            "quant_cr_range": f"[{cr_per_pct_low:.2f}, {'inf' if cr_per_pct_high is None else format(cr_per_pct_high, '.2f')}]",
            "rise_points": [(p[0], round(p[1], 3), p[2]) for p in pts_all]
        })
        
    # Write block_summary.csv and json
    with open(os.path.join(OUT_DIR, "block_summary.json"), "w") as f:
        json.dump(block_results, f, indent=2)
        
    with open(os.path.join(OUT_DIR, "block_summary.csv"), "w", newline="") as f:
        fieldnames = ["block", "model", "sessions", "events", "uncached_tok", "cached_tok", "output_tok", "reasoning_tok",
                      "uncached_cr", "cached_cr", "output_cr", "total_cr", "reading_before", "first_up", "last_up", "delta_p",
                      "a", "a_tail", "b", "b_se", "b_with_intercept", "b_step_rate", "quant_dp_bracket", "quant_cr_range"]
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in block_results:
            w.writerow(r)
            
    # 4. Joint fit across astra blocks (P1-P3)
    # Consecutive rise intervals:
    # We analyze both:
    # Inter-rise intervals within blocks (Way A)
    # Pure rise-to-rise intervals inside blocks (Way B)
    # Continuous rise-to-rise intervals across 3% to 14% (Way C)
    
    # Way A: standard interval accumulation per block
    ivs_A = []
    for b in available_blocks:
        bevs = block_events[b]
        mx = float(bevs[0]["used_percent"])
        su = sc = so = 0.0
        ri, rc, ro = RATES[BLOCK_MODELS[b]]
        for ev in bevs:
            inp, ca, out = int(ev["d_input"]), int(ev["d_cached"]), int(ev["d_output"])
            unc = max(inp - ca, 0)
            su += unc * ri / 1e6
            sc += ca * rc / 1e6
            so += out * ro / 1e6
            up = float(ev["used_percent"])
            if up > mx:
                dy = up - mx
                ivs_A.append({
                    "block": b,
                    "model": BLOCK_MODELS[b],
                    "dy": dy,
                    "from_up": mx,
                    "to_up": up,
                    "uncached_cr": su,
                    "cached_cr": sc,
                    "output_cr": so,
                    "total_cr": su + sc + so
                })
                mx = up
                su = sc = so = 0.0
                
    # Way B: full step intervals within blocks (between consecutive rises)
    ivs_B = []
    for b in available_blocks:
        bevs = block_events[b]
        mx = float(bevs[0]["used_percent"])
        su = sc = so = 0.0
        first_rise_seen = False
        ri, rc, ro = RATES[BLOCK_MODELS[b]]
        for ev in bevs:
            inp, ca, out = int(ev["d_input"]), int(ev["d_cached"]), int(ev["d_output"])
            unc = max(inp - ca, 0)
            up = float(ev["used_percent"])
            if up > mx:
                if not first_rise_seen:
                    first_rise_seen = True
                    mx = up
                    su = sc = so = 0.0
                    continue
                dy = up - mx
                ivs_B.append({
                    "block": b,
                    "model": BLOCK_MODELS[b],
                    "dy": dy,
                    "from_up": mx,
                    "to_up": up,
                    "uncached_cr": su,
                    "cached_cr": sc,
                    "output_cr": so,
                    "total_cr": su + sc + so
                })
                mx = up
                su = sc = so = 0.0
            else:
                if first_rise_seen:
                    su += unc * ri / 1e6
                    sc += ca * rc / 1e6
                    so += out * ro / 1e6
                    
    # Way C: continuous sequence of rises across P1-P3 (from 3% to 14%)
    all_astra = [e for b in ["P1", "P2", "P3"] if b in block_events for e in block_events[b]]
    ivs_C = []
    mx = float(all_astra[0]["used_percent"])
    su = sc = so = 0.0
    first_rise_seen = False
    ri, rc, ro = RATES["gpt-6-astra"]
    for ev in all_astra:
        inp, ca, out = int(ev["d_input"]), int(ev["d_cached"]), int(ev["d_output"])
        unc = max(inp - ca, 0)
        up = float(ev["used_percent"])
        if up > mx:
            if not first_rise_seen:
                first_rise_seen = True
                mx = up
                su = sc = so = 0.0
                continue
            dy = up - mx
            ivs_C.append({
                "block": "continuous",
                "model": "gpt-6-astra",
                "dy": dy,
                "from_up": mx,
                "to_up": up,
                "uncached_cr": su,
                "cached_cr": sc,
                "output_cr": so,
                "total_cr": su + sc + so
            })
            mx = up
            su = sc = so = 0.0
        else:
            if first_rise_seen:
                su += unc * ri / 1e6
                sc += ca * rc / 1e6
                so += out * ro / 1e6
                
    # Run regressions
    fits = {}
    for label, ivs in [("Way_A_all_intra_block_rises", ivs_A),
                      ("Way_B_full_step_rises", ivs_B),
                      ("Way_C_continuous_3_to_14", ivs_C)]:
        X3 = [[iv["uncached_cr"], iv["cached_cr"], iv["output_cr"]] for iv in ivs]
        y = [iv["dy"] for iv in ivs]
        res3 = ols_no_intercept(X3, y)
        
        Xpool = [[iv["total_cr"]] for iv in ivs]
        res_pool = ols_no_intercept(Xpool, y)
        
        co, se, n, dof = res3
        p_co, p_se = res_pool[0][0], res_pool[1][0]
        
        fits[label] = {
            "n_intervals": n,
            "pooled_coef": round(p_co, 6),
            "pooled_se": round(p_se, 6),
            "implied_pool_window": round(100.0 / p_co, 1),
            "terms": {
                "uncached": {
                    "coef": round(co[0], 6),
                    "se": round(se[0], 6),
                    "ratio_to_pooled": round(co[0] / p_co, 4),
                    "ratio_to_uncached": 1.0,
                    "implied_window": round(100.0 / co[0], 1)
                },
                "cached": {
                    "coef": round(co[1], 6),
                    "se": round(se[1], 6),
                    "ratio_to_pooled": round(co[1] / p_co, 4),
                    "ratio_to_uncached": round(co[1] / co[0], 4),
                    "implied_window": round(100.0 / co[1], 1)
                },
                "output": {
                    "coef": round(co[2], 6),
                    "se": round(se[2], 6),
                    "ratio_to_pooled": round(co[2] / p_co, 4),
                    "ratio_to_uncached": round(co[2] / co[0], 4),
                    "implied_window": round(100.0 / co[2], 1)
                }
            },
            "intervals": ivs
        }
        
    with open(os.path.join(OUT_DIR, "joint_fit.json"), "w") as f:
        json.dump(fits, f, indent=2)
        
    # Write intervals.csv
    with open(os.path.join(OUT_DIR, "intervals.csv"), "w", newline="") as f:
        fieldnames = ["block", "from_up", "to_up", "dy", "uncached_cr", "cached_cr", "output_cr", "total_cr"]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for iv in ivs_A:
            w.writerow({k: round(v, 4) if isinstance(v, float) else v for k, v in iv.items() if k in fieldnames})
            
    print("\n=== COMPLETE SUMMARY ===")
    for b in block_results:
        print(f"Block {b['block']}: sess={b['sessions']}, ev={b['events']}, unc_tok={b['uncached_tok']}, ca_tok={b['cached_tok']}, out_tok={b['output_tok']}")
        print(f"         cr: unc={b['uncached_cr']}, ca={b['cached_cr']}, out={b['output_cr']}, tot={b['total_cr']}")
        print(f"         meter: before={b['reading_before']}, first={b['first_up']}, last={b['last_up']}, delta={b['delta_p']}%")
        print(f"         a={b['a']}, b={b['b']} +/- {b['b_se']}, step_rate={b['b_step_rate']}")
        print(f"         quantization: delta {b['quant_dp_bracket']} -> cr/% {b['quant_cr_range']}")
        
    print("\n=== JOINT FIT (Way B - Full Steps) ===")
    b_fit = fits["Way_B_full_step_rises"]
    print(f"Pooled: {b_fit['pooled_coef']} +/- {b_fit['pooled_se']} %/cr (Implied: {b_fit['implied_pool_window']} credits)")
    for t in ["uncached", "cached", "output"]:
        d = b_fit["terms"][t]
        print(f"  {t:<10}: {d['coef']} +/- {d['se']} %/cr | ratio to pool: {d['ratio_to_pooled']} | ratio to unc: {d['ratio_to_uncached']} | implied: {d['implied_window']} cr")
        
    print("\n=== JOINT FIT (Way C - Continuous Trajectory 3%->14%) ===")
    c_fit = fits["Way_C_continuous_3_to_14"]
    print(f"Pooled: {c_fit['pooled_coef']} +/- {c_fit['pooled_se']} %/cr (Implied: {c_fit['implied_pool_window']} credits)")
    for t in ["uncached", "cached", "output"]:
        d = c_fit["terms"][t]
        print(f"  {t:<10}: {d['coef']} +/- {d['se']} %/cr | ratio to pool: {d['ratio_to_pooled']} | ratio to unc: {d['ratio_to_uncached']} | implied: {d['implied_window']} cr")

if __name__ == "__main__":
    main()
