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
        for banned in ("tool.call", "tool.result", "amp.ai", "webhook"):
            self.assertNotIn(banned, self.text)

    def test_size_limits(self):
        self.assertLess(len(self.raw), 16 * 1024)
        self.assertLessEqual(len(self.text.splitlines()), 300)

    def test_lane_tool_and_kit_mode_are_registered_once(self):
        self.assertEqual(re.findall(r"amp\.registerTool\(", self.text), ["amp.registerTool("])
        self.assertIn("name: 'kit_lane_run'", self.text)
        self.assertEqual(re.findall(r"amp\.registerAgentMode\(", self.text), ["amp.registerAgentMode("])
        # The static metadata Amp asks external plugins to carry for each registered mode.
        self.assertIn("// @amp-agent-mode key=kit label=kit", self.text)

    def test_agent_fields_exist_in_the_plugin_api(self):
        # CreateAgentConfig, RunAgentOptions and PluginAgentModeDefinition of @ampcode/plugin (2026-10-30 and 2026-11-13
        # builds). AgentSubagentPin (`subagents`, `oracle`) was removed before the probed build (probe/P1.md, R1).
        self.assertNotIn("subagents", self.text)
        self.assertNotIn("oracle", self.text)
        config = {"name", "extends", "model", "instructions", "tools", "reasoningEffort", "compactionThresholdTokens",
                  "features", "display"}
        for block in re.findall(r"amp\.createAgent\(\{(.*?)\}\)", self.text, re.S):
            for key in re.findall(r"(?:^|[{,\s])(\w+):", block):
                self.assertIn(key, config)
        self.assertIn("{ parentThreadID: parent, timeoutMs: spec.timeoutMs }", self.text)
        self.assertIn("agent: agent.definition", self.text)
        self.assertIn("compactionThresholdTokens: mode.compactionThresholdTokens", self.text)

    def test_worker_silence_comes_before_every_registration(self):
        silence = self.text.index("if (!paths || process.env.KIT_LANE_RUN) return")
        for call in ("amp.registerTool(", "amp.registerAgentMode(", "amp.on("):
            self.assertLess(silence, self.text.index(call))
        # Metering alone stays off with USAGE_OPTIMIZER_TURNS=off; the lane tool and mode do not depend on it.
        self.assertLess(self.text.index("amp.registerAgentMode("), self.text.index("USAGE_OPTIMIZER_TURNS === 'off'"))

    def test_lane_hooks_are_the_python_side(self):
        for name in ("amp-run-spec", "amp-run-end", "amp-mode", "/bin/lane.py"):
            self.assertIn(name, self.text)

    def test_names_the_kit_commands(self):
        self.assertIn("--platform amp", self.text)
        self.assertIn("statusline-text", self.text)
        self.assertIn("turn-meter.py", self.text)
        self.assertIn("usage-optimizer.paths.json", self.text)


if __name__ == "__main__":
    unittest.main()
