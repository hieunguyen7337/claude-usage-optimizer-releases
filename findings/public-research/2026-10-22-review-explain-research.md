# R-B: public benchmarks for code review, code explanation/QA, research, and cross-task transfer (researcher, Sonnet, 2026-10-22)

Verdicts: review THIN; explain/QA THIN; research THIN for our catalog (ENOUGH as direction). Transfer: tier order carries
across task types, adjacent pairs and effort curves do not.
Naming: sources call the OpenAI models "GPT-5.6 Sol/Luna" (ReviewBench, OpenRouter, Scale), "GPT-6 Sol/Luna" (Qodo),
"gpt-6.1-sol" (Vals); not verified to be the same model. Rows keep the source's label.

## 1. Code review
| Benchmark | Date | Model | Effort | Score | $/task | Run by | URL |
|---|---|---|---|---|---|---|---|
| Qodo "Which LLM should review your code" (125 PRs, 703 bugs, F1; judge Sonnet 4.6; single reviewer) | 2026-10-12 | Opus 5.5 | high | 56.8 (P 60.2 / R 53.7) | 1.00 | vendor | https://www.qodo.ai/?p=22396 |
| | | Opus 5.5 | xhigh | 54.0 | n/g | vendor | same |
| | | Sonnet 5.5 | high (table) or xhigh (prose) | 54.9 | 0.73 | vendor | same |
| | | Sonnet 5.5 | high (prose) | 51.7 | 0.31 | vendor | same |
| | | Fable 5.1 | high / low | 53.5 / 53.4 | 2.31 (low similar) | vendor | same |
| | | GPT-6 Sol | medium / xhigh | 48.7 / 48.4 | 0.18 / 0.51 | vendor | same |
| | | Gemini 3.8 Flash | high | 47.0 (P 71.0 / R 35.1) | 3.63 | vendor | same |
| | | GPT-6 Astra | high | 46.6 | 1.56 | vendor | same |
| | | GPT-6 Luna | high / xhigh | 42.2 / 41.7 | ~0.02 | vendor | same |
| | | Haiku 4.5 (no 5.5 row) | high / medium | 30.4 / 30.3 | 0.32 | vendor | same |
| ReviewBench (219 PRs, grounded F1, judge Sonnet 5), BenchLM mirror | rows 2026-06-29..10-14 | gpt-5.6-sol in Codex | low / medium / high / xhigh / max | 17.6 / 23.7 / 26.8 / 29.5 / 30.4 | n/g | submitters | https://benchlm.ai/md/benchmarks/reviewbench.md |
| | | gpt-5.6-luna in Codex | max | 27.4 | n/g | submitters | same |
| | | claude-sonnet-5-5 (Klaussy wrapper) | default / include-nits | 35.9 / 44.1 | n/g | submitters | same |
| | | Laude RevEngine Prime (claude-opus-5.5) | n/s | 59.6 (rank 1) | n/g | submitters | same |
| arXiv 2606.15689 (150 samples + Martian offline) | 2026-04-09 | Haiku 4.5 vs Sonnet 4.6 | n/g | F1 0.365 vs 0.343; Martian 36.4 vs 27.1; Haiku 3.2x cheaper | relative | independent | https://arxiv.org/abs/2606.15689 |
| SWE-PRBench (350 PRs, diff-only) | 2026-03-27 | 8 unnamed frontier models | n/g | top four tied 0.147-0.153; rest ≤ 0.113 | n/g | single author | https://arxiv.org/abs/2603.26130 |

- Qodo on effort: "Raising the reasoning level usually increases recall and lowers precision." Fable low ≈ high; Sol medium ≈ xhigh at ~3x cost.
- Cheapest within ~3 of best (Qodo 56.8): Sonnet 5.5 at $0.73 (54.9); Sol medium 8.1 below at $0.18; Luna 14.6 below at $0.02.
- Conflict: Sol flat medium→xhigh in Qodo, steep low→max in ReviewBench (Codex harness); harness is the likely cause (unverified).

## 2. Code explanation and QA
| Benchmark | Date | Model (harness) | Effort | Score | Run by | URL |
|---|---|---|---|---|---|---|
| SWE Atlas Codebase QnA (124 tasks, rubric pass ± CI) | latest note 2026-07-28 | Opus 5 (Claude Code) | xhigh | 63.17 ± 5.01 | Scale | https://labs.scale.com/leaderboard/sweatlas-qna |
| | | Fable 5.1 (Claude Code) | xhigh* | 59.95 ± 4.85 | Scale | same |
| | | GPT 6 Astra (Codex) | xhigh* | 59.14 ± 4.88 | Scale | same |
| | | Gemini 3.8 Flash (mini-SWE-agent) | n/l | 47.04 ± 5.08 | Scale | same |
| | | GPT-5.6-Sol (Codex) | xhigh* | 46.00 ± 5.00 | Scale | same |
| | | Sonnet 4.6 | n/l | 31.20 | Scale | same |
| SWE-QA-Pro (out of 50, older generation) | 2026-03-17 | Sonnet 4.5 / Gemini 2.5 Pro / DeepSeek V3.2 / GPT-4.1 / Devstral-24B with agent | n/a | 40.67 / 39.46 / 38.69 / 38.47 / 37.30 (no agent 25-29) | academic | https://arxiv.org/html/2603.16124v1 |
| Code-QA-Bench (528 tasks, self-reported) | 2026-05-28 | Opus 4.6 / DeepSeek-V4-Pro / Gemini-3.1-Pro | n/g | 0.918 / 0.899 / 0.755 | authors (Opus 4.6 wrote gold) | https://benchmarklist.com/benchmarks/code_qa_bench/ |

*security-filter refusals scored as failures. No Haiku 5.5, Sonnet 5.5 or Luna rows; no per-effort or cost anywhere. Tools narrow
the spread between very different models to ~3 points (SWE-QA-Pro).

## 3. Web and agentic research
| Benchmark | Date | Model | Effort | Score | $/task | Run by | URL |
|---|---|---|---|---|---|---|---|
| FutureSearch Deep Research Bench (169 tasks) | 2026-06-10 | Opus 4.6 | low / medium / high | 0.514 / 0.532 / 0.553 | 0.24 / 0.36 / 0.53 | independent | https://drb.futuresearch.ai |
| | | Sonnet 4.6 | low / high | 0.504 / 0.549 | 0.27 / 0.46 | independent | same |
| | | GPT-5.5 | low / medium / high | 0.487 / 0.496 / 0.540 | 0.23 / 0.31 / 0.36 | independent | same |
| | | Gemini 3 Flash | minimal / low / high | 0.490 / 0.498 / 0.479 | 0.10 / 0.10 / 0.14 | independent | same |
| | | Haiku 4.5 | low | 0.455 | 0.10 | independent | same |
| OpenRouter BrowseComp (production endpoints) | to 2026-08-18 | Opus 5, 25 turns | high | 89.0% | 0.99 | OpenRouter | https://openrouter.ai/benchmarks/browsecomp |
| | | GPT-5.6 Sol, 25 turns | high | 82.4% | 0.50 | OpenRouter | same |
| | | GPT-5.6 Luna, 25 turns | xhigh | 74.0% | 0.099 | OpenRouter | same |
| | | Opus 5 / Sol, 5 turns | high | 66.5 / 65.2 | 0.51 / 0.29 | OpenRouter | same |
| BrowseComp via BenchLM | 2026-10-20 | Sol / Astra / Opus 5 / Sonnet 5 / Luna | n/s | 92.2 / 91.5 / 90.8 / 84.7 / 83.3 | n/g | vendor-reported | https://benchlm.ai/md/benchmarks/browsecomp.md |
| HLE (Scale) | 2026-09-17 | Astra / Fable 5.1 xhigh / Sonnet 5.5 xhigh / Gemini 3.8 Flash | as listed | 54.8 / 46.5 / 46.1 / 44.5 (±2) | n/g | Scale | https://labs.scale.com/leaderboard/humanitys_last_exam |

- Search budget moves BrowseComp more than the model: Opus 5 66.5% at 5 turns vs 89.0% at 25.
- Effort gap on research 1-5 points; Gemini 3 Flash inverted (high < low); HAL reports higher effort lowered accuracy in most runs.

## 4. Do rankings transfer across task types?
| Evidence | Number | Source |
|---|---|---|
| IBM General Agent Evaluation (ICLR 2026), 15 configurations | Spearman between benchmarks median +0.67 (0.44-0.81); BrowseComp-Plus most distinct | https://arxiv.org/html/2602.22953v2 |
| Epoch AI, 15 benchmarks | median correlation 0.79 within category, 0.68 across (inflated across generations) | https://epochai.substack.com/p/benchmark-scores-are-well-correlated |
| Vals, GPT-6.1 Sol ranks | Science 2/22, Terminal-Bench 4.0 7/52, Legal Research 37/82, CyberBench 45/47 | https://www.vals.ai/models/openai_gpt-6.1-sol |
| Scale, 4 models same harness | same order SWE-bench Pro vs QnA, but Gemini 3.1 Pro 46.1 vs 13.5; Test Writing swaps 3.1 Pro and 3 Flash | Scale leaderboards |
| Qodo vs Coding Agent Index (researcher-derived, n=5) | Spearman 0.9 | derived |
| Qodo vs Scale QnA (researcher-derived, n=5) | Spearman 0.6; Sol and Astra swap | derived |

Implication: tier order (Opus/Sonnet > Sol/Astra > Luna > Haiku 4.5) transfers across review, QnA and the coding index; adjacent pairs
and effort curves do not. Treat a review suite as a tier proxy, not a guide to the cheapest effort on other task types.

## Conflicts and unverified
- Qodo's Sonnet rows contradict (table vs prose); Luna 42.2 vs 41.7; dataset 125 PRs/703 bugs vs earlier 100/580.
- ReviewBench read only via the BenchLM mirror; shattered.io lists Codex Sol at 32.3 vs 29.6.
- FutureSearch task count 169 vs 91 on an older page.
- Not found: Haiku 5.5 on any review benchmark with cost; Greptile/Augment model-level data; GAIA/DRB rows for current models;
  Martian's official table; current RepoQA/LongCodeBench leaderboards.
