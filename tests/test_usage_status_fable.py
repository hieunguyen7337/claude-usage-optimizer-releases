"""Fable's own bar in bin/usage-status, read from the /usage cache Claude Code keeps in ~/.claude.json.

Claude Code rewrites that cache only when usage is fetched (opening /usage), so after a weekly reset the cached bar
is expired until then: usage-status must say so rather than drop the bar silently (seen 2026-11-16)."""

import datetime as dt
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_script(name, filename):
    loader = importlib.machinery.SourceFileLoader(name, os.path.join(ROOT, "bin", filename))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(module)
    return module


usage = load_script("usage_status_fable", "usage-status")
NOW = dt.datetime(2026, 11, 16, 8, 0, 0, tzinfo=dt.timezone.utc)
FETCHED = dt.datetime(2026, 11, 14, 2, 44, 0, tzinfo=dt.timezone.utc)


class FableBarTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp.name, "claude.json")
        patcher = mock.patch.dict(os.environ, {"USAGE_OPTIMIZER_CLAUDE_JSON": self.path})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.temp.cleanup)

    def write(self, resets_at):
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump({"cachedUsageUtilization": {"fetchedAtMs": FETCHED.timestamp() * 1000, "utilization": {
                "limits": [{"kind": "weekly_all", "percent": 14, "resets_at": resets_at},
                           {"kind": "weekly_scoped", "percent": 14, "resets_at": resets_at,
                            "scope": {"model": {"display_name": "Fable"}}}],
                "weekly_scoped_shares": [{"limit_index": 1, "used_percent_of_weekly": 7,
                                          "allowance_percent_of_weekly": 50}]}}}, handle)

    def test_a_current_bar_is_read_and_not_called_expired(self):
        self.write("2026-11-22T02:00:00+00:00")
        limits = usage.cached_scoped_limits(NOW)
        self.assertEqual([(item["name"], item["used_percentage"], item["share_of_week"]) for item in limits],
                         [("Fable", 14, 7)])
        self.assertEqual(usage.cached_scoped_expired(NOW, {"Fable"}), ([], None))

    def test_a_bar_whose_window_reset_since_is_named_with_the_read_time(self):
        self.write("2026-11-15T01:59:59+00:00")
        self.assertEqual(usage.cached_scoped_limits(NOW), [])
        names, fetched = usage.cached_scoped_expired(NOW)
        self.assertEqual(names, ["Fable"])
        self.assertTrue(fetched.startswith("2026-11-14T02:44"), fetched)

    def test_no_cache_means_nothing_to_say(self):
        self.assertEqual(usage.cached_scoped_expired(NOW), ([], None))
        with mock.patch.dict(os.environ, {"USAGE_OPTIMIZER_CLAUDE_JSON": "off"}):
            self.assertEqual(usage.cached_scoped_expired(NOW), ([], None))


if __name__ == "__main__":
    unittest.main()
