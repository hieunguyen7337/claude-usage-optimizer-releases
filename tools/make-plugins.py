#!/usr/bin/env python3
"""Generate the Claude Code and Codex plugins and their marketplace manifests.

The source of truth is plugins/src/ plus the kit version on line 3 of POLICY.md. With --check,
write nothing and exit 1 when a generated file differs from what this tool would write.
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_RE = re.compile(r"Coding Tool Optimizer version: (\d{4}-\d{2}-\d{2}\.\d+)")
HOMEPAGE = "https://github.com/hieunguyen7337/coding-tool-optimizer"
KIT_SUMMARY = (
    "Coding Tool Optimizer routes coding work across the AI plans you already pay for, meters every plan and learns "
    "the cheapest model and effort per usable result. "
)
CLAUDE_DESCRIPTION = KIT_SUMMARY + (
    "This plugin adds the kit-setup skill, which installs the kit with install.sh after a dry run, and a "
    "session-start check that the installed kit is present and current."
)
CODEX_DESCRIPTION = KIT_SUMMARY + (
    "This plugin adds the kit-setup skill, which installs the kit with install.sh after a dry run."
)


class PluginError(Exception):
    pass


def kit_version(policy_path):
    """The kit version on line 3 of POLICY.md, the same line the other generators read."""
    with open(policy_path, encoding="utf-8") as stream:
        lines = stream.read().splitlines()
    version_line = lines[2] if len(lines) > 2 else ""
    match = VERSION_RE.search(version_line)
    if not match:
        raise PluginError("{}: line 3 has no 'Coding Tool Optimizer version: <date>' version".format(policy_path))
    return match.group(1)


def plugin_semver(version):
    """2026-11-17.2 becomes 2026.1117.2 (year, month and day joined, release)."""
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})\.(\d+)", version)
    if not match:
        raise PluginError("kit version is not YYYY-MM-DD.N: {}".format(version))
    year, month, day, release = match.groups()
    return "{}.{}{}.{}".format(year, month, day, release)


def dump_json(value):
    return json.dumps(value, indent=2) + "\n"


def read_text(path):
    with open(path, encoding="utf-8", newline="") as stream:
        return stream.read()


def generated(root):
    """Every file this tool owns, as repo-relative posix path to its exact text."""
    version = kit_version(os.path.join(root, "POLICY.md"))
    semver = plugin_semver(version)
    skill = read_text(os.path.join(root, "plugins", "src", "kit-setup", "SKILL.md"))
    check = read_text(os.path.join(root, "plugins", "src", "core-check.sh"))
    claude_plugin = {
        "name": "coding-tool-optimizer",
        "version": semver,
        "description": CLAUDE_DESCRIPTION,
        "author": {"name": "Coding Tool Optimizer"},
        "license": "MIT",
        "homepage": HOMEPAGE,
    }
    codex_plugin = {
        "name": "coding-tool-optimizer",
        "version": semver,
        "description": CODEX_DESCRIPTION,
        "skills": "./skills/",
    }
    hooks = {
        "hooks": {
            "SessionStart": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "sh \"${CLAUDE_PLUGIN_ROOT}/hooks/core-check.sh\"",
                            "timeout": 10,
                        }
                    ]
                }
            ]
        }
    }
    claude_market = {
        "name": "coding-tool-optimizer",
        "owner": {"name": "Coding Tool Optimizer"},
        "plugins": [
            {
                "name": "coding-tool-optimizer",
                "source": "./plugins/claude-code",
                "description": CLAUDE_DESCRIPTION,
            }
        ],
    }
    codex_market = {
        "name": "coding-tool-optimizer",
        "interface": {"displayName": "Coding Tool Optimizer"},
        "plugins": [
            {
                "name": "coding-tool-optimizer",
                "source": {"source": "local", "path": "./plugins/codex"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                "category": "Productivity",
            }
        ],
    }
    return {
        "plugins/claude-code/.claude-plugin/plugin.json": dump_json(claude_plugin),
        "plugins/claude-code/skills/kit-setup/SKILL.md": skill,
        "plugins/claude-code/hooks/hooks.json": dump_json(hooks),
        "plugins/claude-code/hooks/core-check.sh": check,
        "plugins/claude-code/kit-version": version + "\n",
        "plugins/codex/.codex-plugin/plugin.json": dump_json(codex_plugin),
        "plugins/codex/skills/kit-setup/SKILL.md": skill,
        "public-repo/.claude-plugin/marketplace.json": dump_json(claude_market),
        "public-repo/.agents/plugins/marketplace.json": dump_json(codex_market),
    }


def differences(root):
    """(action, relative path) for each generated file that is missing or different."""
    files = generated(root)
    found = []
    for name, text in files.items():
        path = os.path.join(root, *name.split("/"))
        try:
            current = read_text(path)
        except OSError:
            current = None
        if current != text:
            found.append(("write" if current is None else "update", name))
    return files, found


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=ROOT, help="kit checkout (default: this repository)")
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 on any difference")
    args = parser.parse_args(argv)
    try:
        files, found = differences(args.root)
    except (OSError, PluginError) as exc:
        print("make-plugins: {}".format(exc), file=sys.stderr)
        return 2
    for action, name in found:
        print("{}{} {}".format("would " if args.check else "", action, name))
        if not args.check:
            path = os.path.join(args.root, *name.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(files[name])
    return 1 if args.check and found else 0


if __name__ == "__main__":
    sys.exit(main())
