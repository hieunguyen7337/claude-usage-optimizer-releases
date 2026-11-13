import os
import re
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, "platforms", "amp", "usage-optimizer.ts")

# PluginEventMap keys from plans/amp-codex/probe/api-excerpt.md (api lines 2290-2380).
EVENT_MAP = {"session.start", "tool.call", "tool.result", "agent.start", "agent.end", "changes.prompt"}


class AmpPluginStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(PLUGIN, "rb") as stream:
            cls.raw = stream.read()
        cls.text = cls.raw.decode("utf-8")

    def test_event_names_are_in_the_event_map(self):
        names = re.findall(r"""amp\.on\(\s*['"]([^'"]+)['"]""", self.text)
        self.assertEqual(sorted(names), ["agent.end", "agent.start"])
        for name in names:
            self.assertIn(name, EVENT_MAP)

    def test_experimental_only_behind_optional_chaining(self):
        found = re.findall(r"experimental(?!\?\.)", self.text)
        self.assertEqual(found, [])
        self.assertIn("amp.experimental?.createStatusItem", self.text)

    def test_no_tool_handlers_or_out_of_scope_apis(self):
        for banned in ("tool.call", "tool.result", "amp.ai", "registerTool", "webhook"):
            self.assertNotIn(banned, self.text)

    def test_size_limits(self):
        self.assertLess(len(self.raw), 12 * 1024)
        self.assertLessEqual(len(self.text.splitlines()), 220)

    def test_names_the_kit_commands(self):
        self.assertIn("--platform amp", self.text)
        self.assertIn("statusline-text", self.text)
        self.assertIn("turn-meter.py", self.text)
        self.assertIn("usage-optimizer.paths.json", self.text)


if __name__ == "__main__":
    unittest.main()
