# R-A: public benchmarks for writing code, fixing bugs, refactoring and writing tests (researcher, Sonnet, 2026-10-22)

Verdicts: features THIN, bug fixes THIN, refactors THIN (nearly NONE), tests NONE. No source gives per-effort cost per task.
Run by: vendor = vendor-run; independent = third party; [secondary] = aggregator repeating someone else.

## (1) New code and features in a repo
| Benchmark / version, date | Model | Effort | Score | $/task | Run by | URL |
|---|---|---|---|---|---|---|
| FrontierCode 1.1 Main, AA article 2026-10-12 | Opus 5.5 | max w/ fallback | 52% | 10.15 | independent (AA) | https://artificialanalysis.ai/articles/frontiercode |
| same | GPT-6.1 Sol | max | 49% | 0.81 | independent | same |
| same | Fable 5.1 | max w/ fallback | 49% | 12.00 | independent | same |
| same | GPT-6 Astra | max | ~47% (inferred from "Sol is 2 pts higher") | 4.22 | independent | same |
| same | GPT-6 Luna | max | 42% | 0.09 | independent | same |
| same | Sonnet 5.5 | max w/ fallback | score not stated | 8.26 | independent | same |
| FrontierCode 1.1, AA live page (undated) | Opus 5.5 | medium / high / xhigh | 57.1 / 54.0 / 53.5 | n/a | independent | https://artificialanalysis.ai/evaluations/frontiercode |
| FrontierCode 1.1 Main, system card via secondary, 2026-10-08 | Sonnet 5.5 | xhigh / max | 52.1 / 46.2 | n/a | vendor [secondary] | https://apidog.com/blog/claude-haiku-5-5-benchmarks/ |
| same | Haiku 5.5 | xhigh / max | 45.8 / 46.4 | n/a | vendor [secondary] | same |
| DeepSWE v1.1 (113 tasks, features and bugs), 2026-09-22 | Gemini 3.8 Flash | high | 74% ±1 | 2.36 | independent (Datacurve) | https://deepswe.datacurve.ai/ |
| same | GPT-6 Astra | xhigh | 74% ±3 | 4.43 | independent | same |
| same | Claude Opus 5 (not 5.5) | max | 74% ±4 | 11.84 | independent | same |
| same | Fable 5 / Sonnet 5 (not 5.x.5) | xhigh / max | 70% / 54% | 13.41 / 26.40 | independent | same |
| same | GPT-5.6 Luna (not GPT-6) | max | 67% ±4 | 0.61 | independent | same |
| DeepSWE per effort, Epoch data through Sep 2026 | Astra | low / medium / high / max / xhigh | 67.0 / 72.8 / 73.2 / 73.2 / 74.1 | n/a | independent | https://llmrun.dev/benchmark/deepswe?show=all |
| same | Gemini 3.8 Flash | medium / high | 71.0 / 73.8 | n/a | independent | same |
| same | Opus 5 (not 5.5) | low / med / high / xhigh / max | 58.1 / 68.9 / 72.8 / 73.2 / 73.7 | n/a | independent | same |
| same | Fable 5 (not 5.1) | low / med / high / xhigh / max | 59.6 / 65.4 / 68.6 / 69.9 / 69.7 | n/a | independent | same |
| same | Sonnet 5 (not 5.5) | low / med / high / xhigh / max | 30.5 / 39.8 / 48.2 / 49.7 / 53.8 | n/a | independent | same |
| DeepSWE, Mercor board (undated) | Opus 5.5 / GPT-6.1 Sol / Astra | max | 72.3 / 72.3 / 72.0 | n/a | independent | https://www.mercor.com/apex/oss-benchmarks/oss-deep-swe-leaderboard/ |
| DeepSWE, OpenAI via Vellum [secondary] | GPT-6.1 Sol / Astra | high | 75.2 / 74.8 | ~1.50 / ~7.70 | vendor | https://www.vellum.ai/md/blog/gpt-6-1-sol-benchmarks-explained |
| SWE-bench CLI, Snorkel (200 tasks, undated) | Opus 5.5 / Fable 5.1 / Astra / Sol 6.1 / Gemini 3.8 Flash | n/a | pass@1 16.6 / 14.5 / 12.4 / 9.8 / 6.3 | per trial 3.17 / n/a / 2.16 / 0.29 / 4.61 | independent | https://snorkel.ai/leaderboard/swe-bench-cli/ |
| LiveCodeBench (Vals, updated 2026-09-01) | Fable 5.1 / Gemini 3.8 Flash / Opus 5 / GPT-5.6 Sol / Sonnet 5 | n/a | 90.5 / 89.5 / 89.0 / 82.6 / 82.4 | n/a | independent | https://www.vals.ai/benchmarks/lcb |

- Effort curves: Astra medium within 1.3 of xhigh, low 7.1 lower. Gemini 3.8 Flash medium 2.8 below high. Opus 5 high 0.9 below max; Fable 5 falls from xhigh to max.
- Cheapest within ~3 points (FrontierCode): GPT-6.1 Sol max 49% at $0.81, 3 points under Opus 5.5 at 12.5x lower cost.
- Cheapest within ~3 points (DeepSWE): Gemini 3.8 Flash high at $2.36, or Astra medium (cost unpublished).

## (2) Bug fixes from an issue
| Benchmark, date | Model | Effort | Score | $/task | Run by | URL |
|---|---|---|---|---|---|---|
| SWE-bench Pro, system cards (aggregator, 2026-09-28) | Opus 5.5 / Sonnet 5.5 / Fable 5.1 | max | 89.9 / 81.3 / 81.2 | n/a | vendor | https://benchmarklist.com/benchmarks/swe_bench_pro/ |
| same, Apidog 2026-10-08 [secondary] | Haiku 5.5 / Sonnet 5.5 | max | 64.8 / 81.3 | n/a | vendor | https://apidog.com/blog/claude-haiku-5-5-benchmarks/ |
| same, launch post 2026-07-09 | Mythos 5 (not in catalog) | low / med / high / xhigh / max | 75.0 / 78.2 / 79.8 / 80.4 / 80.4 | n/a | vendor | benchmarklist |
| SWE-bench Multilingual, system card [secondary] | Sonnet 5.5 / Haiku 5.5 | max | 90.3 / 83.7 | n/a | vendor | Apidog |
| SWE-bench Verified, Vals (mini-SWE-agent), 2026-09-01 | Opus 5 / Fable 5 / GPT-5.6 Sol / Gemini 3.8 Flash / Sonnet 5 | n/a | 97.0 / 95.0 / 96.2 / 80.0 / 79.6 | 1.29 / 2.05 / 1.15 / 2.19 / 1.49 | independent | https://www.vals.ai/benchmarks/swebench |

- Not derivable for the 5.5 generation (vendor max only, no cost). Mythos 5 curve: medium 2.2 below max. Verified is saturated.

## (3) Mechanical edits and refactors
| Benchmark, date | Model | Effort | Score | $/task | Run by | URL |
|---|---|---|---|---|---|---|
| SWE-Atlas Refactoring (Scale via BenchLM, 2026-10-19) | GPT-6 Astra (Codex) | xhigh | 59.0 | n/a | independent | https://benchlm.ai/benchmarks/sweatlasrefactoring |
| same | Fable 5.1 (Claude Code) / Gemini 3.8 Flash (mini-SWE-agent) | xhigh / n/a | 56.7 / 44.8 | n/a | independent | same |
| Aider Polyglot (2025-11-20, EARLIER generation) | gpt-5 high / medium / low | as labelled | 88.0 / 86.7 / 81.3 | 29.08 / 17.69 / 10.37 | independent | https://aider.chat/docs/leaderboards/ |

## (4) Writing tests
| Benchmark, date | Model | Score | Run by | URL |
|---|---|---|---|---|
| SWT-Bench Verified, newest 2026-07-08 | PatchTwin+Guard (GPT-5) | reproduction 82.9% | submitter | https://swtbench.com |
| Diffblue report 2026-03 | Claude Code (Opus 4.6) | 32% line coverage vs Diffblue 81% | vendor, competitor | https://www.diffblue.com/wp-content/uploads/2026/03/Diffblue_AI-Testing-Agents_Benchmark-Report_v4.pdf |

No TestGenEval/TestEval results for any catalog model. Verdict NONE.

## Conflicts and unverified
- FrontierCode Opus 5.5: 52% (AA article, max), 54.4% (Anthropic via computingforgeeks), 54.6% (codingfleet), 57.1% medium (AA live page); harness/date unclear.
- Sonnet 5.5 FrontierCode vendor xhigh 52.1 > max 46.2 (non-monotone).
- DeepSWE Astra cost $4.43 (Datacurve, xhigh) vs ~$7.70 (OpenAI via Vellum, high); Astra max 73.2 (Epoch) vs 72.0 (Mercor).
- DeepSWE lists "gpt-5.6-sol"/"GPT-5.6 Luna" on some boards and "GPT-6.1 Sol" on others; not merged.
- DeepSWE Sonnet 5.5 71.0 from an unattributed snippet: unverified.
- SWE-bench Pro validity: ~30% broken tasks (OpenAI, secondary) and validator FP 8.5% / FN 24.0% (DeepSWE team, secondary): unverified.
- Terminal-Bench 4.0 Sonnet 5.5: 70.6 (Apidog vendor max) vs 61.8 (aggregator); Apidog has per-effort TB4 for Haiku and Sonnet 5.5.
- Not found: SWE-Lancer, SWE-bench Live, Multi-SWE-bench 2026 results; Aider Polyglot for 5.x/6.x; independent Haiku 5.5; GPT-6 family on SWE-bench Pro/Verified/Multilingual; per-effort cost anywhere.
