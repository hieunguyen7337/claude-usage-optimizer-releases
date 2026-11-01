#!/usr/bin/env python3
"""Rebuild the inline data of findings/aa-cli-rate/index.html (public scores against cost per task).

Usage: tools/make-aa-cli-rate.py [--write]

Reads findings/public.json (Coding Agent Index v2.0 and Intelligence Index v5.0 rows),
findings/findings.json (Claude window and weights, Codex weekly credits, and the inputs under
"subsidy_inputs") and arms.json (the Pro Lite window epoch: its scale, start time and source),
computes the subsidy factor of each plan and every plan-rate cost per task, and rewrites the page's
<script type="application/json" id="data"> block. With --write it also rewrites the top-level
"subsidy" key of findings/findings.json, keeping that file's indent, separators and key order.

Subsidy factor = API value of a month's allowance / the plan's monthly price; a month is
subsidy_inputs.weeks_per_month weeks. Plan $ per task = API $ per task / factor. Intervals are
[low, high]; a null high is unbounded, and a null bound with no status is not known (n/a).
tools/check-aa-cli-rate.py recomputes every figure independently from the same inputs.
Stdlib only, deterministic.
"""

import argparse
import json
import os
import re
import sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC = os.path.join(KIT, "findings", "public.json")
FINDINGS = os.path.join(KIT, "findings", "findings.json")
ARMS = os.path.join(KIT, "arms.json")
PAGE = os.path.join(KIT, "findings", "aa-cli-rate", "index.html")

USD_DIGITS = 2        # weekly and monthly API value
FACTOR_DIGITS = 3     # subsidy factor
TASK_DIGITS = 6       # plan $ per task

EFFORTS = ["max", "xhigh", "high", "medium", "low"]

# Lane -> maker. The page colors by maker.
MAKERS = {
    "opus": "anthropic", "sonnet": "anthropic", "haiku": "anthropic", "fable": "anthropic",
    "sol": "openai", "terra": "openai", "luna": "openai", "astra": "openai",
    "gemini": "google",
}
MAKER_LABELS = {"anthropic": "Anthropic", "openai": "OpenAI", "google": "Google"}
CODEX_PLANS = ["prolite", "prolite_before", "plus"]
CLAUDE_LANES = ("sonnet", "opus", "haiku", "fable")
DOUBLED_PLAN = "prolite"  # the Codex plan whose window epoch (arms.json) doubled

# Notes that are not inputs. The inputs are in findings.json "subsidy_inputs".
OPUS_FLOOR_NOTE = "point and low are held at the ${:,.0f} calibration floor (the weight alone gives {:.0f})"
GEMINI_FORMULA = "weekly $ = the lower-bound weekly $ in subsidy_inputs.gemini, so the factor is at least its point"
GEMINI_NOTE = "a lower bound: other Gemini use during the sizing calls would make the window larger"

INDEXES = {
    "cai2": {"label": "Coding Agent Index v2.0", "score": "aa_cai2_index",
             "cost": "aa_cai2_cost_per_task_usd", "extra": {"tb4_pct": "aa_cai2_tb4_pct"}},
    "ii5": {"label": "Intelligence Index v5.0", "score": "aa_ii_v5_score",
            "cost": "aa_ii_v5_cost_per_task_usd", "extra": {}},
}

DATA_RE = re.compile(r'(<script type="application/json" id="data">)(.*?)(</script>)', re.S)


def load(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def dig(tree, dotted, label="findings.json"):
    node = tree
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise SystemExit("make-aa-cli-rate: {} has no {}".format(label, dotted))
        node = node[part]
    return node


def rnd(value, digits):
    return None if value is None else round(value, digits)


def div(value, by):
    return None if value is None or by is None else value / by


def money(point, low, high):
    return {"interval": [rnd(low, USD_DIGITS), rnd(high, USD_DIGITS)], "point": rnd(point, USD_DIGITS)}


def window_epoch(arms, plan):
    """The arms.json window epoch of a plan, the latest one if there are several."""
    epochs = [e for e in dig(arms, "providers.codex.window_epochs", "arms.json") if e.get("plan") == plan]
    if not epochs:
        raise SystemExit("make-aa-cli-rate: arms.json has no window_epochs entry for {}".format(plan))
    return max(epochs, key=lambda e: e["from"])


def factor_entry(plan, plan_id, price, weekly, inputs, formula, lanes, source, status, weeks, note=None):
    """weekly is (point, low, high) API dollars a week; high None is unbounded, low and high None
    together are not known. Returns the page entry and the unrounded (point, low, high) factor."""
    point, low, high = weekly
    month = [None if v is None else v * weeks for v in (point, low, high)]
    factor = (div(month[0], price), div(month[1], price), div(month[2], price))
    entry = {
        "formula": formula,
        "inputs": inputs,
        "interval": [rnd(factor[1], FACTOR_DIGITS), rnd(factor[2], FACTOR_DIGITS)],
        "lanes": lanes,
        "monthly_api_usd": money(*month),
        "plan": plan,
        "plan_id": plan_id,
        "point": rnd(factor[0], FACTOR_DIGITS),
        "price_usd_month": price,
        "source": source,
        "status": status,
        "weekly_api_usd": money(point, low, high),
    }
    if note:
        entry["note"] = note
    return entry, factor


def claude_factors(findings, inp, weeks):
    window_path = "claude.windows.weekly.H1"
    window = dig(findings, window_path)
    s_point, s_low, s_high = float(window["point"]), float(window["interval"][0]), float(window["interval"][1])
    sonnet_input = {"interval": list(window["interval"]), "point": window["point"],
                    "source": "findings.json " + window_path, "unit": "list_usd_per_week"}
    price = inp["prices"]["usd_per_month"]["max20x"]
    out, exact = {}, {}
    for lane in CLAUDE_LANES:
        weights = dig(findings, "claude.weights." + lane)
        weekly = weights.get("weekly") or {}
        status, note, window_name = "measured", None, "weekly"
        if weekly.get("point") is None:
            weekly = weights["five_hour"]
            window_name = "five_hour"
            status = "pending"
            note = ("claude.weights.{}.weekly is not measured yet; the 5h weight stands in "
                    "until a probe fills it in").format(lane)
        if weekly.get("point") is None:
            raise SystemExit("make-aa-cli-rate: claude.weights.{} has no point".format(lane))
        w_point = float(weekly["point"])
        w_interval = weekly.get("interval")
        if w_interval is None:
            w_low = w_high = None
            note = "claude.weights.{}.{} has a point but no interval; its bounds are n/a".format(lane, window_name)
        else:
            w_low, w_high = float(w_interval[0]), float(w_interval[1])
        weight_input = {"interval": None if w_interval is None else list(w_interval), "point": weekly["point"],
                        "source": "findings.json claude.weights.{}.{}".format(lane, window_name),
                        "window": window_name}
        inputs = {"sonnet_weekly_usd": sonnet_input, "weight": weight_input}
        share = 1.0
        formula = "weekly $ = Sonnet weekly $ / weight; low = Sonnet low / weight high; high = Sonnet high / weight low"
        source_parts = [sonnet_input["source"], weight_input["source"]]
        if lane == "fable":
            share = inp["fable_weekly_share"]["point"]
            inputs["weekly_share"] = {"point": share, "source": inp["fable_weekly_share"]["source"]}
            sub = dig(findings, "claude.windows.fable_subcap")
            inputs["cross_check_fable_subcap_usd"] = {
                "interval": sub["interval"], "point": sub["point"],
                "source": "findings.json claude.windows.fable_subcap (not used in the formula)"}
            formula = ("weekly $ = {:g} x Sonnet weekly $ / weight; low and high as for the other "
                       "models").format(share)
            source_parts.append(inp["fable_weekly_share"]["source"])
        point = share * s_point / w_point
        low = div(share * s_low, w_high)
        high = None if w_low is None or w_low == 0 else share * s_high / w_low
        if lane == "opus":
            floor = inp["opus_floor"]["weekly_usd"]
            inputs["floor_weekly_usd"] = {"point": floor, "source": inp["opus_floor"]["source"]}
            formula = ("weekly $ = max(Sonnet weekly $ / weight, {:g}) for point and low; "
                       "high = Sonnet high / weight low").format(floor)
            if point < floor:
                if status == "measured":
                    status = "lower_bound"
                note = OPUS_FLOOR_NOTE.format(floor, point)
            point = max(point, floor)
            if low is not None:
                low = max(low, floor)
            source_parts.append(inp["opus_floor"]["source"])
        source_parts.append(inp["prices"]["source"])
        key = "max20x_" + lane
        out[key], exact[key] = factor_entry(
            "Claude Max 20x", "max20x", price, (point, low, high), inputs, formula, [lane],
            "; ".join(source_parts), status, weeks, note)
    return out, exact


def codex_factors(findings, inp, weeks, doubling):
    per_credit_path = "rate_card.usd_per_credit"
    per_credit = float(dig(findings, per_credit_path))
    credit_input = {"point": per_credit, "source": "findings.json " + per_credit_path}
    lanes = sorted(lane for lane, maker in MAKERS.items() if maker == "openai")
    prices = inp["prices"]["usd_per_month"]
    pro = dig(findings, "codex.pro_lite.weekly")
    plus = dig(findings, "codex.plus.weekly")
    scale, day = doubling["scale"], doubling["day"]
    specs = [
        ("prolite", "Codex Pro Lite", prices["prolite"], scale, pro, "findings.json codex.pro_lite.weekly",
         "now: {:g} x the measured week, since the {} doubling; not re-measured yet".format(scale, day)),
        ("prolite_before", "Codex Pro Lite", prices["prolite"], 1, pro, "findings.json codex.pro_lite.weekly",
         "before the {} doubling".format(day)),
        ("plus", "Codex Plus", prices["plus"], 1, plus, "findings.json codex.plus.weekly", None),
    ]
    out, exact = {}, {}
    for key, plan, price, mult, week, path, note in specs:
        c_point = mult * week["point"]
        c_low, c_high = [mult * v for v in week["interval"]]
        inputs = {"usd_per_credit": credit_input,
                  "weekly_credits": {"interval": [c_low, c_high], "point": c_point,
                                     "source": (path if mult == 1 else "{:g} x {}".format(mult, path)),
                                     "unit": "card_credits"}}
        if key == DOUBLED_PLAN:
            inputs["doubling"] = {"date": doubling["date"], "point": mult, "source": doubling["source"]}
        source = "; ".join([inputs["weekly_credits"]["source"], credit_input["source"], inp["prices"]["source"]])
        out[key], exact[key] = factor_entry(
            plan, key, price, (c_point * per_credit, c_low * per_credit, c_high * per_credit),
            inputs, "weekly $ = weekly card credits x $ per credit", lanes, source, "measured", weeks, note)
    return out, exact


def gemini_factor(inp, weeks):
    g = inp["gemini"]
    usd = g["weekly_api_usd"]
    inputs = {"weekly_api_usd": {"interval": [usd, None], "point": usd, "source": g["source"]},
              "weekly_tokens": {"point": g["weekly_tokens"], "model": g["model"], "source": g["source"]}}
    entry, exact = factor_entry(
        "Google AI Pro", "ai_pro", inp["prices"]["usd_per_month"]["ai_pro"], (usd, usd, None),
        inputs, GEMINI_FORMULA, ["gemini"], g["source"] + "; " + inp["prices"]["source"], "lower_bound",
        weeks, GEMINI_NOTE)
    return {"ai_pro": entry}, {"ai_pro": exact}


def subsidy(findings, arms, as_of):
    inp = dig(findings, "subsidy_inputs")
    weeks = inp["weeks_per_month"]
    epoch = window_epoch(arms, DOUBLED_PLAN)
    doubling = {"date": epoch["from"], "day": epoch["from"][:10], "plan": DOUBLED_PLAN,
                "scale": float(epoch["scale"]), "source": epoch["source"]}
    factors, exact = {}, {}
    for part in (claude_factors(findings, inp, weeks), codex_factors(findings, inp, weeks, doubling),
                 gemini_factor(inp, weeks)):
        factors.update(part[0])
        exact.update(part[1])
    block = {
        "_note": ("Subsidy factor = API value of a month's allowance / the plan's monthly price; a month "
                  "is {:g} weeks. Intervals are [low, high]; null means unbounded, or n/a when the input "
                  "is not known. Plan $ per task = API $ per task / factor. Assumes the whole allowance is "
                  "used every week. Generated by tools/make-aa-cli-rate.py, checked by "
                  "tools/check-aa-cli-rate.py.").format(weeks),
        "as_of": as_of,
        "doubling": doubling,
        "factors": factors,
        "generated_by": "tools/make-aa-cli-rate.py",
        "weeks_per_month": weeks,
    }
    return block, exact


def plan_keys(lane):
    maker = MAKERS[lane]
    if maker == "anthropic":
        return ["max20x_" + lane]
    if maker == "openai":
        return list(CODEX_PLANS)
    return ["ai_pro"]


def per_task(api, factor, pending):
    """Plan $ per task from the API $ per task and the (point, low, high) factor. A pending factor
    with no upper bound has no low end yet, so its low is None rather than zero."""
    point, low, high = factor
    if low is None:
        return {"high": None, "low": None, "point": rnd(api / point, TASK_DIGITS)}
    if high is None:
        low_task = None if pending else 0.0
    else:
        low_task = rnd(api / high, TASK_DIGITS)
    return {"high": rnd(api / low, TASK_DIGITS), "low": low_task, "point": rnd(api / point, TASK_DIGITS)}


def pick(rows):
    """Latest date wins; on a tie, the later row in the file."""
    best = {}
    for order, row in enumerate(rows):
        key = (row["lane"], row["effort"], row["metric"])
        rank = (row.get("date", ""), order)
        if key not in best or rank >= best[key][0]:
            best[key] = (rank, row)
    return {key: value[1] for key, value in best.items()}


def split_name(model):
    match = re.match(r"^(.*?)\s*\((.*)\)\s*$", model)
    return (match.group(1), match.group(2)) if match else (model, None)


def build(public, findings, arms=None):
    if arms is None:
        arms = json.loads(load(ARMS))
    metrics = set()
    for spec in INDEXES.values():
        metrics.update([spec["score"], spec["cost"]] + list(spec["extra"].values()))
    rows = [row for row in public if row.get("metric") in metrics and row.get("lane") in MAKERS]
    chosen = pick(rows)
    as_of = max(row["date"] for row in chosen.values())
    block, exact = subsidy(findings, arms, as_of)

    models = {}
    for (lane, effort, metric), row in sorted(chosen.items()):
        if metric == INDEXES["cai2"]["score"]:
            name, harness = split_name(row["model"])
            models[lane] = {"harness": harness, "maker": MAKERS[lane], "name": name,
                            "plans": plan_keys(lane)}
    for lane in sorted(MAKERS):
        if lane not in models and any(key[0] == lane for key in chosen):
            models[lane] = {"harness": None, "maker": MAKERS[lane], "name": lane.title(),
                            "plans": plan_keys(lane)}

    series = {}
    for index_id, spec in sorted(INDEXES.items()):
        out = []
        pairs = sorted({(key[0], key[1]) for key in chosen if key[2] == spec["score"]},
                       key=lambda p: (p[0], EFFORTS.index(p[1]) if p[1] in EFFORTS else 99))
        for lane, effort in pairs:
            score_row = chosen[(lane, effort, spec["score"])]
            cost_row = chosen.get((lane, effort, spec["cost"]))
            api = None if cost_row is None else float(cost_row["value"])
            item = {
                "api_usd": api,
                "date": score_row["date"],
                "effort": effort,
                "lane": lane,
                "model": score_row["model"],
                "plan_usd": None if api is None else {
                    key: per_task(api, exact[key], block["factors"][key]["status"] == "pending")
                    for key in plan_keys(lane)},
                "score": score_row["value"],
                "source": score_row["source"],
                "url": score_row["url"],
            }
            for field, metric in sorted(spec["extra"].items()):
                extra = chosen.get((lane, effort, metric))
                item[field] = None if extra is None else extra["value"]
            out.append(item)
        series[index_id] = out

    sources = {}
    for row in chosen.values():
        index_id = next(i for i, s in INDEXES.items()
                        if row["metric"] in [s["score"], s["cost"]] + list(s["extra"].values()))
        sources.setdefault(row["url"], {"date": row["date"], "index": index_id, "url": row["url"]})
    data = {
        "as_of": as_of,
        "codex_plans": list(CODEX_PLANS),
        "efforts": list(EFFORTS),
        "generated_by": "tools/make-aa-cli-rate.py",
        "indexes": {key: {"label": spec["label"]} for key, spec in INDEXES.items()},
        "makers": MAKER_LABELS,
        "models": models,
        "series": series,
        "sources": sorted(sources.values(), key=lambda s: (s["index"], s["url"])),
        "subsidy": block,
    }
    return data, block


def sort_tree(value):
    if isinstance(value, dict):
        return {key: sort_tree(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [sort_tree(item) for item in value]
    return value


def page_json(data):
    text = json.dumps(data, sort_keys=True, indent=1, ensure_ascii=True)
    return "\n" + text.replace("</", "<\\/") + "\n"


def write_page(data):
    html = load(PAGE)
    if not DATA_RE.search(html):
        raise SystemExit("make-aa-cli-rate: {} has no data block".format(PAGE))
    new = DATA_RE.sub(lambda m: m.group(1) + page_json(data) + m.group(3), html, count=1)
    if new != html:
        with open(PAGE, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(new)
    return new != html


def findings_style(text):
    indent = 3
    for line in text.splitlines()[1:]:
        stripped = line.lstrip(" ")
        if stripped and len(stripped) < len(line):
            indent = len(line) - len(stripped)
            break
    sep = (",", " : ") if '" : ' in text else (",", ": ")
    ascii_only = all(ord(ch) < 128 for ch in text)
    return indent, sep, ascii_only


def write_findings(block):
    text = load(FINDINGS)
    tree = json.loads(text)
    indent, sep, ascii_only = findings_style(text)

    def dump(obj):
        return json.dumps(obj, indent=indent, separators=sep, ensure_ascii=ascii_only) + "\n"

    if dump(tree) != text:
        print("make-aa-cli-rate: warning: findings.json does not round-trip byte for byte; "
              "it will be re-serialized", file=sys.stderr)
    block = sort_tree(block)
    if "subsidy" in tree:
        tree["subsidy"] = block
        out = tree
    else:
        # Insert at its sorted place among the top-level keys, keeping the others in order.
        out, placed = {}, False
        for key, value in tree.items():
            if not placed and key > "subsidy":
                out["subsidy"] = block
                placed = True
            out[key] = value
        if not placed:
            out["subsidy"] = block
    new = dump(out)
    if new != text:
        with open(FINDINGS, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(new)
    return new != text


def shown(value, none):
    return none if value is None else "{:.2f}".format(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true",
                        help='also rewrite the "subsidy" key of findings/findings.json')
    args = parser.parse_args()
    public = json.loads(load(PUBLIC))
    findings = json.loads(load(FINDINGS))
    arms = json.loads(load(ARMS))
    data, block = build(public, findings, arms)
    changed = write_page(data)
    print("make-aa-cli-rate: page data {} ({} Coding Agent rows, {} Intelligence rows, {} factors)".format(
        "rewritten" if changed else "unchanged", len(data["series"]["cai2"]), len(data["series"]["ii5"]),
        len(block["factors"])))
    if args.write:
        changed = write_findings(block)
        print("make-aa-cli-rate: findings.json subsidy {}".format("rewritten" if changed else "unchanged"))
    for key in sorted(block["factors"]):
        entry = block["factors"][key]
        low, high = entry["interval"]
        print("  {:<15} {:>8.2f}x  [{}, {}]  {}".format(
            key, entry["point"], shown(low, "n/a"), shown(high, "null"), entry["status"]))


if __name__ == "__main__":
    main()
