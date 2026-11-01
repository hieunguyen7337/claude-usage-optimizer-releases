import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)
import knowledge_scan


SCANNER = os.path.join(TOOLS, "knowledge_scan.py")
EXPORTER = os.path.join(TOOLS, "export-knowledge.py")
WINDOWS = os.name == "nt"


def find_bash():
    if WINDOWS:
        for candidate in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files (x86)\Git\bin\bash.exe"):
            if os.path.exists(candidate):
                return candidate
        return None
    return shutil.which("bash")


BASH = find_bash()
SEED = {"verbose": True, "tui": "fullscreen", "permissions": {"defaultMode": "bypassPermissions"}}


def write_text(path, text):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as stream:
        stream.write(text)


def read_text(path):
    with open(path, "r", encoding="utf-8", newline="") as stream:
        return stream.read()


class KnowledgeScannerTests(unittest.TestCase):
    def test_scanner_kinds_allowlists_and_cli_output(self):
        key_value = "Abcdefghijklm123"
        key_prefixes = ["sk-", "ghp_", "gho_", "github_pat_", "glpat-", "xoxa-", "xoxb-", "xoxp-", "AKIA", "AIza"]
        positives = "\n".join([
            "jane.roe@mailbox.co",
            "93.184.216.34",
            "93-184-216-34.sslip.io",
            *[prefix + key_value for prefix in key_prefixes],
            "eyJabcdefghijk.eyJ1234567890",
            "-----BEGIN RSA PRIVATE KEY-----\nprivate payload\n-----END RSA PRIVATE KEY-----",
            "legacy_id 4242",
            "Abcdefghijklmnopqrstuvwxyz123456",
        ])
        hits = knowledge_scan.scan_text(positives)
        self.assertTrue({"email", "ipv4", "dashed-ipv4", "key-prefix", "jwt", "pem", "account-id", "long-token"}
                        <= {kind for _, kind, _ in hits}, hits)
        self.assertEqual(len([kind for _, kind, _ in hits if kind == "key-prefix"]), len(key_prefixes))

        allowed = "\n".join([
            "a@example.com b@example.org c@example.net",
            "a@docs.example b@site.test c@site.invalid d@site.localhost e@localhost",
            "noreply@anthropic.com",
            "postgresql@16-main.service",
            "0.0.0.0 127.0.0.1:5433 10.2.3.4 172.16.1.2 192.168.1.2 169.254.1.2",
            "192.0.2.4 198.51.100.9 203.0.113.8 HeadlessChrome/120.0.0.0",
            "a" * 64,
            "<email> <ip> <id>",
            "some-long-hyphenated-slug-with-number-123",
            "/var/www/cal-wt/INT",
            "react@18.3.1",
            "golang.org/x/net@v0.1.0",
            "deploy@vps",
            "git@github.com:Org/Repo.git",
            "sk-learn",
            "MAKIAisjustawordwithmanycharacters",
            "sk-" + "a" * 15,
        ])
        self.assertEqual(knowledge_scan.scan_text(allowed), [])
        markdown_ids = knowledge_scan.scan_text("legacy_id **4242** and `legacy_id` 4343", allow=set())
        self.assertEqual([kind for _, kind, _ in markdown_ids], ["account-id", "account-id"])
        address = "jane.roe@mailbox.co"
        other_address = "robin.smith@mailbox.co"
        allow_hits = knowledge_scan.scan_text(address + " " + other_address, allow={address})
        self.assertEqual(allow_hits, [(1, "email", len(other_address))])
        # The shipped allowlist may only excuse long-token false positives, never an email, IP or key.
        for literal in knowledge_scan.load_allowlist():
            kinds = {kind for _, kind, _ in knowledge_scan.scan_text(literal, allow=set())}
            self.assertEqual(kinds, {"long-token"}, "allowlist entry of length %d" % len(literal))

        with tempfile.TemporaryDirectory() as temp:
            write_text(os.path.join(temp, "one.md"), "contact jane.roe@mailbox.co\n")
            result = subprocess.run(
                [sys.executable, "-I", SCANNER, temp], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                encoding="utf-8", errors="replace", check=False,
            )
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1, output)
        self.assertIn("one.md:1 email len=%d" % len("jane.roe@mailbox.co"), output)
        self.assertNotIn("jane.roe@mailbox.co", output)


class KnowledgeExporterTests(unittest.TestCase):
    def run_export(self, memory, out, rules=None, date="2026-10-16", env_extra=None):
        command = [sys.executable, "-I", EXPORTER, "--memory", memory, "--out", out, "--date", date]
        if rules is not None:
            command.extend(["--rules", rules])
        env = dict(os.environ)
        env.update(env_extra or {})
        return subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              encoding="utf-8", errors="replace", env=env, check=False)

    def test_export_redacts_indexes_and_removes_stale_notes(self):
        with tempfile.TemporaryDirectory() as temp:
            memory = os.path.join(temp, "memory")
            out = os.path.join(temp, "pack")
            os.makedirs(memory)
            write_text(os.path.join(memory, "MEMORY.md"),
                       "---\ndescription: Memory overview\n---\n"
                       "# Memory overview\nmail-note first, then plain-note, then index-by-theme and MEMORY.\n")
            write_text(os.path.join(memory, "index-by-theme.md"),
                       "# Themes\n- **Core** — clustered-note\n")
            write_text(os.path.join(memory, "clustered-note.md"),
                       "---\ndescription: Clustered description\n---\n# Clustered\n")
            write_text(os.path.join(memory, "mail-note.md"),
                       "---\ndescription: Redacted contact note\n---\n"
                       "# Contact details\nmail jane.roe@mailbox.co and 93.184.216.34; "
                       "proxy 93-184-216-34.sslip.io legacy_id 4242 CASEME123\n")
            plain_path = os.path.join(memory, "plain-note.md")
            write_text(plain_path, "# Plain note description\r\nOrdinary content.\r\n")
            write_text(os.path.join(memory, "other-note.md"),
                       "---\ndescription: Archive description\n---\n# Archive\n")
            write_text(os.path.join(memory, "excluded-note.md"), "# Excluded note\n")
            rules = os.path.join(temp, "rules.tsv")
            write_text(rules, "# synthetic rules\nexclude\texcluded-note\nreplace\tCASEME123\tSAFEVALUE\n")
            notes_out = os.path.join(out, "notes")
            os.makedirs(notes_out)
            write_text(os.path.join(notes_out, "old.md"), "old note\n")
            write_text(os.path.join(out, "SKILL.md"), "placeholder owned by gatekeeper\n")
            write_text(os.path.join(out, "keep.txt"), "keep this\n")

            result = self.run_export(memory, out, rules)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("notes=6 records=0 excluded=1 removed=1 email=1 ip=2 id=1 literal=1", result.stdout)
            self.assertFalse(os.path.exists(os.path.join(notes_out, "old.md")))
            self.assertEqual(read_text(os.path.join(out, "SKILL.md")), "placeholder owned by gatekeeper\n")
            self.assertEqual(read_text(os.path.join(out, "keep.txt")), "keep this\n")
            self.assertFalse(os.path.exists(os.path.join(notes_out, "excluded-note.md")))
            self.assertEqual(sorted(os.listdir(notes_out)), sorted([
                "MEMORY.md", "index-by-theme.md", "clustered-note.md", "mail-note.md", "plain-note.md", "other-note.md",
            ]))
            with open(plain_path, "rb") as source, open(os.path.join(notes_out, "plain-note.md"), "rb") as exported:
                self.assertEqual(exported.read(), source.read())

            redacted = read_text(os.path.join(notes_out, "mail-note.md"))
            self.assertNotIn("jane.roe@mailbox.co", redacted)
            self.assertIn("<email>", redacted)
            self.assertIn("<ip>", redacted)
            self.assertIn("<ip>.sslip.io", redacted)
            self.assertIn("legacy_id <id>", redacted)
            self.assertIn("SAFEVALUE", redacted)
            self.assertNotIn("CASEME123", redacted)

            index = read_text(os.path.join(out, "INDEX.md"))
            self.assertTrue(index.startswith("<!-- Generated by tools/export-knowledge.py on 2026-10-16; do not edit. -->\n"))
            self.assertIn("## Core\n\n- [clustered-note](notes/clustered-note.md) — Clustered description", index)
            self.assertLess(index.index("[mail-note]"), index.index("[plain-note]"))
            self.assertLess(index.index("[plain-note]"), index.index("[index-by-theme]"))
            self.assertIn("[mail-note](notes/mail-note.md) — Redacted contact note", index)
            self.assertIn("[plain-note](notes/plain-note.md) — # Plain note description", index)
            self.assertIn("## Other\n\n- [other-note](notes/other-note.md) — Archive description", index)
            self.assertNotIn("excluded-note", index)
            for name in os.listdir(notes_out):
                slug = name[:-3]
                self.assertEqual(index.count("[%s](notes/%s.md)" % (slug, slug)), 1, slug)

    def test_failed_export_is_atomic_and_cleans_staging(self):
        with tempfile.TemporaryDirectory() as temp:
            memory = os.path.join(temp, "memory")
            out = os.path.join(temp, "pack")
            os.makedirs(memory)
            key = "ghp_Abcdefghijklmnop1234"
            write_text(os.path.join(memory, "incident.md"), "# Incident\ncredential: %s\n" % key)
            write_text(os.path.join(out, "notes", "x.md"), "pre-existing note\r\n")
            write_text(os.path.join(out, "INDEX.md"), "pre-existing index\r\n")
            with open(os.path.join(out, "notes", "x.md"), "rb") as stream:
                original_note = stream.read()
            with open(os.path.join(out, "INDEX.md"), "rb") as stream:
                original_index = stream.read()
            result = self.run_export(memory, out)
            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 1, output)
            self.assertIn("notes/incident.md:2 key-prefix len=%d" % len(key), output)
            self.assertNotIn(key, output)
            with open(os.path.join(out, "notes", "x.md"), "rb") as stream:
                self.assertEqual(stream.read(), original_note)
            with open(os.path.join(out, "INDEX.md"), "rb") as stream:
                self.assertEqual(stream.read(), original_index)
            self.assertEqual(glob.glob(os.path.join(temp, ".knowledge-export-*")), [])

    def test_record_and_task_rules_render_redacted_programme_records(self):
        with tempfile.TemporaryDirectory() as temp:
            memory = os.path.join(temp, "memory")
            out = os.path.join(temp, "pack")
            home = os.path.join(temp, "home")
            task_dir = os.path.join(home, "tasks")
            os.makedirs(memory)
            os.makedirs(task_dir)
            write_text(os.path.join(memory, "MEMORY.md"), "# Memory\n")
            programme = os.path.join(home, "programme.md")
            write_text(programme,
                       "# Programme record\nOwner jane.roe@mailbox.co at 93.184.216.34 legacy_id=7\n")
            plan = os.path.join(home, "plan.md")
            write_text(plan, "# Programme plan\nNo personal data.\n")
            write_text(os.path.join(task_dir, "10.json"), json.dumps({
                "id": "10", "subject": "Release task", "status": "in_progress",
                "description": "Deploy to 93.184.216.34\nlegacy_id 4242",
            }))
            write_text(os.path.join(task_dir, "2.json"), json.dumps({
                "id": "2", "subject": "Contact jane.roe@mailbox.co", "status": "open",
                "description": "first line\nsecond line",
            }))
            write_text(os.path.join(task_dir, "broken.json"), "not JSON\n")
            write_text(os.path.join(task_dir, "ignored.json"), json.dumps({"id": 4, "subject": "missing status"}))
            rules = os.path.join(temp, "rules.tsv")
            write_text(rules, "record\t~/programme.md\tzeta\nrecord\t~/plan.md\ntasks\t~/tasks\talpha\n")

            result = self.run_export(memory, out, rules, env_extra={"HOME": home, "USERPROFILE": home})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("notes=1 records=3 excluded=0 removed=0 email=2 ip=2 id=2 literal=0", result.stdout)
            tasks = read_text(os.path.join(out, "records", "alpha.md"))
            self.assertTrue(tasks.startswith("# Task list alpha (2 tasks)\n\n"))
            self.assertLess(tasks.index("- **#2 [open]**"), tasks.index("- **#10 [in_progress]**"))
            self.assertIn("- **#2 [open]** Contact <email>\n  first line\n  second line", tasks)
            self.assertIn("  Deploy to <ip>\n  legacy_id <id>", tasks)
            record = read_text(os.path.join(out, "records", "zeta.md"))
            self.assertIn("Owner <email> at <ip> legacy_id=<id>", record)

            index = read_text(os.path.join(out, "INDEX.md"))
            self.assertIn("Notes: 1\nRecords: 3", index)
            self.assertIn("## Programme records\n\n- [alpha](records/alpha.md) — Task list alpha (2 tasks)", index)
            self.assertLess(index.index("[alpha](records/alpha.md)"), index.index("[zeta](records/zeta.md)"))
            self.assertIn("- [plan](records/plan.md) — Programme plan", index)

            write_text(rules, "")
            again = self.run_export(memory, out, rules)
            self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
            self.assertIn("records=0 excluded=0 removed=3", again.stdout)
            self.assertEqual(os.listdir(os.path.join(out, "records")), [])

    def test_record_rules_reject_bad_names_and_missing_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            memory = os.path.join(temp, "memory")
            out = os.path.join(temp, "pack")
            os.makedirs(memory)
            source = os.path.join(temp, "source.md")
            write_text(source, "# Record\n")
            cases = [
                ("record\t%s\tbad/name\n" % source, 1, "bad record name"),
                ("record\t%s\tvalid-name\n" % os.path.join(temp, "missing.md"), 1, "missing record source"),
                ("record\t%s\tduplicate\nrecord\t%s\tduplicate\n" % (source, source), 2, "duplicate name"),
                ("tasks\t%s\tmissing-tasks\n" % os.path.join(temp, "missing-tasks"), 1, "missing task directory"),
            ]
            for line, line_number, label in cases:
                with self.subTest(label=label):
                    rules = os.path.join(temp, "rules.tsv")
                    write_text(rules, line)
                    result = self.run_export(memory, out, rules)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertIn("invalid rules line %d" % line_number, result.stderr)
                    self.assertNotIn(line.strip(), result.stderr)

    def test_private_packs_are_clean_and_index_links_resolve(self):
        packs = [pack for pack in glob.glob(os.path.join(ROOT, "private", "skills", "*"))
                 if os.path.isdir(os.path.join(pack, "notes"))]
        if not packs:
            self.skipTest("private skill notes are absent in this checkout")
        for pack in packs:
            with self.subTest(pack=os.path.basename(pack)):
                notes = os.path.join(pack, "notes")
                self.assertEqual(knowledge_scan.scan_tree(pack), [])
                index = read_text(os.path.join(pack, "INDEX.md"))
                note_names = sorted(name for name in os.listdir(notes) if name.endswith(".md"))
                links = re.findall(r"\]\(notes/([^\)]+)\)", index)
                self.assertEqual(sorted(links), sorted(name for name in note_names))
                for name in note_names:
                    self.assertTrue(os.path.isfile(os.path.join(notes, name)), name)
                for linked in links:
                    self.assertTrue(os.path.isfile(os.path.join(pack, "notes", linked)), linked)


@unittest.skipIf(BASH is None, "Git Bash (or bash) is not installed")
class KnowledgeInstallTests(unittest.TestCase):
    def test_installs_all_skills_prunes_stale_notes_and_dry_run_keeps_them(self):
        with tempfile.TemporaryDirectory() as home:
            source = os.path.join(home, "source")
            shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", "dist"))
            shutil.rmtree(os.path.join(source, "private", "skills"))
            private_skill = os.path.join(source, "private", "skills", "example-pack")
            public_skill = os.path.join(source, "skills", "public-example-pack")
            for skill in (private_skill, public_skill):
                write_text(os.path.join(skill, "SKILL.md"), "# Example skill\n")
                write_text(os.path.join(skill, "notes", "current-note.md"), "current\n")
                write_text(os.path.join(skill, "records", "current-record.md"), "current\n")
            claude = os.path.join(home, ".claude")
            os.makedirs(claude)
            write_text(os.path.join(claude, "settings.json"), json.dumps(SEED, indent=2))
            prefix = os.path.join(claude, "usage-optimizer")
            installed = os.path.join(claude, "skills", "example-pack")
            kit_skill = os.path.join(prefix, "skills", "example-pack")
            retired_claude = os.path.join(claude, "skills", "codex-delegation")
            retired_prefix = os.path.join(prefix, "skills", "codex-delegation")
            write_text(os.path.join(installed, "notes", "stale-note.md"), "old claude note\n")
            write_text(os.path.join(kit_skill, "notes", "stale-note.md"), "old kit note\n")
            write_text(os.path.join(installed, "records", "stale-record.md"), "old claude record\n")
            write_text(os.path.join(kit_skill, "records", "stale-record.md"), "old kit record\n")
            write_text(os.path.join(retired_claude, "SKILL.md"), "old Claude delegation skill\n")
            write_text(os.path.join(retired_prefix, "SKILL.md"), "old kit delegation skill\n")
            write_text(os.path.join(installed, "keep.txt"), "keep claude\n")
            write_text(os.path.join(kit_skill, "keep.txt"), "keep kit\n")

            def install(*args):
                env = dict(os.environ)
                env.update({"HOME": home, "USERPROFILE": home, "USAGE_OPTIMIZER_SKIP_CLI_CHECK": "1"})
                env.pop("CLAUDE_CONFIG_DIR", None)
                return subprocess.run(
                    [BASH, source.replace("\\", "/") + "/install.sh", *args], cwd=home, env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", errors="replace",
                    timeout=300, check=False,
                )

            result = install()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            source_skills = (glob.glob(os.path.join(source, "skills", "*")) +
                             glob.glob(os.path.join(source, "private", "skills", "*")))
            for source_skill in sorted(source_skills):
                if os.path.isdir(source_skill):
                    name = os.path.basename(source_skill)
                    self.assertTrue(os.path.isfile(os.path.join(claude, "skills", name, "SKILL.md")), name)
            self.assertFalse(os.path.exists(os.path.join(installed, "notes", "stale-note.md")))
            self.assertFalse(os.path.exists(os.path.join(kit_skill, "notes", "stale-note.md")))
            self.assertFalse(os.path.exists(os.path.join(installed, "records", "stale-record.md")))
            self.assertFalse(os.path.exists(os.path.join(kit_skill, "records", "stale-record.md")))
            self.assertFalse(os.path.exists(retired_claude))
            self.assertFalse(os.path.exists(retired_prefix))
            self.assertEqual(read_text(os.path.join(installed, "keep.txt")), "keep claude\n")
            self.assertEqual(read_text(os.path.join(kit_skill, "keep.txt")), "keep kit\n")
            self.assertIn("Removed stale note:", result.stdout)
            self.assertIn("Removed stale record:", result.stdout)
            self.assertIn("Removed retired skill:", result.stdout)
            self.assertTrue(os.path.isfile(os.path.join(prefix, "LANES.md")))
            backups = glob.glob(os.path.join(claude, "backups", "usage-optimizer-*",
                                             "skills", "example-pack", "notes", "stale-note.md"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(read_text(backups[0]), "old claude note\n")
            record_backups = glob.glob(os.path.join(claude, "backups", "usage-optimizer-*",
                                                    "skills", "example-pack", "records", "stale-record.md"))
            self.assertEqual(len(record_backups), 1)
            self.assertEqual(read_text(record_backups[0]), "old claude record\n")
            retired_backups = glob.glob(os.path.join(claude, "backups", "usage-optimizer-*",
                                                     "skills", "codex-delegation", "SKILL.md"))
            self.assertEqual(len(retired_backups), 1)
            self.assertEqual(read_text(retired_backups[0]), "old Claude delegation skill\n")

            write_text(os.path.join(installed, "notes", "stale-note.md"), "dry claude note\n")
            write_text(os.path.join(kit_skill, "notes", "stale-note.md"), "dry kit note\n")
            write_text(os.path.join(installed, "records", "stale-record.md"), "dry claude record\n")
            write_text(os.path.join(kit_skill, "records", "stale-record.md"), "dry kit record\n")
            write_text(os.path.join(retired_claude, "SKILL.md"), "dry Claude delegation skill\n")
            write_text(os.path.join(retired_prefix, "SKILL.md"), "dry kit delegation skill\n")
            dry_run = install("--dry-run")
            self.assertEqual(dry_run.returncode, 0, dry_run.stdout + dry_run.stderr)
            self.assertEqual(read_text(os.path.join(installed, "notes", "stale-note.md")), "dry claude note\n")
            self.assertEqual(read_text(os.path.join(kit_skill, "notes", "stale-note.md")), "dry kit note\n")
            self.assertEqual(read_text(os.path.join(installed, "records", "stale-record.md")), "dry claude record\n")
            self.assertEqual(read_text(os.path.join(kit_skill, "records", "stale-record.md")), "dry kit record\n")
            self.assertTrue(os.path.isfile(os.path.join(retired_claude, "SKILL.md")))
            self.assertTrue(os.path.isfile(os.path.join(retired_prefix, "SKILL.md")))


if __name__ == "__main__":
    unittest.main()
