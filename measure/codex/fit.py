#!/usr/bin/env python3
"""fit.py EVENTS_CSV_GZ OUTDIR  -> windows.csv, fit_a_b.csv, fit_c.csv, unknown_models.json (stdlib only)"""
import sys, os, csv, gzip, json, collections, math
here = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(os.environ.get("CODEX_RATES", os.path.join(here, "..", "..", "findings", "findings.json"))))
R = R.get("rate_card", R)
RATES, FAM, USD = R["models"], R["family"], R["usd_per_credit"]
TYPES = ("unc", "cached", "out")

def ols(X, y):
    """no-intercept OLS; returns (coef, se, n, dof) or None"""
    n, k = len(y), len(X[0])
    if n <= k: return None
    A = [[sum(X[i][a]*X[i][b] for i in range(n)) for b in range(k)] for a in range(k)]
    B = [sum(X[i][a]*y[i] for i in range(n)) for a in range(k)]
    inv = invert(A)
    if inv is None: return None
    coef = [sum(inv[a][b]*B[b] for b in range(k)) for a in range(k)]
    rss = sum((y[i]-sum(coef[a]*X[i][a] for a in range(k)))**2 for i in range(n))
    s2 = rss/(n-k)
    se = [math.sqrt(max(s2*inv[a][a], 0)) for a in range(k)]
    return coef, se, n, n-k

def invert(A):
    k = len(A); M = [r[:] + [1.0 if i == j else 0.0 for j in range(k)] for i, r in enumerate(A)]
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-18: return None
        M[c], M[p] = M[p], M[c]
        d = M[c][c]; M[c] = [v/d for v in M[c]]
        for r in range(k):
            if r != c:
                f = M[r][c]; M[r] = [a-f*b for a, b in zip(M[r], M[c])]
    return [r[k:] for r in M]

def fnum(x):
    try: return float(x)
    except Exception: return None

def main():
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    wins = collections.defaultdict(list); unknown = collections.defaultdict(lambda: [0]*5)
    nonweekly = collections.Counter()
    with (gzip.open if src.endswith(".gz") else open)(src, "rt") as g:
        for r in csv.DictReader(g):
            if r["window_minutes"] == "10080":
                up = fnum(r["used_percent"]); ra = fnum(r["resets_at"])
            elif r["sec_window_minutes"] == "10080":     # weekly meter is the secondary when primary is the 5h one
                up = fnum(r["sec_used_percent"]); ra = fnum(r["sec_resets_at"])
                nonweekly["weekly_from_secondary"] += 1
            else:
                nonweekly[r["window_minutes"]] += 1; continue
            if up is None or ra is None: continue
            d = [int(r[k]) for k in ("d_input","d_cached","d_cache_write","d_output","d_reasoning")]
            m = r["model"]
            cr = None
            if m in RATES:
                ri, rc, ro = RATES[m]
                unc = max(d[0]-d[1], 0)
                cr = (unc*ri/1e6, d[1]*rc/1e6, d[3]*ro/1e6)
            else:
                for i in range(5): unknown[m][i] += d[i]
            wins[round(ra/3600)*3600].append((r["ts_utc"], up, m, d, cr, r["plan_type"], r["delta_src"]))
    json.dump({"unknown_models": unknown, "nonweekly_primary_rows": nonweekly},
              open(os.path.join(out, "unknown_models.json"), "w"), indent=1)
    wrows, abrows, crows = [], [], []; pooled = collections.defaultdict(list)
    for wk in sorted(wins):
        ev = sorted(wins[wk], key=lambda e: e[0])
        ups = [e[1] for e in ev]
        tok = collections.defaultdict(lambda: [0]*5); cred = collections.defaultdict(float)
        for _, up, m, d, cr, pl, s in ev:
            for i in range(5): tok[m][i] += d[i]
            if cr: cred[m] += sum(cr)
        plans = sorted({e[5] for e in ev if e[5]})
        wrows.append({"window_reset_utc_hour": wk, "reset_iso": __import__("datetime").datetime.utcfromtimestamp(wk).isoformat(),
            "n_events": len(ev), "first_ts": ev[0][0], "last_ts": ev[-1][0], "plans": "|".join(plans),
            "min_used": min(ups), "max_used": max(ups), "nonmonotone_steps": sum(1 for a, b in zip(ups, ups[1:]) if b < a),
            "tokens_json": json.dumps({m: dict(zip(("input","cached","cache_write","output","reasoning"), v)) for m, v in tok.items()}),
            "credits_json": json.dumps({m: round(v, 3) for m, v in cred.items()}),
            "credits_total": round(sum(cred.values()), 3)})
        # a: credits after first reading / (last-first)
        tail = [e for e in ev[1:] if e[4]]
        totc = sum(sum(e[4]) for e in tail)
        dp = ups[-1]-ups[0]
        a = totc/dp if dp > 0 else None
        # b: running-max rise points
        pts = []; mx = ups[0]; cum = 0.0
        for e in ev[1:]:
            if e[4]: cum += sum(e[4])
            if e[1] > mx:
                mx = e[1]; pts.append((mx-ups[0], cum))
        b = None; bse = None
        if len(pts) >= 3:
            r_ = ols([[p[0]] for p in pts], [p[1] for p in pts])
            if r_: b, bse = r_[0][0], r_[1][0]
        flag = ""
        if a and b and abs(a-b)/max(a, b) > 0.25: flag = "A_B_DISAGREE>25%"
        abrows.append({"window": wk, "plans": "|".join(plans), "delta_used": dp, "credits_after_first": round(totc, 3),
            "a_credits_per_pct": a and round(a, 3), "b_slope_credits_per_pct": b and round(b, 3), "b_se": bse and round(bse, 3),
            "b_points": len(pts), "implied_window_credits_a": a and round(100*a, 1),
            "implied_window_usd_a": a and round(100*a*USD, 2), "implied_window_credits_b": b and round(100*b, 1),
            "implied_window_usd_b": b and round(100*b*USD, 2), "flag": flag})
        # c: interval regression between rise points
        iv = []; mx = ups[0]; s = {f: [0.0]*3 for f in set(FAM.values())}
        for e in ev[1:]:
            if e[4]:
                f = FAM[e[2]]
                for i in range(3): s[f][i] += e[4][i]
            if e[1] > mx:
                iv.append((e[1]-mx, {f: v[:] for f, v in s.items()}))
                mx = e[1]; s = {f: [0.0]*3 for f in s}
        for fam in sorted(set(FAM.values())):
            rows = [(dy, sm[fam]) for dy, sm in iv if sum(sm[fam]) > 0 and sum(sum(v) for k, v in sm.items() if k != fam) == 0]
            pooled[(plans[0] if plans else "", fam)].extend(rows)
            if len(rows) < 5: continue
            res = ols([x for _, x in rows], [y for y, _ in rows])
            if not res: continue
            co, se, n, dof = res
            for i, t in enumerate(TYPES):
                crows.append({"window": wk, "regression": "family:"+fam, "term": t, "n": n, "coef_pct_per_credit": co[i], "se": se[i],
                    "ratio_to_unc_coef": co[i]/co[0] if co[0] else None, "card_ratio": 1.0})
        # pooled across families, per-family scale
        fams = sorted(set(FAM.values()))
        if len(iv) >= len(fams)+2:
            X = [[sum(sm[f]) for f in fams] for _, sm in iv]; y = [dy for dy, _ in iv]
            res = ols(X, y)
            if res:
                co, se, n, dof = res
                for i, f in enumerate(fams):
                    crows.append({"window": wk, "regression": "by_family_total", "term": f, "n": n, "coef_pct_per_credit": co[i], "se": se[i],
                        "ratio_to_unc_coef": None, "card_ratio": 1.0})
    for (plan, fam), rows in sorted(pooled.items()):   # pooled across windows of one plan (assumes same window size)
        res = ols([x for _, x in rows], [y for y, _ in rows]) if len(rows) >= 8 else None
        if not res: continue
        co, se, n, dof = res
        for i, t in enumerate(TYPES):
            crows.append({"window": "pooled:"+plan, "regression": "family:"+fam, "term": t, "n": n, "coef_pct_per_credit": co[i], "se": se[i],
                "ratio_to_unc_coef": co[i]/co[0] if co[0] else None, "card_ratio": 1.0})
    def dump(name, rows):
        if not rows: open(os.path.join(out, name), "w").write(""); return
        with open(os.path.join(out, name), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    dump("windows.csv", wrows); dump("fit_a_b.csv", abrows); dump("fit_c.csv", crows)
    print(len(wrows), "windows;", len(abrows), "fit rows;", len(crows), "regression rows")

if __name__ == "__main__":
    main()
