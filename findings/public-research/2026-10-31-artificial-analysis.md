# Artificial Analysis, October 2026: Coding Agent Index v2.0 and Intelligence Index v5.0 per effort

Sources read on 2026-10-31 by a researcher unless dated otherwise. Numeric rows are in `../public.json`: v2.0 under
`aa_cai2_index`, `aa_cai2_tb4_pct` and `aa_cai2_cost_per_task_usd`; v5.0 under `aa_ii_v5_score` and
`aa_ii_v5_cost_per_task_usd` (terra and sol were already there from 2026-10-28). The v1.5 rows (`aa_cai_*`, dated
2026-10-20) are unchanged. In this session artificialanalysis.ai did not resolve, so the figures below are the
researcher's readings, not re-fetched here (see Gaps).

## 1. Coding Agent Index v2.0 replaces v1.5

- AA gives no day for the change. A secondary news source says 2026-10-23.
- Method (https://artificialanalysis.ai/methodology/coding-agents-benchmarking): DeepSWE v1.1 is replaced by
  FrontierCode v1.1 (from Cognition); SWE-Atlas-QnA becomes SWE-Atlas-QnA-AA (judged by GPT-6 Luna xhigh, 5 votes per
  criterion); Terminal-Bench 4.0 is unchanged (66 tasks). The index is the equal-weight mean of the three, 290 tasks.
- Secondary source: AA says v1.x and v2.0 scores are not directly comparable. The mean over 21 configurations fell
  from 54.8 to 47.4. Do not read a v2.0 score against a v1.5 score.
- AA's pages no longer show a cost-frontier marker in fetchable text (the charts are rendered by JavaScript), so this
  note and `POLICY.md` carry no frontier flag for v2.0.
- The comparison pages list one row per model at max, except terra, which has every effort. Other efforts are not listed.

| Model (harness) | Effort | Index | TB4 | $ per task | Page |
|---|---|---:|---:|---:|---|
| Opus 5.5 (Claude Code) | max | 62 | 63% | 11.42 | https://artificialanalysis.ai/agents/coding-agents/comparisons/claude-code-vs-codex |
| Sonnet 5.5 (Claude Code) | max | 59 | 66% | 13.30 | same |
| Haiku 5.5 (Claude Code) | max | 37 | 31% | 2.67 | same |
| Fable 5.1 (Claude Code) | max | 58 | 58% | 11.53 | same |
| GPT-6.1 Sol (Codex) | max | 54 | 53% | 1.50 | https://artificialanalysis.ai/agents/coding-agents/comparisons/antigravity-cli-vs-codex |
| GPT-6 Astra (Codex) | max | 55 | 56% | 7.04 | same |
| GPT-6.1 Terra (Codex) | max / xhigh / high | 48 / 48 / 46 | 48 / 46 / 42% | 1.24 / 0.69 / 0.54 | same |
| GPT-6.1 Terra (Codex) | medium / low | 42 / 35 | 35 / 25% | 0.39 / 0.20 | same |
| GPT-6 Luna (Codex) | max | 31 | 16% | 0.16 | same |
| Gemini 3.8 Flash (Antigravity SDK) | high | 33 | 15% | 2.51 | https://artificialanalysis.ai/agents/coding-agents/comparisons/antigravity-sdk-vs-codex |

- Terra non-reasoning: index 39, TB4 25%, $0.45. Not in `public.json` because the kit runs no non-reasoning arm.
- Fable is labelled "with fallback" on AA's v1.5 page; the v2.0 label was not checked for that caveat (see Gaps).
- Gemini 3.8 Flash here is run through the Antigravity SDK. The gemini lane may use a different harness, so this is
  not a direct measure of that lane.

## 2. Intelligence Index v5.0 per effort

- Announced 2026-10-27 (https://artificialanalysis.ai/articles/artificial-analysis-intelligence-index-v5). About 60%
  of the tasks are private test sets. It adds FrontierCode 2.0 and Terminal-Bench-Science.
- Leaderboard read 2026-10-31 (https://artificialanalysis.ai/leaderboards/models). Score / $ per task, by effort:

| Model | max | xhigh | high | medium | low |
|---|---|---|---|---|---|
| Terra (in file 2026-10-28) | 51 / 0.96 | 45 / 0.40 | 42 / 0.26 | 38 / 0.17 | 29 / 0.07 |
| Sol (in file 2026-10-28) | 55 / 1.27 | 52 / 0.76 | 50 / 0.59 | 46 / 0.36 | 35 / 0.16 |
| Opus 5.5 | 58 / 10.04 | 57 / 6.05 | 52 / 3.46 | 48 / 2.45 | 35 / 0.98 |
| Sonnet 5.5 | 54 / 10.02 | 50 / 4.09 | 41 / 1.64 | 30 / 0.78 | 25 / 0.51 |
| Haiku 5.5 | 36 / 0.41 | 34 / 0.25 | 30 / 0.16 | 25 / 0.09 | 19 / 0.04 |
| Fable 5.1 | 49 / 12.99 | 50 / 10.85 | 47 / 7.54 | 43 / 5.56 | 38 / 4.47 |
| Astra | 57 / 6.24 | 55 / 3.66 | 55 / 3.24 | 51 / 2.73 | 43 / 1.42 |
| Luna | 28 / 0.15 | 23 / 0.10 | 21 / 0.07 | 18 / 0.04 | 10 / 0.01 |
| Gemini 3.8 Flash | – | – | 31 / 7.77 | 30 / 6.26 | 22 / – |

- Fable scores lower at max (49) than at xhigh (50), as AA shows it. Luna non-reasoning scores 9 and terra
  non-reasoning 30; neither is a kit effort, so neither is in `public.json`.
- The terra and sol per-effort numbers agree with `2026-10-28-terra-and-subscriptions.md`. Nothing there changed.

## 3. New models and watch items (not kit lanes)

- Gemini 4 Carbon was released 2026-10-28 and has Intelligence Index 59, the highest on AA's list
  (https://artificialanalysis.ai/models/gemini-4-carbon). On v2.0 it scores 59 / 64% / $7.74 at high on the
  antigravity-cli-vs-codex page; Gemini 4 Argon (High) scores 53 / 56% / $11.73. This account's agy does not offer it
  (`lane-stats arms --discover`, 2026-10-31, lists no gemini-4 model), so it is a watch item and no row was added.
  A `gemini` row would match the gemini arms.
- GitHub Copilot Fusion (an agent): AA's changelog for 2026-10-28 says it is 2 points below Opus 5.5 at half the
  cost. No numbers were found, so nothing is recorded.
- glm-5.3 (Opencode) on v2.0: 49 / 40% / $5.23 at max. This is not the z-ai/glm-5.3-flash model the glm lane runs,
  so it is not in `public.json` (a `glm` row would match that lane).
- AA's changelog for 2026-10-20 to 2026-10-30 lists no new Anthropic or OpenAI model.

## Conflicts

- Index versions: v1.5, v2.0 and the Intelligence Index (v5.0 and the 2026-10-20 AA-II rows) are three or four scales.
  Compare within one only.
- Terra's TB4 at max: 48% on the v2.0 coding-agent page and 56% on the v5.0 Intelligence Index. The two AA pages
  use different harnesses; the 56% is the one already in the file.
- Opus 5.5 FrontierCode: 56.0% inside the index (secondary source, FrontierCode v1.1) against 46.4% on AA's
  FrontierCode 2.0 page. These are different versions.
- Opus 5.5 index: 61.7 (secondary) against 62 (AA, rounded).
- Sol at max costs $1.27 per task on the Intelligence Index and $1.50 on the coding-agent index. Those measure
  different things.

## Gaps and unverified

- Claude rows on the claude-code-vs-codex page (Opus, Sonnet, Haiku, Fable): read by the researcher on 2026-10-31.
  The Codex rows were re-read and matched. Not re-fetched in this session: artificialanalysis.ai did not resolve from
  the cloud session, so it has to be allowed in the session's network settings before the figures can be checked here.
- Fable's v2.0 label may need the "with fallback" caveat from v1.5; not checked.
- Gemini 3.8 Flash low on v5.0: no cost given, so no cost row.
- The v2.0 date is unknown: AA gives none. `public.json` uses the reading date, 2026-10-31.
- The 21-configuration mean (54.8 to 47.4) and the Opus 61.7, FrontierCode 56.0 and the secondary-source date come from
  secondary sources only.

## 4. What `lane-bench compare` says now

Run on `findings/suite-r/outcomes.jsonl` (Suite R, review class), before and after these rows. Before: 18 metrics;
after: 21 (`aa_cai2_index`, `aa_cai2_tb4_pct` and `aa_cai2_cost_per_task_usd` are new).

- v1.5 index against our recall: Spearman 0.22 (n=18), unchanged. v1.5 cost against our $ per item: 0.96 (n=18), unchanged.
- v2.0 index against our recall: 0.81 (n=9); per % of week, 0.88 (n=9). v2.0 cost: 0.98 (n=9). Nine arms only: the v2.0
  rows match the kit's max arms and terra and gemini, not the rest.
- Intelligence Index v5.0 score against our recall: 0.57 (n=37), up from 0.37 (n=8). v5.0 cost: 0.60 (n=37).
- Caveat: `lane-bench` pairs each score with the cost of its own source prefix, so `aa_ii_v5_score` is divided by the
  2026-10-20 AA-II cost, not the v5.0 cost. The per-% week correlation for v5.0 (0.81, n=34) is therefore not a valid
  v5.0 figure. The per-$ result for `aa_ii_v5_cost_per_task_usd` is unaffected.
