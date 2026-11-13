#!/usr/bin/env python3
"""Run local integrity and publication checks for a kit release."""

import argparse
import fnmatch
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from release_bundle import (BUNDLE_NAME, EVIDENCE_FILES, EVIDENCE_NAME, BundleError, git_paths,
                            parse_bundle, shipped_files, version_from_policy)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default_kit = pathlib.Path(__file__).resolve().parent.parent
    parser.add_argument("--kit", default=str(default_kit))
    parser.add_argument("--bundle", default=str(default_kit / "dist" / BUNDLE_NAME))
    parser.add_argument("--evidence", help="the evidence file (default: next to --bundle)")
    parser.add_argument("--page", default=str(default_kit / "dist" / "index.html"))
    parser.add_argument("--patterns")
    parser.add_argument("--max-bytes", type=int, default=16000000)
    args = parser.parse_args()
    if args.max_bytes <= 0:
        parser.error("--max-bytes must be positive")

    kit = pathlib.Path(args.kit).resolve()
    statuses = []
    def report(name, state, detail):
        statuses.append(state)
        print("{} {}: {}".format(state, name, detail))

    try:
        version = version_from_policy(kit)
    except BundleError as error:
        version = None
    bundle_obj = None
    bundle_error = None
    try:
        bundle_obj = parse_bundle(args.bundle)
    except BundleError as error:
        bundle_error = str(error)
    try:
        page_bytes = pathlib.Path(args.page).read_bytes()
        page = page_bytes.decode("utf-8")
        page_sha = hashlib.sha256(page_bytes).hexdigest()
    except (OSError, UnicodeDecodeError) as error:
        page = None
        page_sha = "unavailable"
        page_error = str(error)
    else:
        page_error = None
    if version is None:
        version_state, version_detail = "FAIL", "POLICY.md version unavailable"
    elif page is None:
        version_state, version_detail = "FAIL", "cannot read page: " + page_error
    elif bundle_obj is None:
        version_state, version_detail = "FAIL", "bundle version unavailable"
    else:
        matched = version in page and bundle_obj["version"] == version
        version_state = "OK" if matched else "FAIL"
        version_detail = ("{} in bundle and page".format(version) if matched else
                          "POLICY version does not match bundle and page")
    report("version", version_state, version_detail)

    try:
        shipped = shipped_files(kit)
        evidence = shipped_files(kit, evidence=True)
        shipped_error = None
    except BundleError as error:
        shipped = {}
        evidence = {}
        shipped_error = str(error)
    # Every file a release publishes: the bundle's and the evidence file's. The content checks below cover both.
    published = dict(shipped)
    published.update(evidence)
    catalog = kit / "arms.json"
    try:
        catalog_obj = json.loads(catalog.read_text(encoding="utf-8"))
        if not isinstance(catalog_obj, dict) or "catalog_version" not in catalog_obj:
            raise ValueError("missing catalog_version")
        def has_null_measured(value):
            if isinstance(value, dict):
                return any((key == "measured" and child is None) or has_null_measured(child)
                           for key, child in value.items())
            if isinstance(value, list):
                return any(has_null_measured(child) for child in value)
            return False
        if has_null_measured(catalog_obj):
            raise ValueError('contains "measured": null')
        report("catalog", "OK", "arms.json parses; catalog_version present; no null measured")
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        report("catalog", "FAIL", "arms.json: " + str(error))

    json_failures = []
    for relative, item in published.items():
        if relative.endswith(".json") or relative.endswith(".jsonl"):
            try:
                content = item["content"].decode("utf-8")
                if relative.endswith(".jsonl"):
                    for number, line in enumerate(content.splitlines(), 1):
                        if line.strip():
                            json.loads(line)
                else:
                    json.loads(content)
            except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
                json_failures.append(relative)
    json_detail = ("cannot enumerate shipped files: " + shipped_error if shipped_error else
                   "invalid JSON: " + ", ".join(json_failures[:20]) if json_failures else
                   "all shipped JSON and JSONL parse")
    report("json", "FAIL" if shipped_error or json_failures else "OK", json_detail)

    try:
        bundle_bytes = pathlib.Path(args.bundle).read_bytes()
        bundle_sha = hashlib.sha256(bundle_bytes).hexdigest()
        size = len(bundle_bytes)
        size_state = "FAIL" if size > args.max_bytes else (
            "WARN" if size > args.max_bytes * 0.94 else "OK")
        size_detail = "{} bytes (limit {}); {} files; bundle sha256 {}; page sha256 {}".format(
            size, args.max_bytes, len(bundle_obj["files"]) if bundle_obj else 0,
            bundle_sha, page_sha)
    except OSError as error:
        size_state, size_detail = "FAIL", "cannot read bundle: " + str(error)
    if bundle_error:
        size_state, size_detail = "FAIL", "cannot parse bundle: " + bundle_error
    report("bundle", size_state, size_detail)

    if bundle_obj is not None:
        differing = sorted(set(shipped) ^ set(bundle_obj["files"]))
        differing.extend(sorted(path for path in set(shipped) & set(bundle_obj["files"])
                                if shipped[path]["hash"] != bundle_obj["files"][path]["hash"]))
        differing = sorted(set(differing))
        report("fresh", "FAIL" if differing else "OK",
               "differing files: " + ", ".join(differing[:20]) if differing else
               "bundle matches current shipped files")
    else:
        report("fresh", "FAIL", "bundle contents unavailable")

    # The evidence file (findings/bundle-size-plan.md step 2): the same size limit, every listed file, fresh.
    evidence_path = pathlib.Path(args.evidence) if args.evidence else \
        pathlib.Path(args.bundle).resolve().parent / EVIDENCE_NAME
    if not evidence and not evidence_path.exists():
        report("evidence", "OK", "no evidence files in this kit and no evidence file")
    else:
        try:
            evidence_bytes = evidence_path.read_bytes()
            evidence_obj = parse_bundle(str(evidence_path))
        except (OSError, BundleError) as error:
            report("evidence", "FAIL", "cannot read {}: {}".format(evidence_path.name, error))
        else:
            problems = []
            missing = sorted(set(EVIDENCE_FILES) - set(evidence))
            if missing:
                problems.append("listed but not in the kit: " + ", ".join(missing))
            stale = sorted(set(evidence) ^ set(evidence_obj["files"]))
            stale.extend(path for path in set(evidence) & set(evidence_obj["files"])
                         if evidence[path]["hash"] != evidence_obj["files"][path]["hash"])
            if stale:
                problems.append("differing files: " + ", ".join(sorted(set(stale))))
            if version is not None and evidence_obj["version"] != version:
                problems.append("version does not match POLICY.md")
            evidence_size = len(evidence_bytes)
            if evidence_size > args.max_bytes:
                problems.append("{} bytes, over the limit {}".format(evidence_size, args.max_bytes))
            state = "FAIL" if problems else ("WARN" if evidence_size > args.max_bytes * 0.94 else "OK")
            report("evidence", state, "; ".join(problems) if problems else
                   "{} bytes; {} files, fresh; sha256 {}".format(
                       evidence_size, len(evidence_obj["files"]),
                       hashlib.sha256(evidence_bytes).hexdigest()))

    pattern_path = args.patterns
    if pattern_path is None:
        default_patterns = pathlib.Path.home() / ".config" / "lanes" / "release-patterns.local"
        if default_patterns.is_file():
            pattern_path = str(default_patterns)
    if pattern_path is None or not pathlib.Path(pattern_path).is_file():
        report("patterns", "WARN", "no local patterns")
    else:
        try:
            pattern_lines = pathlib.Path(pattern_path).read_text(encoding="utf-8").splitlines()
            regexes = []
            excludes = []
            invalid = False
            for number, raw in enumerate(pattern_lines, 1):
                value = raw.strip()
                if not value or value.startswith("#"):
                    continue
                if value.startswith("!"):
                    excludes.append(value[1:].strip())
                else:
                    try:
                        regexes.append((number, value, re.compile(value, re.IGNORECASE)))
                    except re.error:
                        invalid = True
            hits = []
            for relative in sorted(published):
                if any(fnmatch.fnmatch(relative, glob) for glob in excludes):
                    continue
                try:
                    content = published[relative]["content"].decode("utf-8")
                except UnicodeDecodeError:
                    continue
                for line_number, line in enumerate(content.splitlines(), 1):
                    for pattern_number, _pattern, compiled in regexes:
                        if compiled.search(line):
                            hits.append("{}:{} pattern#{}".format(relative, line_number,
                                                                  pattern_number))
            state = "FAIL" if hits or invalid else "OK"
            detail = "; ".join(hits[:100]) if hits else (
                "invalid regex in patterns file" if invalid else "no local-only patterns found")
            report("patterns", state, detail)
        except (OSError, UnicodeDecodeError) as error:
            report("patterns", "FAIL", "cannot read patterns file: " + str(error))

    private_path = pathlib.Path(os.environ.get(
        "USAGE_OPTIMIZER_PRIVATE_PATTERNS",
        str(pathlib.Path.home() / ".config" / "lanes" / "private-patterns.txt")))
    if not private_path.is_file():
        report("private", "WARN", "no private pattern list at {}; the release is not checked for "
               "private text".format(private_path))
    else:
        try:
            private_lines = private_path.read_text(encoding="utf-8").splitlines()
            private_regexes = []
            bad_patterns = []
            for number, raw in enumerate(private_lines, 1):
                value = raw.strip()
                if not value or value.startswith("#"):
                    continue
                try:
                    private_regexes.append((number, re.compile(value)))
                except re.error:
                    bad_patterns.append(number)
            private_hits = []
            private_sources = [(relative, item["content"].decode("utf-8"))
                               for relative, item in sorted(published.items())]
            if page is not None:
                private_sources.append((str(pathlib.Path(args.page)), page))
            dist_page = kit / "dist" / "index.html"
            if dist_page.is_file() and dist_page.resolve() != pathlib.Path(args.page).resolve():
                private_sources.append(("dist/index.html", dist_page.read_text(encoding="utf-8")))
            for relative, content in private_sources:
                for line_number, line in enumerate(content.splitlines(), 1):
                    for pattern_number, compiled in private_regexes:
                        if compiled.search(line):
                            private_hits.append("{}:{} pattern#{}".format(
                                relative, line_number, pattern_number))
            private_problems = (["bad regular expression at pattern line {}".format(number)
                                 for number in bad_patterns] + private_hits)
            report("private", "FAIL" if private_problems else "OK",
                   "; ".join(private_problems[:100]) if private_problems else
                   "no private text found")
        except (OSError, UnicodeDecodeError) as error:
            report("private", "FAIL", "cannot read private pattern list: " + str(error))

    # The Artifact publish refuses a page or text file holding U+FFFD, and the page renders the shipped
    # docs, so one literal replacement character in a .md file blocks the release at publish time.
    replacement = "\ufffd".encode("utf-8")
    flagged = sorted(relative for relative in published if replacement in published[relative]["content"])
    if page is not None and "\ufffd" in page:
        flagged.insert(0, "page")
    report("replacement", "FAIL" if flagged else "OK",
           "U+FFFD (write it as an escape) in: " + ", ".join(flagged[:20]) if flagged else
           "no U+FFFD in page or shipped files")

    # The bundle carries working-tree bytes, so a file git stores with LF but an editor saved with CRLF
    # ships CRLF; "fresh" cannot see it because it compares the bundle with that same working tree.
    try:
        converted = []
        for entry in git_paths(kit, "ls-files", "--eol", "-z"):
            info, _, relative = entry.partition("\t")
            if relative in published and info.split()[:2] in (["i/lf", "w/crlf"], ["i/lf", "w/mixed"]):
                converted.append(relative)
        report("eol", "FAIL" if converted else "OK",
               "CRLF in the working tree of files git stores with LF (convert them, or build from a "
               "clean checkout): " + ", ".join(converted[:20]) if converted else
               "shipped line endings match git")
    except BundleError as error:
        report("eol", "FAIL", str(error))

    try:
        tracked = set(__import__("release_bundle").git_paths(kit, "ls-files", "-z"))
        untracked = sorted(set(published) - tracked)
        # make-bundle ships untracked, non-ignored files: a stray log once carried an account id into a bundle.
        report("untracked", "FAIL" if untracked else "OK",
               "shipped but not tracked (commit or git-ignore): " + ", ".join(untracked) if untracked
               else "no untracked shipped files")
    except BundleError as error:
        report("untracked", "FAIL", str(error))

    # The platform files (PLAN.md 3.7): the Codex policy file must be the one make-platform-policy writes from
    # POLICY.md, and the Amp plugin's static tests must pass. Each runs under python3 -I, as the checks above
    # read the kit; a kit without a platforms/ folder has nothing to check.
    if not (kit / "platforms").is_dir():
        report("platforms", "OK", "no platform files in this kit")
    else:
        platform_problems = []
        steps = (("make-platform-policy --check", kit / "tools" / "make-platform-policy.py", ["--check"]),
                 ("Amp plugin static tests", kit / "tests" / "test_amp_plugin_static.py", []))
        for label, script, extra in steps:
            run = subprocess.run([sys.executable, "-I", "-B", str(script), *extra], cwd=str(kit),
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, encoding="utf-8", errors="replace")
            lines = [line.strip() for line in run.stdout.splitlines() if line.strip()]
            # unittest prints each failing test's name; the generator prints its one difference.
            shown = [line for line in lines if line.startswith(("FAIL:", "ERROR:"))] or lines[-1:]
            if run.returncode:
                platform_problems.append("{} exits {}: {}".format(
                    label, run.returncode, "; ".join(shown) or "no output"))
        report("platforms", "FAIL" if platform_problems else "OK",
               "; ".join(platform_problems) if platform_problems else
               "make-platform-policy --check and the Amp plugin static tests pass")
    failures = statuses.count("FAIL")
    print("Summary: {} FAIL, {} WARN".format(failures, statuses.count("WARN")))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
