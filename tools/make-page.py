#!/usr/bin/env python3
"""Render dist/index.html, the setup page published next to dist/claude-usage-optimizer-bundle.sh.

Usage: tools/make-page.py [--url <artifact url>]

The URL is remembered in dist/.artifact-url, so later runs need no argument. Run
tools/make-bundle.sh first: the page carries the bundle's sha256 and size.
"""

import argparse
import datetime as dt
import hashlib
import html
import os
import re
import sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(KIT, "dist")
BUNDLE = "claude-usage-optimizer-bundle.sh"
# The Suite R rescore evidence, published next to the bundle (tools/release_bundle.py EVIDENCE_NAME).
EVIDENCE = "claude-usage-optimizer-evidence.sh"


def read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", help="the artifact URL the page is published at")
    args = parser.parse_args()

    url_file = os.path.join(DIST, ".artifact-url")
    url = args.url
    if url:
        os.makedirs(DIST, exist_ok=True)
        with open(url_file, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(url.strip() + "\n")
    elif os.path.exists(url_file):
        url = read(url_file).strip()
    url = url or "<ARTIFACT_URL>"

    bundle_path = os.path.join(DIST, BUNDLE)
    if not os.path.exists(bundle_path):
        sys.exit("make-page: {} is missing; run tools/make-bundle.sh first".format(bundle_path))
    with open(bundle_path, "rb") as handle:
        blob = handle.read()
    sha = hashlib.sha256(blob).hexdigest()
    built = dt.datetime.fromtimestamp(os.path.getmtime(bundle_path), dt.timezone.utc)
    evidence_path = os.path.join(DIST, EVIDENCE)
    if not os.path.exists(evidence_path):
        sys.exit("make-page: {} is missing; run tools/make-bundle.sh first".format(evidence_path))
    with open(evidence_path, "rb") as handle:
        evidence_blob = handle.read()

    policy = read(os.path.join(KIT, "POLICY.md"))
    match = re.search(r"Claude Usage Optimizer version:\s*([0-9][0-9.\-]*[0-9])", policy)
    if not match:
        sys.exit("make-page: no 'Claude Usage Optimizer version:' line in POLICY.md")
    findings_path = os.path.join(KIT, "findings", "FINDINGS.md")
    if not os.path.exists(findings_path):
        sys.exit("make-page: {} is missing".format(findings_path))
    findings = read(findings_path)
    improving_path = os.path.join(KIT, "IMPROVING.md")
    if not os.path.exists(improving_path):
        sys.exit("make-page: {} is missing".format(improving_path))
    improving = read(improving_path)
    prompt = read(os.path.join(KIT, "SETUP_PROMPT.md")).replace("<ARTIFACT_URL>", url).rstrip() + "\n"

    values = {
        "VERSION": match.group(1),
        "GENERATED": built.strftime("%Y-%m-%d %H:%M UTC"),
        "PROMPT": html.escape(prompt, quote=False),
        "POLICY": html.escape(policy, quote=False),
        "FINDINGS": html.escape(findings, quote=False),
        "IMPROVING": html.escape(improving, quote=False),
        "BUNDLE": BUNDLE,
        "SIZE": "{:,} bytes ({:.0f} KB)".format(len(blob), len(blob) / 1024.0),
        "SHA256": sha,
        "EVIDENCE": EVIDENCE,
        "EVIDENCESIZE": "{:,} bytes ({:.1f} MB)".format(len(evidence_blob), len(evidence_blob) / 1e6),
        "EVIDENCESHA": hashlib.sha256(evidence_blob).hexdigest(),
        "URL": html.escape(url, quote=False),
    }
    page = read(os.path.join(KIT, "tools", "page.html"))
    page = re.sub(r"\{\{([A-Z0-9]+)\}\}", lambda m: values[m.group(1)], page)
    out = os.path.join(DIST, "index.html")
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(page)
    print("make-page: wrote {} (version {}, bundle sha256 {}, url {})".format(out, values["VERSION"], sha[:16], url))


if __name__ == "__main__":
    main()
