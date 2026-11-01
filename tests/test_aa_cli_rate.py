"""findings/aa-cli-rate: the checker, the generator and the page contract."""

import copy
import importlib.util
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = ROOT / "findings" / "aa-cli-rate" / "index.html"
PUBLIC = ROOT / "findings" / "public.json"
FINDINGS = ROOT / "findings" / "findings.json"
ARMS = ROOT / "arms.json"
CHECKER = ROOT / "tools" / "check-aa-cli-rate.py"
GENERATOR = ROOT / "tools" / "make-aa-cli-rate.py"
DATA_RE = re.compile(r'(<script type="application/json" id="data">)(.*?)(</script>)', re.S)
HALF_UNIT = 0.0005 + 1e-9  # factors are stored to 3 decimals
ALLOWED_SCRIPT_HOSTS = ("https://cdnjs.cloudflare.com/", "https://cdn.jsdelivr.net/npm/", "https://unpkg.com/",
                        "https://cdn.tailwindcss.com/", "https://code.jquery.com/")
DOUBLING_URL = "https://x.com/thsottiaux/status/2115850175868727621"


def read(path):
    return pathlib.Path(path).read_text(encoding="utf-8")


def load_json(path):
    return json.loads(read(path))


def write_json(path, obj):
    pathlib.Path(path).write_text(json.dumps(obj), encoding="utf-8")


def load_generator():
    spec = importlib.util.spec_from_file_location("make_aa_cli_rate", str(GENERATOR))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_checker(*args):
    return subprocess.run([sys.executable, str(CHECKER)] + list(args), capture_output=True, text=True,
                          encoding="utf-8", cwd=str(ROOT))


def page_data(text):
    return json.loads(DATA_RE.search(text).group(2))


def with_data(text, data):
    blob = "\n" + json.dumps(data, sort_keys=True, indent=1).replace("</", "<\\/") + "\n"
    return DATA_RE.sub(lambda m: m.group(1) + blob + m.group(3), text, count=1)


def with_arms_scale(arms, scale):
    """A copy of arms.json with the Pro Lite window epoch scaled to `scale`."""
    arms = copy.deepcopy(arms)
    for epoch in arms["providers"]["codex"]["window_epochs"]:
        if epoch["plan"] == "prolite":
            epoch["scale"] = scale
    return arms


def plan_per_task(data, index, lane, effort, key):
    row = next(r for r in data["series"][index] if r["lane"] == lane and r["effort"] == effort)
    return row["plan_usd"][key]


class CheckerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_shipped_page_passes(self):
        result = run_checker()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("check-aa-cli-rate: OK", result.stdout)

    def tampered_page(self, mutate):
        text = read(PAGE)
        data = page_data(text)
        mutate(data)
        path = self.base / "index.html"
        path.write_text(with_data(text, data), encoding="utf-8")
        return path

    def test_tampered_plan_figure_fails(self):
        def mutate(data):
            row = next(r for r in data["series"]["cai2"] if r["lane"] == "opus")
            row["plan_usd"]["max20x_opus"]["point"] = round(row["plan_usd"]["max20x_opus"]["point"] * 1.01, 6)
        result = run_checker("--page", str(self.tampered_page(mutate)))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("cai2 opus max max20x_opus point", result.stdout)

    def test_tampered_factor_fails(self):
        def mutate(data):
            data["subsidy"]["factors"]["prolite"]["point"] = 14.6
        result = run_checker("--page", str(self.tampered_page(mutate)))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("page subsidy prolite point", result.stdout)

    def test_tampered_doubling_fails(self):
        def mutate(data):
            data["subsidy"]["doubling"]["source"] = "Doubled, no source given."
        result = run_checker("--page", str(self.tampered_page(mutate)))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("page subsidy doubling", result.stdout)

    def test_tampered_bound_status_fails(self):
        def mutate(data):
            data["subsidy"]["factors"]["max20x_opus"]["status"] = "measured"
        result = run_checker("--page", str(self.tampered_page(mutate)))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("page subsidy max20x_opus status", result.stdout)

    def test_rounding_noise_passes(self):
        def mutate(data):
            value = data["series"]["ii5"][0]["plan_usd"]
            key = sorted(value)[0]
            value[key]["point"] = value[key]["point"] + 0.0000004
        result = run_checker("--page", str(self.tampered_page(mutate)))
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_missing_row_fails(self):
        def mutate(data):
            data["series"]["ii5"] = [r for r in data["series"]["ii5"] if r["lane"] != "luna"]
        result = run_checker("--page", str(self.tampered_page(mutate)))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("ii5 rows", result.stdout)

    def test_changed_source_value_fails(self):
        public = json.loads(read(PUBLIC))
        for row in public:
            if row["metric"] == "aa_cai2_cost_per_task_usd" and row["lane"] == "sol":
                row["value"] = 1.6
        path = self.base / "public.json"
        path.write_text(json.dumps(public), encoding="utf-8")
        result = run_checker("--public", str(path))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("cai2 sol max api_usd", result.stdout)

    def test_findings_subsidy_mismatch_fails(self):
        findings = json.loads(read(FINDINGS))
        findings["subsidy"]["factors"]["max20x_sonnet"]["interval"][1] = 70.0
        path = self.base / "findings.json"
        path.write_text(json.dumps(findings), encoding="utf-8")
        result = run_checker("--findings", str(path))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("findings.json subsidy max20x_sonnet high", result.stdout)

    def test_checker_figures_follow_findings_inputs(self):
        # A changed input, with the page and findings.json both regenerated from it, passes, and the
        # checker prints the figure the generator computed.
        gen = load_generator()
        findings = load_json(FINDINGS)
        findings["subsidy_inputs"]["gemini"]["weekly_api_usd"] = 100
        data, block = gen.build(load_json(PUBLIC), findings, load_json(ARMS))
        findings["subsidy"] = block
        findings_path = self.base / "findings.json"
        write_json(findings_path, findings)
        page = self.base / "index.html"
        page.write_text(with_data(read(PAGE), data), encoding="utf-8")
        result = run_checker("--page", str(page), "--findings", str(findings_path))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(block["factors"]["ai_pro"]["point"], round(100 * 4.345 / 19.99, 3))
        self.assertIn("  {:<15} {:6.2f}x".format("ai_pro", block["factors"]["ai_pro"]["point"]), result.stdout)

    def test_page_disagreeing_with_findings_fails(self):
        findings = load_json(FINDINGS)
        findings["subsidy_inputs"]["gemini"]["weekly_api_usd"] = 100
        path = self.base / "findings.json"
        write_json(path, findings)
        result = run_checker("--findings", str(path))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("page subsidy ai_pro point", result.stdout)

    def test_page_disagreeing_with_arms_fails(self):
        path = self.base / "arms.json"
        write_json(path, with_arms_scale(load_json(ARMS), 3.0))
        result = run_checker("--arms", str(path))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("page subsidy prolite point", result.stdout)


class GeneratorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gen = load_generator()

    def build(self, findings=None, arms=None):
        return self.gen.build(load_json(PUBLIC), load_json(FINDINGS) if findings is None else findings,
                              load_json(ARMS) if arms is None else arms)

    def test_page_is_current(self):
        data, _ = self.build()
        self.assertEqual(page_data(read(PAGE)), json.loads(json.dumps(data)))

    def test_findings_subsidy_is_current(self):
        _, block = self.build()
        self.assertEqual(json.loads(read(FINDINGS)).get("subsidy"), json.loads(json.dumps(block)))

    def test_deterministic(self):
        first, _ = self.build()
        second, _ = self.build()
        self.assertEqual(self.gen.page_json(first), self.gen.page_json(second))

    def test_headline_factors(self):
        _, block = self.build()
        factors = block["factors"]
        self.assertAlmostEqual(factors["max20x_sonnet"]["point"], 1525 * 4.345 / 200, delta=HALF_UNIT)
        self.assertEqual(factors["ai_pro"]["interval"][1], None)
        self.assertEqual(factors["ai_pro"]["interval"][0], factors["ai_pro"]["point"])
        self.assertAlmostEqual(factors["max20x_opus"]["point"], 2700 * 4.345 / 200, delta=HALF_UNIT)
        self.assertAlmostEqual(factors["prolite"]["point"], 2 * factors["prolite_before"]["point"], delta=3 * HALF_UNIT)

    def test_doubling_is_recorded_with_its_source(self):  # F1
        _, block = self.build()
        doubling = block["doubling"]
        self.assertEqual(doubling["date"], "2026-10-29T16:56:07Z")
        self.assertEqual(doubling["day"], "2026-10-29")
        self.assertEqual(doubling["scale"], 2.0)
        self.assertIn("2026-10-29 16:56:07 UTC", doubling["source"])
        self.assertIn(DOUBLING_URL, doubling["source"])
        self.assertIn("Plus is not named", doubling["source"])
        self.assertEqual(block["factors"]["prolite"]["inputs"]["doubling"]["source"], doubling["source"])
        data, _ = self.build()
        self.assertEqual(data["subsidy"]["doubling"], json.loads(json.dumps(doubling)))

    def test_window_scale_comes_from_arms_not_a_constant(self):  # F4
        _, block = self.build(arms=with_arms_scale(load_json(ARMS), 3.0))
        self.assertEqual(block["doubling"]["scale"], 3.0)
        self.assertAlmostEqual(block["factors"]["prolite"]["point"], 3 * block["factors"]["prolite_before"]["point"],
                               delta=3 * HALF_UNIT)
        self.assertNotIn("PRO_LITE_DOUBLING", read(GENERATOR))

    def test_opus_floor_is_a_lower_bound(self):  # F2
        _, block = self.build()
        opus = block["factors"]["max20x_opus"]
        self.assertEqual(opus["status"], "lower_bound")
        self.assertAlmostEqual(opus["point"], 58.7, delta=0.05)
        self.assertIn("calibration floor", opus["note"])

    def test_opus_above_floor_is_measured(self):  # F2
        findings = load_json(FINDINGS)
        findings["claude"]["windows"]["weekly"]["H1"]["point"] = 3000
        _, block = self.build(findings=findings)
        opus = block["factors"]["max20x_opus"]
        self.assertEqual(opus["status"], "measured")
        self.assertAlmostEqual(opus["point"], 3000 / 0.67 * 4.345 / 200, delta=HALF_UNIT)

    def test_haiku_low_end_is_pending_until_weekly_is_measured(self):  # F3
        data, block = self.build()
        self.assertEqual(block["factors"]["max20x_haiku"]["status"], "pending")
        plan = plan_per_task(data, "cai2", "haiku", "max", "max20x_haiku")
        self.assertIsNone(plan["low"])
        self.assertIsNotNone(plan["high"])
        findings = load_json(FINDINGS)
        findings["claude"]["weights"]["haiku"]["weekly"] = {"interval": [1.5, 2.5], "point": 2.0}
        data, _ = self.build(findings=findings)
        plan = plan_per_task(data, "cai2", "haiku", "max", "max20x_haiku")
        self.assertIsNotNone(plan["low"])

    def test_haiku_falls_back_to_five_hour_weight_until_measured(self):
        findings = load_json(FINDINGS)
        findings["claude"]["weights"]["haiku"]["weekly"] = {"interval": None, "point": None}
        _, block = self.build(findings=findings)
        haiku = block["factors"]["max20x_haiku"]
        self.assertEqual(haiku["status"], "pending")
        self.assertEqual(haiku["inputs"]["weight"]["window"], "five_hour")
        findings["claude"]["weights"]["haiku"]["weekly"] = {"interval": [1.5, 2.5], "point": 2.0}
        _, block = self.build(findings=findings)
        haiku = block["factors"]["max20x_haiku"]
        self.assertEqual(haiku["status"], "measured")
        self.assertAlmostEqual(haiku["point"], 1525 / 2.0 * 4.345 / 200, delta=HALF_UNIT)
        self.assertAlmostEqual(haiku["interval"][1], 3050 / 1.5 * 4.345 / 200, delta=HALF_UNIT)

    def test_null_weekly_interval_gives_n_a_not_a_crash(self):  # F5
        findings = load_json(FINDINGS)
        findings["claude"]["weights"]["haiku"]["weekly"] = {"interval": None, "point": 2.0}
        data, block = self.build(findings=findings)
        haiku = block["factors"]["max20x_haiku"]
        self.assertEqual(haiku["status"], "measured")
        self.assertIsNotNone(haiku["point"])
        self.assertEqual(haiku["interval"], [None, None])
        self.assertEqual(haiku["weekly_api_usd"]["interval"], [None, None])
        self.assertIn("no interval", haiku["note"])
        plan = plan_per_task(data, "cai2", "haiku", "max", "max20x_haiku")
        self.assertEqual((plan["low"], plan["high"]), (None, None))
        self.assertIsNotNone(plan["point"])
        json.dumps(data)
        _, shipped = self.build()
        self.assertEqual(block["factors"]["max20x_sonnet"], shipped["factors"]["max20x_sonnet"])

    def test_doubled_window_halves_plan_dollars_per_task(self):  # F6
        public, findings, arms = load_json(PUBLIC), load_json(FINDINGS), load_json(ARMS)
        scale2, _ = self.gen.build(public, findings, with_arms_scale(arms, 2.0))
        scale4, _ = self.gen.build(public, findings, with_arms_scale(arms, 4.0))
        now = plan_per_task(scale2, "cai2", "sol", "max", "prolite")["point"]
        before = plan_per_task(scale2, "cai2", "sol", "max", "prolite_before")["point"]
        doubled_again = plan_per_task(scale4, "cai2", "sol", "max", "prolite")["point"]
        self.assertAlmostEqual(now / before, 0.5, delta=1e-3)
        self.assertAlmostEqual(doubled_again / now, 0.5, delta=1e-3)

    def test_larger_subsidy_factor_lowers_plan_dollars_per_task(self):  # F6
        public, arms = load_json(PUBLIC), load_json(ARMS)
        base_findings = load_json(FINDINGS)
        base, _ = self.gen.build(public, base_findings, arms)
        bigger = copy.deepcopy(base_findings)
        h1 = bigger["claude"]["windows"]["weekly"]["H1"]
        h1["point"] = h1["point"] * 2
        h1["interval"] = [v * 2 for v in h1["interval"]]
        more, _ = self.gen.build(public, bigger, arms)
        base_sonnet = plan_per_task(base, "cai2", "sonnet", "max", "max20x_sonnet")["point"]
        more_sonnet = plan_per_task(more, "cai2", "sonnet", "max", "max20x_sonnet")["point"]
        self.assertLess(more_sonnet, base_sonnet)
        self.assertAlmostEqual(more_sonnet / base_sonnet, 0.5, delta=1e-3)
        cheaper = copy.deepcopy(base_findings)
        cheaper["subsidy_inputs"]["prices"]["usd_per_month"]["prolite"] = 50
        cheap, _ = self.gen.build(public, cheaper, arms)
        base_prolite = plan_per_task(base, "cai2", "sol", "max", "prolite")["point"]
        cheap_prolite = plan_per_task(cheap, "cai2", "sol", "max", "prolite")["point"]
        self.assertLess(cheap_prolite, base_prolite)
        self.assertAlmostEqual(cheap_prolite / base_prolite, 0.5, delta=1e-3)

    def test_findings_write_keeps_style(self):
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "findings.json"
            shutil.copy2(str(FINDINGS), str(path))
            original = read(path)
            saved = self.gen.FINDINGS
            try:
                self.gen.FINDINGS = str(path)
                _, block = self.build()
                self.gen.write_findings(block)
                once = read(path)
                self.gen.write_findings(block)
                twice = read(path)
            finally:
                self.gen.FINDINGS = saved
            self.assertEqual(once, twice)
            self.assertEqual(once, original)  # the shipped file already holds the current block
            self.assertIn('\n   "subsidy" : {\n', once)


class ContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(PAGE)
        cls.style = re.search(r"<style>(.*?)</style>", cls.text, re.S).group(1)
        cls.markup = DATA_RE.sub("", cls.text)

    def test_title_meta_style_come_first(self):
        head = self.text.lstrip()
        match = re.match(r"<title>([^<]*)</title>\s*<meta name=\"claude:viewport-fit-sides\" content=\"cover\">\s*<style>", head)
        self.assertIsNotNone(match, head[:200])
        title = match.group(1)
        self.assertTrue(2 <= len(title.split()) <= 4, title)
        self.assertNotRegex(title, r"[:–—]| - ")
        self.assertNotIn("artificial", title.lower())

    def test_no_document_skeleton_tags(self):
        self.assertNotRegex(self.text, re.compile(r"<\s*(!doctype|html|head|body)\b", re.I))

    def test_scripts_from_allowed_hosts_pinned(self):
        for src in re.findall(r"<script[^>]*\ssrc=\"([^\"]+)\"", self.markup):
            self.assertTrue(src.startswith(ALLOWED_SCRIPT_HOSTS), src)
            self.assertRegex(src, r"[@/]v?\d+\.\d+\.\d+(/|$)", src)
        for href in re.findall(r"<link[^>]*rel=\"stylesheet\"[^>]*href=\"([^\"]+)\"", self.markup):
            self.assertTrue(href.startswith("https://fonts.googleapis.com/"), href)
        for tag, url in re.findall(r"<(img|iframe|video|audio|source|object|embed)[^>]*\s(?:src|data)=\"([^\"]+)\"", self.markup):
            self.fail("external or embedded resource: <{} {}>".format(tag, url))
        self.assertNotRegex(self.markup, r"\bfetch\(|XMLHttpRequest|window\.print|\sdownload[\s=>]")

    def test_fonts_have_fallbacks(self):
        for decl in re.findall(r"--font-[\w-]+:\s*([^;]+);", self.style):
            self.assertRegex(decl, r"(sans-serif|serif|monospace)\s*$", decl)

    def test_tokens_defined_for_light_and_both_dark_blocks(self):
        light = re.search(r"(?<![\w\]\)])\:root\s*\{(.*?)\}", self.style, re.S)
        media = re.search(r"@media \(prefers-color-scheme: dark\)\s*\{\s*:root:not\(\[data-theme=\"light\"\]\)\s*\{(.*?)\}\s*\}",
                          self.style, re.S)
        explicit = re.search(r":root\[data-theme=\"dark\"\]\s*\{(.*?)\}", self.style, re.S)
        self.assertTrue(light and media and explicit)

        def tokens(block):
            return dict(re.findall(r"(--[\w-]+):\s*([^;]+);", block))

        light_t, media_t, explicit_t = tokens(light.group(1)), tokens(media.group(1)), tokens(explicit.group(1))
        colors = {k for k, v in light_t.items() if re.match(r"(#|rgba?\(|hsla?\()", v.strip())}
        self.assertGreater(len(colors), 10)
        self.assertEqual(set(media_t), colors)
        self.assertEqual(media_t, explicit_t)
        for block in (media.group(1), explicit.group(1)):
            self.assertRegex(block, r"color-scheme:\s*dark")
        used = set(re.findall(r"var\((--[\w-]+)", self.markup))
        self.assertFalse(used - set(light_t), used - set(light_t))
        self.assertRegex(self.style, r"\bbody\s*\{[^}]*background:\s*var\(--")
        # Outside the token blocks, no literal colors in the CSS or the script.
        rest = self.style.replace(light.group(0), "").replace(media.group(0), "").replace(explicit.group(0), "")
        rest += self.markup.split("<script>", 1)[1]
        self.assertEqual(re.findall(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b|rgba?\([^)]*\)|hsla?\([^)]*\)", rest), [])

    def test_side_gutter_and_padding_block(self):
        rule = re.search(r"\.page\s*\{(.*?)\}", self.style, re.S).group(1)
        self.assertIn("padding-left: max(16px, env(safe-area-inset-left, 0px))", rule)
        self.assertIn("padding-right: max(16px, env(safe-area-inset-right, 0px))", rule)
        self.assertIn("padding-block:", rule)
        self.assertNotRegex(rule, r"(^|[\s;])padding:")
        self.assertIn("overflow-x: auto", self.style)

    def test_every_control_has_an_id_and_focus_state(self):
        controls = re.findall(r"<(input|select|button|textarea|summary)\b([^>]*)>", self.markup)
        self.assertGreater(len(controls), 10)
        ids = []
        for tag, attrs in controls:
            found = re.search(r"\sid=\"([^\"]+)\"", " " + attrs)
            self.assertIsNotNone(found, "<{}{}> has no id".format(tag, attrs))
            ids.append(found.group(1))
        self.assertEqual(len(ids), len(set(ids)))
        for selector in ("input:focus-visible + label", "summary:focus-visible", ":focus-visible"):
            self.assertIn(selector, self.style)
        script = self.markup.split("<script>", 1)[1]
        self.assertNotRegex(script, r"createElement\(\"(input|select|button|textarea)\"")

    def test_numbers_in_columns_use_tabular_figures(self):
        self.assertRegex(self.style, r"td\.num[^{]*\{[^}]*tabular-nums")

    def test_local_storage_is_guarded(self):
        script = self.markup.split("<script>", 1)[1]
        for match in re.finditer(r"localStorage", script):
            before = script[max(0, match.start() - 200):match.start()]
            self.assertIn("try", before)

    def test_one_data_block_and_cited_source(self):
        self.assertEqual(len(DATA_RE.findall(self.text)), 1)
        data = page_data(self.text)
        self.assertTrue(data["sources"])
        self.assertTrue(all(s["url"].startswith("https://artificialanalysis.ai/") for s in data["sources"]))

    def test_bounds_pending_and_doubling_are_shown(self):  # F1, F2, F3, F5
        script = self.markup.split("<script>", 1)[1]
        self.assertIn('">= "', script)
        self.assertIn('"pending to "', script)
        self.assertIn('" bound"', script)
        self.assertIn('"n/a"', script)
        self.assertIn('id="doubling-note"', self.markup)
        self.assertIn("D.subsidy.doubling.source", script)


if __name__ == "__main__":
    unittest.main()
