import importlib.machinery
import importlib.util
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "bin", "cloud-notify")
_loader = importlib.machinery.SourceFileLoader("cloud_notify_under_test", SCRIPT)
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
cloud_notify = importlib.util.module_from_spec(_spec)
_loader.exec_module(cloud_notify)

TOPIC = "Secret-Topic-q8Zx31"
SESSION = "cse_01TestSessionAbc"
T0 = 1000000.0  # an injected clock, in seconds


def clean_environ():
    """os.environ without the variables this tool reads, so the host session (maybe a cloud one) cannot leak in."""
    return {key: value for key, value in os.environ.items()
            if not key.startswith(("CLAUDE_", "USAGE_OPTIMIZER_"))}


class Sender:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def __call__(self, url, headers, body, timeout):
        self.calls.append({"url": url, "headers": headers, "body": body.decode("utf-8"), "timeout": timeout})
        if self.error:
            raise self.error


class CloudNotifyTestCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cloud-notify-test-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.project = os.path.join(self.root, "my-repo")
        os.makedirs(os.path.join(self.project, ".claude"))
        self.state = os.path.join(self.root, "state")
        self.env = {"CLAUDE_CODE_REMOTE": "true", "CLAUDE_PROJECT_DIR": self.project,
                    "CLAUDE_CODE_REMOTE_SESSION_ID": SESSION, "USAGE_OPTIMIZER_NTFY_TOPIC": TOPIC,
                    "USAGE_OPTIMIZER_NOTIFY_STATE_DIR": self.state}

    def mark(self, content=SESSION):
        with open(os.path.join(self.project, ".claude", "main-session"), "w", encoding="utf-8") as handle:
            handle.write(content + "\n")

    def hook(self, payload, sender, env=None, now=None):
        stderr = io.StringIO()
        payload = dict({"session_id": "s-1", "cwd": self.project}, **payload)
        code = cloud_notify.main(["hook"], env=env or self.env, stdin=io.StringIO(json.dumps(payload)),
                                 stdout=io.StringIO(), stderr=stderr, sender=sender,
                                 clock=None if now is None else (lambda: now))
        self.assertEqual(code, 0)
        self.assertNotIn(TOPIC, stderr.getvalue())
        return stderr.getvalue()


class HookGateTests(CloudNotifyTestCase):
    STOP = {"hook_event_name": "Stop", "last_assistant_message": "All done."}

    def test_not_a_cloud_session_sends_nothing(self):
        self.mark()
        sender = Sender()
        env = dict(self.env)
        del env["CLAUDE_CODE_REMOTE"]
        self.hook(self.STOP, sender, env)
        env["CLAUDE_CODE_REMOTE"] = "false"
        self.hook(self.STOP, sender, env)
        self.assertEqual(sender.calls, [])

    def test_no_main_session_marker_sends_nothing(self):
        sender = Sender()
        self.hook(self.STOP, sender)
        self.assertEqual(sender.calls, [])

    def test_no_topic_sends_nothing(self):
        self.mark()
        sender = Sender()
        env = dict(self.env)
        del env["USAGE_OPTIMIZER_NTFY_TOPIC"]
        self.hook(self.STOP, sender, env)
        env["USAGE_OPTIMIZER_NTFY_TOPIC"] = "not/a topic"
        self.hook(self.STOP, sender, env)
        self.assertEqual(sender.calls, [])

    def test_notify_off_sends_nothing(self):
        self.mark()
        sender = Sender()
        self.hook(self.STOP, sender, dict(self.env, USAGE_OPTIMIZER_NOTIFY="off"))
        self.assertEqual(sender.calls, [])

    def test_marker_of_another_session_sends_nothing(self):
        self.mark("cse_someOtherSession")
        sender = Sender()
        self.hook(self.STOP, sender)
        self.assertEqual(sender.calls, [])

    def test_marker_found_from_hook_cwd_without_project_dir(self):
        self.mark()
        sender = Sender()
        env = dict(self.env)
        del env["CLAUDE_PROJECT_DIR"]
        self.hook(self.STOP, sender, env)
        self.assertEqual(len(sender.calls), 1)

    def test_bad_stdin_still_exits_zero(self):
        self.mark()
        sender = Sender()
        for text in ("not json", "[1, 2]", ""):
            code = cloud_notify.main(["hook"], env=self.env, stdin=io.StringIO(text), stdout=io.StringIO(),
                                     stderr=io.StringIO(), sender=sender)
            self.assertEqual(code, 0)
        self.assertEqual(sender.calls, [])

    def test_events_from_inside_a_subagent_send_nothing(self):
        # The docs: a payload from inside a subagent carries agent_id. agent_type alone is also set for the
        # session's own --agent, so it does not count as a subagent.
        self.mark()
        sender = Sender()
        self.hook(dict(self.STOP, agent_id="a-1", agent_type="Explore"), sender)
        self.hook({"hook_event_name": "Notification", "notification_type": "permission_prompt", "message": "x",
                   "agent_id": "a-1"}, sender)
        self.hook({"hook_event_name": "StopFailure", "error": "overloaded", "agent_id": "a-1"}, sender)
        self.assertEqual(sender.calls, [])
        self.hook(dict(self.STOP, agent_type="Explore"), sender)
        self.assertEqual(len(sender.calls), 1)


class HookMessageTests(CloudNotifyTestCase):
    def setUp(self):
        super().setUp()
        self.mark()

    def one_request(self, payload, session="s-1"):
        sender = Sender()
        self.hook(dict(payload, session_id=session), sender)
        self.assertEqual(len(sender.calls), 1)
        call = sender.calls[0]
        self.assertEqual(call["url"], "https://ntfy.sh/" + TOPIC)
        self.assertEqual(call["timeout"], 10)
        self.assertEqual(call["headers"]["Click"], "https://claude.ai/code/session_01TestSessionAbc")
        return call

    def test_stop_says_finished_with_the_fixed_line(self):
        call = self.one_request({"hook_event_name": "Stop", "last_assistant_message": "word " * 100})
        self.assertEqual(call["headers"]["Title"], "Claude: my-repo finished")
        self.assertEqual(call["body"], cloud_notify.BODIES["stop"])

    def test_stop_failure_says_stopped_with_the_fixed_line(self):
        call = self.one_request({"hook_event_name": "StopFailure", "error": "rate_limit",
                                 "error_details": "429 Too Many Requests"})
        self.assertEqual(call["headers"]["Title"], "Claude: my-repo stopped with an error")
        self.assertEqual(call["body"], cloud_notify.BODIES["error"])

    def test_notification_says_needs_input(self):
        call = self.one_request({"hook_event_name": "Notification", "notification_type": "permission_prompt",
                                 "message": "Claude needs your permission to use Bash"})
        self.assertEqual(call["headers"]["Title"], "Claude: my-repo needs input")
        self.assertEqual(call["body"], cloud_notify.BODIES["input"])

    def test_ask_user_question_says_needs_input(self):
        call = self.one_request({"hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion",
                                 "tool_input": {"questions": [{"question": "Ship it?"}]}})
        self.assertEqual(call["headers"]["Title"], "Claude: my-repo needs input")
        self.assertEqual(call["body"], cloud_notify.BODIES["input"])

    def test_quiet_notification_types_and_other_events_send_nothing(self):
        sender = Sender()
        self.hook({"hook_event_name": "Notification", "notification_type": "auth_success", "message": "x"}, sender)
        self.hook({"hook_event_name": "PreToolUse", "tool_name": "Bash"}, sender)
        self.hook({"hook_event_name": "SessionStart"}, sender)
        self.assertEqual(sender.calls, [])

    def test_stop_with_background_work_waits_for_the_real_finish(self):
        sender = Sender()
        self.hook({"hook_event_name": "Stop", "background_tasks": [{"id": "1", "type": "shell"}]}, sender)
        self.assertEqual(sender.calls, [])
        self.hook({"hook_event_name": "Stop", "background_tasks": [{"id": "2", "type": "monitor"}]}, sender)
        self.assertEqual(len(sender.calls), 1)

    def test_non_ascii_title_is_encoded_for_the_header(self):
        os.rename(self.project, self.project + "-été")
        self.project += "-été"
        self.env["CLAUDE_PROJECT_DIR"] = self.project
        call = self.one_request({"hook_event_name": "Stop", "last_assistant_message": "ok"})
        self.assertTrue(call["headers"]["Title"].startswith("=?UTF-8?B?"))
        call["headers"]["Title"].encode("ascii")

    def test_custom_server(self):
        sender = Sender()
        self.hook({"hook_event_name": "Stop"}, sender,
                  dict(self.env, USAGE_OPTIMIZER_NTFY_SERVER="https://ntfy.example.org/"))
        self.assertEqual(sender.calls[0]["url"], "https://ntfy.example.org/" + TOPIC)


class PayloadTests(CloudNotifyTestCase):
    """C4: the push carries the event kind and the repository (session) title only, never message text."""
    FAKE = "FAKE-TRANSCRIPT-7f3a the assistant wrote this, do not send it"

    def setUp(self):
        super().setUp()
        self.mark()

    def test_push_carries_only_the_event_kind_and_title(self):
        fake = self.FAKE
        payloads = [
            {"hook_event_name": "Stop", "last_assistant_message": fake, "transcript_path": "/t/" + fake},
            {"hook_event_name": "StopFailure", "error": fake, "error_details": fake},
            {"hook_event_name": "Notification", "notification_type": "permission_prompt", "message": fake},
            {"hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion",
             "tool_input": {"questions": [{"question": fake}]}},
        ]
        sender = Sender()
        for index, payload in enumerate(payloads):
            self.hook(dict(payload, session_id="p-{}".format(index)), sender)
        self.assertEqual(len(sender.calls), 4)
        kinds = {"finished", "stopped with an error", "needs input"}
        for call in sender.calls:
            outgoing = call["body"] + json.dumps(call["headers"], ensure_ascii=False)
            self.assertNotIn("FAKE", outgoing)
            self.assertNotIn("transcript", outgoing)
            self.assertIn(call["body"], set(cloud_notify.BODIES.values()))
            self.assertTrue(call["headers"]["Title"].startswith("Claude: my-repo "))
            self.assertTrue(any(call["headers"]["Title"].endswith(kind) for kind in kinds))
            self.assertLessEqual(set(call["headers"]), {"Title", "Content-Type", "Tags", "Click"})


class DebounceTests(CloudNotifyTestCase):
    def setUp(self):
        super().setUp()
        self.mark()
        self.sender = Sender()

    def send(self, event, at, session="s-1", **extra):
        self.hook(dict({"hook_event_name": event, "session_id": session}, **extra), self.sender, now=at)
        return len(self.sender.calls)

    def test_second_prompt_in_one_turn_is_sent_only_after_a_minute(self):
        self.assertEqual(self.send("Notification", T0, notification_type="permission_prompt", message="allow?"), 1)
        self.assertEqual(self.send("Notification", T0 + 5, notification_type="idle_prompt", message="again"), 1)
        self.assertEqual(self.send("PreToolUse", T0 + 61, tool_name="AskUserQuestion",
                                   tool_input={"questions": [{"question": "Ship?"}]}), 2)
        self.assertEqual(self.send("Notification", T0 + 70, notification_type="idle_prompt", message="x"), 2)

    def test_different_kinds_in_one_turn_all_send(self):
        self.assertEqual(self.send("Notification", T0, notification_type="permission_prompt", message="a"), 1)
        self.assertEqual(self.send("Stop", T0 + 1), 2)
        self.assertEqual(self.send("StopFailure", T0 + 2, error="overloaded"), 3)
        self.assertEqual(self.send("Stop", T0 + 3), 3)  # a second stop within the minute is held back
        self.assertEqual(self.send("Notification", T0 + 4, notification_type="idle_prompt", message="b"), 3)

    def test_mid_turn_prompt_then_end_of_turn_stop_send_two(self):
        self.assertEqual(self.send("Notification", T0, notification_type="permission_prompt", message="allow?"), 1)
        self.assertEqual(self.send("Notification", T0 + 1, notification_type="permission_prompt", message="again"), 1)
        self.assertEqual(self.send("Stop", T0 + 2), 2)
        self.assertEqual(self.send("Notification", T0 + 3, notification_type="idle_prompt", message="waiting"), 2)

    def test_a_new_prompt_starts_the_windows_over(self):
        self.assertEqual(self.send("Stop", T0), 1)
        self.assertEqual(self.send("Stop", T0 + 10), 1)
        self.assertEqual(self.send("UserPromptSubmit", T0 + 20, prompt="next"), 1)
        self.assertEqual(self.send("Stop", T0 + 25), 2)

    def test_a_clock_that_went_back_starts_the_window_again(self):
        self.assertEqual(self.send("Stop", T0 + 100), 1)
        self.assertEqual(self.send("Stop", T0 + 50), 2)

    def test_waits_are_kept_per_session(self):
        self.assertEqual(self.send("Stop", T0), 1)
        self.assertEqual(self.send("Stop", T0, session="s-2"), 2)

    def test_state_file_is_private(self):
        self.send("Stop", T0)
        names = os.listdir(self.state)
        self.assertEqual(len(names), 1)
        self.assertNotIn("s-1", names[0])
        if os.name == "posix":
            self.assertEqual(os.stat(os.path.join(self.state, names[0])).st_mode & 0o077, 0)


class GuardTests(CloudNotifyTestCase):
    """`guard`: a PreToolUse hook that denies starting another session in a cloud session."""
    SESSION_TOOL = "mcp__claude-code-remote__create_session"
    TRIGGER_TOOL = "mcp__claude-code-remote__create_trigger"

    def guard(self, payload, env=None, raw=None):
        env = dict(self.env if env is None else env)
        stdout = io.StringIO()
        text = json.dumps(dict({"hook_event_name": "PreToolUse"}, **payload)) if raw is None else raw
        code = cloud_notify.main(["guard"], env=env, stdin=io.StringIO(text), stdout=stdout, stderr=io.StringIO())
        self.assertEqual(code, 0)
        return stdout.getvalue()

    def assert_denied(self, out, reason=cloud_notify.GUARD_REASON):
        decision = json.loads(out)
        self.assertEqual(list(decision), ["hookSpecificOutput"])
        self.assertEqual(sorted(decision["hookSpecificOutput"]),
                         ["hookEventName", "permissionDecision", "permissionDecisionReason"])
        self.assertEqual(decision["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertEqual(decision["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(decision["hookSpecificOutput"]["permissionDecisionReason"], reason)
        self.assertEqual(out.count("\n"), 1)

    def test_denies_create_session_main_and_subagent(self):
        self.assert_denied(self.guard({"tool_name": self.SESSION_TOOL, "tool_input": {}}))
        self.assert_denied(self.guard({"tool_name": self.SESSION_TOOL, "tool_input": {}, "agent_id": "a-1"}))

    def test_denies_a_trigger_that_starts_new_sessions_only(self):
        self.assert_denied(self.guard({"tool_name": self.TRIGGER_TOOL,
                                       "tool_input": {"create_new_session_on_fire": True}}))
        for tool_input in ({}, {"create_new_session_on_fire": False}, {"create_new_session_on_fire": "true"}, None):
            self.assertEqual(self.guard({"tool_name": self.TRIGGER_TOOL, "tool_input": tool_input}), "")

    def test_allows_other_tools(self):
        self.assertEqual(self.guard({"tool_name": "mcp__claude-code-remote__send_later", "tool_input": {}}), "")
        self.assertEqual(self.guard({"tool_name": "Bash", "tool_input": {"command": "ls"}}), "")

    def test_nothing_outside_the_cloud(self):
        env = {key: value for key, value in self.env.items() if key != "CLAUDE_CODE_REMOTE"}
        self.assertEqual(self.guard({"tool_name": self.SESSION_TOOL}, env=env), "")
        self.assertEqual(self.guard({"tool_name": self.SESSION_TOOL}, env=dict(env, CLAUDE_CODE_REMOTE="false")), "")

    def test_off_switch(self):
        for value in ("off", " OFF "):
            env = dict(self.env, USAGE_OPTIMIZER_SESSION_GUARD=value)
            self.assertEqual(self.guard({"tool_name": self.SESSION_TOOL}, env=env), "")
        self.assert_denied(self.guard({"tool_name": self.SESSION_TOOL},
                                      env=dict(self.env, USAGE_OPTIMIZER_SESSION_GUARD="on")))

    def test_ignores_the_notify_settings_and_the_marker(self):
        self.mark()
        env = dict(self.env, USAGE_OPTIMIZER_NOTIFY="off")
        del env["USAGE_OPTIMIZER_NTFY_TOPIC"]
        self.assert_denied(self.guard({"tool_name": self.SESSION_TOOL}, env=env))

    def test_malformed_input_prints_nothing(self):
        for raw in ("", "{not json", "[]", "null", '{"tool_name": 5}'):
            self.assertEqual(self.guard({}, raw=raw), "")

    BASH_DENIED = (
        'claude --cloud "do x"', "/usr/local/bin/claude --cloud x", "claude --cloud=x", "claude -p --cloud x",
        "FOO=1 claude --cloud x", "env -u A B=2 claude --cloud x", "cd /w && claude --cloud x",
        "true; claude --cloud x", "true || claude --cloud x", "echo ok\nclaude --cloud x", "nohup claude --cloud x &",
        "timeout 60 claude --cloud x", 'script -qc "claude --cloud x" /dev/null', "bash -lc 'claude --cloud x'",
        'sh -c "cd /w; claude --cloud x"', "eval claude --cloud x", "echo $(claude --cloud x)",
        'codex cloud exec --env e "task"',
        # The same rule through other shapes: wrapper values, keywords, heredoc scripts, comments, continuations.
        "nice -n 5 claude --cloud x", "if claude --cloud x; then echo; fi", "{ claude --cloud x; }",
        "bash <<EOF\nclaude --cloud x\nEOF", "cat <<EOF | sh\nclaude --cloud x\nEOF", "echo a#b; claude --cloud x",
        "# a note\nclaude --cloud x", "claude \\\n  --cloud x", "bash -c \"bash -c 'claude --cloud x'\"",
        # Comments, quoted '#', arithmetic, redirections, wrappers, substitutions, stdin scripts and codex options.
        "# don't start cloud here\nclaude --cloud x", "ls # it's fine\nclaude --cloud x",
        "grep -n '#' README.md && claude --cloud x", 'git commit -m "#123 done" && claude --cloud x',
        "curl http://h/#frag && claude --cloud x", "echo $((1 << n))\nclaude --cloud x",
        "mask=$((1 << bits))\nclaude --cloud x", "2>/dev/null claude --cloud x", ">log claude --cloud x",
        "claude --cloud x 2>&1 | tee log", "sudo claude --cloud x", "sudo -u root claude --cloud x",
        "printf 'a' | xargs claude --cloud", 'echo "$(claude --cloud x)"', "echo `claude --cloud x`",
        'out="$(claude --cloud x)"', "cat <(claude --cloud x)", "bash -s <<'EOF'\nclaude --cloud x\nEOF",
        "bash <<< 'claude --cloud x'", "echo 'claude --cloud x' | bash", "codex -m m cloud exec --env e t",
        "codex --profile=p cloud exec t",
        # find actions, flock, su, shell options with values, a later unterminated quote, an array's substitution.
        "find . -name x -exec claude --cloud x \\;", "find . -execdir sh -c 'claude --cloud x' \\;",
        "flock /tmp/l claude --cloud x", "flock -w 5 /tmp/l claude --cloud x", "su -c 'claude --cloud x' user",
        "bash --rcfile /dev/null -c 'claude --cloud x'", "bash -O extglob -c 'claude --cloud x'",
        'claude --cloud x\necho "unterminated', "claude --cloud x\necho $(unterminated", "a=( $(claude --cloud x) )",
    )
    BASH_ALLOWED = (
        'git commit -m "claude --cloud is refused"', 'grep -n "claude --cloud" LANES.md', "echo claude --cloud",
        'claude -p "use --cloud later"', "lane haiku --cloud --dry-run -C /w -b b.md",
        "python3 -m unittest tests.test_lane_cloud", 'codex exec "x"', "codex cloud status",
        "cat > f.md <<'EOF'\nclaude --cloud x\nEOF", "cat <<-EOF\n\tclaude --cloud x\n\tEOF", 'echo "claude --cloud',
        "# claude --cloud x", "echo a#b", 'echo "$HOME" # claude --cloud x', "ls -la",
        # Options that take a value, bodies fed to other commands, escaped or quoted substitutions, arithmetic.
        "codex --profile cloud exec 'fix bug'", "codex -p cloud exec x", "codex cloud exec --help",
        "bash -c 'cat > notes.md' <<'EOF'\nclaude --cloud x\nEOF", "bash write_doc.sh <<'EOF'\nclaude --cloud x\nEOF",
        "echo hi > claude --cloud", "cat <<< 'claude --cloud x'", "echo '$(claude --cloud x)'",
        'echo "\\$(claude --cloud x)"', "echo \\`claude --cloud x\\`", 'python3 -c "print(1<<2)"', "echo $((1<<3))",
        "x=$(( a >> 2 ))", "grep -c '#' f", "echo 'claude --cloud x' | cat", "echo it\\'s fine",
        # Arrays hold words, a heredoc ends only at its exact delimiter, and find's other actions run nothing.
        "args=(claude --cloud x); echo ${args[@]}", 'CMD=(codex cloud exec "$t"); echo hi',
        "cat > n.md <<EOF\n  EOF\nclaude --cloud x\nEOF", "cat > n.md <<-EOF\n  EOF\nclaude --cloud x\n\tEOF",
        "find . -name '*.md' -exec grep -l 'claude --cloud' {} +", "find . -name 'claude --cloud'",
    )

    def bash(self, command, env=None):
        return self.guard({"tool_name": "Bash", "tool_input": {"command": command}}, env=env)

    def test_bash_commands_that_start_a_cloud_session_are_denied(self):
        for command in self.BASH_DENIED:
            with self.subTest(command=command):
                self.assert_denied(self.bash(command), cloud_notify.GUARD_BASH_REASON)

    def test_bash_commands_that_only_quote_or_mention_the_command_are_allowed(self):
        for command in self.BASH_ALLOWED:
            with self.subTest(command=command):
                self.assertEqual(self.bash(command), "")

    def test_bash_denial_needs_a_cloud_session_and_the_guard_on(self):
        remote_off = {key: value for key, value in self.env.items() if key != "CLAUDE_CODE_REMOTE"}
        spaced_off = dict(self.env, USAGE_OPTIMIZER_SESSION_GUARD=" Off ")
        for command in self.BASH_DENIED:
            with self.subTest(command=command):
                self.assertEqual(self.bash(command, env=remote_off), "")
                self.assertEqual(self.bash(command, env=spaced_off), "")

    def test_bash_payloads_without_a_string_command_are_allowed(self):
        for tool_input in (None, "claude --cloud x", ["claude", "--cloud"], {}, {"command": None},
                           {"command": ["claude --cloud x"]}):
            with self.subTest(tool_input=tool_input):
                self.assertEqual(self.guard({"tool_name": "Bash", "tool_input": tool_input}), "")
        self.assertEqual(self.guard({"tool_name": "Bash"}), "")

    def test_a_failing_bash_check_fails_open(self):
        with mock.patch.object(cloud_notify, "starts_cloud_session", side_effect=RuntimeError("a bug")):
            self.assertEqual(self.bash("claude --cloud x"), "")

    def test_nested_shells_are_followed_three_levels_deep(self):
        def nest(levels):
            command = "claude --cloud x"
            for _ in range(levels):
                command = "bash -c " + shlex.quote(command)
            return command

        self.assertTrue(cloud_notify.starts_cloud_session(nest(3)))
        self.assertFalse(cloud_notify.starts_cloud_session(nest(4)))

    def test_long_commands_are_read_in_linear_time(self):
        heredoc = "bash <<'EOF'\n" + "echo hi\n" * 100000 + "EOF"
        for name, command in (("one long argument", "git commit -m '" + "a" * 1000000 + "'"),
                              ("many words in a script", "bash -c '" + "a " * 500000 + "'"),
                              ("a long heredoc", heredoc), ("many backslashes", "echo " + "\\" * 200000),
                              ("a run of parentheses", "(" * 200000), ("arithmetic commands", "(( " * 70000),
                              ("unclosed arithmetic", "x;((a" * 40000)):
            with self.subTest(name=name):
                started = time.perf_counter()
                self.assertFalse(cloud_notify.starts_cloud_session(command))
                # 3 s, not 1: the heredoc took 1.14 s once with eight test modules in parallel on a 3-CPU VM
                # (2026-11-02); a quadratic reader on these inputs would take minutes.
                self.assertLess(time.perf_counter() - started, 3.0)

    def test_guard_matcher_names_both_session_tools_and_bash(self):
        self.assertEqual(cloud_notify.GUARD_MATCHER.split("|"), [*cloud_notify.GUARD_TOOLS, "Bash"])

    def test_an_install_updates_the_old_two_tool_guard_matcher_once(self):
        repo = os.path.join(self.root, "old-matcher")
        os.makedirs(os.path.join(repo, ".claude"))
        settings = {}
        cloud_notify.merge_settings(settings)
        for group in settings["hooks"]["PreToolUse"]:
            if group.get("matcher") == cloud_notify.GUARD_MATCHER:
                group["matcher"] = "|".join(cloud_notify.GUARD_TOOLS)
        with open(os.path.join(repo, ".claude", "settings.json"), "w", encoding="utf-8") as handle:
            json.dump(settings, handle)
        self.assertEqual(cloud_notify.install_settings(repo), "registered the hooks")
        with open(os.path.join(repo, ".claude", "settings.json"), encoding="utf-8") as handle:
            groups = json.load(handle)["hooks"]["PreToolUse"]
        self.assertEqual([group.get("matcher") for group in groups], ["AskUserQuestion", cloud_notify.GUARD_MATCHER])
        self.assertEqual(cloud_notify.install_settings(repo), "already registers the hooks")

    def test_merge_settings_fresh_idempotent_and_upgrade(self):
        fresh = {}
        self.assertTrue(cloud_notify.merge_settings(fresh))
        groups = fresh["hooks"]["PreToolUse"]
        self.assertEqual([group.get("matcher") for group in groups], ["AskUserQuestion", cloud_notify.GUARD_MATCHER])
        self.assertEqual(groups[1]["hooks"], [{"type": "command", "command": cloud_notify.GUARD_COMMAND,
                                               "timeout": cloud_notify.HOOK_TIMEOUT}])
        self.assertTrue(groups[0]["hooks"][0]["async"])
        self.assertFalse(cloud_notify.merge_settings(fresh))
        previous = json.loads(json.dumps(fresh))
        del previous["hooks"]["PreToolUse"][1]
        previous["hooks"]["PreToolUse"].insert(0, {"matcher": "Bash", "hooks": [{"type": "command", "command": "x"}]})
        upgraded = json.loads(json.dumps(previous))
        self.assertTrue(cloud_notify.merge_settings(upgraded))
        self.assertEqual(upgraded["hooks"]["PreToolUse"][:2], previous["hooks"]["PreToolUse"])
        self.assertEqual(upgraded["hooks"]["PreToolUse"][2], fresh["hooks"]["PreToolUse"][1])
        self.assertEqual(len(upgraded["hooks"]["PreToolUse"]), 3)
        self.assertFalse(cloud_notify.merge_settings(upgraded))

    @unittest.skipUnless(os.name == "posix" and shutil.which("sh"), "needs a POSIX shell")
    def test_registered_guard_command_end_to_end(self):
        repo = os.path.join(self.root, "guarded")
        os.makedirs(os.path.join(repo, ".claude", "hooks"))
        shutil.copy(SCRIPT, os.path.join(repo, ".claude", "hooks", "cloud-notify.py"))
        payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": self.SESSION_TOOL, "tool_input": {}})
        base = dict(clean_environ(), CLAUDE_PROJECT_DIR=repo)

        def run(env):
            result = subprocess.run([shutil.which("sh"), "-c", cloud_notify.GUARD_COMMAND], input=payload,
                                    capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual((result.returncode, result.stderr), (0, ""))
            return result.stdout

        self.assert_denied(run(dict(base, CLAUDE_CODE_REMOTE="true")))
        self.assertEqual(run(dict(base, CLAUDE_CODE_REMOTE="true", USAGE_OPTIMIZER_SESSION_GUARD="off")), "")
        self.assertEqual(run(dict(base, PATH="/nonexistent")), "")


class PushTests(CloudNotifyTestCase):
    def push(self, env, sender):
        stdout, stderr = io.StringIO(), io.StringIO()
        code = cloud_notify.main(["push", "--title", "Kit update", "--message", "Release 1.2 is out"], env=env,
                                 stdout=stdout, stderr=stderr, sender=sender)
        self.assertEqual(code, 0)
        self.assertNotIn(TOPIC, stdout.getvalue() + stderr.getvalue())
        return stdout.getvalue(), stderr.getvalue()

    def test_push_with_topic_sends_one_without_cloud_or_marker(self):
        sender = Sender()
        self.push({"USAGE_OPTIMIZER_NTFY_TOPIC": TOPIC}, sender)
        self.assertEqual(len(sender.calls), 1)
        self.assertEqual(sender.calls[0]["headers"]["Title"], "Kit update")
        self.assertEqual(sender.calls[0]["body"], "Release 1.2 is out")
        self.assertNotIn("Click", sender.calls[0]["headers"])

    def test_push_without_topic_does_nothing(self):
        sender = Sender()
        stdout, stderr = self.push({}, sender)
        self.assertEqual((sender.calls, stdout, stderr), ([], "", ""))

    def test_push_off_does_nothing(self):
        sender = Sender()
        self.push({"USAGE_OPTIMIZER_NTFY_TOPIC": TOPIC, "USAGE_OPTIMIZER_NOTIFY": "off"}, sender)
        self.assertEqual(sender.calls, [])

    def test_failed_send_exits_zero_and_hides_the_topic(self):
        sender = Sender(OSError("cannot reach https://ntfy.sh/" + TOPIC))
        _, stderr = self.push({"USAGE_OPTIMIZER_NTFY_TOPIC": TOPIC}, sender)
        self.assertIn("could not send to https://ntfy.sh/***", stderr)


class DryRunTests(CloudNotifyTestCase):
    def run_script(self, args, env, payload=None):
        return subprocess.run([sys.executable, SCRIPT] + args, input=json.dumps(payload) if payload else "",
                              capture_output=True, text=True, env=dict(clean_environ(), **env), timeout=60)

    def test_hook_dry_run_writes_the_masked_request_and_sends_nothing(self):
        self.mark()
        out = os.path.join(self.root, "dry.jsonl")
        env = dict(self.env, USAGE_OPTIMIZER_NOTIFY_DRY_RUN="1", USAGE_OPTIMIZER_NOTIFY_DRY_RUN_FILE=out,
                   USAGE_OPTIMIZER_NTFY_SERVER="http://127.0.0.1:9")
        result = self.run_script(["hook"], env, {"hook_event_name": "Stop", "session_id": "d-1",
                                                 "last_assistant_message": "Tests pass."})
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
        with open(out, encoding="utf-8") as handle:
            text = handle.read()
        self.assertNotIn(TOPIC, text)
        self.assertNotIn("Tests pass.", text)
        records = [json.loads(line) for line in text.splitlines()]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["url"], "http://127.0.0.1:9/***")
        self.assertEqual(records[0]["headers"]["Title"], "Claude: my-repo finished")
        self.assertEqual(records[0]["body"], cloud_notify.BODIES["stop"])

    def test_push_dry_run_to_stderr(self):
        result = self.run_script(["push", "--title", "T", "--message", "M"],
                                 {"USAGE_OPTIMIZER_NTFY_TOPIC": TOPIC, "USAGE_OPTIMIZER_NOTIFY_DRY_RUN": "1"})
        self.assertEqual(result.returncode, 0)
        self.assertIn("cloud-notify dry run:", result.stderr)
        self.assertIn("https://ntfy.sh/***", result.stderr)
        self.assertNotIn(TOPIC, result.stdout + result.stderr)


class MarkMainTests(CloudNotifyTestCase):
    def test_mark_main_writes_the_session_id_and_hides_the_topic(self):
        stdout = io.StringIO()
        code = cloud_notify.main(["mark-main", "--dir", self.project], env=self.env, stdout=stdout,
                                 stderr=io.StringIO())
        self.assertEqual(code, 0)
        with open(os.path.join(self.project, ".claude", "main-session"), encoding="utf-8") as handle:
            self.assertEqual(handle.read().strip(), SESSION)
        self.assertNotIn(TOPIC, stdout.getvalue())
        self.assertTrue(cloud_notify.is_main(self.project, self.env))

    def test_mark_main_uses_the_project_dir(self):
        cloud_notify.main(["mark-main"], env={"CLAUDE_PROJECT_DIR": self.project}, stdout=io.StringIO(),
                          stderr=io.StringIO())
        self.assertTrue(os.path.isfile(os.path.join(self.project, ".claude", "main-session")))


class InstallTests(CloudNotifyTestCase):
    def install(self, repo):
        stdout, stderr = io.StringIO(), io.StringIO()
        code = cloud_notify.main(["install", "--repo", repo], env={}, stdout=stdout, stderr=stderr)
        return code, stdout.getvalue(), stderr.getvalue()

    def read_settings(self, repo):
        with open(os.path.join(repo, ".claude", "settings.json"), encoding="utf-8") as handle:
            return json.load(handle)

    def ours(self, settings, event):
        return [hook for group in settings["hooks"].get(event, []) for hook in group["hooks"]
                if cloud_notify.subcommand_of(hook.get("command", "")) in ("hook", "kit-reinstall")]

    def test_install_is_idempotent(self):
        repo = os.path.join(self.root, "fresh")
        os.makedirs(repo)
        code, stdout, _ = self.install(repo)
        self.assertEqual(code, 0)
        self.assertIn("mark-main", stdout)
        self.assertIn("CLAUDE.md, or AGENTS.md if that is the repository's instruction file", stdout)
        first = self.read_settings(repo)
        with open(os.path.join(repo, ".gitignore"), encoding="utf-8") as handle:
            first_ignore = handle.read()
        code, stdout, _ = self.install(repo)
        self.assertEqual(code, 0)
        self.assertIn("already registers the hooks", stdout)
        self.assertEqual(self.read_settings(repo), first)
        with open(os.path.join(repo, ".gitignore"), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), first_ignore)
        self.assertEqual(first_ignore.splitlines().count(".claude/main-session"), 1)
        for event, matcher, is_async in cloud_notify.HOOK_EVENTS:
            hooks = self.ours(first, event)
            self.assertEqual(len(hooks), 1, event)
            self.assertEqual(hooks[0].get("async", False), is_async, event)
        self.assertEqual(first["hooks"]["PreToolUse"][0]["matcher"], "AskUserQuestion")
        copy = os.path.join(repo, ".claude", "hooks", "cloud-notify.py")
        with open(copy, "rb") as a, open(SCRIPT, "rb") as b:
            self.assertEqual(a.read(), b.read())
        if os.name == "posix":
            self.assertTrue(os.access(copy, os.X_OK))

    def test_install_adds_the_session_start_hook_once(self):
        repo = os.path.join(self.root, "kit-hook")
        os.makedirs(repo)
        self.install(repo)
        self.install(repo)
        hooks = self.ours(self.read_settings(repo), "SessionStart")
        self.assertEqual(len(hooks), 1)
        self.assertEqual(hooks[0]["timeout"], 120)
        self.assertNotIn("async", hooks[0])
        self.assertTrue(hooks[0]["command"].startswith('[ "$CLAUDE_CODE_REMOTE" != true ] || '))
        self.assertTrue(hooks[0]["command"].endswith(" kit-reinstall || true"))
        self.assertEqual(self.read_settings(repo)["hooks"]["SessionStart"][0]["matcher"], "startup|resume")

    def test_install_over_an_older_settings_file_adds_just_the_session_start_hook(self):
        repo = os.path.join(self.root, "older")
        os.makedirs(repo)
        self.install(repo)
        path = os.path.join(repo, ".claude", "settings.json")
        older = self.read_settings(repo)
        del older["hooks"]["SessionStart"]
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(older, handle)
        self.install(repo)
        now = self.read_settings(repo)
        self.assertEqual(len(self.ours(now, "SessionStart")), 1)
        del now["hooks"]["SessionStart"]
        self.assertEqual(now, older)

    def test_install_merges_an_existing_settings_file(self):
        repo = os.path.join(self.root, "existing")
        os.makedirs(os.path.join(repo, ".claude"))
        existing = {"model": "sonnet", "permissions": {"deny": ["WebFetch"]},
                    "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}],
                              "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "x"}]}]}}
        with open(os.path.join(repo, ".claude", "settings.json"), "w", encoding="utf-8") as handle:
            json.dump(existing, handle)
        with open(os.path.join(repo, ".gitignore"), "w", encoding="utf-8") as handle:
            handle.write("node_modules/")
        self.assertEqual(self.install(repo)[0], 0)
        self.assertEqual(self.install(repo)[0], 0)
        merged = self.read_settings(repo)
        self.assertEqual(merged["model"], "sonnet")
        self.assertEqual(merged["permissions"], {"deny": ["WebFetch"]})
        self.assertEqual(merged["hooks"]["Stop"][0], existing["hooks"]["Stop"][0])
        self.assertEqual(merged["hooks"]["PreToolUse"][0], existing["hooks"]["PreToolUse"][0])
        self.assertEqual(len(merged["hooks"]["Stop"]), 2)
        self.assertEqual(len(self.ours(merged, "Stop")), 1)
        with open(os.path.join(repo, ".gitignore"), encoding="utf-8") as handle:
            self.assertEqual(handle.read().splitlines()[0], "node_modules/")

    def test_install_updates_an_old_entry_in_place(self):
        repo = os.path.join(self.root, "old")
        os.makedirs(os.path.join(repo, ".claude"))
        old = {"hooks": {"Stop": [{"hooks": [{"type": "command",
                                               "command": "python3 .claude/hooks/cloud-notify.py hook"}]}]}}
        with open(os.path.join(repo, ".claude", "settings.json"), "w", encoding="utf-8") as handle:
            json.dump(old, handle)
        self.install(repo)
        merged = self.read_settings(repo)
        self.assertEqual(len(merged["hooks"]["Stop"]), 1)
        self.assertEqual(merged["hooks"]["Stop"][0]["hooks"][0]["command"], cloud_notify.HOOK_COMMAND)

    def test_install_refuses_invalid_json_and_leaves_it(self):
        repo = os.path.join(self.root, "broken")
        os.makedirs(os.path.join(repo, ".claude"))
        path = os.path.join(repo, ".claude", "settings.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{not json")
        code, _, stderr = self.install(repo)
        self.assertEqual(code, 1)
        self.assertIn("cannot read", stderr)
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "{not json")

    @unittest.skipUnless(os.name == "posix" and shutil.which("sh"), "needs a POSIX shell")
    def test_registered_command_end_to_end(self):
        repo = os.path.join(self.root, "e2e")
        os.makedirs(repo)
        self.install(repo)
        out = os.path.join(self.root, "e2e.jsonl")
        base = dict(clean_environ(), CLAUDE_PROJECT_DIR=repo, USAGE_OPTIMIZER_NTFY_TOPIC=TOPIC,
                    USAGE_OPTIMIZER_NOTIFY_STATE_DIR=self.state, USAGE_OPTIMIZER_NOTIFY_DRY_RUN="1",
                    USAGE_OPTIMIZER_NOTIFY_DRY_RUN_FILE=out, CLAUDE_CODE_REMOTE_SESSION_ID=SESSION)
        payload = json.dumps({"hook_event_name": "Stop", "session_id": "e-1", "last_assistant_message": "hi"})

        def run(env):
            result = subprocess.run([shutil.which("sh"), "-c", cloud_notify.HOOK_COMMAND], input=payload,
                                    capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

        local = dict(base, PATH="/nonexistent")  # locally the shell test ends it before python3 is looked up
        run(local)
        run(dict(base, CLAUDE_CODE_REMOTE="true"))  # cloud, but no marker yet
        self.assertFalse(os.path.exists(out))
        cloud_notify.main(["mark-main", "--dir", repo], env=base, stdout=io.StringIO(), stderr=io.StringIO())
        run(dict(base, CLAUDE_CODE_REMOTE="true"))
        with open(out, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertNotIn(TOPIC, lines[0])
        self.assertEqual(json.loads(lines[0])["headers"]["Title"], "Claude: e2e finished")


class KitReinstallTests(CloudNotifyTestCase):
    """The SessionStart hook that reinstalls the kit on a rebuilt VM, and never on a worker."""

    GOOD = ('#!/bin/bash\nmkdir -p "$HOME/.claude/usage-optimizer" && '
            'echo "$@" > "$HOME/.claude/usage-optimizer/ran"\n')

    def setUp(self):
        super().setUp()
        self.home = os.path.join(self.root, "home")
        os.makedirs(self.home)
        self.env["HOME"] = self.home
        self.origin = os.path.join(self.root, "origin")
        self.git(self.root, "init", "-q", "-b", "main", self.origin)
        self.git(self.project, "init", "-q", "-b", "main")
        self.git(self.project, "remote", "add", "origin", self.origin)

    def git(self, cwd, *args):
        env = dict(clean_environ(), GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
        subprocess.run(["git", "-C", cwd] + list(args), check=True, capture_output=True, env=env)

    def publish_kit(self, script):
        """Commit a fake install.sh on origin's lane-main/kit."""
        self.git(self.origin, "checkout", "-q", "-b", "lane-main/kit")
        with open(os.path.join(self.origin, "install.sh"), "w", encoding="utf-8") as handle:
            handle.write(script)
        self.git(self.origin, "add", "install.sh")
        self.git(self.origin, "commit", "-q", "-m", "kit")

    def transcript(self, text):
        path = os.path.join(self.root, "t.jsonl")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"type": "summary"}) + "\n")
            handle.write(json.dumps({"type": "user", "message": {"role": "user", "content": [
                {"type": "text", "text": text}]}}) + "\n")
            handle.write(json.dumps({"type": "user", "message": {"role": "user", "content": "later"}}) + "\n")
        return path

    def run_hook(self, transcript=None, env=None):
        out = io.StringIO()
        payload = {"transcript_path": transcript} if transcript else {}
        code = cloud_notify.main(["kit-reinstall"], env=env or self.env, stdin=io.StringIO(json.dumps(payload)),
                                 stdout=out, stderr=io.StringIO())
        self.assertEqual(code, 0)
        return out.getvalue()

    def ran(self):
        return os.path.exists(os.path.join(self.home, ".claude", "usage-optimizer", "ran"))

    def has_marker(self):
        return os.path.exists(os.path.join(self.project, ".claude", "main-session"))

    def test_not_remote_does_nothing(self):
        self.publish_kit(self.GOOD)
        self.mark()
        env = dict(self.env, CLAUDE_CODE_REMOTE="false")
        self.assertEqual(self.run_hook(env=env), "")
        self.assertFalse(self.ran())

    def complete_install(self):
        """What install.sh leaves: the kit's POLICY.md and bin/lane, and its line in ~/.claude/CLAUDE.md."""
        prefix = os.path.join(self.home, ".claude", "usage-optimizer")
        os.makedirs(os.path.join(prefix, "bin"))
        for name in ("POLICY.md", os.path.join("bin", "lane")):
            with open(os.path.join(prefix, name), "w", encoding="utf-8") as handle:
                handle.write("x\n")
        with open(os.path.join(self.home, ".claude", "CLAUDE.md"), "w", encoding="utf-8") as handle:
            handle.write("@~/.claude/usage-optimizer/POLICY.md\n")

    def test_existing_prefix_does_nothing(self):
        self.publish_kit(self.GOOD)
        self.mark()
        self.complete_install()
        self.assertEqual(self.run_hook(), "")
        self.assertFalse(self.ran())

    def test_a_partial_install_is_installed_again(self):
        # A hook killed mid-install leaves the folder; a folder test alone would skip every later reinstall.
        self.publish_kit(self.GOOD)
        self.mark()
        os.makedirs(os.path.join(self.home, ".claude", "usage-optimizer"))
        self.run_hook()
        self.assertTrue(self.ran())

    def test_a_mirror_prompt_after_a_tool_result_still_counts(self):
        self.publish_kit(self.GOOD)
        path = os.path.join(self.root, "t2.jsonl")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "x", "content": "ok"}]}}) + "\n")
            handle.write(json.dumps({"type": "user", "isMeta": True, "message": {"role": "user",
                                                                                  "content": "caveat"}}) + "\n")
            handle.write(json.dumps({"type": "user", "message": {"role": "user", "content":
                                     "Kit mirror - acme/shop\n\nYou are the MAIN CLOUD SESSION ..."}}) + "\n")
        self.run_hook(path)
        self.assertTrue(self.ran())
        self.assertTrue(self.has_marker())

    def test_extraction_keeps_only_plain_files_and_folders_inside_the_target(self):
        def member(name, kind=tarfile.REGTYPE):
            info = tarfile.TarInfo(name)
            info.type = kind
            return info
        kept = cloud_notify.safe_members([member("install.sh"), member("bin", tarfile.DIRTYPE), member("bin/lane"),
                                          member("x", tarfile.SYMTYPE), member("y", tarfile.LNKTYPE),
                                          member("/etc/passwd"), member("a/../../b")])
        self.assertEqual([info.name for info in kept], ["install.sh", "bin", "bin/lane"])

    def test_the_reinstall_fits_in_the_hook_timeout(self):
        # fetch, archive and install.sh run one after another inside the hook's own time limit.
        self.assertLess(2 * cloud_notify.FETCH_TIMEOUT + cloud_notify.INSTALL_TIMEOUT, cloud_notify.KIT_TIMEOUT)

    def test_worker_transcript_without_marker_does_nothing(self):
        self.publish_kit(self.GOOD)
        for text in ("You are a worker dispatched by lane. Do X.",
                     "Kit mirror - x. You are the MAIN CLOUD SESSION. CLOUD RUN 3",
                     "Some other side session prompt"):
            self.assertEqual(self.run_hook(self.transcript(text)), "")
            self.assertFalse(self.ran())
            self.assertFalse(self.has_marker())
        self.assertEqual(self.run_hook(), "")  # no transcript at all

    def test_marker_fetches_extracts_and_installs(self):
        self.publish_kit(self.GOOD)
        self.mark()
        self.assertEqual(self.run_hook(), "cloud-notify: kit reinstalled from lane-main/kit\n")
        self.assertTrue(self.ran())
        with open(os.path.join(self.home, ".claude", "usage-optimizer", "ran"), encoding="utf-8") as handle:
            self.assertEqual(handle.read().strip(), "--no-view")

    def test_mirror_transcript_without_marker_writes_it_and_installs(self):
        self.publish_kit(self.GOOD)
        out = self.run_hook(self.transcript("Kit mirror - acme/shop. Keep the mirror."))
        self.assertIn("reinstalled", out)
        self.assertTrue(self.has_marker())
        self.assertTrue(self.ran())

    def test_main_session_phrase_without_marker_installs(self):
        self.publish_kit(self.GOOD)
        self.run_hook(self.transcript("Hello. You are the MAIN CLOUD SESSION for acme/shop."))
        self.assertTrue(self.ran())

    def test_missing_branch_prints_the_message_and_exits_zero(self):
        self.mark()
        self.git(self.origin, "commit", "-q", "--allow-empty", "-m", "x")
        self.assertEqual(self.run_hook(),
                         "cloud-notify: origin has no lane-main/kit; the kit stays uninstalled\n")
        self.assertFalse(self.ran())

    def test_failing_installer_exits_zero_and_shows_its_last_line(self):
        self.publish_kit("#!/bin/bash\necho first\necho 'disk full' >&2\nexit 3\n")
        self.mark()
        self.assertEqual(self.run_hook(), "cloud-notify: kit install failed: disk full\n")
        self.assertFalse(self.ran())


class SettingsTests(unittest.TestCase):
    """C1: no hook command can fail a tool or a stop, so every command ends with `|| true`."""

    def checked_in(self):
        with open(os.path.join(ROOT, ".claude", "settings.json"), encoding="utf-8") as handle:
            return json.load(handle)

    def test_every_hook_command_ends_with_or_true(self):
        commands = [hook["command"] for groups in self.checked_in()["hooks"].values() for group in groups
                    for hook in group["hooks"]]
        self.assertEqual(len(commands), len(cloud_notify.HOOK_EVENTS) + 2)  # plus the guard and the kit hook
        for command in commands:
            self.assertTrue(command.endswith(" || true"), command)

    def test_checked_in_hook_copy_is_byte_identical_to_the_tool(self):
        with open(os.path.join(ROOT, ".claude", "hooks", "cloud-notify.py"), "rb") as a, open(SCRIPT, "rb") as b:
            self.assertEqual(a.read(), b.read())

    def test_checked_in_hooks_match_what_install_writes(self):
        merged = {}
        cloud_notify.merge_settings(merged)
        self.assertEqual(merged["hooks"], self.checked_in()["hooks"])

    @unittest.skipUnless(os.name == "posix" and shutil.which("sh") and shutil.which("python3"),
                         "needs a POSIX shell and python3")
    def test_failing_hook_command_still_exits_zero(self):
        repo = tempfile.mkdtemp(prefix="cloud-notify-empty-")
        self.addCleanup(shutil.rmtree, repo, True)  # no hook script here, so python3 exits with a usage error
        env = dict(clean_environ(), CLAUDE_CODE_REMOTE="true", CLAUDE_PROJECT_DIR=repo)
        payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion"})
        bare = cloud_notify.HOOK_COMMAND[: -len(" || true")]
        failed = subprocess.run([shutil.which("sh"), "-c", bare], input=payload, capture_output=True, text=True,
                                env=env, timeout=60)
        self.assertNotEqual(failed.returncode, 0)
        result = subprocess.run([shutil.which("sh"), "-c", cloud_notify.HOOK_COMMAND], input=payload,
                                capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
