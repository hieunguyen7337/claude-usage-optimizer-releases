#!/usr/bin/env python3
"""Tiny deterministic Codex app-server used only by test_codex_meter.py."""

import json
import os
import sys
import time


def emit(value):
    sys.stdout.write(json.dumps(value, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def log(method):
    path = os.environ.get("FAKE_CODEX_LOG")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(method + "\n")


def main():
    mode = os.environ.get("FAKE_CODEX_MODE", "pro")
    for raw in sys.stdin:
        try:
            request = json.loads(raw)
        except ValueError:
            continue
        method = request.get("method") if isinstance(request, dict) else None
        if not method:
            continue
        log(method)
        if method == "initialize":
            emit({"id": request.get("id"), "result": {"serverInfo": {"name": "fake"}}})
        elif method == "initialized":
            continue
        elif method == "account/rateLimits/read":
            if mode == "hang":
                sys.stdin.read()
                return 0
            if mode == "logged_out":
                emit({"id": request.get("id"), "error": {"code": 401, "message": "Not logged in"}})
                continue
            if mode == "unsupported":
                emit({"id": request.get("id"), "error": {"code": -32601, "message": "Method not found"}})
                continue
            if mode == "api_key":
                emit({"id": request.get("id"), "error": {"code": 401, "message": "API key login"}})
                continue
            if mode == "noise":
                sys.stdout.write("non-JSON app-server noise\n")
                emit({"method": "account/rateLimits/updated", "params": {"unused": True}})
                sys.stdout.flush()
            now = int(time.time())
            if mode == "plus":
                primary = {"usedPercent": 3, "windowDurationMins": 300, "resetsAt": now + 7200}
                secondary = {"usedPercent": 0, "windowDurationMins": 10080, "resetsAt": now + 345600}
                plan = "plus"
                credits = 0
            elif mode == "reached":
                primary = {"usedPercent": 97, "windowDurationMins": 10080, "resetsAt": now + 345600}
                secondary = None
                plan = "prolite"
                credits = 2
            else:
                primary = {"usedPercent": 36, "windowDurationMins": 10080, "resetsAt": now + 345600}
                secondary = None
                plan = "prolite"
                credits = 2
            snapshot = {"limitId": "codex", "planType": plan, "primary": primary,
                        "secondary": secondary,
                        "rateLimitReachedType": "weekly" if mode == "reached" else None,
                        "spendControlReached": False,
                        "credits": {"hasCredits": False, "unlimited": False, "balance": "0"}}
            emit({"id": request.get("id"), "result": {
                "rateLimits": snapshot,
                "rateLimitsByLimitId": {"codex": snapshot},
                "rateLimitResetCredits": {"availableCount": credits, "credits": None},
                "ordinaryUsageAllowed": mode != "reached",
                "accountId": "must-never-be-stored-or-printed"}})
            # The app-server remains open until the client closes stdin.
    return 0


if __name__ == "__main__":
    sys.exit(main())
