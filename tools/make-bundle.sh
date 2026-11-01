#!/usr/bin/env bash
set -euo pipefail

KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# On Windows `python3` is often the Microsoft Store stub, which is on PATH but cannot start.
PYTHON=''
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys' >/dev/null 2>&1; then
    PYTHON=$candidate
    break
  fi
done
if [[ -z "$PYTHON" ]]; then
  printf 'Error: python3 3.8 or newer is required.\n' >&2
  exit 1
fi
if [[ -d "$KIT_DIR/skills" ]]; then
  if "$PYTHON" -I "$KIT_DIR/tools/knowledge_scan.py" "$KIT_DIR/skills"; then
    :
  else
    scan_status=$?
    if ((scan_status == 1)); then
      printf 'Refusing to bundle: the knowledge scan found the hits above.\n'
    fi
    exit "$scan_status"
  fi
fi
"$PYTHON" - "$KIT_DIR" <<'PY'
import datetime
import hashlib
import os
import pathlib
import subprocess
import sys

sys.dont_write_bytecode = True
root = pathlib.Path(sys.argv[1]).resolve()
# One exclusion list for this builder and check-release's "fresh" check (findings/bundle-size-plan.md section 8).
sys.path.insert(0, str(root / "tools"))
from release_bundle import BUNDLE_NAME, EVIDENCE_FILES, EVIDENCE_NAME, is_evidence, is_shipped

delimiter = b"__USAGE_OPTIMIZER_EOF__"

def git_paths(*arguments):
    result = subprocess.run(["git", "-C", str(root), *arguments],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            check=False)
    if result.returncode:
        sys.stderr.write(result.stderr.decode("utf-8", "replace"))
        raise SystemExit(result.returncode)
    paths = []
    for raw in result.stdout.split(b"\0"):
        if raw:
            try:
                paths.append(raw.decode("utf-8"))
            except UnicodeDecodeError:
                raise SystemExit("refusing to bundle a path that is not UTF-8")
    return paths

def is_sensitive(path):
    parts = pathlib.PurePosixPath(path).parts
    if ".ssh" in parts:
        return True
    name = parts[-1] if parts else path
    return (name in {"auth.json", ".credentials.json", "providers.json", ".env"}
            or name.endswith(".key") or name.endswith(".env")
            or name.startswith("secrets"))

def shell_quote(value):
    return "'" + value.replace("'", "'\"'\"'") + "'"

tracked = git_paths("ls-files", "-z")
untracked = git_paths("ls-files", "--others", "--exclude-standard", "-z")
paths = sorted(set(tracked + untracked))
main_paths = [path for path in paths if is_shipped(path)]
evidence_paths = [path for path in paths if is_evidence(path)]
if not main_paths:
    raise SystemExit("no source files found by git ls-files")
if evidence_paths and len(evidence_paths) != len(EVIDENCE_FILES):
    raise SystemExit("evidence files missing (tools/release_bundle.py EVIDENCE_FILES): " +
                     ", ".join(sorted(set(EVIDENCE_FILES) - set(evidence_paths))))

def load(relative):
    if is_sensitive(relative):
        raise SystemExit("refusing to read credential-like path while bundling: " + relative)
    source = root / relative
    if source.is_symlink():
        raise SystemExit("refusing to follow a symlink while bundling: " + relative)
    if not source.is_file():
        raise SystemExit("listed source file is missing or not a regular file: " + relative)
    try:
        contents = source.read_bytes()
        text = contents.decode("utf-8")
    except UnicodeDecodeError:
        raise SystemExit("refusing to bundle non-UTF-8 file: " + relative)
    if b"\0" in contents:
        raise SystemExit("refusing to bundle a file containing NUL bytes: " + relative)
    if any(line.rstrip(b"\r\n") == delimiter for line in contents.splitlines(keepends=True)):
        raise SystemExit("refusing to bundle a file containing the heredoc delimiter line: " + relative)
    added_newline = not contents.endswith(b"\n")
    if added_newline:
        contents += b"\n"
        text += "\n"
        print("NOTE: added a final newline to " + relative + "; its recorded hash covers the added newline.")
    return {
        "path": relative,
        "contents": contents,
        "text": text,
        "hash": hashlib.sha256(contents).hexdigest(),
        # A shebang, not the mode bit: Windows reports every file as executable.
        "executable": contents.startswith(b"#!"),
    }

files = [load(relative) for relative in main_paths]
evidence = [load(relative) for relative in evidence_paths]

policy = next((item for item in files if item["path"] == "POLICY.md"), None)
if policy is None:
    raise SystemExit("POLICY.md is required to build the bundle")
version_line = None
for line in policy["text"].splitlines():
    if "Claude Usage Optimizer version:" in line:
        version_line = line.strip()
        break
if version_line is None:
    raise SystemExit("POLICY.md has no line matching 'Claude Usage Optimizer version:'")

generated_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
dist = root / "dist"

def write_bundle(output, items, about, tail):
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    with temporary.open("wb") as stream:
        def emit(line):
            stream.write(line.encode("utf-8"))

        emit("#!/usr/bin/env bash\n")
        emit("set -euo pipefail\n")
        emit("# " + version_line + "\n")
        emit("# Generated at " + generated_at + " (UTC)\n")
        for line in about:
            emit("# " + line + "\n")
        for item in items:
            emit("#   " + item["hash"] + "  " + item["path"] + "\n")
        emit("\n")
        emit('DEST="${USAGE_OPTIMIZER_DIR:-$HOME/claude-usage-optimizer}"\n')
        emit('if [[ -e "$DEST/.git" ]]; then\n')
        emit("  printf 'Refusing to extract into %s: it is a git checkout, probably the source checkout. Set USAGE_OPTIMIZER_DIR to another directory.\\n' \"$DEST\" >&2\n")
        emit("  exit 1\n")
        emit("fi\n\n")
        for item in items:
            relative = item["path"]
            quoted = shell_quote(relative)
            parent = pathlib.PurePosixPath(relative).parent.as_posix()
            if parent == ".":
                emit('mkdir -p "$DEST"\n')
            else:
                emit('mkdir -p "$DEST"/' + shell_quote(parent) + "\n")
            emit('cat > "$DEST"/' + quoted + " <<'__USAGE_OPTIMIZER_EOF__'\n")
            stream.write(item["contents"])
            emit("__USAGE_OPTIMIZER_EOF__\n")
            if item["executable"]:
                emit('chmod 755 "$DEST"/' + quoted + "\n")
        emit("\nsha256_file() {\n")
        emit("  local output\n")
        emit("  if command -v sha256sum >/dev/null 2>&1; then\n")
        emit('    output="$(sha256sum "$1")"\n')
        emit("  elif command -v shasum >/dev/null 2>&1; then\n")
        emit('    output="$(shasum -a 256 "$1")"\n')
        emit("  else\n")
        emit("    printf 'Error: sha256sum or shasum is required to verify the bundle.\\n' >&2\n")
        emit("    return 1\n")
        emit("  fi\n")
        emit('  printf "%s\\n" "${output%% *}"\n')
        emit("}\n")
        emit("verify_sha256() {\n")
        emit("  local expected=$1 file=$2 actual\n")
        emit('  actual="$(sha256_file "$file")"\n')
        emit('  if [[ "$actual" != "$expected" ]]; then\n')
        emit('    printf "SHA-256 mismatch: %s\\n" "$file" >&2\n')
        emit("    exit 1\n")
        emit("  fi\n")
        emit("}\n\n")
        for item in items:
            emit("verify_sha256 " + shell_quote(item["hash"]) + ' "$DEST"/' +
                 shell_quote(item["path"]) + "\n")
        emit('printf "SHA-256 checks passed for %d files.\\n" ' + str(len(items)) + "\n")
        for line in tail:
            emit(line + "\n")

    os.chmod(temporary, 0o755)
    os.replace(str(temporary), str(output))
    print("Wrote " + str(output) + " with " + str(len(items)) + " files.")

write_bundle(dist / BUNDLE_NAME, files,
             ["Extracts to ${USAGE_OPTIMIZER_DIR:-~/claude-usage-optimizer} (in a dry run too), verifies every sha256, then",
              "runs install.sh with the same arguments. Files, with their sha256:"],
             ['exec bash "$DEST/install.sh" "$@"'])

# The Suite R rescore evidence ships as a second file next to the bundle (findings/bundle-size-plan.md step 2).
evidence_output = dist / EVIDENCE_NAME
if evidence:
    write_bundle(evidence_output, evidence,
                 ["Suite R rescore evidence (findings/FINDINGS.md section 8), kept out of the main bundle for its size.",
                  "Extracts to ${USAGE_OPTIMIZER_DIR:-~/claude-usage-optimizer}, next to the kit, verifies every sha256",
                  "and installs nothing: the next install.sh run from there copies it into the kit. Files, with their sha256:"],
                 ["printf 'Suite R evidence extracted under %s/findings/suite-r; the next install.sh run copies it into the kit.\\n' \"$DEST\""])
elif evidence_output.exists():
    evidence_output.unlink()
PY
