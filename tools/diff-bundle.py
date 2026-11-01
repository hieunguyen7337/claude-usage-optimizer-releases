#!/usr/bin/env python3
"""Compare or safely extract the files recorded in a generated kit bundle."""

import argparse
import os
import pathlib
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from release_bundle import BundleError, is_evidence, parse_bundle, shipped_files


def inside_git_checkout(path):
    current = path.resolve()
    for parent in (current,) + tuple(current.parents):
        if (parent / ".git").exists():
            return True
    return False


def extract(files, destination):
    destination = pathlib.Path(destination).expanduser().absolute()
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise BundleError("extract destination exists and is not empty")
    if inside_git_checkout(destination):
        raise BundleError("refusing to extract inside a git checkout")
    destination.mkdir(parents=True, exist_ok=True)
    for relative, item in files.items():
        target = destination.joinpath(*relative.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            raise BundleError("refusing to overwrite symlink: " + relative)
        target.write_bytes(item["content"])
        os.chmod(str(target), 0o755 if item["executable"] else 0o644)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle")
    parser.add_argument("--kit", default=str(pathlib.Path(__file__).resolve().parent.parent))
    parser.add_argument("--extract")
    args = parser.parse_args()
    try:
        bundle = parse_bundle(args.bundle)
        kit = pathlib.Path(args.kit).resolve()
        bundled = bundle["files"]
        # An evidence file (claude-usage-optimizer-evidence.sh) is compared with the evidence files, not the kit's.
        evidence = bool(bundled) and all(is_evidence(path) for path in bundled)
        current = shipped_files(kit, evidence=evidence)
        added = sorted(set(bundled) - set(current))
        removed = sorted(set(current) - set(bundled))
        changed = sorted(path for path in set(current) & set(bundled)
                         if current[path]["hash"] != bundled[path]["hash"])
        kit_version = "unknown"
        try:
            from release_bundle import version_from_policy
            kit_version = version_from_policy(kit)
        except BundleError:
            pass
        print("Bundle version: " + bundle["version"])
        print("Kit version: " + kit_version)
        for name, paths in (("added", added), ("removed", removed), ("changed", changed)):
            print("{} ({}):".format(name, len(paths)))
            for path in paths:
                print("  " + path)
        if args.extract:
            extract(bundled, args.extract)
        return 1 if added or removed or changed else 0
    except BundleError as error:
        print("diff-bundle: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
