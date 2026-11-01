# R-C: hybrid (multi-model) coding setups and predicting them from single-model results (researcher, Sonnet, 2026-10-22)

## 1. Artificial Analysis
AA has no dedicated hybrid article. Its only multi-model rows are three Devin Fusion CLI rows on the Coding Agent Index v1.5
(lead model plans and reviews, executor executes, per Cognition). AA index = 303 tasks x 3 runs: DeepSWE v1.1 (113),
Terminal-Bench 4.0 (66), SWE-Atlas-QnA (124), equally weighted; cost = pay-per-token API cost per task incl. cache.
Methodology: https://artificialanalysis.ai/methodology/coding-agents-benchmarking

| Configuration (lead + executor) | Index | DeepSWE / TB4 / QnA | $/task | Time | Pareto | URL |
|---|---|---|---|---|---|---|
| Fusion: Opus 5.5 max + GPT-6 Luna high | 68 | 73 / 63 / 69 | 9.02 | 55.0m | unverified | https://artificialanalysis.ai/agents/coding-agents/comparisons/devin-fusion-cli-vs-kimi-code-cli |
| Fusion: Fable 5.1 xhigh + SWE-2 medium | 61.7 | 63 / 56 / 66 | 7.90 | 35.8m | yes (AA post, Sep 2026, snippet only) | https://artificialanalysis.ai/agents/coding-agents/comparisons/codex-vs-devin-fusion-cli |
| Fusion: GPT-6 Astra xhigh + SWE-2 medium | 58.9 | 67 / 50 / 59 | 4.55 | 24.7m | yes (same post) | same |

Single-model baselines (https://artificialanalysis.ai/agents/coding-agents/comparisons/codex-vs-claude-code): Sonnet 5.5 max 68 / $14.19;
Opus 5.5 max 66 / $13.04; Sonnet 5.5 xhigh 63 / $3.33; Fable 5.1 max 62 / $12.39; Sol xhigh 63 / $1.04; Sol medium 61 / $0.70;
Astra max 62 / $7.50; Luna max 41 / $0.18; Haiku 5.5 xhigh 41 / $0.61.
- Opus max + Luna high: +2 points over Opus max alone, 31% cheaper; but Sol xhigh is 63 at $1.04 (9x cheaper, 5 points lower).
- Fable + SWE-2: -0.5 points, 36% cheaper. Astra + SWE-2: -2.7 points, 39% cheaper. Fusion used ~70% more tokens and ~3x turns.
- FrontierCode (AA, 2026-10-12): single model per run, no hybrids. Frontier: Luna max 42% $0.09; Sol max 49% $0.81; Opus 5.5 max 52% $10.15.

## 2. Other public hybrid results
| Configuration | Result | Cost | Source |
|---|---|---|---|
| Fusion Fable 5.1 + SWE-2, Vals Code Migration | 57.3% vs 54.6% Fable alone | $42.00 vs $70.97 | The Batch 2026-09-25 (Vals run) https://www.deeplearning.ai/the-batch/one-agent-works-another-directs |
| Fusion Astra + SWE-2, same | 61.3% vs 67.7% Astra alone | $35.51 vs $44.36 | same |
| Advisor: Sonnet 4.6 + Opus 4.6 advisor, SWE-bench Multilingual | +2.7 points | -11.9%/task | vendor 2026-04-09 https://claude.com/blog/the-advisor-strategy |
| Advisor: Haiku 4.5 + Opus 4.6, BrowseComp | 41.2% vs 19.7% | 85% below Sonnet solo | same |
| Advisor: Opus 5.5 high + Fable 5.1, internal coding | 90.1%, +1.7 ("edge of noise") | ~2.1x | vendor https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence |
| Advisor: Opus 5.5 low + Fable 5.1, Chartography | 7 points LOWER (consulted 1/300) | ~same | same |
| Orchestrator + Sonnet 5 workers vs Fable 5.1 alone, defect search | 10-12 points lower | ~half | same |
| Aider architect/editor (2024-25, old gen) | o1-preview+o1-mini 85.0% vs 79.7% | n/g | https://aider.chat/2024/09/26/architect.html |
| Fusion + Fable 5, FrontierCode Extended | 57.6 vs 57.0 | $3.00 vs $5.12 | eesel.ai [secondary of vendor] |

Anthropic guidance (vendor): sweep effort on the single model first; build a pairing only if it beats the single model's whole
score-vs-spend curve; on one dependent chain that fits in one context, the orchestrator's model alone at lower effort won every
case measured. Advisor benefit tracks the executor's consult rate. Codex docs: subagents inherit model/effort; suggest Luna high
for exploration, Sol medium for review; no numbers.

## 3. Predicting a hybrid from its components
| Evidence | Finding | Source |
|---|---|---|
| Handoff Tax, arXiv 2608.24358 (2026-08-25), SWE-bench Verified | weak->strong with full trajectory recovers only 47% (Claude) / 36% (GPT) of the gap; fresh restart 100%; later switch recovers less (57 -> 39); strong->weak 50% / 79%; interface choice moves recovery 28 -> 56. Cost descriptive only. | https://arxiv.org/html/2608.24358 |
| Scaling Agent Systems (Google/Cornell, 2026-01-28) | R^2 0.513 model picks the best architecture for 87% of unseen configs; independent agents amplify errors 17.2x, centralized 4.4x; multi-agent lost 39-70% on sequential planning. Not coding. | https://arxiv.org/pdf/2512.08296v1 |
| Union of models (oracle ceiling) | different models solve different instances (SWE-bench 2023; LLVM-Bench union 17.0% vs 1.4-4.0% single) | snippets |

- No published method predicts a coding hybrid's score from single-model scores and then validates the prediction.
- Hybrids landed BELOW the stronger component in 4 of 9 results with a stronger solo baseline.
- Cost fell 31-41% whenever the lead did less of the work; cost is easier to predict than quality.
- Whether the strong part is actually consulted matters most (consult rate).

## Conflicts / unverified
Astra max cost $7.09 / $7.47 / $7.50 by date; Fusion effort label high vs xhigh; Cognition savings claims 27-60% (vendor/secondary);
advisor -11.9% baseline unclear; Opus+Luna Pareto status not stated by AA; SWE-2 free until Oct 15 may flatter Fusion costs;
Handoff Tax uses older models (Opus 4.7, Haiku 4.5, GPT-5.6).
