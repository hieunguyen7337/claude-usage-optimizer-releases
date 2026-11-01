#!/usr/bin/env python3
"""Find likely personal data and credentials in Markdown files."""

import argparse
import ipaddress
import os
import re


ALLOWLIST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge-scan.allow")

EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9.!#$%&'*+/=?^_`{|}~-])"
    r"([A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+)@"
    r"((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})"
    r"(?![A-Za-z0-9-])"
)
_IP_OCTET = r"(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|0?[0-9]{1,2})"
IPV4_RE = re.compile(
    r"(?<![A-Za-z0-9./])(?:" + _IP_OCTET + r"\.){3}" + _IP_OCTET + r"(?![A-Za-z0-9.])"
)
DASHED_IPV4_RE = re.compile(
    r"(?<![A-Za-z0-9-])(?:" + _IP_OCTET + r"-){3}" + _IP_OCTET + r"(?=\.[A-Za-z])"
)
KEY_PREFIX_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    r"sk-|ghp_|gho_|github_pat_|glpat-|xoxa-|xoxb-|xoxp-|AKIA"
    r")[A-Za-z0-9_-]{16,}|(?<![A-Za-z0-9])AIza[A-Za-z0-9_-]{16,}"
)
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}")
PEM_RE = re.compile(r"-----BEGIN[\s\S]*?PRIVATE KEY-----")
# Markdown may sit between the key and the number: legacy_id **42**, `legacy_id` 42.
ACCOUNT_ID_RE = re.compile(r"(?<![A-Za-z0-9_])(legacy_id|user_id)([=: *`'\"]+)\d+", re.IGNORECASE)
LONG_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9+_./-])"
    r"(?=[A-Za-z0-9+_-]{32,}(?![A-Za-z0-9+_./-]))"
    r"(?=[A-Za-z0-9+_-]*[A-Z])(?=[A-Za-z0-9+_-]*[a-z])"
    r"(?=[A-Za-z0-9+_-]*[0-9])[A-Za-z0-9+_-]{32,}"
    r"(?![A-Za-z0-9+_./-])"
)

PATTERNS = {
    "email": EMAIL_RE,
    "ipv4": IPV4_RE,
    "dashed-ipv4": DASHED_IPV4_RE,
    "key-prefix": KEY_PREFIX_RE,
    "jwt": JWT_RE,
    "pem": PEM_RE,
    "account-id": ACCOUNT_ID_RE,
    "long-token": LONG_TOKEN_RE,
}

_ALLOWED_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "localhost",
    "anthropic.com",
}
_ALLOWED_DOMAIN_SUFFIXES = (".example", ".test", ".invalid", ".localhost")
_SYSTEMD_SUFFIXES = (".service", ".socket", ".timer", ".target", ".mount", ".path", ".slice")


def email_is_allowed(match):
    address = match.group(0).lower()
    local_part = match.group(1).lower()
    domain = match.group(2).lower()
    if local_part == "git":
        return True
    if address == "noreply@anthropic.com":
        return True
    if domain in _ALLOWED_DOMAINS:
        return True
    if domain.endswith(_ALLOWED_DOMAIN_SUFFIXES) or domain.endswith(_SYSTEMD_SUFFIXES):
        return True
    return False


def ipv4_is_public(value):
    try:
        octets = value.split(".")
        if len(octets) != 4 or any(not octet.isdigit() or int(octet) > 255 for octet in octets):
            return False
        address = ipaddress.ip_address(".".join(str(int(octet)) for octet in octets))
        return address.is_global
    except (ValueError, TypeError):
        return False


def load_allowlist(path=None):
    if path is None:
        path = ALLOWLIST_PATH
    if not os.path.isfile(path):
        return set()
    allowed = set()
    with open(path, "r", encoding="utf-8", newline="") as stream:
        for line in stream.read().splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            allowed.add(line)
    return allowed


def iter_matches(text, kind, allow=None):
    """Yield regex matches of a kind after applying scanner allowlists."""
    allowed = load_allowlist() if allow is None else allow
    pattern = PATTERNS[kind]
    for match in pattern.finditer(text):
        if match.group(0) in allowed:
            continue
        if kind == "email" and email_is_allowed(match):
            continue
        if kind == "ipv4" and not ipv4_is_public(match.group(0)):
            continue
        if kind == "dashed-ipv4":
            dotted = match.group(0).replace("-", ".")
            if not ipv4_is_public(dotted):
                continue
        yield match


def scan_text(text, allow=None):
    """Return (line, kind, match length) for each privacy-scanner hit."""
    allowed = load_allowlist() if allow is None else allow
    hits = []
    for kind in PATTERNS:
        for match in iter_matches(text, kind, allowed):
            line_number = text.count("\n", 0, match.start()) + 1
            hits.append((line_number, kind, len(match.group(0)), match.start()))
    hits.sort(key=lambda hit: (hit[0], hit[3], hit[1]))
    return [(line, kind, length) for line, kind, length, _ in hits]


def scan_tree(root, allow=None):
    """Scan every Markdown file below root, returning relative-path hits."""
    hits = []
    if not os.path.isdir(root):
        return hits
    allowed = load_allowlist() if allow is None else allow
    for current, directories, filenames in os.walk(root):
        directories.sort()
        for filename in sorted(filenames):
            if not filename.endswith(".md"):
                continue
            path = os.path.join(current, filename)
            with open(path, "r", encoding="utf-8", newline="") as stream:
                text = stream.read()
            relative = os.path.relpath(path, root).replace(os.sep, "/")
            for line, kind, length in scan_text(text, allowed):
                hits.append((relative, line, kind, length))
    return hits


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    args = parser.parse_args(argv)
    if not os.path.isdir(args.directory):
        parser.error("directory does not exist or is not a directory")
    hits = scan_tree(args.directory)
    for relative, line, kind, length in hits:
        print("%s:%d %s len=%d" % (relative, line, kind, length))
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
