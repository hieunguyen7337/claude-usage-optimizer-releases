"""The Amp line of bin/usage-status: parsing `amp usage --details`, the 15-minute cache, and quiet degradation.

No network and no real amp: the live call is mocked, and the parse runs on the sanitised fixture."""

import datetime as dt
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "amp", "usage-details.txt")


def load_script(name, filename):
    loader = importlib.machinery.SourceFileLoader(name, os.path.join(ROOT, "bin", filename))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(module)
    return module


usage = load_script("usage_status_amp", "usage-status")
NOW = dt.datetime(2026, 11, 13, 13, 0, 0, tzinfo=dt.timezone.utc)


def fixture_text():
    with open(FIXTURE, "r", encoding="utf-8") as handle:
        return handle.read()


class ParseTests(unittest.TestCase):
    def test_fixture_parses_credits_recorded_cost_range_and_sources(self):
        parsed = usage.amp_parse(fixture_text())
        self.assertEqual(parsed["credits_remaining_usd"], 9.97)
        self.assertEqual(parsed["recorded_usd"], 0.03)
        self.assertEqual(parsed["range_days"], 7)
        self.assertEqual(parsed["sources"], [
            {"name": "Amp", "tokens": 204316, "recorded_usd": 0.03},
            {"name": "Claude Subscription", "tokens": 377818, "recorded_usd": 0.0},
        ])

    def test_missing_credits_section_is_omitted_not_fatal(self):
        text = fixture_text().replace("**Individual credits:**", "Individual credits (none):")
        parsed = usage.amp_parse(text)
        self.assertNotIn("credits_remaining_usd", parsed)
        self.assertEqual(parsed["recorded_usd"], 0.03)

    def test_no_known_figures_gives_none(self):
        self.assertIsNone(usage.amp_parse("Signed in as <account>\nnothing here\n"))
        self.assertIsNone(usage.amp_parse(None))
        self.assertIsNone(usage.amp_parse(""))

    def test_source_table_without_costs_is_skipped(self):
        text = "Total recorded cost: $0.50\n\n## From\n\n| Source | Tokens | Recorded cost |\n| --- | ---: | ---: |\n" \
               "| Amp | lots | n/a |\n"
        parsed = usage.amp_parse(text)
        self.assertEqual(parsed["recorded_usd"], 0.5)
        self.assertNotIn("sources", parsed)

    def test_signed_in_line_and_email_never_reach_the_output(self):
        text = fixture_text() + "\nSigned in as someone@example.com\n"
        data, line = self._section(text)
        self.assertNotIn("Signed in", line)
        self.assertNotIn("@", line)
        self.assertNotIn("@", json.dumps(data))

    def _section(self, text):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(usage, "amp_binary", return_value="amp"), \
                    mock.patch.object(usage, "_amp_live", return_value=usage.amp_parse(text)):
                return usage.amp_section(directory, NOW)


class SectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="amp-line-")
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        os.environ.pop("USAGE_OPTIMIZER_AMP", None)

    def tearDown(self):
        self.env.stop()
        for name in os.listdir(self.directory):
            os.unlink(os.path.join(self.directory, name))
        os.rmdir(self.directory)

    def cache_path(self):
        return os.path.join(self.directory, "amp-latest.json")

    def write_cache(self, observed, attempted=None):
        with open(self.cache_path(), "w", encoding="utf-8") as handle:
            json.dump({"observed_at": observed, "attempted_at": attempted or observed,
                       "parsed": usage.amp_parse(fixture_text())}, handle)

    def test_fixture_line_is_printed(self):
        with mock.patch.object(usage, "amp_binary", return_value="amp"), \
                mock.patch.object(usage, "_amp_live", return_value=usage.amp_parse(fixture_text())):
            data, line = usage.amp_section(self.directory, NOW)
        self.assertEqual(line, "Amp: credits $9.97 remaining; last 7 days $0.03 recorded (Amp $0.03 for 204,316 "
                               "tokens, Claude Subscription $0.00 for 377,818 tokens); read 0s ago")
        self.assertFalse(data["stale"])
        print("\nsample line from fixture: " + line)

    def test_no_binary_means_no_line_and_no_call(self):
        with mock.patch.object(usage, "amp_binary", return_value=None), \
                mock.patch.object(usage, "_amp_live") as live:
            self.assertEqual(usage.amp_section(self.directory, NOW), (None, None))
        live.assert_not_called()

    def test_off_hides_the_line_without_a_call(self):
        os.environ["USAGE_OPTIMIZER_AMP"] = "off"
        with mock.patch.object(usage, "amp_binary", return_value="amp"), \
                mock.patch.object(usage, "_amp_live") as live:
            self.assertEqual(usage.amp_section(self.directory, NOW), (None, None))
        live.assert_not_called()

    def test_fresh_cache_is_used_without_a_call(self):
        self.write_cache(utc(NOW - dt.timedelta(minutes=4)))
        with mock.patch.object(usage, "amp_binary", return_value="amp"), \
                mock.patch.object(usage, "_amp_live") as live:
            data, line = usage.amp_section(self.directory, NOW)
        live.assert_not_called()
        self.assertTrue(line.endswith("read 4m ago"), line)
        self.assertFalse(data["stale"])

    def test_expired_cache_triggers_a_live_read_and_is_rewritten(self):
        self.write_cache(utc(NOW - dt.timedelta(minutes=20)))
        with open(self.cache_path(), "r", encoding="utf-8") as handle:
            before = json.load(handle)
        newer = dict(usage.amp_parse(fixture_text()), recorded_usd=0.07)
        with mock.patch.object(usage, "amp_binary", return_value="amp"), \
                mock.patch.object(usage, "_amp_live", return_value=newer) as live:
            data, line = usage.amp_section(self.directory, NOW)
        live.assert_called_once()
        self.assertIn("$0.07 recorded", line)
        with open(self.cache_path(), "r", encoding="utf-8") as handle:
            after = json.load(handle)
        self.assertEqual(after["parsed"]["recorded_usd"], 0.07)
        self.assertNotEqual(before["observed_at"], after["observed_at"])

    def test_failed_live_read_shows_stale_cache_with_its_age(self):
        self.write_cache(utc(NOW - dt.timedelta(minutes=40)))
        with mock.patch.object(usage, "amp_binary", return_value="amp"), \
                mock.patch.object(usage, "_amp_live", return_value=None):
            data, line = usage.amp_section(self.directory, NOW)
        self.assertTrue(line.endswith("read 40m ago (stale)"), line)
        self.assertTrue(data["stale"])
        self.assertIn("$9.97 remaining", line)

    def test_failed_read_with_no_cache_is_quiet(self):
        with mock.patch.object(usage, "amp_binary", return_value="amp"), \
                mock.patch.object(usage, "_amp_live", return_value=None):
            self.assertEqual(usage.amp_section(self.directory, NOW), (None, None))

    def test_failed_read_is_not_retried_within_the_cache_window(self):
        self.write_cache(utc(NOW - dt.timedelta(minutes=40)), attempted=utc(NOW - dt.timedelta(minutes=2)))
        with mock.patch.object(usage, "amp_binary", return_value="amp"), \
                mock.patch.object(usage, "_amp_live") as live:
            data, line = usage.amp_section(self.directory, NOW)
        live.assert_not_called()
        self.assertTrue(data["stale"])

    def test_live_call_exception_never_escapes(self):
        with mock.patch.object(usage, "amp_binary", return_value="amp"), \
                mock.patch.object(usage, "_amp_live", side_effect=RuntimeError("boom")):
            self.assertEqual(usage.amp_section(self.directory, NOW), (None, None))


class LiveCallTests(unittest.TestCase):
    def test_timeout_on_windows_kills_the_tree_with_taskkill(self):
        proc = mock.Mock(pid=4242, returncode=None)
        proc.communicate.side_effect = [usage.subprocess.TimeoutExpired("amp", 20), ("", "")]
        with mock.patch.object(usage.subprocess, "Popen", return_value=proc), \
                mock.patch.object(usage.os, "name", "nt"), \
                mock.patch.object(usage.subprocess, "run") as run:
            self.assertIsNone(usage._amp_live("amp"))
        self.assertEqual(run.call_args[0][0], ["taskkill", "/T", "/F", "/PID", "4242"])
        proc.kill.assert_called_once()

    def test_nonzero_exit_gives_none(self):
        proc = mock.Mock(returncode=1)
        proc.communicate.return_value = (fixture_text(), "")
        with mock.patch.object(usage.subprocess, "Popen", return_value=proc):
            self.assertIsNone(usage._amp_live("amp"))

    def test_missing_binary_gives_none(self):
        with mock.patch.object(usage.subprocess, "Popen", side_effect=OSError("no amp")):
            self.assertIsNone(usage._amp_live("amp"))


def utc(moment):
    return moment.isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    unittest.main()
