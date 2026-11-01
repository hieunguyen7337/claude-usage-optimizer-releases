# Terra against sol, and what each subscription holds (main session, Opus, 2026-10-28)

Sources read on 2026-10-28 unless dated otherwise. Numeric rows are also in `../public.json` (metrics
`aa_ii_v5_score`, `aa_ii_v5_cost_per_task_usd`, `aa_ii_v5_tb4_pct`, `frontiercode_v2_pct`,
`vendor_terminal_bench_4_pct`). Our own measurements are in `../FINDINGS.md` §1–3 and §12–15.

## 1. Terra and sol per effort (Artificial Analysis)

Artificial Analysis rescaled its Intelligence Index to v5.0 after our 2026-10-20 rows (`aa_ii_*` in `public.json`),
so v5.0 scores are stored under their own metric and must not be compared with the older ones. TB4 = its
Terminal-Bench 4.0 hard-task pass rate; $ = list cost per task in its harness.

| Effort | Index v5.0, terra / sol | TB4, terra / sol | $ per task, terra / sol | Terra cost ÷ sol | Page |
|---|---|---|---|---:|---|
| low | 29 / 35 | 15% / 31% | 0.07 / 0.16 | 0.44 | https://artificialanalysis.ai/models/comparisons/gpt-6-1-sol-low-vs-gpt-6-1-terra-low |
| medium | 38 / 46 | 32% / 48% | 0.17 / 0.36 | 0.47 | https://artificialanalysis.ai/models/comparisons/gpt-6-1-sol-medium-vs-gpt-6-1-terra-medium |
| high | 42 / 50 | 42% / 52% | 0.26 / 0.59 | 0.44 | https://artificialanalysis.ai/models/comparisons/gpt-6-1-sol-high-vs-gpt-6-1-terra-high |
| xhigh | 45 / 52 | 46% / 54% | 0.40 / 0.76 | 0.53 | https://artificialanalysis.ai/models/comparisons/gpt-6-1-sol-xhigh-vs-gpt-6-1-terra-xhigh |
| max | 51 / 55 | 56% / 56% | 0.96 / 1.27 | 0.76 | https://artificialanalysis.ai/models/comparisons/gpt-6-1-sol-vs-gpt-6-1-terra |

- FrontierCode v2 at max: terra 42%, sol 41% (same max page).
- At matched cost terra equals sol one effort lower: sol medium (46, $0.36) beats terra xhigh (45, $0.40), and sol
  xhigh (52, $0.76) beats terra max (51, $0.96). Only terra low and medium sit below every sol arm on cost.
- Vendor: OpenAI gives terra 50.3% and sol 55.9% on Terminal-Bench 4.0
  (https://openai.com/index/introducing-gpt-6-1-terra/, 2026-10-26; the page returned 403, read through search
  snippets). Vendor numbers run high (POLICY).
- Unverified: a coding-agent index v2.0 of terra 48, sol 54 appears in blogs but not on Artificial Analysis's own
  coding-agent pages (https://artificialanalysis.ai/agents/coding-agents), so it is not in `public.json`.
- No public code-review benchmark covers terra; our Suite R run is the only review measurement (FINDINGS §12).
- Card: 25 / 1.25 / 125 credits per 1M input / cached / output, half sol and 10× luna
  (https://help.openai.com/en/articles/20001106-codex-rate-card; https://learn.chatgpt.com/docs/pricing).

## 2. Separate usage bars and proportionality

| Plan | Bars | Proportional to API price? | Sources |
|---|---|---|---|
| Claude Max 20x | One 5h and one weekly bar for all models; Fable has an extra weekly sub-cap (up to 50% of the week) | No (FINDINGS §1 weights). SemiAnalysis also finds Claude's limits departing from API price ratios and puts Fable at about $2,485 a month | https://support.claude.com/en/articles/15424964; https://support.claude.com/en/articles/12429409; https://newsletter.semianalysis.com/p/anthropic-subscriptions-offer-5x (secondary summaries: https://pasqualepillitteri.it/en/news/4793/semianalysis-token-value-claude-chatgpt-plans, https://explainx.ai/blog/semianalysis-claude-vs-chatgpt-subscription-api-value-limit-testing-2026) |
| Codex Pro / Plus | One pool for all models; weekly only on Pro, 5h plus weekly on Plus. Plus's per-model 5h ranges (luna 350–3,000 messages, terra 35–285, sol 15–160, astra 5–45) express that one pool per model | Yes, by the per-model credit card | https://learn.chatgpt.com/docs/pricing; https://help.openai.com/en/articles/20001106-codex-rate-card; https://inventivehq.com/blog/codex-subscription-usage-measured (Pro $330–380 a week, Plus about $66) |
| Google AI Pro (Antigravity) | Two pools, Gemini models and third-party models, each with 5h and weekly bars; no published sizes; third-party access ends 2026-11-02 | Yes: Gemini models draw one pool at API prices | https://antigravity.google/docs/plans/; https://antigravity.google/blog/changes-to-antigravity-plans/; https://antigravity.google/docs/models/; https://antigravity.google/docs/faq/ |

- One older Claude Code page (https://code.claude.com/docs/en/model-config) describes per-model limits on Max and
  contradicts itself; nothing else supports it.
- Gemini 3.8 Flash in Antigravity: https://antigravity.google/blog/gemini-3-8-flash-in-google-antigravity/.
  List price $0.75 / $3.75 per 1M input / output.
- Antigravity terms (https://antigravity.google/terms/): consumer terms; interactions may be kept, used to improve
  Google's models and read by human reviewers, with an opt-out in settings. Keep the toggle off and send only
  non-sensitive work.

## Conflicts

- Index versions: v1.5 coding-agent (POLICY's benchmark table), the older Intelligence Index rows of 2026-10-20 and
  v5.0 here are three scales. Compare within one only.
- Terra's TB4 at max: 56% (Artificial Analysis v5.0), 55.6% (Artificial Analysis through secondary sources,
  2026-10-27) and 50.3% (OpenAI). The first two agree; the vendor figure is lower than the neutral harness, which is
  unusual and unexplained.
