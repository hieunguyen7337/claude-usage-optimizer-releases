# Audit the kit for reusable lessons

## 1. Goal

Find every reusable fact, measurement, method, tool or lesson in the named sources that is missing from or
incomplete in the kit. Done means the section 4 report is complete, every claim is tagged and located, and
every kit-bound lesson has a destination.

## 2. Files

- **Kit to compare against (read-only):** `<kit-root>`; inspect only `<kit-files-and-directories>`.
- **Sources (read-only):** `<source-root>`; inspect only `<named-source-directories>`, to depth `<depth>`,
  and only files matching `<allowed-globs>`.
- Skip raw data, transcripts, session extracts, credentials, secrets and files larger than `<max-bytes>`.
- Search the kit before calling an item missing. Use bounded searches over the named kit paths.

## 3. Constraints

- Run this as a read-only lane unit with class `research` and tag `<audit-tag>`; the tag must identify this
  audit without naming a person, project, host or machine path.
- Do not change files. Bash may write even in read-only mode, so return the report in the lane's final output.
- Never read credentials, secrets, tokens, raw transcripts or any file outside the named sources.
- Rewrite kit-wide lessons generically. Do not include project or paper names, personal data, hostnames, user
  ids or home paths in proposed kit text. Say “a high-performance computing (HPC) login node” or “a research
  project” when needed.
- Assign exactly one class to each candidate: KIT-MISSING, KIT-PARTIAL, PRESENT, EXCLUDED, MACHINE,
  PROJECT, SUPERSEDED or OBSOLETE. Count every class. Only KIT-MISSING and KIT-PARTIAL need proposals.
- Tag every claim `[OBSERVED path:line]` or `[INFERRED]`. Literally grep every quoted string before quoting it.
- Bound every search to named directories and depth; report what was searched when a target is absent.
- Treat a lane verdict and a null agent result as claims. Read the tree before rerunning, and redispatch only
  stages whose output is missing.
- If a check needs a tool, use `<tool-name>` with its own output or `--write`. Never hand-edit its JSON with
  `jq`, a script or a heredoc. Validate JSON with `<json-validator>` and include the real output.

## 4. Return contract

Return these sections in order:

1. A table of every KIT-MISSING and KIT-PARTIAL item: generic lesson, source `path:line`, destination file and
   section, and the bounded search that showed it was absent or incomplete.
2. Tools and scripts in the sources without a counterpart in `<kit-tool-directories>`, and whether kit users
   need them.
3. Counts for KIT-MISSING, KIT-PARTIAL, PRESENT, EXCLUDED, MACHINE, PROJECT, SUPERSEDED and OBSOLETE.
4. Anything unreadable or undecided. Tag every claim `[OBSERVED path:line]`, `[OBSERVED command output]` or
   `[INFERRED]`.
