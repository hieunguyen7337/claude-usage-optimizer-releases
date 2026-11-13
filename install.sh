#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf 'Usage: %s [--dry-run] [--prefix DIR] [--no-view] [--reset-view] [--platform LIST]\n' "$0" >&2
  printf '  --no-view     leave the mobile view alone (mod, output style, view settings)\n' >&2
  printf '  --reset-view  set the view settings again even where you changed them by hand\n' >&2
  printf '  --platform    comma list of claude-code, amp, codex (default: the list the last install saved, else claude-code)\n' >&2
}

DRY_RUN=0
VIEW=apply
RESET_VIEW=0
PLATFORM_GIVEN=0
PLATFORM_FLAG=''
PREFIX_INPUT="${HOME}/.claude/usage-optimizer"
while (($#)); do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --no-view) VIEW=skip; shift ;;
    --reset-view) RESET_VIEW=1; shift ;;
    --prefix)
      if (($# < 2)); then usage; exit 2; fi
      PREFIX_INPUT=$2
      shift 2
      ;;
    --platform)
      if (($# < 2)); then usage; exit 2; fi
      PLATFORM_GIVEN=1
      PLATFORM_FLAG=$2
      shift 2
      ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; usage; exit 2 ;;
  esac
done

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$PREFIX_INPUT" = /* ]]; then
  PREFIX="$PREFIX_INPUT"
else
  PREFIX="$PWD/$PREFIX_INPUT"
fi
CLAUDE_DIR="$HOME/.claude"
SETTINGS_FILE="$CLAUDE_DIR/settings.json"
CLAUDE_MD="$CLAUDE_DIR/CLAUDE.md"

case "$(uname -s 2>/dev/null || true)" in
  Linux*) OS_NAME=Linux ;;
  Darwin*) OS_NAME=macOS ;;
  MINGW*|MSYS*|CYGWIN*) OS_NAME=Windows ;;
  *) OS_NAME=other ;;
esac

# The first interpreter that actually runs. On Windows `python3` is often the Microsoft Store stub,
# which is on PATH but cannot start, so fall back to `python` and the `py -3` launcher.
PYTHON=''
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys' >/dev/null 2>&1; then
    PYTHON="$(command -v "$candidate")"
    break
  fi
done
if [[ -z "$PYTHON" && "$OS_NAME" == Windows ]] && command -v py >/dev/null 2>&1 &&
   py -3 -c 'import sys' >/dev/null 2>&1; then
  PYTHON="$(cygpath -u "$(py -3 -c 'import sys; print(sys.executable)')")"
fi
if [[ -z "$PYTHON" ]]; then
  printf 'Error: python3 3.8 or newer is required.\n' >&2
  exit 1
fi
PY_VERSION="$("$PYTHON" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')"
if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'; then
  printf 'Error: python3 3.8 or newer is required (found %s).\n' "$PY_VERSION" >&2
  exit 1
fi
PREFIX="$("$PYTHON" -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$PREFIX")"
# PREFIX_NATIVE and PYTHON_NATIVE are what Windows programs (Claude Code, cmd.exe) are given.
PREFIX_NATIVE="$PREFIX"
PYTHON_NATIVE="$PYTHON"
if [[ "$OS_NAME" == Windows ]]; then
  PREFIX="$(cygpath -u "$PREFIX")"
  PREFIX_NATIVE="$(cygpath -m "$PREFIX")"
  PYTHON_NATIVE="$(cygpath -m "$("$PYTHON" -c 'import sys; print(sys.executable)')")"
fi
# The installed kit carries a copy of this script (see KIT_ITEMS). Run from there, it would copy the kit onto itself
# and remove files it is still reading, so it refuses; a checkout or an unpacked bundle is the place to run it.
if [[ "$(cd "$SOURCE_DIR" && pwd -P)" == "$(cd "$PREFIX" 2>/dev/null && pwd -P)" ]]; then
  printf 'Error: %s is the installed copy of the kit; run install.sh from a checkout or an unpacked bundle.\n' \
    "$SOURCE_DIR" >&2
  exit 1
fi

printf 'Operating system: %s\n' "$OS_NAME"
printf 'Python: %s (%s)\n' "$PY_VERSION" "$PYTHON_NATIVE"

# The platforms to install for: --platform, else the list the last install saved, else Claude Code. The core steps
# (the prefix copy, the tools on PATH, ~/.config/lanes) run for every list; each platform adds its own steps.
KNOWN_PLATFORMS=(claude-code amp codex)
normalize_platforms() {
  local input=$1 name candidate known selected=',' ordered=''
  local -a parts=()
  IFS=',' read -r -a parts <<< "$input" || true
  if ((${#parts[@]} == 0)); then
    printf 'no platform given\n' >&2
    return 1
  fi
  for name in "${parts[@]}"; do
    name="${name//[[:space:]]/}"
    known=0
    for candidate in "${KNOWN_PLATFORMS[@]}"; do
      if [[ "$name" == "$candidate" ]]; then known=1; fi
    done
    if ((!known)); then
      printf 'unknown platform "%s" (use claude-code, amp, codex)\n' "$name" >&2
      return 1
    fi
    selected+="$name,"
  done
  for candidate in "${KNOWN_PLATFORMS[@]}"; do
    if [[ "$selected" == *",$candidate,"* ]]; then ordered+="${ordered:+,}$candidate"; fi
  done
  printf '%s' "$ordered"
}
PLATFORMS_FILE="$PREFIX/platforms.installed"
PLATFORM_INPUT=claude-code
PLATFORM_NOTE=default
if ((PLATFORM_GIVEN)); then
  PLATFORM_INPUT=$PLATFORM_FLAG
  PLATFORM_NOTE='--platform'
elif [[ -f "$PLATFORMS_FILE" ]]; then
  IFS= read -r PLATFORM_INPUT < "$PLATFORMS_FILE" || true
  PLATFORM_NOTE="saved in $PLATFORMS_FILE"
fi
if ! PLATFORMS_CSV="$(normalize_platforms "$PLATFORM_INPUT")"; then
  if ((PLATFORM_GIVEN)); then usage; exit 2; fi
  printf 'Error: %s holds an invalid platform list; fix it or pass --platform.\n' "$PLATFORMS_FILE" >&2
  exit 1
fi
printf 'Platforms: %s (%s)\n' "$PLATFORMS_CSV" "$PLATFORM_NOTE"
has_platform() { [[ ",$PLATFORMS_CSV," == *",$1,"* ]]; }

version_check() {
  local executable=$1 output status
  if command -v timeout >/dev/null 2>&1; then
    if output="$(timeout 10 "$executable" --version 2>&1)"; then status=0; else status=$?; fi
  else
    if output="$("$PYTHON" - "$executable" <<'PY'
import subprocess
import sys

try:
    result = subprocess.run([sys.argv[1], "--version"], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=10, check=False)
except subprocess.TimeoutExpired:
    print("version check timed out")
    sys.exit(124)
text = result.stdout.decode("utf-8", "replace")
if not text:
    text = result.stderr.decode("utf-8", "replace")
sys.stdout.write(text)
sys.exit(result.returncode)
PY
    )"; then status=0; else status=$?; fi
  fi
  VERSION_STATUS=$status
  VERSION_OUTPUT=$output
}

# The version an npm package records, for a CLI that must not be started: npm puts a global
# package's launcher beside node_modules (Windows) or in bin/ beside lib/node_modules (Unix).
package_version() {
  local executable=$1 package=$2 dir candidate
  dir="$(dirname "$executable")"
  for candidate in "$dir/node_modules/$package/package.json" "$dir/../lib/node_modules/$package/package.json"; do
    if [[ -f "$candidate" ]]; then
      "$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("version", ""))' \
        "$candidate" 2>/dev/null || true
      return
    fi
  done
}

CLIS=(claude codex agy cline)
if has_platform amp; then CLIS+=(amp); fi
CLI_MISSING=()
codex_version=''
if [[ "${USAGE_OPTIMIZER_SKIP_CLI_CHECK:-}" == 1 ]]; then
  # For the installer's own tests: starting every CLI is slow and depends on the machine.
  CLIS=()
  printf '\nCLI check skipped (USAGE_OPTIMIZER_SKIP_CLI_CHECK=1)\n'
else
  printf '\n%-14s %-12s %s\n' 'CLI' 'STATUS' 'VERSION'
  printf '%-14s %-12s %s\n' '--------------' '------------' '-------'
fi
for cli in ${CLIS[@]+"${CLIS[@]}"}; do
  executable="$(command -v "$cli" 2>/dev/null || true)"
  if [[ -z "$executable" && "$OS_NAME" == Windows ]]; then
    # npm and app installers on Windows often provide only a .cmd launcher.
    executable="$(command -v "$cli.cmd" 2>/dev/null || true)"
  fi
  if [[ -z "$executable" ]]; then
    CLI_MISSING+=("$cli")
    printf '%-14s %-12s %s\n' "$cli" 'missing' '-'
    continue
  fi
  if [[ "$cli" == cline ]]; then
    # Starting cline, even for --version, launches its self-update (npm update -g cline) in a new
    # window, and updates started by installs run close together overwrite each other and break cline.
    version_line="$(package_version "$executable" cline)"
    printf '%-14s %-12s %s\n' "$cli" 'found' "${version_line:-version not read (cline is not started)}"
    continue
  fi
  version_check "$executable"
  version_line="${VERSION_OUTPUT%%$'\n'*}"
  if [[ "$cli" == cline ]] && ((VERSION_STATUS == 86)); then
    version_line='locked by a local guard (exit 86)'
  elif ((VERSION_STATUS == 124)); then
    version_line='version check timed out'
  elif [[ -z "$version_line" ]]; then
    version_line="version unavailable (exit $VERSION_STATUS)"
  fi
  if [[ "$cli" == codex ]]; then codex_version=$version_line; fi
  printf '%-14s %-12s %s\n' "$cli" 'found' "$version_line"
done

if [[ -n "$codex_version" && "$codex_version" =~ ([0-9]+)\.([0-9]+)\.([0-9]+) ]]; then
  codex_major=$((10#${BASH_REMATCH[1]}))
  codex_minor=$((10#${BASH_REMATCH[2]}))
  codex_patch=$((10#${BASH_REMATCH[3]}))
  if ((codex_major < 0 || (codex_major == 0 && codex_minor < 156) ||
       (codex_major == 0 && codex_minor == 156 && codex_patch < 1))); then
    printf 'Warning: codex %s is older than 0.156.1. Update Codex before relying on delegation.\n' "$codex_version" >&2
  elif ((codex_major == 0 && (codex_minor < 159 || (codex_minor == 159 && codex_patch < 1)))); then
    printf 'Note: %s runs luna, but terra needs 0.159.0 and sol and astra 0.159.1 or newer (codex update).\n' "$codex_version" >&2
  fi
fi

required_files=(POLICY.md LANES.md README.md IMPROVING.md SETUP_PROMPT.md settings.fragment.json arms.json output-styles/Mobile.md
                mods/mobile-view/.claude-plugin/plugin.json mods/mobile-view/hooks/hooks.json)
for file in "${required_files[@]}"; do
  if [[ ! -f "$SOURCE_DIR/$file" ]]; then
    printf 'Error: required file is missing: %s\n' "$SOURCE_DIR/$file" >&2
    exit 1
  fi
done
for dir in bin agents mods output-styles improve; do
  if [[ ! -d "$SOURCE_DIR/$dir" ]]; then
    printf 'Error: required directory is missing: %s\n' "$SOURCE_DIR/$dir" >&2
    exit 1
  fi
done
platform_files=()
if has_platform amp; then platform_files+=(platforms/amp/PLATFORM.md platforms/amp/usage-optimizer.ts); fi
if has_platform codex; then platform_files+=(platforms/codex/PLATFORM.md platforms/codex/AGENTS.kit.md platforms/codex/hooks.fragment.json); fi
for file in ${platform_files[@]+"${platform_files[@]}"}; do
  if [[ ! -f "$SOURCE_DIR/$file" ]]; then
    printf 'Error: required file is missing for the platform list: %s\n' "$SOURCE_DIR/$file" >&2
    exit 1
  fi
done
RETIRED_SKILLS=(codex-delegation)

action() {
  if ((DRY_RUN)); then
    printf 'DRY-RUN:'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

utc_stamp="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$CLAUDE_DIR/backups/usage-optimizer-$utc_stamp"
suffix=1
while [[ -e "$BACKUP_DIR" || -L "$BACKUP_DIR" ]]; do
  printf -v padded '%02d' "$suffix"
  BACKUP_DIR="$CLAUDE_DIR/backups/usage-optimizer-$utc_stamp-$padded"
  ((suffix += 1))
done

backup_file() {
  local source=$1 relative=$2 target="$BACKUP_DIR/$2"
  action mkdir -p "$(dirname "$target")"
  action cp -pP "$source" "$target"
}

retire_old_skills() {
  local retired_name retired_path retired_file relative prefix_path
  for retired_name in "${RETIRED_SKILLS[@]}"; do
    if [[ -d "$SOURCE_DIR/skills/$retired_name" ||
          -d "$SOURCE_DIR/private/skills/$retired_name" ]]; then
      continue
    fi
    retired_path="$CLAUDE_DIR/skills/$retired_name"
    if [[ -e "$retired_path" || -L "$retired_path" ]]; then
      if [[ -d "$retired_path" && ! -L "$retired_path" ]]; then
        while IFS= read -r -d '' retired_file; do
          relative="${retired_file#"$retired_path/"}"
          backup_file "$retired_file" "skills/$retired_name/$relative"
        done < <(find "$retired_path" \( -type f -o -type l \) -print0)
      else
        backup_file "$retired_path" "skills/$retired_name/$(basename "$retired_path")"
      fi
      action rm -rf "$retired_path"
      printf 'Removed retired skill: %s\n' "$retired_path"
    fi

    prefix_path="$PREFIX/skills/$retired_name"
    if [[ -e "$prefix_path" || -L "$prefix_path" ]]; then
      action rm -rf "$prefix_path"
      printf 'Removed retired skill: %s\n' "$prefix_path"
    fi
  done
}

copy_managed_file() {
  local source=$1 destination=$2 backup_relative=$3
  if [[ -e "$destination" || -L "$destination" ]]; then
    if cmp -s "$source" "$destination"; then
      printf 'Identical, skipping: %s\n' "$destination"
      return
    fi
    printf 'Different, backing up and replacing: %s\n' "$destination"
    backup_file "$destination" "$backup_relative"
    action mkdir -p "$(dirname "$destination")"
    action rm -f "$destination"
    action cp -p "$source" "$destination"
  else
    printf 'Absent, installing: %s\n' "$destination"
    action mkdir -p "$(dirname "$destination")"
    action cp -p "$source" "$destination"
  fi
}

printf '\nCopying Claude Usage Optimizer to %s\n' "$PREFIX"
action mkdir -p "$PREFIX"
# install.sh goes too: `lane main` builds the mirror's lean kit branch from the installed kit, and that copy must be
# able to install itself in the mirror's cloud VM.
KIT_ITEMS=(install.sh POLICY.md LANES.md README.md IMPROVING.md improve SETUP_PROMPT.md settings.fragment.json arms.json bin agents mods output-styles findings measure LICENSE)
PRESENT_KIT_ITEMS=()
for item in "${KIT_ITEMS[@]}"; do
  # Only LICENSE may be missing (trees before 2026-11-01.6 have none); any other missing item still fails the copy.
  if [[ "$item" != LICENSE || -e "$SOURCE_DIR/$item" ]]; then
    PRESENT_KIT_ITEMS+=("$item")
    action cp -R "$SOURCE_DIR/$item" "$PREFIX/"
  fi
done
# A checkout where the tests ran holds compiled caches (git-ignored, so never in the bundle); keep them out.
while IFS= read -r -d '' cache; do
  action rm -rf "$PREFIX/$cache"
done < <(cd "$SOURCE_DIR" && find "${PRESENT_KIT_ITEMS[@]}" -name __pycache__ -type d -prune -print0)
while IFS= read -r -d '' source_file; do
  relative="${source_file#"$SOURCE_DIR/bin/"}"
  action chmod 755 "$PREFIX/bin/$relative"
done < <(find "$SOURCE_DIR/bin" -name __pycache__ -prune -o -type f -print0)

# An absolute, symlink-free path for a folder, or nothing; "" never counts as the current folder.
canonical_dir() { [[ -n "${1:-}" ]] && (cd "$1" 2>/dev/null && pwd -P); }

# The git checkout to record, printed (nothing when there is none). A linked worktree (git worktree add) is often
# removed, so its main working tree is recorded instead: the parent of the common git dir, when that folder is a
# working tree of the same repository.
source_checkout() {
  local top git_dir common_dir main_top
  top="$(git -C "$SOURCE_DIR" rev-parse --show-toplevel 2>/dev/null)" || return 0
  top="$(canonical_dir "$top")" || return 0
  [[ "$top" == "$(canonical_dir "$SOURCE_DIR")" ]] || return 0
  git_dir="$(git -C "$SOURCE_DIR" rev-parse --path-format=absolute --git-dir 2>/dev/null)" || git_dir=''
  common_dir="$(git -C "$SOURCE_DIR" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || common_dir=''
  if [[ -z "$common_dir" || "$git_dir" == "$common_dir" ]]; then
    printf '%s\n' "$top"
    return 0
  fi
  # A linked worktree keeps its common dir at <main>/.git. Any other layout is not recorded.
  [[ "$(basename "$common_dir")" == .git ]] || return 0
  main_top="$(canonical_dir "$(dirname "$common_dir")")" || return 0
  [[ "$(canonical_dir "$(git -C "$main_top" rev-parse --show-toplevel 2>/dev/null)")" == "$main_top" ]] || return 0
  [[ "$(canonical_dir "$(git -C "$main_top" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)")" == \
     "$(canonical_dir "$common_dir")" ]] || return 0
  printf '%s\n' "$main_top"
}

# An install from a git checkout records it, so bin/kit-update can fetch the checkout's origin and say when a
# newer release is published. A bundle unpacks without .git (or inside some other repository, such as a home
# folder kept in git), so it records nothing.
SOURCE_CHECKOUT=''
if command -v git >/dev/null 2>&1; then
  SOURCE_CHECKOUT="$(source_checkout)"
  if [[ -n "$SOURCE_CHECKOUT" && "$OS_NAME" == Windows ]]; then SOURCE_CHECKOUT="$(cygpath -m "$SOURCE_CHECKOUT")"; fi
fi
if [[ -n "$SOURCE_CHECKOUT" ]]; then
  if ((DRY_RUN)); then
    printf 'DRY-RUN: record the source checkout %s in %q\n' "$SOURCE_CHECKOUT" "$PREFIX/source.json"
  elif "$PYTHON" - "$PREFIX_NATIVE/source.json" "$SOURCE_CHECKOUT" <<'PY'
import datetime
import json
import os
import sys
import tempfile

path, checkout = sys.argv[1:]
installed_at = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
fd, temporary = tempfile.mkstemp(prefix=".source-", suffix=".tmp", dir=os.path.dirname(path))
try:
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
        json.dump({"checkout": checkout, "installed_at": installed_at}, stream, indent=2)
        stream.write("\n")
    os.replace(temporary, path)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
PY
  then
    printf 'Recorded the source checkout for update checks: %s\n' "$SOURCE_CHECKOUT"
  else
    printf 'Warning: could not record the source checkout in %s; update checks stay off.\n' "$PREFIX/source.json" >&2
  fi
fi

# The list used, so a later run without --platform installs the same platforms. Written only when it changes.
saved_platforms=''
if [[ -f "$PLATFORMS_FILE" ]]; then IFS= read -r saved_platforms < "$PLATFORMS_FILE" || true; fi
if [[ -f "$PLATFORMS_FILE" && "$saved_platforms" == "$PLATFORMS_CSV" ]]; then
  printf 'Platform list already recorded: %s\n' "$PLATFORMS_FILE"
elif ((DRY_RUN)); then
  printf 'DRY-RUN: record the platform list %s in %q\n' "$PLATFORMS_CSV" "$PLATFORMS_FILE"
else
  printf '%s\n' "$PLATFORMS_CSV" > "$PLATFORMS_FILE"
  printf 'Recorded the platform list in %s\n' "$PLATFORMS_FILE"
fi

if has_platform claude-code; then retire_old_skills; fi

PYTHON_TOOLS=(lane lane-stats lane-bench usage-status claude-statusline claude-prompts turn-meter kit-update)
if [[ "$OS_NAME" == Windows ]]; then
  # Windows ignores shebangs, and Git Bash resolves `env python3` to the Store stub. Keep each Python
  # tool as bin/<tool>.py and put wrappers at bin/<tool> (bash) and bin/<tool>.cmd (cmd, PowerShell),
  # so the documented ~/.claude/usage-optimizer/bin/<tool> paths keep working.
  WRAPPER_DIR="$(mktemp -d)"
  python_windows="$(cygpath -w "$PYTHON_NATIVE")"
  for tool in "${PYTHON_TOOLS[@]}"; do
    printf '#!/usr/bin/env bash\nexec %q %q "$@"\n' "$PYTHON" "$PREFIX/bin/$tool.py" > "$WRAPPER_DIR/$tool"
    printf '@"%s" "%s" %%*\r\n' "$python_windows" "$(cygpath -w "$PREFIX/bin/$tool.py")" > "$WRAPPER_DIR/$tool.cmd"
    action mv -f "$PREFIX/bin/$tool" "$PREFIX/bin/$tool.py"
    action cp "$WRAPPER_DIR/$tool" "$PREFIX/bin/$tool"
    action cp "$WRAPPER_DIR/$tool.cmd" "$PREFIX/bin/$tool.cmd"
    action chmod 755 "$PREFIX/bin/$tool"
  done
fi

if has_platform claude-code; then
# The Claude Code steps (agents, skills, mods, the mobile view, CLAUDE.md, settings.json) run only for that platform.
printf '\nInstalling agent files\n'
shopt -s nullglob
agent_files=("$SOURCE_DIR"/agents/*.md)
shopt -u nullglob
for source_file in "${agent_files[@]}"; do
  base="${source_file##*/}"
  copy_managed_file "$source_file" "$CLAUDE_DIR/agents/$base" "agents/$base"
done

printf '\nInstalling skill files\n'
shopt -s nullglob
skill_dirs=("$SOURCE_DIR"/skills/*/ "$SOURCE_DIR"/private/skills/*/)
shopt -u nullglob
for source_skill_dir in "${skill_dirs[@]}"; do
  skill_name="${source_skill_dir%/}"
  skill_name="${skill_name##*/}"
  while IFS= read -r -d '' source_file; do
    relative="${source_file#"$source_skill_dir"}"
    copy_managed_file "$source_file" "$CLAUDE_DIR/skills/$skill_name/$relative" "skills/$skill_name/$relative"
    copy_managed_file "$source_file" "$PREFIX/skills/$skill_name/$relative" "skills/$skill_name/$relative"
  done < <(find "$source_skill_dir" -type f -print0)
done

prune_stale_skill_files() {
  local destination_root=$1 source_skill_dir=$2 skill_name=$3 folder_name=$4 label=$5 save_backup=$6
  local destination_notes="$destination_root/skills/$skill_name/$folder_name"
  local stale_file relative source_counterpart
  [[ -d "$destination_notes" ]] || return 0
  while IFS= read -r -d '' stale_file; do
    relative="${stale_file#"$destination_notes/"}"
    source_counterpart="$source_skill_dir/$folder_name/$relative"
    if [[ -e "$source_counterpart" || -L "$source_counterpart" ]]; then
      continue
    fi
    if [[ "$save_backup" == 1 ]]; then
      backup_file "$stale_file" "skills/$skill_name/$folder_name/$relative"
    fi
    action rm -f "$stale_file"
    printf 'Removed stale %s: %s\n' "$label" "$stale_file"
  done < <(find "$destination_notes" \( -type f -o -type l \) -print0)
}

for source_skill_dir in "${skill_dirs[@]}"; do
  skill_name="${source_skill_dir%/}"
  skill_name="${skill_name##*/}"
  prune_stale_skill_files "$CLAUDE_DIR" "$source_skill_dir" "$skill_name" notes note 1
  prune_stale_skill_files "$PREFIX" "$source_skill_dir" "$skill_name" notes note 0
  prune_stale_skill_files "$CLAUDE_DIR" "$source_skill_dir" "$skill_name" records record 1
  prune_stale_skill_files "$PREFIX" "$source_skill_dir" "$skill_name" records record 0
done

KIT_VERSION="$(sed -n 's/^Claude Usage Optimizer version: \([^ ]*\)\..*/\1/p' "$SOURCE_DIR/POLICY.md" | head -n 1)"
MOD_DIR="$CLAUDE_DIR/skills/mobile-view"
printf '\nInstalling mods\n'
shopt -s nullglob
mod_dirs=("$SOURCE_DIR"/mods/*/)
shopt -u nullglob
for source_mod_dir in "${mod_dirs[@]}"; do
  mod_dir="${source_mod_dir%/}"
  mod_name="${mod_dir##*/}"
  if [[ "$mod_name" == mobile-view && "$VIEW" != apply ]]; then
    continue
  fi
  printf 'Installing mod %s\n' "$mod_name"
  # A plugin folder under ~/.claude/skills loads by its name (mobile-view as mobile-view@skills-dir). Its
  # tests stay in the kit, and the engine's generated typings and tsconfig are never copied.
  while IFS= read -r -d '' source_file; do
    relative="${source_file#"$mod_dir/"}"
    copy_managed_file "$source_file" "$CLAUDE_DIR/skills/$mod_name/$relative" "skills/$mod_name/$relative"
  done < <(find "$mod_dir" \( -path "$mod_dir/tests" -o -path "$mod_dir/.claude-plugin/types" -o -name node_modules \) -prune \
             -o -type f ! -name tsconfig.json -print0)
done
if [[ "$VIEW" == apply ]]; then
  printf '\nInstalling the mobile view (mod and output style)\n'
  # Where the mod finds Python and bin/claude-prompts, the transcript indexer behind the question list (>).
  if [[ "$OS_NAME" == Windows ]]; then
    prompts_script="$PREFIX_NATIVE/bin/claude-prompts.py"
  else
    prompts_script="$PREFIX_NATIVE/bin/claude-prompts"
  fi
  PATHS_DIR="$(mktemp -d)"
  "$PYTHON" - "$PATHS_DIR/install-paths.json" "$PYTHON_NATIVE" "$prompts_script" "$PREFIX_NATIVE" "$KIT_VERSION" <<'PY'
import json
import sys

path, python, prompts_script, prefix, version = sys.argv[1:]
with open(path, "w", encoding="utf-8", newline="\n") as stream:
    json.dump({"python": python, "promptsScript": prompts_script, "prefix": prefix, "kitVersion": version},
              stream, indent=2)
    stream.write("\n")
PY
  copy_managed_file "$PATHS_DIR/install-paths.json" "$MOD_DIR/install-paths.json" "skills/mobile-view/install-paths.json"
  rm -rf "$PATHS_DIR"
  copy_managed_file "$SOURCE_DIR/output-styles/Mobile.md" "$CLAUDE_DIR/output-styles/Mobile.md" "output-styles/Mobile.md"
else
  printf '\nMobile view skipped (--no-view)\n'
fi

printf '\nUpdating CLAUDE.md\n'
if [[ ! -e "$CLAUDE_MD" && ! -L "$CLAUDE_MD" ]]; then
  action mkdir -p "$CLAUDE_DIR"
  if ((DRY_RUN)); then
    printf 'DRY-RUN: create empty %q\n' "$CLAUDE_MD"
  else
    : > "$CLAUDE_MD"
  fi
fi
if { [[ -e "$CLAUDE_MD" || -L "$CLAUDE_MD" ]] && [[ ! -f "$CLAUDE_MD" ]]; }; then
  printf 'Error: %s is not a regular file.\n' "$CLAUDE_MD" >&2
  exit 1
fi
OLD_IMPORT='@~/.claude/kit/POLICY.md'
OLD_HEADING='# Usage policy (shared across machines; edit the kit, not this line)'
NEW_IMPORT='@~/.claude/usage-optimizer/POLICY.md'
NEW_HEADING='# Claude Usage Optimizer policy (shared across machines; edit its source, not this line)'
import_migrated=0
if [[ -f "$CLAUDE_MD" ]] && grep -Fqx "$OLD_IMPORT" "$CLAUDE_MD"; then
  # Installed under the old name, claude-kit: re-point the import in place, keeping its position.
  backup_file "$CLAUDE_MD" 'CLAUDE.md'
  import_migrated=1
  if ((DRY_RUN)); then
    printf 'DRY-RUN: replace %s with %s in %q\n' "$OLD_IMPORT" "$NEW_IMPORT" "$CLAUDE_MD"
  else
    "$PYTHON" - "$CLAUDE_MD" "$OLD_IMPORT" "$NEW_IMPORT" "$OLD_HEADING" "$NEW_HEADING" <<'PY'
import sys
path, old_import, new_import, old_heading, new_heading = sys.argv[1:]
with open(path, encoding="utf-8", newline="") as stream:
    lines = stream.read().splitlines(keepends=True)
swap = {old_import: new_import, old_heading: new_heading}
out = []
for line in lines:
    body = line.rstrip("\r\n")
    out.append(swap[body] + line[len(body):] if body in swap else line)
with open(path, "w", encoding="utf-8", newline="") as stream:
    stream.write("".join(out))
PY
    printf 'Re-pointed the policy import from claude-kit to Claude Usage Optimizer.\n'
  fi
fi
if ((import_migrated)) || { [[ -f "$CLAUDE_MD" ]] && grep -Fqx "$NEW_IMPORT" "$CLAUDE_MD"; }; then
  printf 'Usage policy import already present; skipping.\n'
else
  backup_file "$CLAUDE_MD" 'CLAUDE.md'
  if ((DRY_RUN)); then
    printf 'DRY-RUN: append policy heading and @~/.claude/usage-optimizer/POLICY.md to %q\n' "$CLAUDE_MD"
  else
    printf '\n# Claude Usage Optimizer policy (shared across machines; edit its source, not this line)\n@~/.claude/usage-optimizer/POLICY.md\n' >> "$CLAUDE_MD"
  fi
fi

printf '\nMerging settings.json\n'
if [[ ! -e "$SETTINGS_FILE" && ! -L "$SETTINGS_FILE" ]]; then
  action mkdir -p "$CLAUDE_DIR"
  if ((DRY_RUN)); then
    printf 'DRY-RUN: create %q containing {}\n' "$SETTINGS_FILE"
  else
    printf '{}\n' > "$SETTINGS_FILE"
  fi
fi
# What the view keys were last set to, so a later run can tell a value the person changed by hand.
VIEW_STATE="$PREFIX/view-settings.applied.json"
# One merge program serves the real run and the dry run, so the preview shows exactly what changes.
run_settings_merge() {
  "$PYTHON" - "$@" <<'PY'
import copy
import json
import os
import re
import sys

(fragment_path, settings_path, prefix, output_path, os_name, python_native, mode,
 view, reset_view, state_path) = sys.argv[1:]
preview = mode == "preview"

def replace_prefix(value):
    if isinstance(value, str):
        return value.replace("__PREFIX__", prefix)
    if isinstance(value, list):
        return [replace_prefix(item) for item in value]
    if isinstance(value, dict):
        return {key: replace_prefix(item) for key, item in value.items()}
    return value

with open(fragment_path, encoding="utf-8") as stream:
    fragment = json.load(stream)
with open(settings_path, encoding="utf-8") as stream:
    settings = json.load(stream)
if not isinstance(fragment, dict) or not isinstance(settings, dict):
    raise ValueError("settings and settings fragment must be JSON objects")
added = []
changed = []

for key, value in replace_prefix(fragment.get("set_if_absent", {})).items():
    if key not in settings:
        settings[key] = copy.deepcopy(value)
        added.append("%s = %s" % (key, json.dumps(value)))

# A kit default the person still has at an old value moves to the new one. Any other value, and an
# absent key (set_if_absent's job), is left alone.
for key, spec in fragment.get("replace_kit_defaults", {}).items():
    if key in settings and settings[key] in spec["previous"] and settings[key] != spec["value"]:
        changed.append("%s: %s -> %s" % (key, json.dumps(settings[key]), json.dumps(spec["value"])))
        settings[key] = copy.deepcopy(spec["value"])

# The main session's model and effort come from arms.json explore.main_session (beside the fragment), so a
# switch is one line there. Absent: set. At a previous kit value: moved, as replace_kit_defaults does. Any
# other value is the person's and is kept.
main_session = None
try:
    with open(os.path.join(os.path.dirname(fragment_path), "arms.json"), encoding="utf-8") as stream:
        main_session = json.load(stream).get("explore", {}).get("main_session")
except (OSError, ValueError, AttributeError):
    main_session = None
if not isinstance(main_session, dict) or not main_session.get("model") or not main_session.get("effort"):
    print("Warning: arms.json has no explore.main_session; using model opus[1m] and effortLevel xhigh.",
          file=sys.stderr)
    main_session = {"model": "opus[1m]", "effort": "xhigh"}
for key, value_key, previous_key in (("model", "model", "previous_models"),
                                     ("effortLevel", "effort", "previous_efforts")):
    value = main_session[value_key]
    previous = main_session.get(previous_key) or []
    if key not in settings:
        settings[key] = value
        added.append("%s = %s" % (key, json.dumps(value)))
    elif settings[key] in previous and settings[key] != value:
        changed.append("%s: %s -> %s" % (key, json.dumps(settings[key]), json.dumps(value)))
        settings[key] = value

env_updates = replace_prefix(fragment.get("env_if_absent", {}))
if env_updates:
    if "env" not in settings:
        settings["env"] = {}
    if not isinstance(settings["env"], dict):
        raise ValueError("settings.env must be a JSON object")
    for key, value in env_updates.items():
        if key not in settings["env"]:
            settings["env"][key] = copy.deepcopy(value)
            added.append("env.%s = %s" % (key, json.dumps(value)))

env = settings.get("env")
if isinstance(env, dict) and "CLAUDE_KIT_TZ" in env:
    # The old name of USAGE_OPTIMIZER_TZ.
    value = env.pop("CLAUDE_KIT_TZ")
    env.setdefault("USAGE_OPTIMIZER_TZ", value)
    added.append("env.USAGE_OPTIMIZER_TZ = %s (renamed from CLAUDE_KIT_TZ)" % json.dumps(env["USAGE_OPTIMIZER_TZ"]))

if "statusLine_if_absent" in fragment:
    def is_kit_statusline(value):
        return isinstance(value, dict) and prefix + "/bin/claude-statusline" in str(value.get("command", ""))

    if settings.get("statusLine") is None:
        status_line = replace_prefix(fragment["statusLine_if_absent"])
        if os_name == "Windows":
            # Windows cannot start the script from its shebang. Unquoted paths run unchanged in
            # bash, cmd and PowerShell, whichever shell Claude Code uses for the statusline.
            script = prefix + "/bin/claude-statusline.py"
            if " " in python_native or " " in script:
                raise ValueError("on Windows the Python and install paths must not contain spaces: %s %s" % (python_native, script))
            status_line["command"] = "%s %s" % (python_native, script)
        settings["statusLine"] = status_line
        added.append("statusLine.command = %s" % json.dumps(status_line.get("command")))
    elif isinstance(settings["statusLine"], dict) and re.search(
            r"/\.claude/kit/bin/claude-statusline", str(settings["statusLine"].get("command", ""))):
        # Installed under the old name, claude-kit: point the statusline at the new install.
        command = re.sub(r"\S*/\.claude/kit/bin/claude-statusline",
                         lambda _: prefix + "/bin/claude-statusline", settings["statusLine"]["command"])
        settings["statusLine"]["command"] = command
        added.append("statusLine.command = %s (moved from claude-kit)" % json.dumps(command))
    elif is_kit_statusline(settings["statusLine"]):
        pass  # The kit's own statusline: its refreshInterval is topped up below, and nothing is warned about.
    else:
        print("Warning: an existing statusLine %s preserved. To switch, remove or change statusLine in ~/.claude/settings.json and rerun install.sh." % ("will be" if preview else "was"), file=sys.stderr)
    # The kit's statusline re-runs every refreshInterval seconds, so the turn's ETA counts down. A value already set is kept.
    refresh = fragment["statusLine_if_absent"].get("refreshInterval")
    if refresh is not None and is_kit_statusline(settings.get("statusLine")) and "refreshInterval" not in settings["statusLine"]:
        settings["statusLine"]["refreshInterval"] = refresh
        changed.append("statusLine.refreshInterval: (absent) -> %s" % json.dumps(refresh))

def has_turn_meter_command(value):
    if isinstance(value, dict):
        command = value.get("command")
        if isinstance(command, str) and "turn-meter" in command:
            return True
        return any(has_turn_meter_command(item) for item in value.values())
    if isinstance(value, list):
        return any(has_turn_meter_command(item) for item in value)
    return False

hook_updates = replace_prefix(fragment.get("hooks_if_absent", {}))
if hook_updates:
    if "hooks" not in settings:
        settings["hooks"] = {}
    if not isinstance(settings["hooks"], dict):
        raise ValueError("settings.hooks must be a JSON object")
    for event, command in hook_updates.items():
        if os_name == "Windows":
            script = prefix + "/bin/turn-meter.py"
            if " " in python_native or " " in script:
                raise ValueError("on Windows the Python and install paths must not contain spaces: %s %s" % (python_native, script))
            command = "%s %s hook" % (python_native, script)
        existing = settings["hooks"].get(event)
        if has_turn_meter_command(existing):
            continue
        if existing is None:
            existing = []
            settings["hooks"][event] = existing
        if not isinstance(existing, list):
            raise ValueError("settings.hooks.%s must be a JSON array" % event)
        entry = {"hooks": [{"type": "command", "command": command, "timeout": 5}]}
        existing.append(entry)
        added.append("hooks.%s += %s" % (event, json.dumps(entry)))

def has_command_with(value, tool, args):
    if isinstance(value, dict):
        command = value.get("command")
        if isinstance(command, str) and tool in command and args in command:
            return True
        return any(has_command_with(item, tool, args) for item in value.values())
    if isinstance(value, list):
        return any(has_command_with(item, tool, args) for item in value)
    return False

command_hooks = fragment.get("command_hooks_if_absent", [])
if command_hooks:
    if "hooks" not in settings:
        settings["hooks"] = {}
    if not isinstance(settings["hooks"], dict):
        raise ValueError("settings.hooks must be a JSON object")
for spec in command_hooks:
    event, tool, args = spec["event"], spec["tool"], spec["args"]
    if os_name == "Windows":
        script = prefix + "/bin/" + tool + ".py"
        if " " in python_native or " " in script:
            raise ValueError("on Windows the Python and install paths must not contain spaces: %s %s" % (python_native, script))
        command = "%s %s %s" % (python_native, script, args)
    else:
        command = "%s/bin/%s %s" % (prefix, tool, args)
    existing = settings["hooks"].get(event)
    if has_command_with(existing, tool, args):
        continue
    if existing is None:
        existing = []
        settings["hooks"][event] = existing
    if not isinstance(existing, list):
        raise ValueError("settings.hooks.%s must be a JSON array" % event)
    entry = {}
    if "matcher" in spec:
        entry["matcher"] = spec["matcher"]
    entry["hooks"] = [{"type": "command", "command": command, "timeout": spec["timeout"]}]
    existing.append(entry)
    added.append("hooks.%s += %s" % (event, json.dumps(entry)))

# The view keys are overwritten, not only set when absent: the kit's view is the point of installing
# it. A value the person changed by hand after an earlier install (it differs from what the kit
# recorded setting) is kept, unless --reset-view.
applied = {}
if view == "apply":
    try:
        with open(state_path, encoding="utf-8") as stream:
            recorded = json.load(stream)
        if not isinstance(recorded, dict):
            recorded = {}
    except (OSError, ValueError):
        recorded = {}
    missing = object()
    for key, value in fragment.get("view_overwrite", {}).items():
        current = settings.get(key, missing)
        if current == value:
            applied[key] = value
        elif current is missing:
            settings[key] = copy.deepcopy(value)
            applied[key] = value
            changed.append("%s: (absent) -> %s" % (key, json.dumps(value)))
        elif key in recorded and recorded[key] != current and reset_view != "1":
            print("Warning: %s = %s %s kept; you changed it after an earlier install. Rerun with --reset-view to set %s." % (
                key, json.dumps(current), "will be" if preview else "was", json.dumps(value)), file=sys.stderr)
        else:
            settings[key] = copy.deepcopy(value)
            applied[key] = value
            changed.append("%s: %s -> %s" % (key, json.dumps(current), json.dumps(value)))

if preview:
    for line in added or ["nothing; every key is already set"]:
        print("DRY-RUN: settings.json would gain " + line)
    for line in changed:
        print("DRY-RUN: settings.json would change " + line)
else:
    with open(output_path, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(settings, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    # Hooks run on every prompt, so say when the install adds one; other absent keys stay quiet.
    for line in added:
        if line.startswith("hooks."):
            print("settings.json: " + line)
    for line in changed:
        print("settings.json: " + line)
    if view == "apply":
        with open(state_path, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(applied, stream, indent=2)
            stream.write("\n")
PY
}
if ((DRY_RUN)); then
  if [[ -f "$SETTINGS_FILE" ]]; then
    action cp -pP "$SETTINGS_FILE" "$BACKUP_DIR/settings.json"
    preview_source="$SETTINGS_FILE"
  else
    printf 'DRY-RUN: back up the new empty settings.json to %q/settings.json\n' "$BACKUP_DIR"
    preview_source="$(mktemp)"
    printf '{}\n' > "$preview_source"
  fi
  printf 'DRY-RUN: merge settings.fragment.json into %q (absent keys set; view keys overwritten)\n' "$SETTINGS_FILE"
  printf 'DRY-RUN: write settings.json with indent 2 and re-read to validate\n'
  if ! run_settings_merge "$SOURCE_DIR/settings.fragment.json" "$preview_source" "$PREFIX_NATIVE" - \
       "$OS_NAME" "$PYTHON_NATIVE" preview "$VIEW" "$RESET_VIEW" "$VIEW_STATE"; then
    printf 'Warning: dry-run could not inspect settings merge.\n'
  fi
  if [[ "$preview_source" != "$SETTINGS_FILE" ]]; then rm -f "$preview_source"; fi
else
  backup_file "$SETTINGS_FILE" 'settings.json'
  settings_tmp="$SETTINGS_FILE.usage-optimizer-tmp.$$"
  merge_status=0
  if run_settings_merge "$SOURCE_DIR/settings.fragment.json" "$SETTINGS_FILE" "$PREFIX_NATIVE" "$settings_tmp" \
       "$OS_NAME" "$PYTHON_NATIVE" write "$VIEW" "$RESET_VIEW" "$VIEW_STATE"; then
    if mv -f "$settings_tmp" "$SETTINGS_FILE" && "$PYTHON" -c 'import json,sys; value=json.load(open(sys.argv[1], encoding="utf-8")); sys.exit(0 if isinstance(value, dict) else 1)' "$SETTINGS_FILE"; then
      printf 'settings.json merged and validated.\n'
    else
      merge_status=1
    fi
  else
    merge_status=1
  fi
  if ((merge_status)); then
    rm -f "$settings_tmp"
    rm -f "$SETTINGS_FILE"
    cp -pP "$BACKUP_DIR/settings.json" "$SETTINGS_FILE"
    printf 'Error: settings merge or validation failed; restored the backup.\n' >&2
    exit 1
  fi
fi

else
  printf '\nClaude Code is not in the platform list; its steps are skipped.\n'
fi

if has_platform amp; then
  printf '\nInstalling the Amp adapter\n'
  AMP_DIR="$HOME/.config/amp"
  AMP_AGENTS="$AMP_DIR/AGENTS.md"
  AMP_PLUGINS="$AMP_DIR/plugins"
  copy_managed_file "$SOURCE_DIR/platforms/amp/PLATFORM.md" "$PREFIX/platforms/amp/PLATFORM.md" \
    "platforms/amp/PLATFORM.md"
  copy_managed_file "$SOURCE_DIR/platforms/amp/usage-optimizer.ts" "$AMP_PLUGINS/usage-optimizer.ts" \
    "amp/plugins/usage-optimizer.ts"
  # The plugin finds the interpreter and the kit folder in this file beside it. json.dump writes it, so any path is escaped.
  PATHS_DIR="$(mktemp -d)"
  "$PYTHON" - "$PATHS_DIR/usage-optimizer.paths.json" "$PYTHON_NATIVE" "$PREFIX_NATIVE" <<'PY'
import json
import sys

path, python, prefix = sys.argv[1:]
with open(path, "w", encoding="utf-8", newline="\n") as stream:
    json.dump({"python": python, "prefix": prefix}, stream, indent=2)
    stream.write("\n")
PY
  copy_managed_file "$PATHS_DIR/usage-optimizer.paths.json" "$AMP_PLUGINS/usage-optimizer.paths.json" \
    "amp/plugins/usage-optimizer.paths.json"
  rm -rf "$PATHS_DIR"

  printf '\nUpdating the Amp AGENTS.md\n'
  if [[ -e "$AMP_AGENTS" || -L "$AMP_AGENTS" ]] && [[ ! -f "$AMP_AGENTS" ]]; then
    printf 'Error: %s is not a regular file.\n' "$AMP_AGENTS" >&2
    exit 1
  fi
  AMP_HEADING='# Claude Usage Optimizer on Amp (shared across machines; edit its source, not this line)'
  AMP_IMPORTS=('@~/.claude/usage-optimizer/platforms/amp/PLATFORM.md' '@~/.claude/usage-optimizer/POLICY.md')
  amp_missing=()
  for line in "${AMP_IMPORTS[@]}"; do
    if [[ ! -f "$AMP_AGENTS" ]] || ! grep -Fqx "$line" "$AMP_AGENTS"; then amp_missing+=("$line"); fi
  done
  if ((${#amp_missing[@]} == 0)); then
    printf 'Amp policy imports already present; skipping.\n'
  else
    if [[ -f "$AMP_AGENTS" ]]; then backup_file "$AMP_AGENTS" 'amp/AGENTS.md'; fi
    if ((DRY_RUN)); then
      printf 'DRY-RUN: append the Amp heading and %s to %q\n' "${amp_missing[*]}" "$AMP_AGENTS"
    else
      if [[ ! -d "$AMP_DIR" ]]; then mkdir -p "$AMP_DIR"; fi
      {
        if [[ -s "$AMP_AGENTS" ]]; then printf '\n'; fi
        printf '%s\n' "$AMP_HEADING"
        printf '%s\n' "${amp_missing[@]}"
      } >> "$AMP_AGENTS"
      printf 'Added the Amp policy imports to %s\n' "$AMP_AGENTS"
    fi
  fi
fi

if has_platform codex; then
  printf '\nInstalling the Codex adapter\n'
  # POLICY.md points Codex sessions at these notes; the AGENTS.md block below carries the same text.
  copy_managed_file "$SOURCE_DIR/platforms/codex/PLATFORM.md" "$PREFIX/platforms/codex/PLATFORM.md" \
    "platforms/codex/PLATFORM.md"
  CODEX_DIR="${CODEX_HOME:-$HOME/.codex}"
  if [[ "$OS_NAME" == Windows ]]; then CODEX_DIR="$(cygpath -u "$CODEX_DIR")"; fi
  CODEX_AGENTS="$CODEX_DIR/AGENTS.md"
  CODEX_HOOKS="$CODEX_DIR/hooks.json"
  if ((DRY_RUN)); then CODEX_MODE=preview; else CODEX_MODE=write; fi
  # Both files are merged into a scratch folder first, so a bad input changes nothing under CODEX_HOME.
  CODEX_MERGED="$(mktemp -d)"
  if ! "$PYTHON" - "$SOURCE_DIR/platforms/codex/AGENTS.kit.md" "$CODEX_AGENTS" "$CODEX_MERGED/AGENTS.md" "$CODEX_MODE" <<'PY'
import os
import sys

kit_path, path, out_path, mode = sys.argv[1:]
prefix = "DRY-RUN: " if mode == "preview" else ""
start = "<!-- usage-optimizer:start -->"
end = "<!-- usage-optimizer:end -->"
with open(kit_path, encoding="utf-8", newline="") as stream:
    kit = stream.read().replace("\r\n", "\n").rstrip("\n")
block = start + "\n" + kit + "\n" + end + "\n"
text = ""
if os.path.exists(path):
    with open(path, encoding="utf-8", newline="") as stream:
        text = stream.read()
lines = text.splitlines(keepends=True)
starts = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == start]
ends = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == end]
if len(starts) != len(ends) or len(starts) > 1 or (starts and ends[0] < starts[0]):
    sys.stderr.write("Error: %s has a usage-optimizer marker that is unmatched or repeated; fix it and rerun.\n" % path)
    sys.exit(1)
if starts:
    new_text = "".join(lines[:starts[0]]) + block + "".join(lines[ends[0] + 1:])
else:
    separator = "" if not text or text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    new_text = text + separator + block
if new_text == text:
    print("Codex AGENTS.md already has the current usage-optimizer block; skipping.")
    sys.exit(0)
size = len(new_text.encode("utf-8"))
with open(out_path, "w", encoding="utf-8", newline="\n") as stream:
    stream.write(new_text)
print(prefix + "Codex AGENTS.md: %s the usage-optimizer block (the file is then %d bytes)"
      % ("replace" if starts else "add", size))
if size > 32768:
    sys.stderr.write("Warning: %s would be %d bytes; Codex reads at most 32 KiB of AGENTS.md instructions in total.\n"
                     % (path, size))
PY
  then
    rm -rf "$CODEX_MERGED"
    exit 1
  fi
  if ! "$PYTHON" - "$SOURCE_DIR/platforms/codex/hooks.fragment.json" "$CODEX_HOOKS" "$CODEX_MERGED/hooks.json" \
       "$CODEX_MODE" "$OS_NAME" "$PYTHON_NATIVE" "$PREFIX_NATIVE" <<'PY'
import copy
import json
import os
import re
import sys

fragment_path, path, out_path, mode, os_name, python_native, prefix = sys.argv[1:]
label = "DRY-RUN: Codex hooks.json would gain " if mode == "preview" else "Codex hooks.json gains "

def fill(value):
    if isinstance(value, str):
        return value.replace("__PYTHON__", python_native).replace("__PREFIX__", prefix)
    if isinstance(value, list):
        return [fill(item) for item in value]
    if isinstance(value, dict):
        return {key: fill(item) for key, item in value.items()}
    return value

if os_name == "Windows" and (" " in python_native or " " in prefix):
    sys.stderr.write("Error: on Windows the Python and install paths must not contain spaces: %s %s\n"
                     % (python_native, prefix))
    sys.exit(1)
with open(fragment_path, encoding="utf-8") as stream:
    wanted = fill(json.load(stream)["hooks"])
# Each handler's Windows command is under "windowsCommand" in the fragment. It is never written: on Windows it becomes
# "command" (the script run with the Python that installed the kit), elsewhere "command" stays the bin/ wrapper.
for groups in wanted.values():
    for group in groups:
        for handler in group["hooks"]:
            windows_command = handler.pop("windowsCommand")
            if os_name == "Windows":
                handler["command"] = windows_command

data = {}
if os.path.exists(path):
    try:
        with open(path, encoding="utf-8") as stream:
            data = json.load(stream)
    except ValueError as error:
        sys.stderr.write("Error: %s is not valid JSON (%s); fix it or move it aside, then rerun.\n" % (path, error))
        sys.exit(1)
if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict):
    sys.stderr.write("Error: %s must hold a JSON object, and its hooks must be an object.\n" % path)
    sys.exit(1)
hooks = data.setdefault("hooks", {})

def turn_args(command):
    # The arguments after turn-meter (or turn-meter.py): "hook --platform codex" or "compact-gate --platform codex".
    match = re.search(r"turn-meter(?:\.py)?\s+(.*)$", command)
    return match.group(1).strip() if match else None

def has_turn_hook(value, args):
    if isinstance(value, dict):
        text = value.get("command")
        if isinstance(text, str) and turn_args(text) == args:
            return True
        return any(has_turn_hook(item, args) for item in value.values())
    if isinstance(value, list):
        return any(has_turn_hook(item, args) for item in value)
    return False

messages = []
for event, groups in wanted.items():
    existing = hooks.get(event)
    if existing is not None and not isinstance(existing, list):
        sys.stderr.write("Error: %s: hooks.%s must be a JSON array.\n" % (path, event))
        sys.exit(1)
    for group in groups:
        args = turn_args(group["hooks"][0]["command"])
        if has_turn_hook(existing or [], args):
            continue
        if existing is None:
            existing = hooks[event] = []
        existing.append(copy.deepcopy(group))
        messages.append("%s %s" % (event, json.dumps(group)))
if not messages:
    print("Codex hooks.json already has the turn-meter hooks; skipping.")
    sys.exit(0)
with open(out_path, "w", encoding="utf-8", newline="\n") as stream:
    json.dump(data, stream, indent=2, ensure_ascii=False)
    stream.write("\n")
for message in messages:
    print(label + message)
PY
  then
    rm -rf "$CODEX_MERGED"
    exit 1
  fi
  # Both merges have succeeded, so nothing under CODEX_HOME changes unless every input was valid.
  if [[ -f "$CODEX_MERGED/AGENTS.md" ]]; then
    if [[ ! -d "$CODEX_DIR" ]]; then action mkdir -p "$CODEX_DIR"; fi
    if [[ -f "$CODEX_AGENTS" ]]; then backup_file "$CODEX_AGENTS" 'codex/AGENTS.md'; fi
    action cp "$CODEX_MERGED/AGENTS.md" "$CODEX_AGENTS"
  fi
  if [[ -e "$CODEX_DIR/AGENTS.override.md" ]]; then
    printf 'Warning: %s exists; Codex reads it instead of AGENTS.md, so the usage-optimizer block is not used until you remove it or copy the block into it.\n' \
      "$CODEX_DIR/AGENTS.override.md" >&2
  fi
  if [[ -f "$CODEX_MERGED/hooks.json" ]]; then
    hooks_existed=0
    if [[ -f "$CODEX_HOOKS" ]]; then
      hooks_existed=1
      backup_file "$CODEX_HOOKS" 'codex/hooks.json'
    fi
    if ((DRY_RUN)); then
      printf 'DRY-RUN: write %q and read it back to validate it\n' "$CODEX_HOOKS"
    else
      if [[ ! -d "$CODEX_DIR" ]]; then mkdir -p "$CODEX_DIR"; fi
      hooks_tmp="$CODEX_HOOKS.usage-optimizer-tmp.$$"
      cp "$CODEX_MERGED/hooks.json" "$hooks_tmp"
      if mv -f "$hooks_tmp" "$CODEX_HOOKS" && "$PYTHON" -c 'import json,sys; value=json.load(open(sys.argv[1], encoding="utf-8")); sys.exit(0 if isinstance(value, dict) else 1)' "$CODEX_HOOKS"; then
        printf 'Codex hooks.json merged and validated.\n'
      else
        rm -f "$hooks_tmp"
        if ((hooks_existed)); then
          cp -pP "$BACKUP_DIR/codex/hooks.json" "$CODEX_HOOKS"
        else
          rm -f "$CODEX_HOOKS"
        fi
        rm -rf "$CODEX_MERGED"
        printf 'Error: Codex hooks.json merge or validation failed; restored the previous file.\n' >&2
        exit 1
      fi
    fi
  fi
  rm -rf "$CODEX_MERGED"
fi

printf '\nInstalling tools on PATH\n'
LOCAL_BIN="$HOME/.local/bin"
action mkdir -p "$LOCAL_BIN"
if [[ "$OS_NAME" == Windows ]]; then
  # Git Bash symlinks are copies unless Developer Mode is on, so ~/.local/bin gets the same wrappers
  # as the install's bin directory (generated above).
  for tool in "${PYTHON_TOOLS[@]}"; do
    copy_managed_file "$WRAPPER_DIR/$tool" "$LOCAL_BIN/$tool" "local-bin/$tool"
    copy_managed_file "$WRAPPER_DIR/$tool.cmd" "$LOCAL_BIN/$tool.cmd" "local-bin/$tool.cmd"
  done
  rm -rf "$WRAPPER_DIR"
else
  for tool in "${PYTHON_TOOLS[@]}"; do
    link="$LOCAL_BIN/$tool"
    target="$PREFIX/bin/$tool"
    if [[ -L "$link" && "$(readlink "$link")" == "$target" ]]; then
      printf 'Symlink already correct: %s\n' "$link"
    else
      action ln -sfn "$target" "$link"
    fi
  done
fi
case ":${PATH:-}:" in
  *":$LOCAL_BIN:"*) ;;
  *) printf 'Warning: %s is not on PATH. Add it to your shell startup file.\n' "$LOCAL_BIN" >&2 ;;
esac

OLD_PREFIX="$HOME/.claude/kit"
if [[ "$OLD_PREFIX" != "$PREFIX" && -f "$OLD_PREFIX/POLICY.md" ]] && grep -q '^Kit version:' "$OLD_PREFIX/POLICY.md"; then
  # The import, statusline and PATH tools point at the new install by now, so the old one is unused.
  printf '\nRetiring the old claude-kit install\n'
  action mkdir -p "$BACKUP_DIR"
  action mv "$OLD_PREFIX" "$BACKUP_DIR/claude-kit-install"
fi
if [[ -d "$HOME/claude-kit" && ! -e "$HOME/claude-kit/.git" ]]; then
  printf 'Note: %s is the old claude-kit source folder; nothing uses it now, so it can be deleted.\n' "$HOME/claude-kit"
fi

printf '\nPreparing ~/.config/lanes\n'
LANES_DIR="$HOME/.config/lanes"
# Git Bash cannot set Unix modes; NTFS ACLs under the profile govern access on Windows.
if [[ "$OS_NAME" == Windows ]]; then
  if [[ ! -d "$LANES_DIR" ]]; then
    action mkdir -p "$LANES_DIR"
  fi
elif [[ ! -d "$LANES_DIR" ]]; then
  if ((DRY_RUN)); then
    printf 'DRY-RUN: mkdir -m 700 -p %q\n' "$LANES_DIR"
  else
    mkdir -p -m 700 "$LANES_DIR"
  fi
else
  action chmod 700 "$LANES_DIR"
fi
LANES_BIN="$LANES_DIR/bin"
# Empty on purpose: operators drop a newer codex (or other lane CLI) here; install never writes into it.
if [[ "$OS_NAME" == Windows ]]; then
  if [[ ! -d "$LANES_BIN" ]]; then
    action mkdir -p "$LANES_BIN"
  fi
elif [[ ! -d "$LANES_BIN" ]]; then
  if ((DRY_RUN)); then
    printf 'DRY-RUN: mkdir -m 700 -p %q\n' "$LANES_BIN"
  else
    mkdir -p -m 700 "$LANES_BIN"
  fi
else
  action chmod 700 "$LANES_BIN"
fi
mask_file="$LANES_DIR/mask.local"
if [[ ! -e "$mask_file" ]]; then
  if ((DRY_RUN)); then
    printf 'DRY-RUN: create %q with commented mask header\n' "$mask_file"
  else
    printf '# extra absolute paths to hide from masked workers, one per line, e.g. /etc/myapp or ~/secrets-backup\n' > "$mask_file"
    if [[ "$OS_NAME" != Windows ]]; then chmod 600 "$mask_file"; fi
  fi
fi

printf '\nFinal checklist\n'
if ((${#CLI_MISSING[@]})); then
  printf 'Missing CLIs: %s\n' "${CLI_MISSING[*]}"
else
  printf 'Missing CLIs: none\n'
fi
printf 'Logins: codex login; agy login.\n'
if [[ "$OS_NAME" == Windows ]]; then
  printf 'Windows has no credential mask: lane refuses glm unless you pass --no-mask.\n'
fi
printf 'Account switches: ChatGPT data controls off; Antigravity training off; Claude model-training setting off; Claude extra usage: check it (the policy assumes it is off, so there is no reserve).\n'
printf 'Verify: ~/.claude/usage-optimizer/bin/usage-status --no-agy\n'
printf 'Verify: ~/.claude/usage-optimizer/bin/lane luna -C <dir> -b <brief> -e medium --dry-run\n'
if has_platform claude-code; then
  printf 'Verify: ~/.claude/usage-optimizer/bin/claude-prompts --latest --text (your questions in the newest session)\n'
fi
if [[ -n "$SOURCE_CHECKOUT" ]]; then
  printf 'Updates: the statusline checks the origin of %s every 6 hours and names a newer release;\n' "$SOURCE_CHECKOUT"
  printf '  check now with ~/.claude/usage-optimizer/bin/kit-update check (USAGE_OPTIMIZER_UPDATE_CHECK=off turns it off).\n'
else
  printf 'Updates: not checked; a bundle install has no checkout to fetch (install from a git clone for that).\n'
fi
if has_platform claude-code; then
  printf 'Verify: claude plugin list shows sessions@skills-dir (the Sessions pane: /sessions, or . in an empty prompt)\n'
fi
if has_platform claude-code && [[ "$VIEW" == apply ]]; then
  printf 'Verify: claude plugin validate %s; claude plugin list shows mobile-view@skills-dir\n' "$MOD_DIR"
  printf 'Mobile view: restart Claude Code. Tool calls show one line each (click one to expand it), long code\n'
  printf '  blocks fold, > in an empty prompt lists your questions (Esc goes back), /mobile-view off shows the stock view.\n'
fi
if [[ "$OS_NAME" == Windows ]]; then
  printf 'On Windows the tools run through the wrappers in ~/.local/bin (lane, or lane.cmd outside Git Bash).\n'
fi
if has_platform claude-code; then
  printf 'Restart Claude Code sessions to load the new settings.\n'
fi
if has_platform amp; then
  printf 'Amp: restart Amp or run `plugins: reload` to load the usage-optimizer plugin.\n'
  printf 'Amp: the policy is imported from %s; ~/.config/amp/settings.json and ~/.config/AGENTS.md are not changed.\n' \
    "$AMP_AGENTS"
fi
if has_platform codex; then
  printf 'Codex: open /hooks once in Codex and trust the usage-optimizer hooks.\n'
  printf 'Codex status line (suggested, not written): tui.status_line = ["model-with-reasoning", "context-used", "five-hour-limit", "weekly-limit"] in %s\n' \
    "$CODEX_DIR/config.toml"
  printf 'Codex: the hooks and the policy block are unverified against a live Codex session.\n'
fi
if ((DRY_RUN)); then
  printf 'Dry run complete; installer actions were not applied.\n'
fi
