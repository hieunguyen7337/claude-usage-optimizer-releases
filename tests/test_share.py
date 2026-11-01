import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "bin", "lane-stats")


class ShareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="lane-share-")
        self.state = os.path.join(self.temp, "state")
        self.config = os.path.join(self.temp, "config")
        os.makedirs(os.path.join(self.state, "runs"))
        self.catalog = os.path.join(self.temp, "arms.json")
        with open(os.path.join(ROOT, "arms.json"), encoding="utf-8") as stream:
            data = json.load(stream)
        data["explore"]["share"] = {"repo": "owner/releases", "min_reviewed": 3}
        with open(self.catalog, "w", encoding="utf-8") as stream:
            json.dump(data, stream)
        self.env = os.environ.copy()
        self.env.update({"LANES_STATE": self.state, "LANES_CONFIG": self.config, "LANES_ARMS": self.catalog,
                         "LANES_ARMS_LOCAL": os.path.join(self.temp, "none.json"), "PYTHONUTF8": "1"})

    def tearDown(self):
        shutil.rmtree(self.temp)

    def cli(self, *args, **kwargs):
        env = kwargs.pop("env", self.env)
        return subprocess.run([sys.executable, SCRIPT] + list(args), cwd=ROOT, env=env,
                              input=kwargs.pop("input", None), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              encoding="utf-8", check=False, **kwargs)

    def add_run(self, number, outcome="accepted", reviewed=True):
        path = os.path.join(self.state, "runs", "private-run-{}".format(number))
        os.makedirs(path)
        row = {"run_dir": path, "lane": "luna", "provider": "codex", "model": "luna",
               "effort": "medium", "class": "mechanical", "tag": "SECRET-TAG", "note": "SECRET-NOTE",
               "directory": "/private/repository", "started_at": "2026-10-20T00:00:00Z",
               "ended_at": "2026-10-20T00:02:00Z", "duration_s": 120 + number, "eta_s": 60,
               "verdict": "OK", "plan": "prolite", "usage": {"list_usd": 0.5}}
        with open(os.path.join(path, "meta.json"), "w", encoding="utf-8") as stream:
            json.dump(row, stream)
        with open(os.path.join(self.state, "ledger.jsonl"), "a", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")
        if reviewed:
            with open(os.path.join(path, "review.json"), "w", encoding="utf-8") as stream:
                json.dump({"outcome": outcome, "note": "PRIVATE REVIEW", "reviewed_at": "2026-10-21T00:00:00Z"}, stream)

    def enable(self):
        result = self.cli("share", "--enable")
        self.assertEqual(result.returncode, 0, result.stderr)

    def payload(self):
        result = self.cli("share", "--week", "2026-W43")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout.rsplit("\nNothing was sent.", 1)[0]), result.stdout

    def test_preview_allowlist_and_minimum_reviewed(self):
        for number in range(2):
            self.add_run(number)
        payload, text = self.payload()
        self.assertEqual(payload["cells"], [])
        self.add_run(2)
        payload, text = self.payload()
        self.assertEqual(payload["cells"][0]["reviewed"], 3)
        self.assertEqual(set(payload["cells"][0]), {"lane", "effort", "class", "runs", "reviewed", "usable",
                                                     "med_min", "eta_ratio", "wk_pct_per_usable", "usd_per_usable"})
        for secret in ("SECRET", "private-run", "/private", "repository"):
            self.assertNotIn(secret, text)

    def test_validate_rejects_extra_key_string_number_and_oversize(self):
        for number in range(3):
            self.add_run(number)
        payload, _ = self.payload()
        cases = []
        extra = dict(payload, extra="no")
        cases.append(extra)
        wrong = json.loads(json.dumps(payload))
        wrong["cells"][0]["runs"] = "3"
        cases.append(wrong)
        for index, value in enumerate(cases):
            path = os.path.join(self.temp, "bad{}.json".format(index))
            with open(path, "w", encoding="utf-8") as stream:
                json.dump(value, stream)
            result = self.cli("share", "--validate", path)
            self.assertEqual(result.returncode, 1)
            self.assertNotIn(json.dumps(value), result.stderr)
        huge = os.path.join(self.temp, "huge.json")
        with open(huge, "w", encoding="utf-8") as stream:
            stream.write(" " * 65537)
        result = self.cli("share", "--validate", huge)
        self.assertEqual(result.returncode, 1)
        self.assertIn("exceeds 64 KB", result.stderr)

    def test_validate_accepts_markdown(self):
        for number in range(3):
            self.add_run(number)
        payload, _ = self.payload()
        path = os.path.join(self.temp, "body.md")
        with open(path, "w", encoding="utf-8") as stream:
            stream.write("intro\n```json\n" + json.dumps(payload) + "\n```\n")
        self.assertEqual(self.cli("share", "--validate", path).returncode, 0)

    def test_send_refusals(self):
        result = self.cli("share", "--send", "--week", "2026-W43", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("disabled", result.stderr)
        self.enable()
        result = self.cli("share", "--send", "--week", "2026-W43")
        self.assertEqual(result.returncode, 1)
        self.assertIn("--yes", result.stderr)
        os.makedirs(self.state, exist_ok=True)
        with open(os.path.join(self.state, "shared.jsonl"), "w", encoding="utf-8") as stream:
            stream.write(json.dumps({"week": "2026-W43", "sha256": "0" * 64}) + "\n")
        result = self.cli("share", "--send", "--week", "2026-W43", "--yes")
        self.assertEqual(result.returncode, 1)
        self.assertIn("already shared", result.stderr)

    @unittest.skipIf(os.name == "nt", "the fake gh is a POSIX script; on Windows the real gh would run")
    def test_send_uses_gh_body_file_and_never_payload_url(self):
        for number in range(3):
            self.add_run(number)
        self.enable()
        fake_dir = os.path.join(self.temp, "bin")
        os.makedirs(fake_dir)
        capture = os.path.join(self.temp, "capture.json")
        fake = os.path.join(fake_dir, "gh")
        with open(fake, "w", encoding="utf-8") as stream:
            stream.write("""#!/usr/bin/env python3
import json, os, sys
if sys.argv[1:3] == ['auth', 'status']:
    raise SystemExit(0)
args=sys.argv[1:]
body=args[args.index('--body-file')+1]
json.dump({'args': args, 'body': open(body, encoding='utf-8').read()}, open(os.environ['CAPTURE'], 'w', encoding='utf-8'))
""")
        os.chmod(fake, os.stat(fake).st_mode | stat.S_IXUSR)
        env = self.env.copy()
        env.update({"PATH": fake_dir + os.pathsep + env.get("PATH", ""), "CAPTURE": capture})
        result = self.cli("share", "--send", "--week", "2026-W43", "--yes", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(capture, encoding="utf-8") as stream:
            sent = json.load(stream)
        self.assertIn("--body-file", sent["args"])
        self.assertIn('"schema": 1', sent["body"])
        self.assertFalse(any('"schema"' in arg for arg in sent["args"]))
        with open(os.path.join(self.state, "shared.jsonl"), encoding="utf-8") as stream:
            self.assertEqual(json.loads(stream.readline())["week"], "2026-W43")


if __name__ == "__main__":
    unittest.main()
