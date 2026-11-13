"""Shared, non-executing parser for generated kit bundles."""

import hashlib
import os
import pathlib
import re
import subprocess

DELIMITER = "__USAGE_OPTIMIZER_EOF__"
VERSION_MARKER = "Claude Usage Optimizer version:"


class BundleError(Exception):
    pass


def git_paths(root, *arguments):
    result = subprocess.run(["git", "-C", str(root), *arguments],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise BundleError(result.stderr.decode("utf-8", "replace").strip() or
                          "git command failed")
    try:
        return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]
    except UnicodeDecodeError:
        raise BundleError("kit contains a non-UTF-8 path")


BUNDLE_NAME = "claude-usage-optimizer-bundle.sh"
EVIDENCE_NAME = "claude-usage-optimizer-evidence.sh"

#: The one exclusion list: tools/make-bundle.sh imports is_shipped and EVIDENCE_FILES from here, and
#: check-release's "fresh" check uses the same functions, so the two can never disagree
#: (findings/bundle-size-plan.md section 8). The files stay in git; only the bundle leaves them out.
#: - dist/: build output.
#: - .claude/: the source checkout's own Claude Code setup; install.sh never copies it (plan step 1).
#: - mods/<name>/tests/: install.sh never copies a mod's tests.
#: - plans/: planning notes and probe captures for kit work (e.g. plans/amp-codex); never installed.
EXCLUDED = re.compile(
    r"^(?:dist(?:/|$)|private(?:/|$)|public-repo(?:/|$)|plans(?:/|$)|\.claude/|mods/[^/]+/tests/)"
)

#: Suite R rescore evidence (FINDINGS.md section 8). No kit tool reads it at run time, so it ships as its
#: own file, EVIDENCE_NAME, published next to the bundle (plan step 2).
EVIDENCE_FILES = (
    "findings/suite-r/by-arm-v2.json",
    "findings/suite-r/outcomes-v2.jsonl",
    "findings/suite-r/rescore-per-run.jsonl",
)


def is_shipped(path):
    """True when the main bundle carries this repository path."""
    return not EXCLUDED.match(path) and path not in EVIDENCE_FILES


def is_evidence(path):
    """True when the evidence file carries this repository path."""
    return path in EVIDENCE_FILES


def shipped_files(root, evidence=False):
    """The main bundle's files, or with evidence=True the evidence file's, as the builder reads them."""
    tracked = git_paths(root, "ls-files", "-z")
    untracked = git_paths(root, "ls-files", "--others", "--exclude-standard", "-z")
    keep = is_evidence if evidence else is_shipped
    paths = [path for path in sorted(set(tracked + untracked)) if keep(path)]
    files = {}
    for relative in paths:
        source = root / relative
        if source.is_symlink() or not source.is_file():
            raise BundleError("listed source is not a regular file: " + relative)
        try:
            content = source.read_bytes()
            content.decode("utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise BundleError("cannot read UTF-8 source " + relative + ": " + str(error))
        if b"\0" in content:
            raise BundleError("source contains NUL bytes: " + relative)
        if not content.endswith(b"\n"):
            content += b"\n"
        files[relative] = {"content": content, "hash": hashlib.sha256(content).hexdigest(),
                           "executable": content.startswith(b"#!")}
    return files


def version_from_policy(root):
    try:
        lines = (root / "POLICY.md").read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise BundleError("cannot read POLICY.md: " + str(error))
    for line in lines:
        if VERSION_MARKER in line:
            return line.strip()
    raise BundleError("POLICY.md has no version line")


def parse_bundle(path):
    try:
        text = pathlib.Path(path).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise BundleError("cannot read bundle as UTF-8: " + str(error))
    lines = text.split("\n")
    clean = lambda line: line
    version = next((clean(line)[2:].strip() for line in lines
                    if clean(line).startswith("# ") and VERSION_MARKER in clean(line)), None)
    if version is None:
        raise BundleError("bundle has no version line")
    files = {}
    i = 0
    cat_re = re.compile(r"^cat > \"\$DEST\"/('(?:[^']|'\"'\"'[^']*)*') <<'" +
                        re.escape(DELIMITER) + r"'$")
    def unquote(value):
        return value[1:-1].replace("'\"'\"'", "'")
    while i < len(lines):
        current = clean(lines[i])
        if current.startswith("cat > "):
            match = cat_re.match(current)
            if not match:
                raise BundleError("malformed file block at line {}".format(i + 1))
            path_name = unquote(match.group(1))
            if not path_name or path_name.startswith("/") or "\\" in path_name or \
                    any(part in ("", ".", "..") for part in path_name.split("/")):
                raise BundleError("unsafe bundle path: " + path_name)
            i += 1
            content_lines = []
            while i < len(lines) and clean(lines[i]) != DELIMITER:
                content_lines.append(lines[i])
                i += 1
            if i == len(lines):
                raise BundleError("unterminated file block: " + path_name)
            content = ("\n".join(content_lines) + "\n").encode("utf-8") if content_lines else b""
            if path_name in files:
                raise BundleError("duplicate bundle path: " + path_name)
            files[path_name] = {"content": content, "hash": hashlib.sha256(content).hexdigest(),
                                "executable": content.startswith(b"#!")}
        i += 1
    verifies = {}
    verify_re = re.compile(r"^verify_sha256 '([0-9a-f]{64})' \"\$DEST\"/('(?:[^']|'\"'\"'[^']*)*')$")
    for raw_line in lines:
        line = clean(raw_line)
        if line.startswith("verify_sha256 "):
            match = verify_re.match(line)
            if not match:
                raise BundleError("malformed verify_sha256 line")
            path_name = unquote(match.group(2))
            if path_name in verifies:
                raise BundleError("duplicate hash verification: " + path_name)
            verifies[path_name] = match.group(1)
    if set(files) != set(verifies):
        raise BundleError("file blocks and verify_sha256 paths do not match")
    for path_name, item in files.items():
        if item["hash"] != verifies[path_name]:
            raise BundleError("SHA-256 mismatch for " + path_name)
    return {"version": version, "files": files}
