# Build and review a kit release

## 1. Goal

Prepare a release of `<kit-name>` from `<kit-root>`. Done means the requested version and catalog are valid,
the tests and release checks pass, the installer preview is clean, and the section 4 report contains real
outputs. Do not publish unless the user has asked for publication.

## 2. Files

- **Workspace:** `<kit-root>`; preserve existing user changes.
- **You may change:** `<release-files>` and generated `<build-output>` only.
- **Read-only sources:** `<source-files>`.
- **Out of scope:** `<protected-files-and-directories>`.

## 3. Constraints

- Use the lane class `<class>` and tag `<release-tag>`. State all four brief parts, including exact scope and
  the return contract below.
- Never hand-edit machine-readable output. For JSON, use the tool's own stdout or `--write`; never rewrite it
  with `jq`, a script or a heredoc. Validate with `<json-validator>` and check
  `[.. | objects | select(has("measured") and .measured==null)] | length` is 0 when the catalog has measured
  blocks.
- Check the version line in `POLICY.md`; change `catalog_version` in `arms.json` only if the catalog changes.
- Run `<test-command>` and report every test file's result line. Load the catalog with
  `<lane-stats-command>` and report its output.
- Build with `bash tools/make-bundle.sh`, then `python3 -I tools/make-page.py`. Preview with
  `bash install.sh --dry-run`.
- Run `python3 -I tools/check-release.py [--kit DIR] [--bundle PATH] [--page PATH] [--patterns FILE] [--max-bytes N]`.
  It checks version, catalog, JSON, bundle size (maximum 16,000,000 bytes), bundle freshness, local release
  patterns, line endings (a file git stores with LF must not have CRLF in the tree) and untracked files. Exit 0
  is clean; exit 1 means a check failed. The patterns file is local and
  never ships; `!glob` excludes paths. Report only the printed path, line and pattern number for each hit.
- The bundle currently uses 13.9 MB of the 16,000,000-byte Artifact limit. Keep workspaces git-ignored:
  `make-bundle.sh` includes untracked non-ignored files. Install from the clone that built the bundle.
- Recompute before/after tables from `git show HEAD:`; do not trust a worker table without checking its
  source values. Tag every claim `[OBSERVED path:line]`, `[OBSERVED command output]` or `[INFERRED]`, and
  literally grep any quoted string.
- If publishing from a machine other than the last publisher, compare and merge the live bundle first with
  `python3 -I tools/diff-bundle.py <live bundle> [--kit DIR] [--extract DIR]`. It never runs the bundle;
  exit 0 means identical, 1 differences, 2 error.
- Publish only when requested. The bundle must be a `.sh` supporting file with `contentType: "text/plain"`
  at the existing Artifact URL. If a commit is requested, use `kit <kit@localhost>`, never a personal
  identity.

## 4. Return contract

Return these sections in order:

1. `git status --short` and `git diff --stat`; list every changed file and `file:line` for each lesson added.
2. The test job id (or `<not applicable>`) and each test file's result line.
3. Every catalog, build, installer, bundle-size, freshness, pattern and untracked check with its real output.
4. Before/after values recomputed from `git show HEAD:`, and anything unresolved. Tag every claim
   `[OBSERVED path:line]`, `[OBSERVED command output]` or `[INFERRED]`.
