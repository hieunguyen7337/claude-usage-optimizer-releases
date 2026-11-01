#!/usr/bin/env python3
"""Write one Claude Code agent definition per Claude arm: agents/lane-<lane>-<effort>.md.

An arm of a Claude lane (haiku, sonnet, opus, fable) gets a file when its status is active; a fable arm also
when its status is manual, since the fable lane's arms are advisors called by role, never drawn by the picker.
"""
import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANES = ("haiku", "sonnet", "opus", "fable")
# Lanes whose manual arms get a file too.
MANUAL_LANES = ("fable",)
TEMPLATE = """---
name: lane-{lane}-{effort}
description: Kit worker arm {lane} {effort} ({model}). Only for prompts printed by `lane --subagent`.
model: {model}
effort: {effort}
omitClaudeMd: true
---

You are a worker for the Claude Usage Optimizer kit. Your prompt names a brief file: read it in full first and
follow it exactly. Work only in the directory the brief names. Your final message is your report.
"""


def wanted(arms_path):
    with open(arms_path, encoding="utf-8") as stream:
        data = json.load(stream)
    files = {}
    for arm in data.get("arms", []):
        lane, status = arm.get("lane"), arm.get("status")
        if lane in LANES and (status == "active" or (status == "manual" and lane in MANUAL_LANES)):
            name = "lane-{}-{}.md".format(arm["lane"], arm["effort"])
            files[name] = TEMPLATE.format(lane=arm["lane"], effort=arm["effort"], model=arm["model"])
    return dict(sorted(files.items()))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arms", default=os.path.join(ROOT, "arms.json"))
    parser.add_argument("--out", default=os.path.join(ROOT, "agents"))
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 on any difference")
    args = parser.parse_args(argv)
    files = wanted(args.arms)
    existing = {os.path.basename(path) for path in glob.glob(os.path.join(args.out, "lane-*.md"))}
    differences = []
    for name, text in files.items():
        path = os.path.join(args.out, name)
        try:
            with open(path, encoding="utf-8", newline="") as stream:
                current = stream.read()
        except OSError:
            current = None
        if current != text:
            differences.append(("write" if current is None else "update", name))
            if not args.check:
                os.makedirs(args.out, exist_ok=True)
                with open(path, "w", encoding="utf-8", newline="\n") as stream:
                    stream.write(text)
    for name in sorted(existing - set(files)):
        differences.append(("remove", name))
        if not args.check:
            os.unlink(os.path.join(args.out, name))
    for action, name in differences:
        print("{}{} {}".format("would " if args.check else "", action, name))
    return 1 if args.check and differences else 0


if __name__ == "__main__":
    sys.exit(main())
