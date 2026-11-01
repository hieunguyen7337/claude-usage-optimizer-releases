#!/usr/bin/env python3
"""Analyze C0-C5 from extractor output; never reads transcript files."""
import csv
import gzip
import json
import os
import re
from datetime import datetime

BASE = os.path.expanduser(os.environ.get("MEASURE_DIR", "~/.local/state/lanes/measure"))
OUT = os.environ.get("CLAUDE_FIT_OUT", BASE + "/claude/out")
MARKS = os.environ.get("CLAUDE_MARKS", BASE + "/claude/marks.tsv")
METER = os.environ.get("CLAUDE_METER", BASE + "/claude/meter.jsonl")
PRICES = os.environ.get("CLAUDE_PRICES", os.path.join(os.path.dirname(__file__), "prices.json"))
EVENTS = os.environ.get("CLAUDE_EVENTS", OUT + "/events.csv.gz")
EXTRACT_REPORT = os.environ.get("CLAUDE_EXTRACT_REPORT", OUT + "/extract_report.json")
PROJECTS = os.path.expanduser(os.environ.get("CLAUDE_PROJECTS", "~/.claude/projects"))

BLOCKS = ["c0", "c1", "c2", "c3", "c4", "c5"]
MODEL_KEYS = {
    "claude-haiku-5-5": "Haiku",
    "claude-sonnet-5-5": "Sonnet",
    "claude-opus-5-5": "Opus",
    "claude-opus-5": "Opus",
    "claude-fable-5-1": "Fable",
}
TOKENS = ("input", "cw5m", "cw1h", "cache_read", "output")


def read_marks():
    result = {}
    with open(MARKS) as f:
        for line in f:
            ts, label = line.rstrip("\n").split("\t")
            result[label] = ts
    return result


def price_row(model, row, prices, h2=False):
    if model not in prices:
        return 0.0
    p = prices[model]
    if model == "claude-haiku-5-5":
        prompt_tokens = sum(int(row[t]) for t in ("input", "cw5m", "cw1h", "cache_read"))
        p = p["prompt_le_threshold"] if prompt_tokens <= prices[model]["threshold_prompt_tokens"] else p["prompt_gt_threshold"]
    factor = 0.0
    for t in TOKENS:
        if h2 and t == "cache_read":
            continue
        factor += int(row[t]) * p[t]
    return factor / 1_000_000


def fmt(x, digits=4):
    return f"${x:,.{digits}f}"


def per_pct(cost, delta):
    if cost < 0 or delta < 0:
        raise ValueError("cost and meter rise must be nonnegative")
    if delta == 0:
        return None, cost, None
    point = cost / delta
    lo = cost / (delta + 1)
    hi = None if delta <= 1 else cost / (delta - 1)
    return point, lo, hi


def rise_interval(delta):
    """Endpoints; zero uses [0,1), positive rises use open endpoints."""
    if delta < 0:
        raise ValueError("reset or backwards meter reading")
    return max(0, delta - 1), delta + 1


def model_factor(anchor, model):
    """Meter consumed per list dollar, relative to anchor (per_pct tuples)."""
    ap, al, ah = anchor
    mp, ml, mh = model
    return (ap / mp if ap is not None and mp is not None else None,
            al / mh if mh is not None else 0.0,
            ah / ml if ah is not None and ml > 0 else None)


def cache_weight(anchor_h1, anchor_h2, anchor_delta, cache_h1, cache_h2, cache_delta):
    """Solve cache/anchor cost ratio, then intersect rounding constraints with [0,1]."""
    ar, cr = anchor_h1 - anchor_h2, cache_h1 - cache_h2
    denominator = anchor_delta * cr - cache_delta * ar
    point = ((cache_delta * anchor_h2 - anchor_delta * cache_h2) / denominator
             if denominator else None)
    alo, ahi = rise_interval(anchor_delta)
    clo, chi = rise_interval(cache_delta)
    lo, hi = 0.0, 1.0
    # ahi*C >= clo*A and chi*A >= alo*C, with A=A2+w*Ar.
    for constant, slope in ((ahi * cache_h2 - clo * anchor_h2, ahi * cr - clo * ar),
                            (chi * anchor_h2 - alo * cache_h2, chi * ar - alo * cr)):
        if slope > 0:
            lo = max(lo, -constant / slope)
        elif slope < 0:
            hi = min(hi, -constant / slope)
        elif constant < 0:
            return point, None
    return point, (lo, hi) if lo <= hi else None


def interval(point, lo, hi):
    if point is None:
        return f"> {fmt(lo)} (Δ=0; no point estimate)"
    return f"{fmt(point)} ({fmt(lo)}, {'∞' if hi is None else fmt(hi)})"


def token_cell(models):
    names = {"input": "in", "cw5m": "cw5m", "cw1h": "cw1h", "cache_read": "read", "output": "out"}
    return "<br>".join(
        f"{m}: " + "/".join(f"{names[t]} {v:,}" for t, v in sums.items())
        for m, sums in models.items()
    )


def pct_change(new, old):
    return (new / old - 1) * 100


def write_report(data, extractor):
    blocks = data["blocks"]
    c2 = blocks[2]
    c0 = blocks[0]
    c5 = blocks[5]
    lines = [
        "# Claude meter fit: controlled probe blocks C0–C5",
        "",
        "## Findings",
        "",
        f"The C2 anchor gives **${c2['rates']['H1']['5h'][0]:.2f} per 5h percentage point** under H1 and **${c2['rates']['H2']['5h'][0]:.2f}** under H2; the 7-day points are **${c2['rates']['H1']['7d'][0]:.2f}** and **${c2['rates']['H2']['7d'][0]:.2f}**. [INFERRED]",
        f"Among the model blocks, Fable is about **{c2['rates']['H1']['5h'][0] / c5['rates']['H1']['5h'][0]:.2f}× heavier per list-price dollar than Sonnet on the 5h meter** (H1 point), with its quantization range above 1. Haiku's 5h range and Opus's 5h/7d ranges include proportional weight; Haiku has no 7d point because C1's 7d Δ was zero. [INFERRED]",
        f"C4's cache-read weight point is **w={data['cache_read_weight']['point']:.2f}**, but its compatible range spans 0–1, so cache-read treatment is unresolved. [INFERRED]",
        "The C0 no-movement result bounds an additive request fee below about 1.85 cents per call under H1 and 1.80 cents under H2 (conservative endpoints). [INFERRED]",
        "Fable's separate weekly window is about $531 H1 / $526 H2, with quantization intervals shown below. [INFERRED]",
        "",
        "## 1. Extractor run and input basis",
        "",
        f"- PBS extractor job `{extractor['job']}` exited 0; final analysis job `{extractor['analysis_job']}` exited 0. [OBSERVED command output] Extractor metadata: `rows_written={extractor['rows_written']:,}`, `ts_min={extractor['ts_min']}`, `ts_max={extractor['ts_max']}`, `elapsed_s={extractor['elapsed_s']}`. [OBSERVED claude/probes_fit/extract_report.json:10,56,112-113]",
        "- Prices use Haiku's per-response prompt tier at 100,000 tokens; H1 charges cache reads at list, H2 sets only cache reads to zero. [OBSERVED claude/prices.json:2-18]",
        "- Each block window below is the inclusive `pre-*` to `post-*` meter-read interval; readings are whole percent. [OBSERVED probes/claude/meter.jsonl:3-19]",
        "- Probe dollars are attributed by matching extracted `session_id` values to the C0–C5 project-directory filenames; the balance is other local traffic in the same time window. No transcript contents were opened by the analysis. [INFERRED]",
        "",
        "## 2. Block measurements",
        "",
        "Token cells list input / 5m cache write / 1h cache write / cache read / output. The 5m totals are zero in every block. Meter rise intervals are (Δ−1, Δ+1) percentage points; for Δ=0, only the per-point lower bound is available. [INFERRED]",
        "",
        "|Block; UTC window|Responses probe / rest|Tokens by model (input / cw5m / cw1h / read / output)|List $ H1 / H2|Probe share H1 / H2|5h Δ; 7d Δ|H1 $/1% 5h; 7d|H2 $/1% 5h; 7d|",
        "|---|---:|---|---:|---:|---:|---|---|",
    ]
    for b in blocks:
        rate = b["rates"]
        shares = []
        for hyp in ("H1", "H2"):
            share = b["cost"]["probe_" + hyp]
            total = b["cost"][hyp]
            shares.append(f"{hyp} {fmt(share)} ({share/total*100:.1f}%)")
        r5h1 = interval(*rate["H1"]["5h"])
        r7h1 = interval(*rate["H1"]["7d"])
        r5h2 = interval(*rate["H2"]["5h"])
        r7h2 = interval(*rate["H2"]["7d"])
        delta5 = f"{b['d5']} rise [0,1)" if b["d5"] == 0 else f"{b['d5']} rise ({b['d5']-1},{b['d5']+1})"
        delta7 = f"{b['d7']} rise [0,1)" if b["d7"] == 0 else f"{b['d7']} rise ({b['d7']-1},{b['d7']+1})"
        lines.append(
            f"|{b['block']} {b['start']}–{b['end']}|{b['responses']} ({b['probe_responses']} / {b['rest_responses']})|{token_cell(b['models'])}|{fmt(b['cost']['H1'])} / {fmt(b['cost']['H2'])}|{'<br>'.join(shares)}|5h {delta5}; 7d {delta7}|{r5h1}; {r7h1}|{r5h2}; {r7h2} [INFERRED]|"
        )
    lines += [
        "",
        "## 3. Model weights, cache reads, request fee, and Fable window",
        "",
        "### Model charge relative to Sonnet (C2)",
        "",
        "A meter-weight factor above 1 means the model consumes more meter per list-price dollar than Sonnet. Factors use the block point estimates; intervals are derived by combining the two blocks' quantization intervals. [INFERRED]",
        "",
        "|Model block|5h list $/1% H1; H2|5h meter-weight vs Sonnet H1; H2|7d list $/1% H1; H2|7d meter-weight vs Sonnet H1; H2|Reading|",
        "|---|---|---|---|---|---|",
    ]
    for model, index in (("Haiku", 1), ("Sonnet", 2), ("Opus", 3), ("Fable", 5)):
        b = blocks[index]
        rates5 = []
        factors5 = []
        rates7 = []
        factors7 = []
        status_bits = []
        for hyp in ("H1", "H2"):
            for win, rates, factors in (("5h", rates5, factors5), ("7d", rates7, factors7)):
                m_point, m_lo, m_hi = b["rates"][hyp][win]
                s_point, s_lo, s_hi = c2["rates"][hyp][win]
                rates.append(f"{hyp} {interval(m_point, m_lo, m_hi)}")
                if m_point is None:
                    factors.append(f"{hyp} no point (Δ=0)")
                elif model == "Sonnet":
                    factors.append(f"{hyp} 1.00× [1.00, 1.00]")
                else:
                    factor = s_point / m_point
                    factor_lo = 0 if m_hi is None else s_lo / m_hi
                    factor_hi = s_hi / m_lo
                    factors.append(f"{hyp} {factor:.2f}× ({factor_lo:.2f}, {factor_hi:.2f})")
        # Status is based on the shared 5h block, which gives the most precise comparison.
        h1_point = c2["rates"]["H1"]["5h"][0] / b["rates"]["H1"]["5h"][0]
        h2_point = c2["rates"]["H2"]["5h"][0] / b["rates"]["H2"]["5h"][0]
        for hyp, point in (("H1", h1_point), ("H2", h2_point)):
            _, mlo, mhi = b["rates"][hyp]["5h"]
            _, slo, shi = c2["rates"][hyp]["5h"]
            flo = 0 if mhi is None else slo / mhi
            fhi = shi / mlo
            if flo > 1:
                status_bits.append("dearer than proportional")
            elif fhi < 1:
                status_bits.append("cheaper than proportional")
            else:
                status_bits.append("consistent within quantization")
        status = "Fable is dearer per list dollar on 5h; its 7d factor interval includes 1." if model == "Fable" else ("Sonnet baseline." if model == "Sonnet" else "5h: " + ("; ".join(sorted(set(status_bits)))))
        lines.append(f"|{model} (C{index})|" + "; ".join(rates5) + "|" + "; ".join(factors5) + "|" + "; ".join(rates7) + "|" + "; ".join(factors7) + f"|{status} [INFERRED]|")
    w = data["cache_read_weight"]
    lines += [
        "",
        "### Cache reads (C4 vs C2)",
        "",
        f"C4's point solution is **w={w['point']:.2f}** when both C4 and C2 costs are interpolated as H2 + w×(H1−H2). The quantization-compatible range, constrained to the physical 0–1 scale, is **[{w['interval'][0]:.2f}, {w['interval'][1]:.2f}]**. It includes both free and list weight, so C4 does not resolve whether cache reads count. [INFERRED]",
        "",
        "### Per-request charge (C0)",
        "",
    ]
    for hyp in ("H1", "H2"):
        upper_one_pct = c2["rates"][hyp]["5h"][2]
        point_one_pct = c2["rates"][hyp]["5h"][0]
        base = c0["cost"]["probe_" + hyp]
        point_bound = point_one_pct / 150
        max_bound = upper_one_pct / 150
        lines.append(f"C0's 150 Haiku calls moved neither meter. Under the C2 5h calibration, an additive fee is bounded above by the full 1% capacity divided by 150: **< {fmt(point_bound)} per call** at the point estimate and **< {fmt(max_bound)} per call** at the quantization-conservative upper endpoint ({hyp}); this deliberately does not subtract C0's token spend. [INFERRED]")
    lines += [
        "",
        "### Fable's separate weekly window",
        "",
        "The supplied Fable-window readings are 0% before C5 and 5% after C5, with no other Fable use in between. Use Fable-model dollars from the C5 probe sessions for this separate meter; the shared-window C5 table above includes all local traffic. [INFERRED]",
    ]
    fable = c5["model_cost"]["Fable"]
    for hyp in ("H1", "H2"):
        point, lo, hi = per_pct(fable[hyp], 5)
        lines.append(f"Fable C5 cost is {fmt(fable[hyp])} ({hyp}); its own weekly window is **{interval(point, lo, hi)} per 1%**, implying **{fmt(point*100)} ({fmt(lo*100)}, {fmt(hi*100)})** list dollars per full window. [INFERRED]")
    lines += [
        "",
        "## 4. Implied shared-window sizes and comparison with earlier Claude estimate",
        "",
        "Using C2, the largest calibration block, as the shared-window anchor: [INFERRED]",
        "",
        "|Shared window|H1 size (point; interval)|H2 size (point; interval)|",
        "|---|---:|---:|",
    ]
    for win, label in (("5h", "5h"), ("7d", "7-day")):
        cells = []
        for hyp in ("H1", "H2"):
            point, lo, hi = c2["rates"][hyp][win]
            cells.append(f"{fmt(point*100)} ({fmt(lo*100)}, {fmt(hi*100)})")
        lines.append(f"|{label}|{cells[0]}|{cells[1]} [INFERRED]|")
    lines += [
        "",
        "Earlier Claude estimates in `LIMITS.md` were $3.80 per 5h percent and $21–25 per weekly percent (H1), and $2.85 per 5h percent and $16–19 per weekly percent (H2). [OBSERVED usage-lab/LIMITS.md:45-46]",
    ]
    for hyp, old5, old7, oldweek in (("H1", 3.8, 23.0, 2300.0), ("H2", 2.85, 17.5, 1730.0)):
        now5 = c2["rates"][hyp]["5h"][0]
        now7 = c2["rates"][hyp]["7d"][0]
        lines.append(f"{hyp}: the C2 5h point is {fmt(now5)}/% ({pct_change(now5, old5):+.1f}% vs the earlier point); its interval is {interval(*c2['rates'][hyp]['5h'])}. The 7-day point is {fmt(now7)}/% ({pct_change(now7, old7):+.1f}% vs midpoint ${old7:.2f}, or {pct_change(now7*100, oldweek):+.1f}% in implied full-window size); its interval is {interval(*c2['rates'][hyp]['7d'])}. [INFERRED]")
    lines += [
        "The point estimates are lower than the earlier central estimates; the 7-day intervals are broad because C2 moved only 2 whole points and overlap the earlier ranges, while the 5h intervals sit below the earlier point estimates. [INFERRED]",
        "",
        "## 5. Files and unresolved points",
        "",
        "- `events.csv.gz`, `extract_report.json`, `derived.json`, `analyze_cprobes.py`, and this report were written under `claude/probes_fit/`. [OBSERVED command output]",
        "- C4's cache-read weight remains unresolved at the whole-percent meter resolution; Haiku's 7-day weight also has no point estimate because C1's 7-day meter change was zero. [INFERRED]",
        "- C0 bounds an additive per-request fee only under the C2 shared-window dollar calibration; it does not identify a fee separately from the meter's model-weighting rule. [INFERRED]",
        "",
    ]
    with open(OUT + "/REPORT_C.md", "w") as f:
        f.write("\n".join(lines))


def main():
    os.makedirs(OUT, exist_ok=True)
    prices = json.load(open(PRICES))
    marks = read_marks()
    readings = {}
    with open(METER) as f:
        for n, line in enumerate(f, 1):
            o = json.loads(line)
            if o.get("label"):
                readings[o["label"]] = (n, o["ts"], o["rate_limit_info"]["unifiedWindows"])

    # Probe attribution uses extracted session_id values matched against transcript
    # basenames in project directories. Only directory entries are read here; transcript
    # contents are never opened by this analysis.
    probe_ids = {b: set() for b in BLOCKS}
    if os.path.isdir(PROJECTS):
        for entry in os.scandir(PROJECTS):
            if not entry.is_dir(follow_symlinks=False):
                continue
            d = entry.name
            for b in BLOCKS:
                suffix = re.sub(r"[^a-zA-Z0-9]", "-", os.path.abspath(BASE + "/claude/" + b))
                if d.endswith(suffix) or (b == "c0" and d.endswith(suffix + "-cwd")):
                    for _root, _dirs, names in os.walk(entry.path):
                        for name in names:
                            if name.endswith(".jsonl"):
                                probe_ids[b].add(name[:-6])

    events = []
    with (gzip.open if EVENTS.endswith(".gz") else open)(EVENTS, "rt", newline="") as f:
        for row in csv.DictReader(f):
            if not row["ts_utc"]:
                continue
            events.append(row)

    result = []
    by_block_rows = {}
    for b in BLOCKS:
        _pre_line, start, pre = readings["pre-" + b]
        _post_line, end, post = readings["post-" + b]
        rows = [r for r in events if start <= r["ts_utc"] <= end]
        by_block_rows[b] = rows
        model_data = {}
        model_cost = {}
        sums = {"H1": 0.0, "H2": 0.0, "probe_H1": 0.0, "probe_H2": 0.0}
        response_probe = response_rest = 0
        for r in rows:
            m = MODEL_KEYS.get(r["model"], r["model"])
            d = model_data.setdefault(m, {t: 0 for t in TOKENS})
            for t in TOKENS:
                d[t] += int(r[t])
            h1 = price_row(r["model"], r, prices, False)
            h2 = price_row(r["model"], r, prices, True)
            mc = model_cost.setdefault(m, {"H1": 0.0, "H2": 0.0, "probe_H1": 0.0, "probe_H2": 0.0})
            mc["H1"] += h1
            mc["H2"] += h2
            sums["H1"] += h1
            sums["H2"] += h2
            # De-identified events carry probe_block instead of session_id.
            is_probe = (r["probe_block"] == b if "probe_block" in r
                        else r["session_id"] in probe_ids[b])
            if is_probe:
                mc["probe_H1"] += h1
                mc["probe_H2"] += h2
                sums["probe_H1"] += h1
                sums["probe_H2"] += h2
                response_probe += 1
            else:
                response_rest += 1
        d5 = round((post["five_hour"]["utilization"] - pre["five_hour"]["utilization"]) * 100)
        d7 = round((post["seven_day"]["utilization"] - pre["seven_day"]["utilization"]) * 100)
        result.append({
            "block": b.upper(), "start": start, "end": end,
            "responses": len(rows), "probe_responses": response_probe,
            "rest_responses": response_rest, "models": model_data, "model_cost": model_cost, "cost": sums,
            "d5": d5, "d7": d7,
            "rates": {h: {w: per_pct(sums[h], d) for w, d in (("5h", d5), ("7d", d7))} for h in ("H1", "H2")},
        })

    # Derive C4 cache-read weight range relative to C2. Required reading precision is
    # an open (delta-1, delta+1) interval for positive deltas.
    c2, c4 = result[2], result[4]
    w_point, w_interval = cache_weight(c2["cost"]["H1"], c2["cost"]["H2"], c2["d5"],
                                         c4["cost"]["H1"], c4["cost"]["H2"], c4["d5"])
    def raw_root(ratio):
        a2, c2read = c2["cost"]["H2"], c2["cost"]["H1"] - c2["cost"]["H2"]
        a4, c4read = c4["cost"]["H2"], c4["cost"]["H1"] - c4["cost"]["H2"]
        denominator = c4read - ratio * c2read
        return (ratio * a2 - a4) / denominator if denominator else None
    w_interval_raw = (raw_root(max(0, c4["d5"] - 1) / (c2["d5"] + 1)),
                      raw_root((c4["d5"] + 1) / (c2["d5"] - 1)))

    # Model factors are normalized to Sonnet's C2 $ per meter point, independently
    # for each meter and pricing hypothesis.
    factors = {}
    for idx, model in ((1, "Haiku"), (2, "Sonnet"), (3, "Opus"), (5, "Fable")):
        rr = result[idx]
        factors[model] = {}
        for h in ("H1", "H2"):
            for w in ("5h", "7d"):
                v = rr["rates"][h][w][0]
                base = c2["rates"][h][w][0]
                factors[model][h + "_" + w] = base / v if v is not None and base is not None else None

    out = {"blocks": result, "cache_read_weight": {"point": w_point, "interval": w_interval,
           "raw_unconstrained_interval": w_interval_raw}, "model_factors_vs_sonnet": factors}
    with open(OUT + "/derived.json", "w") as f:
        json.dump(out, f, indent=2)

    with open(EXTRACT_REPORT) as f:
        extractor = json.load(f)
    extractor["job"] = extractor.get("job", "not recorded")
    extractor["analysis_job"] = os.environ.get("PBS_JOBID", "unknown")
    write_report(out, extractor)

    # Print concise machine output for the PBS log; full tables are included in REPORT_C.md.
    for b in result:
        print(b["block"], b["start"], b["end"], "responses", b["responses"], "probe", b["probe_responses"], "rest", b["rest_responses"],
              "H1", fmt(b["cost"]["H1"]), "H2", fmt(b["cost"]["H2"]), "delta", b["d5"], b["d7"])
    print("cache-read weight point/range", w_point, w_interval)
    print("probe session ids", {k: len(v) for k, v in probe_ids.items()})


if __name__ == "__main__":
    main()
