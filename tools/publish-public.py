#!/usr/bin/env python3
"""Refresh and publish a clone of the public releases repository."""

import argparse
import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import release_bundle


IDENTITY = "Coding Tool Optimizer <kit@localhost>"
PUBLIC_NAME = "coding-tool-optimizer"
REPO_URL = "https://github.com/hieunguyen7337/coding-tool-optimizer"
PAGES_URL = "https://hieunguyen7337.github.io/coding-tool-optimizer/"
# The kit page (tools/make-page.py writes dist/index.html) is served by GitHub Pages from the docs/ folder.
PAGE_SOURCE = pathlib.Path("dist") / "index.html"
PAGE_TARGET = "docs/index.html"
# Optional: the release's own notes, written by the publisher, shown above the standard install notes.
NOTES_SOURCE = pathlib.Path("dist") / "release-notes.md"


class PublishError(Exception):
    pass


def run(command, cwd=None, check=True):
    result = subprocess.run(command, cwd=str(cwd) if cwd else None, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode:
        raise PublishError(result.stderr.strip() or result.stdout.strip() or
                           "command failed: " + " ".join(command))
    return result


def git(clone, *arguments, check=True):
    return run(["git", "-C", str(clone), *arguments], check=check)


def version(kit):
    marker = release_bundle.VERSION_MARKER
    value = release_bundle.version_from_policy(kit)
    match = re.search(re.escape(marker) + r"\s*([^\s.]+(?:\.[^\s.]+)+)\.?(?:\s|$)", value)
    if not match:
        raise PublishError("cannot read release version from POLICY.md")
    return match.group(1)


def check_release(kit):
    command = [sys.executable, "-I", str(kit / "tools" / "check-release.py"),
               "--kit", str(kit)]
    result = run(command, cwd=kit, check=False)
    output = result.stdout + result.stderr
    if result.returncode or not any(line.startswith("OK private:") for line in output.splitlines()):
        raise PublishError("release check refused publication:\n" + output.rstrip())
    return output


def check_clone(clone):
    if not clone.is_dir() or not (clone / ".git").is_dir():
        raise PublishError("clone is not a git work tree: " + str(clone))
    if git(clone, "status", "--porcelain").stdout:
        raise PublishError("clone has a dirty work tree: " + str(clone))
    origin = git(clone, "remote", "get-url", "origin").stdout.strip()
    if PUBLIC_NAME not in origin:
        raise PublishError("origin is not the public releases repository: " + origin)
    return origin


def public_files(kit, require_page=False):
    """The public tree: the shipped files, LICENSE, the prefaced README and, when built, the kit page in docs/.

    The source README's own title is dropped, so the public README has one H1 (the preface's)."""
    files = {name: item["content"] for name, item in release_bundle.shipped_files(kit).items()}
    try:
        license_bytes = (kit / "LICENSE").read_bytes()
        preface = (kit / "public-repo" / "README-public.md").read_bytes()
        readme = (kit / "README.md").read_bytes()
    except OSError as error:
        raise PublishError("cannot read public release input: " + str(error))
    files["LICENSE"] = license_bytes
    readme = re.sub(rb"\A# [^\n]*\n+", b"", readme, count=1)
    files["README.md"] = preface.rstrip(b"\r\n") + b"\n\n" + readme
    page = kit / PAGE_SOURCE
    if page.is_file():
        files[PAGE_TARGET] = page.read_bytes()
        files["docs/.nojekyll"] = b""
    elif require_page:
        raise PublishError("the kit page is missing: run tools/make-page.py first ({})".format(page))
    public_root = kit / "public-repo"
    for path in sorted(public_root.rglob("*")):
        if path.is_symlink():
            raise PublishError("public-repo contains a symlink: " + str(path))
        if path.is_file() and path.name != "README-public.md":
            files[path.relative_to(public_root).as_posix()] = path.read_bytes()
    return files


def replace_tree(clone, files):
    for path in clone.iterdir():
        if path.name == ".git":
            continue
        shutil.rmtree(str(path)) if path.is_dir() and not path.is_symlink() else path.unlink()
    for relative, content in files.items():
        destination = clone / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        if content.startswith(b"#!"):
            destination.chmod(0o755)


def refuse_existing_tag(clone, tag):
    result = git(clone, "ls-remote", "--exit-code", "--tags", "origin", "refs/tags/" + tag,
                 check=False)
    if result.returncode == 0 and result.stdout.strip():
        raise PublishError("tag already exists on origin: " + tag)
    if result.returncode not in (0, 2):
        raise PublishError(result.stderr.strip() or "cannot check remote tag")


def commit_and_tag(clone, release_version, executables=()):
    config = ["-c", "user.name=Coding Tool Optimizer", "-c", "user.email=kit@localhost"]
    git(clone, *config, "add", "-A")
    # Record scripts as executable in git too: on Windows core.fileMode is false, so the chmod above is not seen.
    if executables:
        git(clone, "update-index", "--chmod=+x", "--", *sorted(executables))
    git(clone, *config, "commit", "-m", "Release " + release_version)
    git(clone, *config, "tag", "v" + release_version)


def checksums(kit, directory):
    names = (release_bundle.BUNDLE_NAME, release_bundle.EVIDENCE_NAME)
    lines = []
    assets = []
    for name in names:
        path = kit / "dist" / name
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as error:
            raise PublishError("cannot read release asset: " + str(error))
        lines.append("{}  {}\n".format(digest, name))
        assets.append(str(path))
    sum_path = directory / "SHA256SUMS"
    sum_path.write_text("".join(lines), encoding="ascii")
    return assets + [str(sum_path)]


def release_notes(kit, release_version):
    """The GitHub Release body: the publisher's notes for this release, when written, then how to install it."""
    try:
        own = (kit / NOTES_SOURCE).read_text(encoding="utf-8").strip()
    except OSError:
        own = ""
    standard = """Coding Tool Optimizer {version}: a usage optimizer for AI coding agents (Claude Code, Amp, Codex CLI).

**Install.** Paste the setup prompt for your agent from [SETUP_PROMPT.md]({repo}/blob/main/SETUP_PROMPT.md), or:

```bash
grep bundle SHA256SUMS | sha256sum -c        # macOS: grep bundle SHA256SUMS | shasum -a 256 -c
bash coding-tool-optimizer-bundle.sh --dry-run    # add --platform amp or --platform codex for those agents
bash coding-tool-optimizer-bundle.sh
```

The bundle extracts to `~/claude-usage-optimizer`, checks every file's sha256 and runs `install.sh`. The kit sends
nothing to its authors; the README's "What leaves your machine" lists every connection. Kit page: {pages}

Assets: `coding-tool-optimizer-bundle.sh` (the kit), `coding-tool-optimizer-evidence.sh` (optional Suite R
evidence), `SHA256SUMS`.""".format(version=release_version, repo=REPO_URL, pages=PAGES_URL)
    return (own + "\n\n" + standard) if own else standard


def publish(clone, kit):
    print("ACTION check release: {}".format(kit))
    check_release(kit)
    print("ACTION check clean public clone: {}".format(clone))
    check_clone(clone)
    release_version = version(kit)
    tag = "v" + release_version
    print("ACTION check remote tag is absent: {}".format(tag))
    refuse_existing_tag(clone, tag)
    files = public_files(kit, require_page=True)
    print("ACTION replace public tree: {} files".format(len(files)))
    replace_tree(clone, files)
    print("ACTION commit: Release {}".format(release_version))
    commit_and_tag(clone, release_version, [name for name, content in files.items() if content.startswith(b"#!")])
    print("ACTION push branch: git push origin HEAD")
    git(clone, "push", "origin", "HEAD")
    print("ACTION push tag: git push origin {}".format(tag))
    git(clone, "push", "origin", tag)
    with tempfile.TemporaryDirectory() as temporary:
        assets = checksums(kit, pathlib.Path(temporary))
        command = ["gh", "release", "create", tag, "--title", release_version,
                   "--notes", release_notes(kit, release_version)] + assets
        print("ACTION GitHub release: " + " ".join(command[:-3]) + " [3 assets]")
        run(command, cwd=clone)


def dry_run(clone, kit):
    print("DRY RUN: no files, commits, tags, pushes, or releases will be changed")
    print("ACTION check clean public clone: {}".format(clone))
    check_clone(clone)
    release_version = version(kit)
    files = public_files(kit)
    print("WOULD check release with OK private")
    print("WOULD replace public tree with {} files".format(len(files)))
    print("WOULD commit Release {} and tag v{}".format(release_version, release_version))
    print("WOULD push origin HEAD and v{} without force".format(release_version))
    print("WOULD publish the kit page as {}".format(PAGE_TARGET) if PAGE_TARGET in files
          else "WARN the kit page is missing (run tools/make-page.py); a real publish refuses")
    print("WOULD create GitHub release with bundle, evidence, and SHA256SUMS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clone", required=True)
    parser.add_argument("--kit", default=str(pathlib.Path(__file__).resolve().parent.parent))
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args()
    try:
        clone = pathlib.Path(args.clone).resolve()
        kit = pathlib.Path(args.kit).resolve()
        publish(clone, kit) if args.push else dry_run(clone, kit)
    except (PublishError, release_bundle.BundleError) as error:
        print("REFUSED: " + str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
