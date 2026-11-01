#!/usr/bin/env python3
"""Check the inline data of findings/aa-cli-rate/index.html against its sources.

Usage: tools/check-aa-cli-rate.py [--page PATH] [--public PATH] [--findings PATH] [--arms PATH]

Recomputes, without importing tools/make-aa-cli-rate.py, every subsidy factor and every plan-rate
cost per task from findings/public.json, findings/findings.json (its "subsidy_inputs" and the Claude
and Codex measurements) and arms.json (the Pro Lite window epoch), and compares them with the
page's <script type="application/json" id="data"> block and with the "subsidy" key of findings.json.
Prints a summary; exits 1 on any mismatch beyond rounding.
"""

import argparse
import json
import math
import os
import re
import sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TOL_USD = 0.005 + 1e-9        # weekly and monthly dollars, stored to 2 decimals
TOL_FACTOR = 0.0005 + 1e-9    # factors, stored to 3 decimals
TOL_TASK = 0.0000005 + 1e-12  # plan $ per task, stored to 6 decimals

CLAUDE = ("opus", "sonnet", "haiku", "fable")
CODEX = ("sol", "terra", "luna", "astra")
GOOGLE = ("gemini",)
DOUBLED_PLAN = "prolite"
METRICS = {
    "cai2": ("aa_cai2_index", "aa_cai2_cost_per_task_usd"),
    "ii5": ("aa_ii_v5_score", "aa_ii_v5_cost_per_task_usd"),
}
TB4 = "aa_cai2_tb4_pct"
PLANS = ("max20x_sonnet", "max20x_opus", "max20x_haiku", "max20x_fable", "prolite", "prolite_before", "plus", "ai_pro")


def read_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def page_data(path):
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()
    found = re.findall(r'<script type="application/json" id="data">(.*?)</script>', text, re.S)
    if len(found) != 1:
        raise SystemExit("check-aa-cli-rate: expected one data block in {}, found {}".format(path, len(found)))
    return json.loads(found[0])


class Report:
    def __init__(self):
        self.checked = 0
        self.problems = []

    def num(self, where, got, want, tol):
        self.checked += 1
        if want is None or got is None:
            if want is not got:
                self.problems.append("{}: page has {!r}, expected {!r}".format(where, got, want))
            return
        if not isinstance(got, (int, float)) or isinstance(got, bool) or not math.isfinite(got) \
                or abs(got - want) > tol:
            self.problems.append("{}: page has {!r}, expected {:.6g}".format(where, got, want))

    def same(self, where, got, want):
        self.checked += 1
        if got != want:
            self.problems.append("{}: page has {!r}, expected {!r}".format(where, got, want))


def pair_mul(value, by):
    return None if value is None else value * by


def pair_div(value, by):
    return None if value is None or by is None else value / by


def prolite_epoch(arms):
    epochs = [e for e in arms["providers"]["codex"]["window_epochs"] if e.get("plan") == DOUBLED_PLAN]
    return max(epochs, key=lambda e: e["from"])


def weekly_claude(findings, inp, lane):
    """((point, low, high) list dollars of `lane` a week on Max 20x, status). A None low and high
    means the weight's interval is not known; a None high alone means unbounded."""
    h1 = findings["claude"]["windows"]["weekly"]["H1"]
    son, son_lo, son_hi = float(h1["point"]), float(h1["interval"][0]), float(h1["interval"][1])
    weights = findings["claude"]["weights"][lane]
    pending = (weights.get("weekly") or {}).get("point") is None
    weight = weights["five_hour"] if pending else weights["weekly"]
    w = float(weight["point"])
    w_iv = weight.get("interval")
    share = inp["fable_weekly_share"]["point"] if lane == "fable" else 1.0
    point = share * son / w
    if w_iv is None:
        low = high = None
    else:
        w_lo, w_hi = float(w_iv[0]), float(w_iv[1])
        low = share * son_lo / w_hi
        high = share * son_hi / w_lo if w_lo > 0 else None
    status = "pending" if pending else None
    if lane == "opus":
        floor = float(inp["opus_floor"]["weekly_usd"])
        if point < floor and status is None:
            status = "lower_bound"
        point = max(point, floor)
        if low is not None:
            low = max(low, floor)
    return (point, low, high), status


def weekly_codex(findings, plan, scale):
    per_credit = findings["rate_card"]["usd_per_credit"]
    week = findings["codex"]["plus" if plan == "plus" else "pro_lite"]["weekly"]
    mult = scale if plan == DOUBLED_PLAN else 1.0
    return tuple(mult * c * per_credit for c in (week["point"], week["interval"][0], week["interval"][1]))


def expected_factors(findings, arms):
    inp = findings["subsidy_inputs"]
    weeks = inp["weeks_per_month"]
    prices = inp["prices"]["usd_per_month"]
    scale = float(prolite_epoch(arms)["scale"])
    raw = {}
    for lane in CLAUDE:
        week, status = weekly_claude(findings, inp, lane)
        raw["max20x_" + lane] = (week, prices["max20x"], status)
    for plan in ("prolite", "prolite_before", "plus"):
        price = prices["plus"] if plan == "plus" else prices["prolite"]
        raw[plan] = (weekly_codex(findings, plan, scale), price, None)
    gem = inp["gemini"]["weekly_api_usd"]
    raw["ai_pro"] = ((gem, gem, None), prices["ai_pro"], "lower_bound")
    result = {}
    for key, (week, price, status) in raw.items():
        month = tuple(pair_mul(v, weeks) for v in week)
        fac = tuple(pair_div(v, price) for v in month)
        result[key] = {"week": week, "month": month, "factor": fac, "price": price, "status": status}
    return result


def expected_doubling(findings, arms):
    epoch = prolite_epoch(arms)
    return {"date": epoch["from"], "day": epoch["from"][:10], "plan": DOUBLED_PLAN,
            "scale": float(epoch["scale"]), "source": epoch["source"]}


def check_subsidy(report, label, block, want, doubling, weeks):
    block = block if isinstance(block, dict) else {}
    report.same(label + " doubling", block.get("doubling"), doubling)
    report.same(label + " weeks_per_month", block.get("weeks_per_month"), weeks)
    factors = block.get("factors", {}) if isinstance(block.get("factors"), dict) else {}
    report.same(label + " factor keys", sorted(factors), sorted(want))
    for key in sorted(want):
        got, exp = factors.get(key), want[key]
        if not isinstance(got, dict):
            continue
        where = "{} {}".format(label, key)
        report.num(where + " price", got.get("price_usd_month"), exp["price"], 1e-9)
        point, low, high = exp["factor"]
        report.num(where + " point", got.get("point"), point, TOL_FACTOR)
        interval = got.get("interval") or [None, None]
        report.num(where + " low", interval[0], low, TOL_FACTOR)
        report.num(where + " high", interval[1], high, TOL_FACTOR)
        for name, idx in (("weekly_api_usd", "week"), ("monthly_api_usd", "month")):
            money = got.get(name) or {}
            values = exp[idx]
            report.num("{} {} point".format(where, name), money.get("point"), values[0], TOL_USD)
            span = money.get("interval") or [None, None]
            report.num("{} {} low".format(where, name), span[0], values[1], TOL_USD)
            report.num("{} {} high".format(where, name), span[1], values[2], TOL_USD)
        if exp["status"]:
            report.same(where + " status", got.get("status"), exp["status"])
        elif got.get("status") in ("pending", "lower_bound"):
            report.problems.append("{}: status {!r}, expected a measured figure".format(where, got.get("status")))


def latest(public):
    keep = {}
    for order, row in enumerate(public):
        key = (row.get("lane"), row.get("effort"), row.get("metric"))
        if key not in keep or (row.get("date", ""), order) >= keep[key][0]:
            keep[key] = ((row.get("date", ""), order), row)
    return {key: pair[1] for key, pair in keep.items()}


def plans_of(lane):
    if lane in CLAUDE:
        return ["max20x_" + lane]
    if lane in CODEX:
        return ["prolite", "prolite_before", "plus"]
    return ["ai_pro"]


def expected_task(api, factor, status):
    """Plan $ per task (point, low, high) from the API $ per task and a (point, low, high) factor."""
    point, low, high = factor
    if low is None:
        return {"point": api / point, "low": None, "high": None}
    low_task = (None if status == "pending" else 0.0) if high is None else api / high
    return {"point": api / point, "low": low_task, "high": api / low}


def check_series(report, data, public, factors):
    rows = latest(public)
    series = data.get("series", {})
    lanes = set(CLAUDE + CODEX + GOOGLE)
    for index, (score_metric, cost_metric) in sorted(METRICS.items()):
        want = {(lane, effort): row for (lane, effort, metric), row in rows.items()
                if metric == score_metric and lane in lanes}
        got = {(r.get("lane"), r.get("effort")): r for r in series.get(index, [])}
        report.same(index + " rows", sorted(got), sorted(want))
        for key in sorted(set(want) & set(got)):
            where = "{} {} {}".format(index, *key)
            row, item = want[key], got[key]
            report.num(where + " score", item.get("score"), float(row["value"]), 1e-9)
            report.same(where + " url", item.get("url"), row["url"])
            report.same(where + " date", item.get("date"), row["date"])
            if index == "cai2":
                tb4 = rows.get(key + (TB4,))
                report.num(where + " tb4_pct", item.get("tb4_pct"), None if tb4 is None else float(tb4["value"]), 1e-9)
            cost = rows.get(key + (cost_metric,))
            api = None if cost is None else float(cost["value"])
            report.num(where + " api_usd", item.get("api_usd"), api, 1e-9)
            plans = item.get("plan_usd")
            if api is None:
                report.same(where + " plan_usd", plans, None)
                continue
            plans = plans if isinstance(plans, dict) else {}
            report.same(where + " plan keys", sorted(plans), sorted(plans_of(key[0])))
            for plan in plans_of(key[0]):
                fac = factors[plan]
                value = plans.get(plan) or {}
                want_task = expected_task(api, fac["factor"], fac["status"])
                tag = "{} {}".format(where, plan)
                for part in ("point", "low", "high"):
                    report.num(tag + " " + part, value.get(part), want_task[part], TOL_TASK)


def show(value, none):
    return none if value is None else "{:.2f}".format(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--page", default=os.path.join(KIT, "findings", "aa-cli-rate", "index.html"))
    parser.add_argument("--public", default=os.path.join(KIT, "findings", "public.json"))
    parser.add_argument("--findings", default=os.path.join(KIT, "findings", "findings.json"))
    parser.add_argument("--arms", default=os.path.join(KIT, "arms.json"))
    args = parser.parse_args()

    data = page_data(args.page)
    public = read_json(args.public)
    findings = read_json(args.findings)
    arms = read_json(args.arms)
    weeks = findings["subsidy_inputs"]["weeks_per_month"]
    doubling = expected_doubling(findings, arms)
    factors = expected_factors(findings, arms)
    report = Report()

    check_subsidy(report, "page subsidy", data.get("subsidy"), factors, doubling, weeks)
    if "subsidy" in findings:
        check_subsidy(report, "findings.json subsidy", findings["subsidy"], factors, doubling, weeks)
    else:
        report.problems.append('findings.json has no "subsidy" key; run tools/make-aa-cli-rate.py --write')
    check_series(report, data, public, factors)

    rows = sum(len(v) for v in data.get("series", {}).values())
    print("check-aa-cli-rate: {} figures checked ({} rows, {} factors)".format(report.checked, rows, len(factors)))
    print("  doubling {} scale {:g} from {}".format(doubling["plan"], doubling["scale"], doubling["date"]))
    for key in PLANS:
        point, low, high = factors[key]["factor"]
        print("  {:<15} {:6.2f}x  [{}, {}]".format(key, point, show(low, "n/a"), show(high, "null")))
    if report.problems:
        print("check-aa-cli-rate: {} mismatch(es):".format(len(report.problems)))
        for problem in report.problems[:50]:
            print("  " + problem)
        if len(report.problems) > 50:
            print("  ... and {} more".format(len(report.problems) - 50))
        sys.exit(1)
    print("check-aa-cli-rate: OK")


if __name__ == "__main__":
    main()
