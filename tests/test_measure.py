"""Synthetic fits only; no provider executable or probe driver is started."""
import contextlib
import csv
import gzip
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LIMITS = ROOT / 'findings' / 'limits'


def load(relative, **env):
    """Import a script; its module-level paths are read from `env` while it loads."""
    saved = {key: os.environ.get(key) for key in env}
    os.environ.update(env)
    try:
        spec = importlib.util.spec_from_file_location(relative.replace('/', '_'), ROOT / relative)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return module


def read_text(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8') as f:
        return f.read()


def run_quiet(function, *args):
    with contextlib.redirect_stdout(io.StringIO()):
        return function(*args)


claude = load('measure/claude/analyze_cprobes.py')
codex = load('measure/codex/fit_probes.py')
passive = load('measure/codex/fit.py')


class MeasureTests(unittest.TestCase):
    def test_quantization(self):
        self.assertEqual(claude.rise_interval(0), (0, 1))
        self.assertEqual(claude.rise_interval(1), (0, 2))
        self.assertEqual(claude.rise_interval(12), (11, 13))
        with self.assertRaises(ValueError):
            claude.rise_interval(-1)

    def test_zero_and_one_rise(self):
        # Spending 6 without a whole-point rise: capacity >6, no point or upper bound.
        self.assertEqual(claude.per_pct(6, 0), (None, 6, None))
        self.assertEqual(claude.per_pct(6, 1), (6, 3, None))
        self.assertEqual(codex.quantization(6, 0), ((0, 1), (6, None)))
        self.assertEqual(codex.quantization(6, 1), ((0, 2), (3, None)))

    def test_positive_rise(self):
        # 30 / 3 = 10, endpoints 30/4=7.5 and 30/2=15.
        self.assertEqual(claude.per_pct(30, 3), (10, 7.5, 15))
        self.assertEqual(codex.quantization(30, 3), ((2, 4), (7.5, 15)))
        with self.assertRaises(ValueError):
            claude.per_pct(30, -1)

    def test_model_factors(self):
        # Anchor 30/3=10 dollars/point; model 20/4=5: twice the meter per dollar.
        point, low, high = claude.model_factor(claude.per_pct(30, 3), claude.per_pct(20, 4))
        self.assertEqual(point, 2)
        self.assertEqual(low, 7.5 / (20 / 3))
        self.assertEqual(high, 15 / 4)
        self.assertEqual(claude.model_factor(claude.per_pct(30, 3), claude.per_pct(2, 0))[0], None)

    def test_cache_solve(self):
        # A=20+10w, C=2+6w, rise ratio 2/10: 2+6w=4+2w -> w=1/2.
        # Rounding: C/A in (1/11,3/9). Lower root -1/28; upper root 7/4.
        point, interval = claude.cache_weight(30, 20, 10, 8, 2, 2)
        self.assertAlmostEqual(point, 0.5)
        self.assertEqual(interval, (0, 1))

    def test_cache_narrow_interval(self):
        # Same costs, rises 20/100. Ratios 19/101 and 21/99.
        # Solve w=(20r-2)/(6-10r): endpoints 89/208 and 37/64.
        point, interval = claude.cache_weight(30, 20, 100, 8, 2, 20)
        self.assertAlmostEqual(point, 0.5)
        self.assertAlmostEqual(interval[0], 89 / 208)
        self.assertAlmostEqual(interval[1], 37 / 64)

    def test_cache_unidentifiable(self):
        # C=0.2*A at every weight; no unique point solution.
        point, interval = claude.cache_weight(30, 20, 10, 6, 4, 2)
        self.assertIsNone(point)
        self.assertEqual(interval, (0, 1))

    def test_codex_joint_and_passive_fit(self):
        # Hand-computed y=2u+3c+5o, independent columns, positive residual dof.
        x = [[1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 1]]
        for fit in (codex.ols_no_intercept, passive.ols):
            result = fit(x, [2, 3, 5, 10])
            for actual, expected in zip(result[0], [2, 3, 5]):
                self.assertAlmostEqual(actual, expected)
            self.assertEqual(result[2:], (4, 1))

    def test_machine_readable_evidence(self):
        data = json.loads((ROOT / 'findings/findings.json').read_text())
        self.assertEqual(data['codex']['pro_lite']['weekly']['point'], 8400)
        self.assertTrue(data['claude']['windows']['weekly']['source'])
        self.assertEqual(data['rate_card']['models']['gpt-6.1-sol'], [50, 2.5, 250])

    def test_shipped_measurements_privacy(self):
        scanner = load('tools/knowledge_scan.py')
        forbidden = re.compile(r'/home/|/mnt/|n1219|iaes|sidekick|seal\.py|campaign')
        for directory in ('measure', 'findings'):
            for path in (ROOT / directory).rglob('*'):
                if not path.is_file() or '__pycache__' in path.parts:
                    continue
                text = read_text(path)
                self.assertIsNone(forbidden.search(text), str(path.relative_to(ROOT)))
                self.assertEqual(scanner.scan_text(text), [], str(path.relative_to(ROOT)))

    def test_limits_data_manifest(self):
        data = json.loads((ROOT / 'findings/findings.json').read_text())['limits_data']
        self.assertEqual(data['dir'], 'limits/')
        self.assertTrue((ROOT / data['rerun']).is_file())
        shipped = sorted(p.relative_to(LIMITS).as_posix() for p in LIMITS.rglob('*') if p.is_file())
        self.assertEqual(data['files'], shipped)
        readme = (LIMITS / 'README.md').read_text()
        for name in shipped:
            if name != 'README.md':
                self.assertIn('`' + name.split('/')[-1] + '`', readme, name)
        for name in shipped:
            path = LIMITS / name
            if name.endswith('.json'):
                json.loads(path.read_text())
            elif name.endswith('.jsonl'):
                for line in path.read_text().splitlines():
                    json.loads(line)
            elif name.endswith('.csv'):
                rows = list(csv.reader(io.StringIO(read_text(path))))
                self.assertGreater(len(rows), 1, name)
                self.assertTrue(all(len(r) == len(rows[0]) for r in rows), name)

    def test_limits_events_are_deidentified(self):
        for name, columns in (
                ('claude/events_cprobes.csv',
                 ['ts_utc', 'model', 'input', 'cw5m', 'cw1h', 'cache_read', 'output', 'probe_block']),
                ('codex/events_probes.csv',
                 ['ts_utc', 'session_seq', 'model', 'd_input', 'd_cached', 'd_output', 'd_reasoning',
                  'used_percent'])):
            rows = list(csv.DictReader(io.StringIO(read_text(LIMITS / name))))
            self.assertEqual(list(rows[0]), columns)
        sequence = re.compile(r's\d{3}')
        ids = {r['session_seq'] for r in csv.DictReader(io.StringIO(read_text(LIMITS / 'codex/events_probes.csv')))}
        self.assertTrue(all(sequence.fullmatch(i) for i in ids))
        self.assertEqual(len(ids), 153)
        total = sum(p.stat().st_size for p in LIMITS.rglob('*') if p.is_file())
        self.assertLess(total, 1_500_000)

    def test_rerun_claude_from_shipped_data(self):
        with tempfile.TemporaryDirectory() as out:
            module = load('measure/claude/analyze_cprobes.py',
                          CLAUDE_FIT_OUT=out,
                          CLAUDE_MARKS=str(LIMITS / 'claude/marks.tsv'),
                          CLAUDE_METER=str(LIMITS / 'claude/meter_readings.jsonl'),
                          CLAUDE_EVENTS=str(LIMITS / 'claude/events_cprobes.csv'),
                          CLAUDE_EXTRACT_REPORT=str(LIMITS / 'claude/extract_report.json'),
                          CLAUDE_PROJECTS=out + '/absent')
            run_quiet(module.main)
            derived = json.loads((Path(out) / 'derived.json').read_text())
            report = (Path(out) / 'REPORT_C.md').read_text()
        shipped = json.loads((LIMITS / 'claude/derived.json').read_text())
        self.assertEqual(len(derived['blocks']), 6)
        for mine, theirs in zip(derived['blocks'], shipped['blocks']):
            self.assertEqual(mine, theirs, mine['block'])
        c2 = derived['blocks'][2]['rates']['H1']
        self.assertAlmostEqual(c2['7d'][0] * 100, 1524.9437, places=3)
        self.assertAlmostEqual(c2['7d'][1] * 100, 1016.6292, places=3)
        self.assertAlmostEqual(c2['7d'][2] * 100, 3049.8875, places=3)
        self.assertAlmostEqual(c2['5h'][0] * 100, 254.1573, places=3)
        self.assertAlmostEqual(c2['5h'][1] * 100, 234.6067, places=3)
        self.assertAlmostEqual(c2['5h'][2] * 100, 277.2625, places=3)
        weights = derived['model_factors_vs_sonnet']
        self.assertAlmostEqual(weights['Opus']['H1_5h'], 0.9453, places=4)
        self.assertAlmostEqual(weights['Haiku']['H1_5h'], 1.7195, places=4)
        self.assertAlmostEqual(weights['Fable']['H1_5h'], 2.0601, places=4)
        self.assertAlmostEqual(derived['cache_read_weight']['point'], 0.3568, places=4)
        self.assertEqual(derived['cache_read_weight']['interval'], [0.0, 1.0])
        self.assertIn('$531.3921 ($442.8268, $664.2402)', report)

    def test_rerun_codex_probes_from_shipped_data(self):
        with tempfile.TemporaryDirectory() as out:
            module = load('measure/codex/fit_probes.py',
                          CODEX_FIT_OUT=out,
                          CODEX_EVENTS=str(LIMITS / 'codex/events_probes.csv'),
                          CODEX_MARKS=str(LIMITS / 'codex/marks.tsv'))
            run_quiet(module.main)
            for name in ('intervals.csv', 'joint_fit.json'):
                self.assertEqual((Path(out) / name).read_text(), (LIMITS / 'codex' / name).read_text(), name)
            mine = list(csv.DictReader(open(Path(out) / 'block_summary.csv')))
        theirs = list(csv.DictReader(open(LIMITS / 'codex/block_summary.csv')))
        self.assertEqual(len(mine), 5)
        for a, b in zip(mine, theirs):
            if a['block'] == 'P5':
                # A zero-point block has no upper bound (the lab's copy had an invented 145.73 here).
                self.assertEqual(a['quant_cr_range'], '[14.57, inf]')
            self.assertEqual(a, b, a['block'])
        credits = sum(float(r['total_cr']) for r in mine[:3])
        self.assertAlmostEqual(credits, 1010.711, places=3)
        self.assertAlmostEqual(100 * credits / 12, 8422.6, delta=0.1)
        self.assertAlmostEqual(100 * credits / 13, 7774.7, delta=0.1)
        self.assertAlmostEqual(100 * credits / 11, 9188.3, delta=0.1)
        self.assertEqual([r['sessions'] for r in mine], ['40', '1', '29', '40', '40'])

    def test_events_read_plain_csv_and_gzip_alike(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain = LIMITS / 'codex/events_probes.csv'
            zipped = Path(tmp) / 'events_probes.csv.gz'
            with gzip.open(zipped, 'wt', encoding='utf-8', newline='') as f:
                f.write(plain.read_text(encoding='utf-8'))
            outputs = []
            for events in (plain, zipped):
                out = Path(tmp) / events.suffix.lstrip('.')
                out.mkdir()
                module = load('measure/codex/fit_probes.py',
                              CODEX_FIT_OUT=str(out),
                              CODEX_EVENTS=str(events),
                              CODEX_MARKS=str(LIMITS / 'codex/marks.tsv'))
                run_quiet(module.main)
                outputs.append({p.name: p.read_text() for p in sorted(out.iterdir())})
        self.assertIn('joint_fit.json', outputs[0])
        self.assertEqual(outputs[0], outputs[1])


if __name__ == '__main__':
    unittest.main()
