#!/usr/bin/env python3
"""Stand-in for bin/lane in tests. Never runs a model: it writes findings.jsonl and a ledger meta.json.

Behaviour comes from FAKE_LANE_MAP (a JSON map keyed by "<arm>/<item>", where <arm> is the workspace's
parent directory). Every call is appended to FAKE_LANE_LOG as one JSON line, so tests can assert on argv.
"""
import argparse
import datetime
import json
import os
import sys


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("lane")
    parser.add_argument("-C", dest="workspace", required=True)
    parser.add_argument("-b", dest="brief", required=True)
    parser.add_argument("-e", dest="effort", required=True)
    parser.add_argument("-m", dest="model")
    parser.add_argument("--class", dest="unit_class")
    parser.add_argument("--tag")
    parser.add_argument("--off-catalog", action="store_true")
    parser.add_argument("--timeout", type=int)
    parser.add_argument("-o", dest="outdir", required=True)
    args = parser.parse_args(argv)

    workspace = os.path.abspath(args.workspace)
    arm = os.path.basename(os.path.dirname(workspace))
    item = os.path.basename(workspace)
    brief_text = open(args.brief, encoding="utf-8").read() if os.path.isfile(args.brief) else ""
    log_path = os.environ.get("FAKE_LANE_LOG")
    if log_path:
        with open(log_path, "a", encoding="utf-8") as stream:
            stream.write(json.dumps({"arm": arm, "item": item, "argv": argv,
                                     "brief_rendered": "{{ITEM_PATH}}" not in brief_text}) + "\n")

    with open(os.environ["FAKE_LANE_MAP"], encoding="utf-8") as stream:
        spec = json.load(stream).get(arm + "/" + item, {})
    model = args.model or spec.get("model") or args.lane
    os.makedirs(args.outdir, exist_ok=True)
    started = spec.get("started_at") or utc_now()
    meta = {"lane": args.lane, "provider": "codex" if args.lane.startswith(("luna", "sol", "astra")) else "claude",
            "model": model, "effort": args.effort, "dir": workspace, "class": args.unit_class, "tag": args.tag,
            "off_catalog": bool(args.off_catalog), "usage": {"before": None, "after": None,
                                                              **(spec.get("usage") or {})},
            "started_at": started, "ended_at": None, "duration_s": None, "exit_code": None,
            "verdict": None, "session_id": spec.get("session_id")}
    with open(os.path.join(args.outdir, "meta.json"), "w", encoding="utf-8") as stream:
        json.dump(meta, stream, indent=2)

    findings = spec.get("findings")
    if findings is not None:
        with open(os.path.join(workspace, "findings.jsonl"), "w", encoding="utf-8") as stream:
            for row in findings:
                stream.write(json.dumps(row) + "\n")
    code = int(spec.get("exit", 0))
    meta.update({"ended_at": utc_now(), "duration_s": spec.get("duration_s", 1.0), "exit_code": code,
                 "verdict": spec.get("verdict", "OK" if code == 0 else "FAILED")})
    with open(os.path.join(args.outdir, "meta.json"), "w", encoding="utf-8") as stream:
        json.dump(meta, stream, indent=2)
    print("lane={} verdict={} exit={}".format(args.lane, meta["verdict"], code))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
