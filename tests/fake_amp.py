#!/usr/bin/env python3
"""Tiny stand-in for `amp threads usage <id> --details`, used only by test_turn_meter.py.

FAKE_AMP_MODE: "ok" (the default) prints the sanitised fixture; "subscription" prints the report of a thread routed through
the Claude subscription (threads-usage-subscription.txt); "window" prints it with a windowed scope; "garbage" prints text
with no cost line; "fail" exits 1; "hang" sleeps past any timeout the test sets. FAKE_AMP_LOG, when set, gets one line per
call with its arguments.
"""

import os
import sys
import time

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "amp")
FIXTURE = os.path.join(FIXTURES, "threads-usage-details.txt")
SUBSCRIPTION_FIXTURE = os.path.join(FIXTURES, "threads-usage-subscription.txt")


def main():
    log = os.environ.get("FAKE_AMP_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(" ".join(sys.argv[1:]) + "\n")
    mode = os.environ.get("FAKE_AMP_MODE", "ok")
    if mode == "hang":
        time.sleep(30)
        return 0
    if mode == "fail":
        sys.stderr.write("error: not signed in\n")
        return 1
    if mode == "garbage":
        sys.stdout.write("something other than a usage report\n")
        return 0
    with open(SUBSCRIPTION_FIXTURE if mode == "subscription" else FIXTURE, encoding="utf-8") as handle:
        text = handle.read()
    if mode == "window":
        text = text.replace("Scope: Entire lifetime of this thread.", "Scope: Last 7 days.")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
