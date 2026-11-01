#!/usr/bin/env python3
"""Export a redacted snapshot of a Claude Code memory directory."""

import argparse
import datetime
import json
import os
import re
import shutil
import sys
import tempfile


TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

import knowledge_scan


CLUSTER_RE = re.compile(r"^\s*-\s+\*\*(.*?)\*\*\s+(?:—|--)\s*(.*?)\s*$")
DESCRIPTION_RE = re.compile(r"^\s*description:\s*(.*?)\s*$", re.IGNORECASE)
NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
ATX_HEADING_RE = re.compile(r"^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$")
SETEXT_RE = re.compile(r"^ {0,3}(?:=+|-+)\s*$")


def read_text(path):
    with open(path, "r", encoding="utf-8", newline="") as stream:
        return stream.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="") as stream:
        stream.write(text)


def invalid_rules_line(line_number):
    return ValueError("invalid rules line %d" % line_number)


def load_rules(path):
    excludes = set()
    replacements = []
    records = []
    names = set()
    if path is None:
        return excludes, replacements, records
    path = os.path.expanduser(path)
    for line_number, raw_line in enumerate(read_text(path).splitlines(), 1):
        if not raw_line.strip() or raw_line.startswith("#"):
            continue
        fields = raw_line.split("\t")
        if len(fields) == 2 and fields[0] == "exclude" and fields[1]:
            excludes.add(fields[1])
            continue
        if len(fields) == 3 and fields[0] == "replace" and fields[1]:
            replacements.append((fields[1], fields[2]))
            continue

        if fields and fields[0] == "record" and len(fields) in (2, 3) and fields[1]:
            source = os.path.expanduser(fields[1])
            basename = os.path.basename(source)
            default_name = basename[:-3] if basename.endswith(".md") else basename
            name = fields[2] if len(fields) == 3 else default_name
            if not NAME_RE.fullmatch(name) or name in names or not os.path.isfile(source):
                raise invalid_rules_line(line_number)
            records.append(("record", source, name, line_number))
            names.add(name)
            continue

        if fields and fields[0] == "tasks" and len(fields) == 3 and fields[1]:
            source = os.path.expanduser(fields[1])
            name = fields[2]
            if not NAME_RE.fullmatch(name) or name in names or not os.path.isdir(source):
                raise invalid_rules_line(line_number)
            records.append(("tasks", source, name, line_number))
            names.add(name)
            continue
        raise invalid_rules_line(line_number)
    return excludes, replacements, records


def replace_kind(text, kind, replacement, allow):
    matches = list(knowledge_scan.iter_matches(text, kind, allow))
    if not matches:
        return text, 0
    pieces = []
    position = 0
    for match in matches:
        pieces.append(text[position:match.start()])
        if kind == "account-id":
            pieces.append(match.group(1) + match.group(2) + replacement)
        else:
            pieces.append(replacement)
        position = match.end()
    pieces.append(text[position:])
    return "".join(pieces), len(matches)


def redact(text, replacements, allow):
    literal_count = 0
    for literal, replacement in replacements:
        literal_count += text.count(literal)
        text = text.replace(literal, replacement)

    counts = {"email": 0, "ip": 0, "id": 0}
    text, counts["email"] = replace_kind(text, "email", "<email>", allow)
    text, dotted_count = replace_kind(text, "ipv4", "<ip>", allow)
    text, dashed_count = replace_kind(text, "dashed-ipv4", "<ip>", allow)
    counts["ip"] = dotted_count + dashed_count
    text, counts["id"] = replace_kind(text, "account-id", "<id>", allow)
    return text, counts, literal_count


def render_tasks(directory, name):
    tasks = []
    for filename in sorted(os.listdir(directory)):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(directory, filename)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", newline="") as stream:
                task = json.load(stream)
        except (OSError, UnicodeError, ValueError):
            continue
        if not isinstance(task, dict) or not all(key in task for key in ("id", "subject", "status")):
            continue
        task_id = task["id"]
        if isinstance(task_id, bool):
            continue
        try:
            if isinstance(task_id, int):
                numeric_id = task_id
            elif isinstance(task_id, str) and re.fullmatch(r"-?[0-9]+", task_id):
                numeric_id = int(task_id)
            else:
                continue
        except (TypeError, ValueError):
            continue
        tasks.append((numeric_id, filename, task))
    tasks.sort(key=lambda item: (item[0], item[1]))

    lines = ["# Task list %s (%d tasks)" % (name, len(tasks)), ""]
    for _, _, task in tasks:
        lines.append("- **#%s [%s]** %s" % (task["id"], task["status"], task["subject"]))
        description = task.get("description")
        if description:
            for line in str(description).splitlines():
                lines.append("  " + line)
    return "\n".join(lines) + "\n"


def parse_clusters(text, included_slugs):
    clusters = []
    claimed = set()
    for line in text.splitlines():
        match = CLUSTER_RE.match(line)
        if not match:
            continue
        theme = match.group(1).strip()
        slugs = []
        for slug in (part.strip() for part in match.group(2).split(",")):
            if slug in included_slugs and slug not in claimed:
                slugs.append(slug)
                claimed.add(slug)
        clusters.append((theme, slugs))
    return clusters, claimed


def note_description(text):
    lines = text.splitlines()
    body_start = 0
    frontmatter = []
    if lines and lines[0].strip() == "---":
        end = None
        for index in range(1, len(lines)):
            if lines[index].strip() in ("---", "..."):
                end = index
                break
        if end is None:
            body_start = 1
        else:
            frontmatter = lines[1:end]
            body_start = end + 1
    for line in frontmatter:
        match = DESCRIPTION_RE.match(line)
        if match:
            value = match.group(1).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if value:
                return value[:160]
    for line in lines[body_start:]:
        value = line.strip()
        if value:
            return value[:160]
    return ""


def record_description(text):
    lines = text.splitlines()
    body_start = 0
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() in ("---", "..."):
                body_start = index + 1
                break
        else:
            body_start = 1
    first_nonblank = ""
    for index in range(body_start, len(lines)):
        line = lines[index]
        value = line.strip()
        if not value:
            continue
        if not first_nonblank:
            first_nonblank = value
        heading = ATX_HEADING_RE.match(line)
        if heading:
            return heading.group(1).strip()[:160]
        if index + 1 < len(lines) and SETEXT_RE.match(lines[index + 1]):
            return value[:160]
    return first_nonblank[:160]


def first_mention_order(memory_text, slugs):
    found = []
    for slug in slugs:
        pattern = re.compile(r"(?<![A-Za-z0-9_-])" + re.escape(slug) + r"(?![A-Za-z0-9_-])")
        match = pattern.search(memory_text)
        if match:
            found.append((match.start(), slug))
    found.sort()
    return [slug for _, slug in found]


def build_index(date_text, note_texts, record_texts):
    included = set(note_texts)
    descriptions = {slug: note_description(text) for slug, text in note_texts.items()}
    clusters = []
    clustered = set()
    theme_text = note_texts.get("index-by-theme")
    if theme_text is not None:
        clusters, clustered = parse_clusters(theme_text, included)

    memory_text = note_texts.get("MEMORY", "")
    remaining = included - clustered
    recent = first_mention_order(memory_text, remaining)
    recent_set = set(recent)
    other = sorted(remaining - recent_set, key=lambda slug: (slug.lower(), slug))

    lines = [
        "<!-- Generated by tools/export-knowledge.py on %s; do not edit. -->" % date_text,
        "",
        "# Migration knowledge pack",
        "",
        "Notes: %d" % len(note_texts),
        "Records: %d" % len(record_texts),
    ]

    def add_section(title, slugs):
        lines.extend(["", "## " + title, ""])
        for slug in slugs:
            lines.append("- [%s](notes/%s.md) — %s" % (slug, slug, descriptions[slug]))

    for theme, slugs in clusters:
        add_section(theme, slugs)
    add_section("Recent and operative", recent)
    add_section("Other", other)

    lines.extend(["", "## Programme records", ""])
    for name in sorted(record_texts):
        lines.append("- [%s](records/%s.md) — %s" % (
            name, name, record_description(record_texts[name]),
        ))
    return "\n".join(lines) + "\n"


def surviving_rule_literals(root, replacements):
    hits = []
    literals = sorted(set(literal for literal, _ in replacements), key=len, reverse=True)
    if not literals:
        return hits
    for current, directories, filenames in os.walk(root):
        directories.sort()
        for filename in sorted(filenames):
            path = os.path.join(current, filename)
            with open(path, "r", encoding="utf-8", errors="replace", newline="") as stream:
                text = stream.read()
            relative = os.path.relpath(path, root).replace(os.sep, "/")
            for line_number, line in enumerate(text.splitlines(), 1):
                for literal in literals:
                    start = 0
                    while True:
                        start = line.find(literal, start)
                        if start < 0:
                            break
                        hits.append((relative, line_number, len(literal)))
                        start += len(literal)
    return hits


def remove_path(path):
    if os.path.islink(path) or os.path.isfile(path):
        os.remove(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)


def markdown_names(path):
    if not os.path.isdir(path):
        return set()
    return set(name for name in os.listdir(path) if name.endswith(".md") and
               (os.path.isfile(os.path.join(path, name)) or os.path.islink(os.path.join(path, name))))


def commit_stage(stage_dir, out_dir):
    out_existed = os.path.lexists(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    components = ("notes", "records", "INDEX.md")
    backups = {}
    installed = []
    try:
        for component in components:
            destination = os.path.join(out_dir, component)
            if os.path.lexists(destination):
                backup = os.path.join(stage_dir, ".previous-" + component.replace("/", "_"))
                os.replace(destination, backup)
                backups[destination] = backup
        for component in components:
            staged = os.path.join(stage_dir, component)
            destination = os.path.join(out_dir, component)
            os.replace(staged, destination)
            installed.append(destination)
    except Exception:
        for destination in reversed(installed):
            remove_path(destination)
        for destination, backup in backups.items():
            if os.path.lexists(backup):
                os.replace(backup, destination)
        if not out_existed and not os.listdir(out_dir):
            os.rmdir(out_dir)
        raise


def export(memory_dir, out_dir, rules_path=None, date_text=None):
    if not os.path.isdir(memory_dir):
        raise ValueError("--memory is not a directory")
    excludes, replacements, record_rules = load_rules(rules_path)
    if date_text is None:
        date_text = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    memory_dir = os.path.abspath(memory_dir)
    out_dir = os.path.abspath(out_dir)
    parent = os.path.dirname(out_dir)
    os.makedirs(parent, exist_ok=True)
    stage_dir = tempfile.mkdtemp(prefix=".knowledge-export-", dir=parent)
    try:
        notes_dir = os.path.join(stage_dir, "notes")
        records_dir = os.path.join(stage_dir, "records")
        os.makedirs(notes_dir)
        os.makedirs(records_dir)

        allow = knowledge_scan.load_allowlist()
        included = {}
        excluded_count = 0
        totals = {"email": 0, "ip": 0, "id": 0, "literal": 0}
        source_names = sorted(name for name in os.listdir(memory_dir) if name.endswith(".md") and
                              os.path.isfile(os.path.join(memory_dir, name)))
        for name in source_names:
            slug = name[:-3]
            if slug in excludes:
                excluded_count += 1
                continue
            text, counts, literal_count = redact(read_text(os.path.join(memory_dir, name)), replacements, allow)
            included[slug] = text
            for key, count in counts.items():
                totals[key] += count
            totals["literal"] += literal_count
            write_text(os.path.join(notes_dir, slug + ".md"), text)

        record_texts = {}
        for record_type, source, name, _ in record_rules:
            if record_type == "record":
                text = read_text(source)
            else:
                text = render_tasks(source, name)
            text, counts, literal_count = redact(text, replacements, allow)
            record_texts[name] = text
            write_text(os.path.join(records_dir, name + ".md"), text)
            for key, count in counts.items():
                totals[key] += count
            totals["literal"] += literal_count

        write_text(os.path.join(stage_dir, "INDEX.md"), build_index(date_text, included, record_texts))

        privacy_hits = knowledge_scan.scan_tree(stage_dir, allow=allow)
        literal_hits = surviving_rule_literals(stage_dir, replacements)
        for relative, line, kind, length in privacy_hits:
            print("%s:%d %s len=%d" % (relative, line, kind, length))
        for relative, line, length in literal_hits:
            print("%s:%d rule-literal len=%d" % (relative, line, length))
        if privacy_hits or literal_hits:
            return 1

        new_paths = set(os.path.join("notes", name) for name in markdown_names(notes_dir))
        new_paths.update(os.path.join("records", name) for name in markdown_names(records_dir))
        removed_count = 0
        for old_name in markdown_names(os.path.join(out_dir, "notes")):
            if os.path.join("notes", old_name) not in new_paths:
                removed_count += 1
        for old_name in markdown_names(os.path.join(out_dir, "records")):
            if os.path.join("records", old_name) not in new_paths:
                removed_count += 1

        commit_stage(stage_dir, out_dir)
        print("notes=%d records=%d excluded=%d removed=%d email=%d ip=%d id=%d literal=%d" % (
            len(included), len(record_texts), excluded_count, removed_count,
            totals["email"], totals["ip"], totals["id"], totals["literal"],
        ))
        return 0
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--rules")
    parser.add_argument("--date")
    args = parser.parse_args(argv)
    if args.date:
        try:
            parsed = datetime.datetime.strptime(args.date, "%Y-%m-%d")
            if parsed.strftime("%Y-%m-%d") != args.date:
                raise ValueError("invalid date")
        except ValueError:
            parser.error("--date must be YYYY-MM-DD")
    try:
        return export(args.memory, args.out, args.rules, args.date)
    except (OSError, UnicodeError, ValueError) as error:
        message = str(error)
        if message.startswith("invalid rules line "):
            print("Error: " + message, file=sys.stderr)
        elif message == "--memory is not a directory":
            print("Error: --memory is not a directory", file=sys.stderr)
        else:
            print("Error: %s" % message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
