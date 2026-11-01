# Subscription measurements

2026-10-20. These are account measurements, not promised allowances. List dollars are API-equivalent token prices, not subscription bills. Evidence references below are relative to the originating lab. `LIMITS.md` is the verified summary and takes precedence over earlier reports. The de-identified data behind §1–2 ships in `limits/` (`limits/README.md` says what each file supports), and `../measure/README.md` shows how to rerun the fits on it: the Claude window sizes, model weights and Fable sub-cap and the Codex Pro Lite blocks all regenerate from the bundle. The Plus estimate ships as its fitted tables only: its event file (6.4 MB) is too large for the bundle. The raw session-level extracts stay in the lab, because they carry session identifiers. Machine-readable values and provenance are in `findings.json`. Updated 2026-10-28: a calibration cross-check and the separate-bar question (§1), terra's card and Plus's per-model ranges (§2), a Gemini window estimate and whether each plan charges in proportion to API prices (§3), and new sections §12–15. Updated 2026-10-29: how long work takes and how well it can be estimated (§16). Updated 2026-10-31: the Pro Lite doubling (§2), the credit basis of §18, and plan subsidy factors (§19).

## 1. Claude Max 20x

Sonnet's C2 block anchors the shared windows. H1 charges every token type at list; H2 makes cache reads free. Rounding intervals are open, not statistical confidence intervals.

| Window | H1 list dollars (interval) | H1 dollars per 1% | H2 list dollars (interval) | Evidence |
|---|---:|---:|---:|---|
| Weekly | 1,525 (1,017–3,050) | 15.25 (10.17–30.50) | 1,483 (989–2,966) | LIMITS.md:51; claude/probes_fit/REPORT_C.md:26,66 |
| 5h | 254 (235–277) | 2.54 (2.35–2.77) | 247 (228–270) | LIMITS.md:52; claude/probes_fit/REPORT_C.md:26,65 |

The shared meters cover Sonnet, Opus and Haiku. Model weights mean meter consumed per list dollar, relative to Sonnet; these are block comparisons, with other local traffic included.

| Model | 5h weight (interval) | Weekly weight (interval) | Evidence |
|---|---:|---:|---|
| Sonnet | 1 (anchor) | 1 (anchor) | claude/probes_fit/REPORT_C.md:40 |
| Opus | 0.95 (0.82–1.09) | 0.67 (0.22–2.00) | LIMITS.md:53; claude/probes_fit/REPORT_C.md:41 |
| Haiku | 1.72 (0–3.75), unresolved | No point estimate | LIMITS.md:53; claude/probes_fit/REPORT_C.md:39 |
| Fable | 2.06 (1.82–2.35) | 1.69 (0.75–4.49) | LIMITS.md:54; claude/probes_fit/REPORT_C.md:42 |

Fable opens `seven_day_overage_included`: about $531 list/week ($443–664), based on $26.57 moving that meter from 0 to 5%. This is a sub-cap drawn from the shared week, not extra room. Anthropic says up to 50% of the shared weekly limit can go to Fable. Assuming exactly half, the separate meter implies a weekly weight of 1.43 (1.29–1.58), conditional on the Sonnet point estimate. [INFERRED; LIMITS.md:54; claude/probes_fit/REPORT_C.md:55–56]

Cache reads remain unresolved: the fitted list-price weight is 0.36, but the whole-percent readings allow anything from 0 to 1. [INFERRED; LIMITS.md:55; claude/probes_fit/REPORT_C.md:46]

There is no per-request charge worth counting: 150 tiny Haiku calls moved neither meter. The point-calibrated bound is below $0.017/call; allowing calibration rounding gives the more conservative $0.0185/call bound. This does not prove a literal zero fee. [INFERRED; LIMITS.md:56; claude/probes_fit/REPORT_C.md:50]

Extra usage is off on this account (`org_level_disabled`); no reserve is available after the cap. [OBSERVED LIMITS.md:49]

**Cross-check (2026-10-28).** A second machine's `turn-meter calibrate`, from a main loop that is almost all Opus, gives $22.3 list per weekly 1%. The Opus weekly weight predicts $15.25 / 0.67 = $22.8, so the two methods agree: the week holds about $1.5k of Sonnet or $2.2–2.3k of Opus at list. SemiAnalysis's all-model figure (≈ $2.7k a week, §3) sits above both. [INFERRED from the calibration and the weights above]

**One bar per window, plus Fable's.** Every model draws on the same 5h and weekly bars. Fable alone has a second weekly bar (`seven_day_overage_included`), which is a sub-cap inside the shared week. No separate Opus or Sonnet bar on Max has been seen: one older Claude Code help page describes one but contradicts itself, and SemiAnalysis describes only the Fable bar. [INFERRED from the sources in §3]

## 2. Codex Pro Lite and Plus

Pro Lite has one shared weekly pool, no 5h window. Before its doubling on 2026-10-29 it held about 8,400 card credits (7,800–9,200), approximately $340 API value ($312–368; exact point conversion $336). At $0.04 per credit this was about 84 credits per 1% (78–92) before the doubling, and about 168 since (below). Astra-only controlled blocks are the primary estimate. Pooling P1–P4 while assuming sol follows the card instead gives 7,870 credits (7,400–8,400). [INFERRED; LIMITS.md:4,13–18]

The official card below is credits per million tokens, in input / cached-input / output order. Cached input is a subset of input; subtract it before charging uncached input. Reasoning output is already in output. [OBSERVED LIMITS.md:28–29; codex/REPORT.md:46]

| Model | Input | Cached | Output | Evidence |
|---|---:|---:|---:|---|
| gpt-6-astra | 250 | 25 | 1,250 | LIMITS.md:29; codex/rates.json:5 |
| gpt-6.1-sol | 50 | 2.5 | 250 | LIMITS.md:29; codex/rates.json:6 |
| gpt-6.1-terra | 25 | 1.25 | 125 | Official card, 2026-10-26; `arms.json` `lanes.terra` |
| gpt-6-luna | 2.5 | 0.25 | 12.5 | LIMITS.md:29; codex/rates.json:8 |

Token-type charging is consistent with the card within about ±25%. Sol's charge relative to astra is 1.19× card (1.09–1.30) from integer crossings, or 1.36× (0.94–1.85) at block level. Thus 1.19–1.36× describes two estimators, not an uncertainty interval. Luna is unmeasurable here: 14.6 card credits moved no whole point, bounding its factor below 5.8 only. [INFERRED; LIMITS.md:16–17]

Plus is about 1,450 credits/week (about $58), with a separate 5h window whose size was not fitted. Three clean weeks give 1,451, 1,447 and 1,383 credits (two reached 91–100% of the window, the third 74%, not 91–100% as the lab summary says; `limits/codex/fit_a_b.csv`), and the clean high-use windows support 1,360–1,490 credits ($54–60); passive local usage is still a lower bound if other devices consume the pool. Before the doubling Pro Lite was about 5.8× Plus, and since it about 11.6×. [INFERRED; LIMITS.md:19,27; codex/REPORT.md:8]

OpenAI's Plus page lists 5h message ranges per model: luna 350–3,000, terra 35–285, sol 15–160, astra 5–45. These are the one shared pool expressed per model, not separate bars; the live `account/rateLimits/read` returns a single bucket on both plans. [OBSERVED 2026-10-28]

Terra's card price is not yet confirmed on the meter. During the 2026-10-28 Suite R run (§12) the week moved about 37 card credits per 1% against the 84 a Pro Lite week implies, but another machine was using Codex at the same time, so the card price stands until a clean block measures it. [OBSERVED meter readings; INFERRED cause]

What a Pro Lite week buys if each model follows the card, spending entirely on one token type:

| Model | Output tokens | Uncached input tokens | Evidence |
|---|---:|---:|---|
| astra | 6.7M | 34M | LIMITS.md:39 |
| sol | 34M | 168M | LIMITS.md:40 |
| luna | 670M | 3.4B | LIMITS.md:41 |

These are rounded card scenarios, not guaranteed yields; the measured sol premium reduces its yield. [INFERRED; LIMITS.md:17,35–41]

**The Pro Lite doubling (2026-10-29).** Tibo (@thsottiaux, OpenAI) posted on X at 2026-10-29 16:56:07 UTC that usage limits were doubled for the Pro 100/200/500 tiers and Business Premium, effective that day, with no end date given. Plus is not named (https://x.com/thsottiaux/status/2115850175868727621). The meter agrees: the window fell from 6% to 3% between 2026-10-29 04:02 and 10-30 00:24 UTC, on the window that resets 2026-11-04T06:42Z, with no spend between. So a Pro Lite week is about 16,800 credits (about 168 per 1%) while the doubling lasts. The 8,400 measured before it stays as the pre-doubling measurement. Plus stays at about 1,450. Per credit, Plus costs about 2.3 times Pro Lite (72.5 against 168 credits per dollar); a Pro Lite week holds about 11.6 times a Plus week's credits (168 against 14.5 per 1%). [OBSERVED meter reading; the doubling is as stated by its source]

**Reset credits.** A banked reset sets the weekly window back to 0%, so it is worth exactly the share used when it is redeemed: about 8,000 credits at 96% on Pro Lite before the doubling (about 16,000 since), about 1,400 on Plus. Redeem one only when the window is near its limit, work is queued to spend the new room before the natural reset, and the plan is still the larger one; a credit redeemed early, or left unused at its expiry (30 days after it is granted), returns nothing. [INFERRED]

**An unscheduled restart.** On 2026-10-20 at 06:32 UTC our Pro Lite week restarted 5.8 days early. Within 27 seconds the live reading went from 96% (`resets_at` 2026-10-26 01:32 UTC) to 0%, and the new `resets_at` was the restart time plus exactly 7 days. The account's reset-credit count stayed at 2 before and after, so no banked credit was spent. [OBSERVED: `usage.before`/`usage.after` in the lane runs either side of the restart] So a restart starts a fresh 7-day clock instead of keeping the old schedule. Restarts like this cannot be predicted, which is one more reason to redeem a credit only when the window is near its limit and work is queued. Whether redeeming a credit also restarts the clock is still unmeasured: compare `resets_at` in `usage-status --json` before and after the next redemption. [INFERRED]

## 3. Contrast with outside sources

Numerical claims below reproduce the verified summary's contrasts; dates are source dates. Publisher article URLs were recovered by web lookup. The finopsllm source remains unavailable.

| Source and date | Weekly list value | 5h | Cache reads | Comparison and evidence |
|---|---|---|---|---|
| Our controlled Claude, 2026-10-19 | $1,525 ($1,017–3,050) | $254 ($235–277) | Weight 0–1 | LIMITS.md:63 |
| [Wokey](https://wokey.ai/claude-pro-vs-max), 2026-10-19, n=17 | $1,643 ($1,547–1,751) | $205 | Barely count | Weekly agrees; 5h is 19% below ours.  LIMITS.md:64 |
| [SemiAnalysis](https://newsletter.semianalysis.com/p/anthropic-subscriptions-offer-5x), 2026-10-05 | $11.7k/month, ≈ $2.7k/week by our division; Fable $2,485/month ≈ $574/week | — | Free if 500M reads leave meter still | Fable cap is 8% above ours; all-model total higher. Chart unreadable on 2026-10-20. LIMITS.md:65 |
| [Anthropic](https://support.claude.com/en/articles/15424964), 2026-09-02; update 2026-09-22 | Fable up to 50% of shared week | Limits raised, no sizes | — | Official, no dollar sizes. Separate-window help: [12429409](https://support.claude.com/en/articles/12429409). LIMITS.md:48,54,66 |
| [Classmethod](https://dev.classmethod.jp/articles/claude-max-20x-weekly-limit-not-4x/), 2026-08-20 | $3.4–3.9k in +50% promotion; ≈ $2.3–2.6k without | — | Weight 0–0.12 | Higher weekly point. LIMITS.md:67 |
| U2 history, superseded | $11–46 per 1% | $2.8–4.3 per 1% | Regression 1.35 ± 0.32 | Unidentified; controlled cache test remains unresolved. LIMITS.md:68 |

| Source and date | Codex claim | Comparison and evidence |
|---|---|---|
| [inventivehq](https://inventivehq.com/blog/codex-subscription-usage-measured), 2026-10-04 | Pro 5x $330–380/week (8,250–9,500 credits); projected Plus $66 (1,650 credits) | Agrees with our Pro Lite and near our Plus. LIMITS.md:24–25 |
| finopsllm, date and original URL unavailable | $100 Pro week ≈ $175 API | Could not be found again; contradicted. LIMITS.md:26 |
| [Official card](https://learn.chatgpt.com/docs/pricing), checked 2026-10-15 | Pro has no 5h window; weekly limits may apply, no size | No independent weekly-size measurement since 2026-09-01 in the 2026-10-20 researcher sweep. LIMITS.md:28–31 |

**Gemini (Google AI Pro via agy).** agy reports separate pools for Gemini and for third-party models (Claude 4.6, GPT-OSS), each with a 5h and a weekly window; no official sizes are published. agentpedia (July 2026) gives about 250 units per 5h and 2,800 per week per model family. Third-party pool access ends 2026-11-02. [OBSERVED LIMITS.md:70–74] On 2026-10-20 its windows read 0–4% (`usage-status`). [OBSERVED]

*Window estimate (2026-10-28).* agy's meter reads fractional percents, so the 2026-10-24 classification evals (§14) sized the Gemini pool: about 100M gemini-3.8-flash tokens a week, about $80 at the $0.75 / $3.75 per 1M list price (about one Codex Plus week), and about 17–36M tokens per 5h. Other Gemini use during those calls would make the real window larger, so these are lower bounds. [INFERRED from `usage.before`/`usage.after` on the eval runs] It draws on no Claude or Codex meter and sat almost unused, so for work that may leave the machine it is the cheapest lane we have.

*Data terms.* Antigravity runs under Google's consumer terms: interactions may be kept, used to improve Google's models and read by human reviewers, with an opt-out in its settings (keep the training toggle off, POLICY Data). That is why Suite R items, which are private code, never run on gemini, and why gemini has almost no review or code-writing score here. Give it non-sensitive work only.

**Does each plan charge in proportion to API prices (2026-10-28)?**

| Plan | Proportional? | Evidence |
|---|---|---|
| Codex | Yes, by design: one pool drawn down by a per-model card, luna 1 : terra 10 : sol 20 : astra 100, about $0.04 of API value per credit | §2; sol measured at 1.19–1.36× its card relative to astra; luna and terra unmeasured |
| Claude | No: per list dollar, Opus draws 0.67× Sonnet on the week and 0.95× on 5h, Fable 1.69× and 2.06×, cache reads about 0.36× | §1 weights; the calibration cross-check above; SemiAnalysis also reports Claude departing from API ratios |
| Gemini | Yes, officially: Gemini models share one pool drawn down at API prices | Google AI Pro help pages, 2026-10-28 |

So per list dollar, Opus is the best value on Max and Fable the worst. On Codex the card is the price, and on Gemini the API price is.

U1's Pro Lite 2,700–3,400 estimate is superseded: non-local use moved the meter without local rollouts. The earlier Claude passive estimate was $21–25 per weekly point and $3.8 per 5h point; the latter is 37–62% above the controlled interval, unexplained. The controlled report quotes older line references into an earlier LIMITS revision; use today's summary. [OBSERVED LIMITS.md:22–23,57; codex/REPORT.md:9; claude/probes_fit/REPORT_C.md:68–71]

## 4. Machine limits

The 2026-10-19 crash exposed a 1,024-task user cgroup. A Codex lane takes about 80–90 tasks; `TOKIO_WORKER_THREADS` is ignored. Keep at most about 6 Codex lanes running together and leave headroom for the main session and tools. `lane` now waits for headroom and returns BUSY 70 when it cannot obtain it. These machine-specific observations come from the task brief and `briefs/K3a-lane-usage-and-pids.md:9,76–90`, not the subscription reports. [OBSERVED briefs/K3a-lane-usage-and-pids.md:9,76–90; task brief §3.3; INFERRED concurrency recommendation]

On a busy login node a cold `codex app-server` start took 7.7–24 s before it answered the meter read, against 1.2 s warm. With the old 8 s limit every background refresh for ten hours failed and the statusline showed a stale rollout reading; from 2026-10-20.2 the background refresh waits 30 s and an inline read 15 s, and a server that dies before answering is reported as `exited`, not `timeout`. [OBSERVED 2026-10-20 probes on the originating machine]

## 5. Model × effort results on our review suite

2026-10-20. Suite R is 36 review items cut from accepted commits of one Python research codebase: 30 items carry 38 planted defects and 6 are clean controls. Every model ran at every effort through its own lane with the same brief. The Codex arms ran more than once: luna four times, sol and astra xhigh and max three times, and the other astra efforts twice. Fable 5.1 ran through the opus lane (`-m claude-fable-5-1`), and its `max` arm was stopped at 18 items to save the week. The items and the reviewers' comments stay with the originating lab because they are that project's code. Everything else ships here:
- `suite-r/outcomes.jsonl`: every run of every arm on every item (2,412 rows), with the defect ids found and missed, false alarms, format failures, tokens, cost and window shares, and no code, paths or comment text;
- `suite-r/stats.md` (per arm, pooled, effort curves, McNemar tests, replicates, Pareto), `suite-r/compare.md` (against `public.json`), `suite-r/priors.json` (the measured priors in `arms.json`), `suite-r/panels.md` (pairs and triples of reviewers) and `suite-r/replicates.md` (how much repeat runs of one arm differ, and a held-out check of the panel picks).

`lane-bench stats|compare|priors|panels|replicates --outcomes suite-r/outcomes.jsonl` regenerates the shipped files from the bundle alone; stats, compare and priors were checked identical to the originals. `lane-bench grade|export` builds the same from any suite laid out as `../measure/SUITE.md` describes.

Recall is planted defects found ÷ 38; a finding matches a defect in the same file within 5 lines, one to one. With 38 defects a single arm's 95% interval is about ±0.1 (Wilson), so smaller gaps between single arms are noise. Claude costs are list dollars per item (weekly share ≈ $ ÷ 15.25 %, 5h share ≈ $ × model weight ÷ 2.54 %, weights from §1); Codex costs are Pro Lite credits per item (8,400 a week).

| Model | low | medium | high | xhigh | max | Cost per item, low → max |
|---|---:|---:|---:|---:|---:|---|
| Haiku 5.5 | 0.89 | 0.95 | 0.95 | 1.00 | 0.97 | $0.008 → $0.16 |
| Sonnet 5.5 | 0.84 | 0.87 | 0.92 | 0.95 | 0.97 | $0.11 → $0.94 |
| Opus 5.5 | 0.92 | 0.95 | 0.95 | 0.95 | 1.00 | $0.23 → $1.43 |
| Fable 5.1 | 0.95 | 0.97 | 0.92 | 0.95 | 22/24 on its 18 items | $0.72 → $2.57 |
| sol (3 runs) | 0.84 | 0.88 | 0.90 | 0.92 | 0.95 | 1.6 → 3.2 credits |
| terra (1 run, 2026-10-28, §12) | 0.92 | 0.92 | 0.92 | 28/30 on its 23 items | not run | 0.70 → 1.32 credits (low → xhigh) |
| astra (2–3 runs) | 0.92 | 0.89 | 0.91 | 0.94 | 0.98 | 9.0 → 18.7 credits |
| luna (4 runs) | 0.39 | 0.57 | 0.72 | 0.78 | 0.82 | 0.10 → 0.21 credits |

[OBSERVED suite-r/stats.md, pooled table and effort curves]

1. **The suite is near its ceiling for every model but luna.** 29 of the 34 complete model-effort rows find at least 84% of the defects; the five below are all luna. None of the 27 adjacent-effort McNemar tests reaches p < 0.05 (the smallest is luna high → xhigh, p = 0.07). For review, effort above medium buys little recall that this suite can detect, and the suite separates models on cost far better than on quality. [OBSERVED suite-r/stats.md]
2. **Higher effort lowers the Claude models' v1 precision; once real bugs count (§8), only Haiku's still falls.** From low to max, precision falls from 0.79 to 0.47 for Haiku, 0.97 to 0.79 for Sonnet and 0.80 to 0.59 for Opus; the Codex models stay between 0.69 and 0.79 at every effort. The picker scores *usable* items (a planted item with a defect found and at most 2 false alarms; a control with at most 1), so this is priced into the measured priors. [OBSERVED suite-r/stats.md]
3. **The cheapest good reviewers.** On Claude, Haiku low and medium ($0.008–0.011 an item) match Sonnet and Opus within noise at 1/10–1/14 of Sonnet's and 1/26–1/28 of Opus's price per item. On Codex, sol low and medium (1.6–1.9 credits) are the steady choice; luna xhigh costs a tenth of that but misses one defect in five. astra costs about 5x sol for the same recall. [OBSERVED suite-r/stats.md; INFERRED ratios]
4. **Fable 5.1 is no better than Opus here and costs far more.** At low to xhigh its recall (0.92–0.97) equals Opus's within noise, at about 3x Opus's list price per item at each effort. With its 5h weight of 2.06, one Fable xhigh item takes about 1.4% of the 5h window against 0.21% for Opus xhigh. Fable max cost $2.57 an item (about 2.1% of the 5h window) and found 22 of the 24 defects in its 18 items, where Opus max found 24 and Sonnet max 23 on the same items. Fable is not in the catalog, and nothing here argues for adding it for review. [OBSERVED suite-r/stats.md; INFERRED 5h shares from §1 weights]
5. **luna is the one model where effort decides, and its single runs are noisy.** Pooled over four runs, recall climbs from 0.39 at low to 0.78 at xhigh and 0.82 at max. Within one arm, a single run's recall moved by up to 0.24 (luna low ranged from 0.26 to 0.50). Runs also agree poorly on which defects they find. Of the defects a luna arm found in any run, only 15–59% were found in every run, against 91–100% for sol and astra. 47 of luna's 720 findings files (6.5%) were not valid JSONL — objects split across lines, raw newlines inside strings, a stray heredoc `EOF'` — against 1 of 1,674 for every other model together. [OBSERVED suite-r/stats.md, replicates.md; INFERRED heredoc cause, from the broken files]
6. **Two cheap reviewers beat one dear one, and Haiku is the partner.** Every defect was found by at least one arm, but the hardest (item 018, D1) by only 6 of the 67 runs: Haiku medium, Haiku xhigh, Opus max, one of luna xhigh's four runs, one of luna max's four and one of astra max's three. Sonnet, sol and Fable missed it every time. Over all 6,579 pairs and triples of the 34 complete arms, the cheapest panels on the recall-cost frontier are Haiku medium alone (0.95, $0.011 an item), Haiku medium with luna high (0.97) and Haiku medium with Haiku high (1.00, about $0.028 an item), against $0.05 for Haiku xhigh alone and $1.43 for Opus max. A Haiku arm is the best second reviewer for 32 of the 34 arms (medium for 16, xhigh for 15, high for 1), sol, Sonnet, astra, Opus and Fable included. It adds 0.02–0.16 recall to the models other than luna and 0.18–0.61 to luna. Summed false alarms grow with each member (0.39 an item for Haiku medium, 1.2 for the 1.00 pair). [OBSERVED suite-r/panels.md, panels.json, outcomes.jsonl; INFERRED $ from weekly shares × $15.25 per 1%]
7. **Running the same model twice is a weak second review.** A second run of the same arm adds 0.09–0.17 recall for luna, so two luna runs reach 0.56–0.92. For sol and astra it adds 0–0.04, because their runs mostly find the same defects. Haiku medium does better as the second reviewer. With a luna arm it reaches 0.95–0.98, for 1.0–1.5x the cost of a second luna run. With sol or astra it reaches 0.99–1.00, at about half the cost of a second run. Panels picked on runs 1–2 also held up on the held-out runs 3–4. Every pick still met its recall target, and its luna members did better held out, not worse (+0.07 and +0.12 alone, unchanged in pairs). The Claude arms ran once, so their run-to-run spread is unmeasured, and the all-Claude picks (Haiku medium with Haiku high, Haiku xhigh alone) are not tested by this check. [OBSERVED suite-r/replicates.md, panels.json; INFERRED cost ratios from cost points per item]

**Against public numbers** (Spearman over distinct model-effort points; `suite-r/compare.md`):

| Our measure | Public measure | ρ | n |
|---|---|---:|---:|
| $ per item | AA intelligence index, $ per task | 0.98 | 34 |
| $ per item | AA coding-agent index, $ per task | 0.96 | 18 |
| Recall | AA intelligence index score | 0.62 | 34 |
| Recall | AA coding-agent index | 0.25 | 18 |
| Recall | Terminal-Bench 4 hard (AA) | 0.37 | 18 |
| $ per item | AA intelligence index v5.0, $ per task (terra and sol per effort, added 2026-10-28) | 0.93 | 8 |
| Recall | AA intelligence index v5.0 score (same points) | 0.37 | 8 |

Public prices carry over almost exactly: an AA coding-agent task costs about 11x one of our review items and an AA intelligence-index task about 4x, at every model. Public quality rankings carry over weakly: the intelligence-index correlation comes mostly from luna's steep effort curve, and the coding-agent index barely orders our review results. Hence the kit's rule that benchmarks set the prior and our own runs decide. [OBSERVED suite-r/compare.md]

**What changed in the kit.** Every catalog arm in `arms.json` now carries a `measured.review` block from this sweep, pooled over replicates. The Codex blocks were measured on Pro Lite, and `lane-stats` rescales them by `plan_scale` on Plus. Haiku low and medium now serve the review class; luna high no longer does (pooled recall 0.72 over four runs, against 0.78 and 0.82 for xhigh and max). The retirements of sol max and Haiku max stand: neither gains recall over xhigh here, at a higher price.

**Limits of this evidence.** One suite, one codebase, one class (review), single runs for the Claude models. Planted defects are smaller and more local than real bugs, and the ceiling hides quality differences among the strong models. Weekly shares use weight 1 for every Claude model, because the weekly weights in §1 are unresolved; if Fable's inferred weekly weight of 1.43 holds, its weekly cost is 43% higher than shown. Fable max is a partial arm and is excluded from the curves, tests, comparison, priors and panels. The panel winners were picked from 6,579 candidates on the same 38 defects, and the Claude arms are single runs, so the best panels' recall may be optimistic. The held-out check in finding 7 found no such loss for picks with a Codex member, but it cannot test the all-Claude picks.

## 6. Every model at every effort: capability and usage

2026-10-20. This section brings together, for each model and effort, what we have measured about how well it works and what it costs.
- **Capability** is Suite R review recall and precision (§5), pooled over runs.
- **Usage** is the list price of one review item and how many such items one full window would hold. That count is a ceiling for this kind of work, not a forecast.

The Claude weekly column uses weight 1 for every model, because the weekly weights are unresolved (§1). The 5h column uses §1's 5h weights. The Codex columns follow the card (§2). `suite-r/by-arm.md` adds the intervals, false alarms, run-to-run range and stable share, tokens, wall time and every matched public number. To regenerate it, run `lane-bench summary --outcomes suite-r/outcomes.jsonl --public public.json --arms-json ../arms.json --out-dir <dir>`.

**Claude** (Max 20x, about $1,525 a week and $254 per 5h; one run per arm)

| Model | Effort | Recall | Precision | List $ per item | Items per week | Items per 5h |
|---|---|---:|---:|---:|---:|---:|
| Haiku 5.5 | low | 0.89 | 0.79 | 0.008 | 186,000 | 18,000 |
| | medium | 0.95 | 0.72 | 0.011 | 136,000 | 13,100 |
| | high | 0.95 | 0.55 | 0.017 | 91,000 | 8,810 |
| | xhigh | 1.00 | 0.51 | 0.051 | 30,100 | 2,920 |
| | max | 0.97 | 0.47 | 0.16 | 9,450 | 915 |
| Sonnet 5.5 | low | 0.84 | 0.97 | 0.11 | 13,500 | 2,240 |
| | medium | 0.87 | 0.92 | 0.12 | 12,900 | 2,150 |
| | high | 0.92 | 0.85 | 0.14 | 11,000 | 1,840 |
| | xhigh | 0.95 | 0.69 | 0.24 | 6,450 | 1,070 |
| | max | 0.97 | 0.79 | 0.94 | 1,620 | 269 |
| Opus 5.5 | low | 0.92 | 0.80 | 0.23 | 6,650 | 1,170 |
| | medium | 0.95 | 0.69 | 0.29 | 5,290 | 928 |
| | high | 0.95 | 0.63 | 0.35 | 4,410 | 773 |
| | xhigh | 0.95 | 0.60 | 0.56 | 2,700 | 474 |
| | max | 1.00 | 0.59 | 1.43 | 1,060 | 186 |
| Fable 5.1 | low | 0.95 | 0.82 | 0.72 | 2,120 (1,060) | 171 |
| | medium | 0.97 | 0.69 | 0.81 | 1,880 (940) | 152 |
| | high | 0.92 | 0.69 | 1.09 | 1,400 (699) | 113 |
| | xhigh | 0.95 | 0.69 | 1.70 | 895 (447) | 72 |
| | max | 22 of 24 on 18 items | 0.69 | 2.57 | 594 (297) | 48 |

Fable's bracketed figure is what fits under its 50% cap on the shared week.

**Codex** (Pro Lite, about 8,400 credits a week; Plus about 1,450; 1 credit is about $0.04)

| Model | Effort | Runs | Recall | Precision | Credits per item | API $ per item | Items per Pro Lite week | Items per Plus week |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| luna | low | 4 | 0.39 | 0.75 | 0.13 | 0.005 | 66,200 | 11,400 |
| | medium | 4 | 0.57 | 0.76 | 0.10 | 0.004 | 84,500 | 14,600 |
| | high | 4 | 0.72 | 0.77 | 0.14 | 0.006 | 59,500 | 10,300 |
| | xhigh | 4 | 0.78 | 0.72 | 0.19 | 0.008 | 43,700 | 7,540 |
| | max | 4 | 0.82 | 0.69 | 0.21 | 0.008 | 40,700 | 7,020 |
| sol | low | 3 | 0.84 | 0.77 | 1.6 | 0.065 | 5,210 | 899 |
| | medium | 3 | 0.88 | 0.78 | 1.9 | 0.077 | 4,340 | 749 |
| | high | 3 | 0.90 | 0.73 | 2.4 | 0.097 | 3,470 | 599 |
| | xhigh | 3 | 0.92 | 0.74 | 2.9 | 0.12 | 2,880 | 498 |
| | max | 3 | 0.95 | 0.76 | 3.2 | 0.13 | 2,640 | 456 |
| terra | low | 1 | 0.92 | 0.73 | 0.70 | 0.028 | 12,100 | 2,080 |
| | medium | 1 | 0.92 | 0.67 | 0.80 | 0.032 | 10,400 | 1,800 |
| | high | 1 | 0.92 | 0.64 | 0.91 | 0.037 | 9,170 | 1,580 |
| | xhigh | partial | 28/30 on 23 items | 0.57 | 1.32 | 0.053 | 6,330 | 1,090 |
| astra | low | 2 | 0.92 | 0.76 | 9.0 | 0.36 | 931 | 161 |
| | medium | 2 | 0.89 | 0.79 | 9.3 | 0.37 | 899 | 155 |
| | high | 2 | 0.91 | 0.76 | 12.0 | 0.48 | 701 | 121 |
| | xhigh | 3 | 0.94 | 0.74 | 16.7 | 0.67 | 503 | 87 |
| | max | 3 | 0.98 | 0.77 | 18.7 | 0.75 | 449 | 78 |

The Plus column ignores Plus's 5h window, whose size is not fitted.
- Retired: Haiku max, sol max, and terra xhigh and max (2026-10-28, §12).
- Run for the sweep but not offered by the picker: Sonnet low, Opus low, astra low to high, and every Fable effort.
- Not run on Suite R: gemini low, medium and high, glm, and terra max (approved; paused by the user).

[OBSERVED suite-r/by-arm.json; INFERRED items per window, from the window sizes in §1 and §2]

**What each model showed.** Real units are this machine's reviewed lane runs up to 2026-10-20, from `lane-stats report`. There are 33 in all, one or two per arm: too few to rank arms. Their cost depends on each unit's size, so it is not compared here. Public scores are the Artificial Analysis intelligence index (II), coding-agent index (CAI) and Terminal-Bench 4 hard (TB4), from `public.json`.

- **Haiku 5.5.**
  - *Capability:*
    - 0.89–1.00 recall at every effort, at the lowest price of any Claude model.
    - xhigh found all 38 defects, and medium and xhigh were two of the six runs to find the hardest one.
    - Effort buys unmatched findings, most of them real unplanted bugs (§8): 0.23 per planted item at low, 0.9–1.2 at high to max, so precision falls from 0.79 to 0.47.
    - It is the best second reviewer for 32 of 34 arms (§5, finding 6).
  - *Public:* II 29–43, CAI 28–41, TB4 6–30.
  - *Usage:*
    - $0.008–0.16 an item, so a week holds about 186,000 low items.
    - Its 5h weight is unresolved (1.72, 0–3.75), and its weekly weight is unmeasured.
  - *Real units:* 7 reviewed, all accepted.
  - max is retired: no recall over xhigh, at 3x the price.
- **Sonnet 5.5.**
  - *Capability:*
    - 0.84–0.97, rising with effort.
    - The most precise reviewer at low and medium: 0.97 and 0.92, with 0.03–0.10 false alarms per planted item.
    - Missed the hardest defect at every effort.
  - *Public:* II 36–56, CAI 42–68 (the highest in the table, at max), TB4 25–66.
  - *Usage:* $0.11–0.94 an item. Sonnet is the anchor of every Claude weight, 1 on both meters.
  - *Real units:* 5 reviewed, all usable: 2 accepted, 3 after a small fix.
- **Opus 5.5.**
  - *Capability:*
    - 0.92–1.00.
    - max found all 38, including the hardest.
    - Precision falls from 0.80 at low to 0.59 at max.
  - *Public:* II 42–58, CAI 66 and TB4 63 at max.
  - *Usage:*
    - $0.23–1.43 an item.
    - 5h weight 0.95 (0.82–1.09); weekly weight 0.67 (0.22–2.00), unresolved.
  - *Real units:* none as a worker, since it is the main session.
- **Fable 5.1.**
  - *Capability:*
    - 0.92–0.97 from low to xhigh, equal to Opus within noise.
    - max found 22 of the 24 defects on its 18 items, held there to save the week.
    - Missed the hardest defect.
  - *Public:* II 47–53, and CAI 62 and TB4 58 at max.
  - *Usage:*
    - $0.72–2.57 an item: about 3x Opus at low to xhigh, and 1.8x at max.
    - Its 5h weight is 2.06, so one xhigh item takes 1.4% of the 5h window.
    - It may use at most half the week, a sub-cap of about $531 (§1).
  - It is not in the catalog.
- **luna** (gpt-6-luna).
  - *Capability:*
    - The one model where effort decides: 0.39, 0.57, 0.72, 0.78 and 0.82 from low to max, over four runs each.
    - Single runs are noisy: luna low ranged from 0.26 to 0.50.
    - Runs are inconsistent: only 15–59% of what an arm found was found in every run.
    - 6.5% of its findings files were broken.
    - Two of its 20 runs found the hardest defect.
  - *Public:* II 22–38, and CAI 41 and TB4 15 at max.
  - *Usage:*
    - The cheapest per item of any model, at 0.10–0.21 credits (under $0.01).
    - A Pro Lite week holds 41,000–84,000 items, and a Plus week 7,000–14,600.
    - Its charged rate is unmeasured: it never moved the meter a whole point, which bounds it below 5.8x the card.
  - *Real units:* 10 reviewed, 8 usable, 5 accepted as returned.
- **sol** (gpt-6.1-sol).
  - *Capability:*
    - 0.84–0.95, and repeatable: 91–95% of what an arm found was found in every run.
    - Missed the hardest defect in all 15 runs.
  - *Public:* II 42–52, CAI 57–63, TB4 49–55.
  - *Usage:*
    - 1.6–3.2 credits ($0.06–0.13) an item.
    - Charged 1.19–1.36x the card relative to astra (§2).
    - A Pro Lite week holds 2,600–5,200 items, and a Plus week 460–900.
  - *Real units:* 6 reviewed, 4 usable.
  - max is retired.
- **astra** (gpt-6-astra).
  - *Capability:*
    - 0.89–0.98, and repeatable: 92–100% stable.
    - One of max's three runs found all 38, including the hardest.
  - *Public:* II 46–53, and CAI 62 and TB4 56 at max.
  - *Usage:*
    - 9.0–18.7 credits ($0.36–0.75) an item, about 5x sol for the same recall.
    - A Pro Lite week holds 450–930 items, and a Plus week 78–161.
    - Its blocks anchor the Pro Lite window size.
  - *Real units:* none reviewed yet.
  - Only xhigh and max are in the catalog.
- **Gemini 3.8 Flash** (agy; low, medium and high).
  - *Capability:* not run on Suite R, because the originating lab keeps that project's code off the Gemini and glm lanes.
  - *Public:* CAI 42 (unverified), TB4 15.
  - *Usage:* one real unit took 0.7–0.8% of agy's Gemini week, whose size is not measured.
  - *Real units:* 5 reviewed, 4 usable.
- **glm** (z-ai/glm-5.3-flash). Throwaway work only and never picked, so nothing is measured.

[OBSERVED suite-r/by-arm.json, suite-r/stats.md, suite-r/replicates.md, `lane-stats report --by lane,effort` on 2026-10-20; INFERRED where §1–2 are cited]

Tokens per item are not comparable across providers. Claude's count includes the cached context it re-reads on every turn (126,000–941,000 per review). Codex's count is 22,000–43,000.

## 7. Unusual results and why (2026-10-21)

Each unusual result in §5–§6 was traced to a cause in the reviewers' own transcripts, Codex rollouts and run records,
then checked against public benchmarks other than Artificial Analysis. "Unmatched" means a finding the grader could not
pair with a planted defect (same file, within 5 lines, one finding per defect, descriptions never compared).

### Precision

1. **The answer key is incomplete, so every model's precision reads low.**
   - The 36 items are real changes to real code, which holds real bugs nobody planted. Reviewers keep finding them.
     44% of all 813 unmatched findings sit on 5 items (005, 019, 020, 026, 030). One unplanted bug on item 020, where
     provenance records a different adapter than the runner uses, was reported independently by 44 of 67 runs.
   - Leaving those 5 items out lifts sol from 0.73–0.78 to 0.85–0.89 and astra from 0.74–0.79 to 0.85–0.92.
   - A finding-by-finding audit of 204 unmatched findings over 12 arms judged 105 to be real unplanted bugs, 17
     duplicates or near misses of a planted one, and 82 speculative, wrong or not about correctness. For sol and astra
     every audited one was real, a duplicate or a near miss.
   - Public review benchmarks on real bugs report precision of 46–71% (Qodo 3.0, vendor) and 84–92% (Macroscope,
     vendor), so ours is not unusually low.
2. **Effort lowers Claude's precision because it makes Claude read the code around the change.**
   - At low effort Claude reviews the diff alone: Opus 5.5 low read about 1 line of the post-change source per item,
     Sonnet low 6, Haiku low 31 (Opus low on item 001: read the diff, one search, wrote the answer; 4 turns, 129
     thinking tokens). At max they read about 1,000–1,600 lines per item, and Haiku, Sonnet and Opus think
     29,000–75,000 tokens over 14–17 turns.
   - That reading surfaces more real unplanted bugs (in the audit, Haiku 2 → 22 and Opus 2 → 15 from low to max) and
     more low-severity, speculative and test-coverage complaints the brief excludes (unmatched low-severity findings:
     Haiku 4 → 23, Opus 5 → 20; 20 of Opus max's 26 unmatched are low severity).
   - Ruled out: reviewing unchanged code (310 of Claude's 329 unmatched findings, 94%, sit inside the changed lines)
     and duplicate reports (6–12% of the increase).
   - Caveat: within one effort, how much a run read and how many unmatched findings it made barely correlate (Spearman
     −0.36 to 0.28), so reading is the route effort acts through, not a per-item law.
   - sol and astra read 200–550 lines at every effort, list at most 3 findings per item, and keep their unmatched
     findings at medium severity, so their precision stays flat at the level the incomplete key allows.
   - Public: Qodo 3.0 (vendor) reports that raising reasoning effort raises recall and lowers precision; GitHub
     ReviewBench shows sol's precision flat across effort, as here.
3. **Sonnet's dip at xhigh (0.85 → 0.69 → 0.79) is noise.** Its 10 extra unmatched findings are spread over 10 items
   with no common cause, from one run per effort.
4. **Controls.** sol and astra reported nothing on the 6 clean controls at any effort. The Claude models' control
   findings are test-coverage complaints (item 033) and speculative boundary claims (item 031), not correctness bugs.

### Recall

5. **luna low (0.39) barely thinks and calls a third of the bugged diffs clean.**
   - At low effort luna spent zero reasoning tokens on most items (mean 48–107 per item; 4,248 at max) and wrote an
     empty answer on 6–15 of the 30 bugged diffs per run, against 0 of 30 at max. It ran about as many commands (4–6
     against 6–7), so it did not read less; it judged without reasoning.
   - Wrong line numbers rescue none of its misses (lenient matching recovers 0).
   - The same coin flip explains its run-to-run instability (stable share 0.15–0.60): the number of "clean" verdicts
     ranged from 6 to 15 between runs of the same arm.
   - Public: Hex DataBench shows the same steep luna curve (30.3 at low to 52.3 at max).
6. **luna's broken output files (47 of them) come from hand-writing JSON in shell.** It writes `findings.jsonl` with a
   heredoc or `printf`, and an unescaped quote or newline breaks the line. Briefs that produce JSON should ask for a
   serializer (`jq -n`, `json.dumps`) and name a validator (see POLICY, Briefs).
7. **The hardest defect, 018:D1 (6 of 67 runs), is a one-character regex boundary.** The new pattern accepts an empty
   double-quoted entry (`[^"]*`) but needs at least one character in a single-quoted one (`[^']+`). The diff's own new
   tests cover single quotes but not an empty entry, so reviewers who trust the tests accept it. Sonnet low and medium
   never opened the implementation; Sonnet high opened it and dismissed a related issue as minor. The six finders
   (Haiku medium and xhigh, Opus max, astra max run 3, luna xhigh, luna max run 3) checked the empty-value branch
   explicitly.
8. **The non-monotone steps are one-defect flips: astra low above medium, Fable high below low, Haiku max below xhigh,
   sol max above xhigh.** Each rests on 1–2 discordant defects (exact McNemar p 0.5–1.0), and the flipped defect differs
   by model. Public data show the same small dips: Hex DataBench astra 55.0 at low against 52.7 at medium and Fable 21.0
   at medium against 20.3 at high; CodeRabbit (vendor) Fable recall 61.0 at low against 57.1 at high; LiveBench Haiku
   max 67.9 against xhigh 72.1; Artificial Analysis coding-agent index Haiku max 36 against xhigh 41 and sol max 60
   against xhigh 63. Near the top, effort is not monotone, on our suite or theirs.
   - So Suite R cannot separate sol max from xhigh (0.947 against 0.921, p = 1.0); sol max stays retired on public price
     and score alone.
9. **Suite R cannot tell Haiku from Opus.** All 38 planted defects are mutations inside the changed lines, so any model
   that reads the diff can spot them: pooled over effort, Haiku and Opus 5.5 each found 181 of 190. Public indexes
   measure long agentic tasks, which is why they rank our recall poorly (Spearman 0.25–0.62). Public real-bug review
   benchmarks do separate small and large models (Qodo 3.0: Haiku 4.5 recall 22.6 against Opus 5.5 53.7). Separating
   them here needs items whose evidence sits outside the diff.

### Usage

10. **Claude's 126k–941k tokens per item against Codex's 22k–43k is a counting rule.** Codex's "tokens used" leaves
    out cached input; Claude's total includes every cached re-read. On total input processed, Sonnet xhigh (295k per
    item) and luna xhigh (247k) are within 20%. One luna low item reported 25,568 tokens and processed 169,489.
11. **Claude's cost jump at max is thinking.** Sonnet max thinks 41,700 tokens per item against 3,200 at xhigh (13x),
    over 16.9 turns against 9.3; that adds $0.40 of output and $0.31 of cache use per item. Opus 5.5 thinks 28,800
    against 4,200, Haiku 75,000 against 27,000. Public: Sonnet 5.5 max used its whole 128k thinking budget on a simple
    prompt (Simon Willison's test, via eesel), and Haiku 5.5 max used 132k output tokens on one small task
    (computingforgeeks).
12. **Fable costs 3x Opus 5.5 at low–xhigh and 1.7x at max** (on the 18 items both ran). Fable's list price is 2.5x
    Opus's for cache writes and output and 1.25x for cache reads, and at low–xhigh Fable also thinks about twice as
    much and writes 1.6–2.0x the output. At max Opus's thinking grows 6.9x over xhigh while Fable's grows 1.8x, so Fable
    becomes the leaner one. Public: Artificial Analysis shows Fable max at 188M output tokens against Opus max's 260M.
13. **luna low costs more per item than luna medium (0.127 against 0.099 credits)** because with almost no reasoning
    (57 against 340 tokens per item) it reads instead: 6.1 commands per item against 4.7, more whole-file dumps (3.0
    against 2.4) and searches (1.65 against 0.81). Every extra command re-sends the growing context, so cached input
    rose from 127k to 193k per item. Public sources show luna low using fewer output tokens than medium, which fits:
    the extra is input, not output.
14. **Opus 5.5's weekly weight (0.67) against its 5h weight (0.95) is within measurement error.** The weekly fit rests
    on 2–3 whole-percent steps and spans 0.22–2.00. A 17-account community measurement (Wokey, 2026-10-19) puts Opus
    5.5 at about 0.6x per token on the weekly meter, consistent with 0.67. Fable's 5h weight 2.06 (1.82–2.35) fits
    Anthropic's note that Fable "uses limits faster" and a separate Fable weekly meter.
15. **sol's charge of 1.19–1.36x its card rests on four 1% meter steps** (about 84 credits each). Fast mode is ruled
    out (none of 540 sol commands set it) and reasoning tokens are already inside `output_tokens`; the rest is meter
    resolution and possible use elsewhere on the account. luna's charge cannot be measured this way: the 14.6 card
    credits it used never moved the meter by 1%.
16. **The Codex week reset early (2026-10-20 06:32 UTC, 96% → 0%).** OpenAI's 28-day pledge (posted about 2026-10-04:
    each day either an improvement or a full usage reset; resets reported 10-02 and 10-15) fits the timing; no report
    names that day.
17. **Max 20x holds about $1,525 list a week here; a 17-account community measurement (Wokey) gives $1,643**
    ($1,547–1,751), within 7%. Our 5h figure ($254) is 24% above its $205.

Sources: Qodo 3.0 (qodo.ai, 2026-10-12, vendor); Macroscope benchmark (macroscope.com, undated, vendor); GitHub
ReviewBench (github.blog, 2026-10-05); Hex DataBench (hex.tech/databench, 2026-10-07); LiveBench via AI Agent Store
(2026-10-20); CodeRabbit Fable 5.1 review (2026-09-01, vendor); eesel on Sonnet 5.5 (2026-09-29); computingforgeeks on
Haiku 5.5 (2026-10-08); Artificial Analysis model pages (2026-10); Anthropic pricing docs and support articles
15424964 and 11145838; Wokey Claude usage limits (2026-10-19); learn.chatgpt.com pricing; nerdschalk on the Codex
28-day pledge (2026-10-04). Our evidence: prior analysis runs on the lab machine (not shipped).

## 8. Suite R rescored with an extended answer key (2026-10-22)

§7 found that about half of the "unmatched" findings were real bugs the answer key lacked. This section judges every one
of them and rescores all 70 runs (67 earlier runs plus a Sonnet replicate at high, xhigh and max).

**How the key was extended** (procedure and templates: `../measure/ADJUDICATE.md`; tools: `lane-bench export-findings`,
`lane-bench rescore`):
1. Four Codex adjudicators (astra xhigh and max, sol xhigh), one group of items each, grouped every unmatched finding into
   issues and judged each issue: real (a reachable input gives a wrong result, crash, lost data or broken contract, with the
   trigger and the line cited), speculative, wrong (the claim about the code is false) or not a defect.
2. Every issue went to Sonnet 5.5 high blind: it saw one reviewer's own words, never the Codex verdict. The two families
   agreed on real versus not for 78 of 104 issues.
3. The other 26 went to a Codex tie-breaker that ran a reproducer of the shipped code in a batch job for every one. The
   reproducers sided with the Codex adjudicator 23 times and with Sonnet 3 times. Codex as tie-breaker is a same-family
   risk; every decision rests on a reproducer's output instead of an argument.
4. A separate pass checked all 2,245 location matches (2,140 from the first 67 runs, 105 from the replicate): 2,221
   describe the planted defect they matched, 23 describe another problem within the ±5-line window, 1 only partly.

Of the 867 findings judged: **550 report one of 36 real bugs the key lacked** (34 in the changed lines; 6 high, 26 medium,
4 low severity), 105 describe a planted defect from more than 5 lines away or a second time, and 212 are false alarms
(22 speculative issues, 26 wrong, 20 not a defect). The most-reported real bugs are cross-file consistency bugs: a
provenance record that reads a setting from a config section the runner never applies (35 runs), two files reading an
adapter name from different keys (36 runs), and a statistics loop that drops a missing score but still pairs every key with
the surviving differences, moving each later difference onto the wrong task (56 runs). Counts only:
`suite-r/key-summary.json`; per run and item: `suite-r/rescore-per-run.jsonl` (with `outcomes-v2.jsonl` and
`by-arm-v2.json`, in the kit's git repository and in `claude-usage-optimizer-evidence.sh`, published next to the bundle,
not in the bundle itself).

**Rescored, pooled over replicates** (v1 = the old scoring, reproduced exactly; v2 credits real bugs and near misses and
drops matches that describe another problem; full table `suite-r/by-arm-v2.md`):

| Arm | Runs | Planted recall v1 → v2 | Precision v1 → v2 | Real bugs found / run (of 36) | False alarms / planted item | $ / usable item | % week / usable item |
|---|---:|---|---|---:|---:|---:|---:|
| haiku low | 1 | 0.89 → 0.92 | 0.79 → 0.88 | 3 | 0.10 | 0.009 | 0.0006 (Claude) |
| haiku medium | 1 | 0.95 → 0.97 | 0.72 → 0.84 | 5 | 0.17 | 0.012 | 0.0008 |
| haiku xhigh | 1 | 1.00 → 0.97 | 0.51 → 0.70 | 15 | 0.50 | 0.055 | 0.0036 |
| haiku max | 1 | 0.97 → 0.97 | 0.47 → 0.78 | 24 | 0.37 | 0.171 | 0.0112 |
| sonnet high | 2 | 0.89 → 0.95 | 0.86 → 0.98 | 2.5 | 0.03 | 0.141 | 0.0092 |
| sonnet xhigh | 2 | 0.93 → 0.97 | 0.68 → 0.87 | 8 | 0.15 | 0.237 | 0.0156 |
| sonnet max | 2 | 0.97 → 0.97 | 0.82 → 0.96 | 6 | 0.07 | 0.915 | 0.0600 |
| opus low | 1 | 0.92 → 0.97 | 0.80 → 0.89 | 2 | 0.13 | 0.229 | 0.0150 |
| opus max | 1 | 1.00 → 1.00 | 0.59 → 0.86 | 17 | 0.23 | 1.476 | 0.0968 |
| fable low | 1 | 0.95 → 0.97 | 0.82 → 0.86 | 1 | 0.13 | 0.720 | 0.0472 |
| luna high | 4 | 0.72 → 0.73 | 0.77 → 0.92 | 5 | 0.08 | 0.007 | 0.0019 (Codex) |
| luna max | 4 | 0.82 → 0.82 | 0.69 → 0.89 | 9 | 0.13 | 0.009 | 0.0027 |
| sol low | 3 | 0.84 → 0.88 | 0.77 → 0.98 | 7.7 | 0.00 | 0.069 | 0.0205 |
| sol medium | 3 | 0.88 → 0.90 | 0.78 → 0.98 | 8 | 0.00 | 0.081 | 0.0242 |
| sol xhigh | 3 | 0.92 → 0.95 | 0.74 → 1.00 | 11.3 | 0.00 | 0.118 | 0.0350 |
| astra max | 3 | 0.98 → 0.97 | 0.77 → 0.99 | 11.3 | 0.01 | 0.748 | 0.2227 |

1. **sol and astra raise almost no false alarms.** Their v2 precision is 0.98–1.00 at every effort: their low v1
   precision was the key's fault.
2. **Once real bugs count, only Haiku's precision still falls with effort.** Opus stays at 0.83–0.89 from low to max.
   Haiku's false alarms per planted item rise from 0.10 at low to 0.50 at xhigh: its extra reading finds real bugs
   (3 → 24 per run) and also more claims that do not hold.
3. **Real bugs separate the arms where the planted ones could not, by effort more than by tier.** Planted recall is
   0.87–1.00 for every arm except luna. Real bugs found per run grow with effort inside every model (Haiku 3 → 24, Opus
   2 → 17, luna 1 → 9, sol 7.7 → 11.3); Haiku max finds the most. Sonnet finds the fewest at every effort (0–8) and is the
   most precise Claude reviewer.
4. **Sonnet's xhigh precision dip replicated** (0.85 and 0.89 in two runs, against 0.97–0.98 at high and 0.94–0.98 at max).
   Cause, from the transcripts: xhigh reads 4.5x as much surrounding code as high (508 against 113 lines per item) and
   reports more nearby claims (22% low severity, against 8% at high and 10% at max), but thinks 3,200 tokens per item
   against max's 40,000 and makes 8 tool calls against 16, so it checks them less. The 12 false alarms in its two runs
   (against 2 at high and 4 at max) sit on five items and two controls; 9 are not defects (intended behaviour, or a test-coverage
   complaint) and 3 are speculative. Transcripts show behaviour, not internals: xhigh does screen some candidates, just less.
5. **Future runs need no new adjudication.** Grading with the planted defects plus the real bugs' line windows (same ±5
   matcher) agrees with the adjudication on 93.4% of findings.

Binary agreement was 2,883/3,088 findings (93.4%); exact credited-issue agreement was 2,710/3,088 (87.8%).

**Cheapest arm that succeeds at review** (`suite-r/cheapest.md`; bars: planted recall ≥ 0.90, precision ≥ 0.85, usable
≥ 0.90 of items):
- Haiku low clears all three at $0.009 and 0.0006% of Claude's week per usable item, from one run.
- Replicated arms that clear them: Sonnet high (2 runs, $0.14, 0.009% Claude) and sol medium (3 runs, $0.08, 0.024%
  Codex; in the picker's cost points, which weight Codex at 0.3, 0.007 against Sonnet high's 0.009).
- With the bars on the 95% bootstrap lower bounds, only astra max and Sonnet max clear: 30 planted items is a small sample.
- To also catch the real bugs, sol xhigh (11 per run, no false alarms, 0.035% Codex) is the clean choice; Opus max finds
  more (17) at 12x its list price, Haiku max the most (24) with false alarms.

**Is Suite R representative?** For reviewing your own diffs, yes in content: the items are real commits, and with the
extended key it measures both local planted bugs and the cross-file bugs that were already there. It is not a proxy for
other task types (§9).

## 9. Which model for which task: public benchmarks and our records (2026-10-22)

Public sources: `public-research/2026-10-22-code-writing-tests.md`, `…-review-explain-research.md`,
`…-hybrid-setups.md` (dated rows with URLs, conflicts listed); numeric rows are also in `public.json`. Our records: the lane
ledger and a second project's worker notes (porting and gating work).

Ledger tags do not fully identify task type. Costs remain in native units (USD, weekly share and credits), so
they cannot be ranked directly across providers.

- **Tier carries over between task types; effort and close pairs do not.** Median rank correlation across benchmarks is
  0.67–0.79 (IBM, ICLR 2026; Epoch). Sol's review score is flat from medium to xhigh on Qodo but rises steeply on
  ReviewBench. Measure effort on each task type.
- **No public source gives cost per task at each effort** for any of our models, so the cheapest effort is unknown
  everywhere except review.

| Task | Public evidence | Our evidence | Enough? | Current best guess |
|---|---|---|---|---|
| Review (routine diffs) | Qodo (vendor; F1 Opus 5.5 high 56.8 at $1.00, Sonnet 5.5 54.9 at $0.73, Sol medium 48.7 at $0.18, Luna 42.2 at $0.02), ReviewBench | Suite R, 70 runs, rescored (§8) | **enough** | Haiku low (replicate first), Sonnet high, sol medium; sol xhigh to catch real bugs |
| Write code / features | FrontierCode (AA): Sol max 49% at $0.81, Opus 5.5 max 52% at $10.15, Luna max 42% at $0.09; DeepSWE: Astra medium within 1.3 points of xhigh; AA index: Sol xhigh 63 at $1.04, Opus max 66 at $13.04 | porting project: luna xhigh 24/24 work packages merged after fix rounds, sol xhigh 11/12, gemini 3.8 flash 11/15 | **enough for tier, thin for effort** | sol xhigh; luna xhigh for well-specified units; Opus only for the hardest |
| Fix bugs | SWE-bench Pro, vendor max only | luna medium 2/2 | thin | as write code |
| Mechanical edits | SWE-Atlas Refactoring, xhigh only | luna and sol all usable (n = 2–5) | thin, low stakes | luna medium |
| Write tests | none for our models | 1 unit | **none** | gap |
| Explain code | SWE-Atlas QnA, xhigh only (Opus 5 63, Fable 60, Astra 59, Gemini Flash 47, Sol 46) | one anecdote | **thin** | gap at cheap efforts |
| Web research | Deep Research Bench (older models): effort adds 1–5 points; BrowseComp: search budget matters more than the model | none | thin | Sonnet researcher |
| Design / planning | none | 2 units, both reworked | none | Claude |

Next measurements, each a capability test that needs the user's approval: a Haiku low replicate on Suite R; a small
multi-task suite for fix-bug (built from Suite R's known bugs and reproducers), write-tests (graded by mutation score) and
explain-code (checkable answers), climbing each model's efforts cheapest first and stopping at the first arm that clears
the bar.

## 10. Hybrid setups (2026-10-22)

- **AA's hybrid rows are Devin Fusion runs on its Coding Agent Index v1.5**, a collection of 303 tasks (DeepSWE 113,
  Terminal-Bench 4.0 66, SWE-Atlas QnA 124). Opus 5.5 max leading with GPT-6 Luna high executing: 68 at $9.02 per task,
  against 66 at $13.04 for Opus max alone (checked on AA's page). Fable 5.1 xhigh + SWE-2: 62 at $7.90; Astra xhigh +
  SWE-2: 59 at $4.55. Sol xhigh alone: 63 at $1.04.
- **Whole-task scores cannot predict a hybrid.** Opus + Luna beat both parts alone (66 and 41). Across public results,
  hybrids landed below the stronger part in 4 of 9 cases, and no published method predicts a coding hybrid from
  single-model scores and validates it. Handing a weak model's full trajectory to a strong one recovers only 36–47% of the
  gap (Handoff Tax, arXiv 2608.24358). Anthropic's guidance: sweep the single model's effort first, and pair only if the
  pair beats that whole curve.
- **Parallel hybrids predict well.** `lane-bench panels` builds 2–3 reviewer panels from single runs, and on held-out
  replicates every tested panel's recall matched its prediction.
- **For sequential hybrids, measure roles, not models.** A review-gated pipeline is
  P(done) ≈ p_execute + (1 − p_execute) · r · p_fix, where r is the reviewer's recall on real bugs (§8), not planted ones,
  and cost is c_execute + c_review + ((1 − p_execute) · r + false alarms) · c_fix. Lead × executor pairs need their own
  runs: fit lead and executor effects in log-odds on a sparse, connected set of pairs and check the prediction on held-out
  pairs, as the panels were checked.

## 11. Reviewed lane runs on real work (2026-10-22)

One machine's `lane-stats report --by lane,effort,class --json`, taken on 2026-10-22, contains 69 grouped rows;
36 have `reviewed > 0`, and they hold 111 reviewed runs of real work.

The per-lane table is computed from the filtered grouped JSON rows. Accepted and usable rates are weighted by
each row's `reviewed` count. Median minutes is the weighted median of the grouped rows' `med_min` values,
weighted by `reviewed`, not the median of raw run times. Weekly share and list dollars per usable unit are
weighted by estimated usable counts (`reviewed × usable%`); list dollars exclude rows with no listed dollar value.

| Lane | Reviewed runs | Accepted | Usable | Median min* | Weekly % / usable | List $ / usable |
|---|---:|---:|---:|---:|---:|---:|
| astra | 6 | 100.0% | 100.0% | 1.1 | 6.745 | 16.293 |
| gemini | 5 | 60.0% | 80.0% | 18.1 | 0.987 | — |
| haiku | 8 | 100.0% | 100.0% | 8.9 | 0.014 | 0.445 |
| luna | 33 | 57.6% | 78.8% | 5.6 | 0.235 | 0.090 |
| opus | 21 | 100.0% | 100.0% | 2.0 | 0.283 | 8.011 |
| sol | 28 | 92.9% | 92.9% | 1.0 | 1.238 | 1.384 |
| sonnet | 10 | 60.0% | 100.0% | 8.8 | 0.116 | 2.225 |

The 36 source rows with reviews, without run identifiers or notes, are in `ledger/reviewed-runs.json` and
`ledger/reviewed-runs.md`. Weekly percentages are shares of each provider's own weekly window; dollar prices
and provider-window shares are native units and cannot be ranked directly across providers.

Three findings from the grouped rows:

- Luna has the largest reviewed sample: 19/33 accepted and 26/33 usable.
- Sol has 26/28 accepted and usable outcomes.
- Opus has 21/21 usable outcomes, but 18/21 are xhigh review runs and only 3/21 are substantive; this is
  narrow evidence, not a result for other efforts or task types.

Caveats: one machine; small counts in many lane-by-effort-by-class cells; the orchestrator assigns classes;
task tags do not fully identify task type (§9); and Suite R capability-test runs are not in these real-work
rows.

## 12. Terra on Suite R, against sol and outside benchmarks (2026-10-28)

The user approved one Suite R run of terra at every effort (180 item runs). Before the user paused it, low, medium
and high had run on all 36 items and xhigh on 23; max had not started. The runs were graded on the planted key; the
rescored key of §8 holds judges' verdicts, not a gradable key, so terra has no rescored precision yet. The rows are
`terra-*` in `suite-r/outcomes.jsonl`, `by-arm.md`, `stats.md` and `compare.md`.

| Effort | Items | Recall, planted [Wilson 95%] | Precision, planted | Unmatched findings / item | Credits / item |
|---|---:|---|---:|---:|---:|
| low | 36 | 0.92 [0.79, 0.97] (35/38) | 0.73 | 0.43 | 0.70 |
| medium | 36 | 0.92 (35/38) | 0.67 | 0.57 | 0.80 |
| high | 36 | 0.92 (35/38) | 0.64 | 0.63 | 0.91 |
| xhigh | 23 | 0.93 on its items (28/30) | 0.57 | 0.95 | 1.32 |

- **Effort buys nothing on review.** Low, medium and high find the same 35 defects (McNemar p = 1). Each step up
  costs more and raises more findings that match no planted defect. Some of those may be real bugs the key lacks;
  they have not been adjudicated.
- **Against sol on the same key** (sol from its three Suite R runs):

  | Pair | Defects found | Only terra / only sol | Credits / item |
  |---|---|---|---:|
  | terra low vs sol low | 35 vs 31, 33, 32 | 3–5 / 0–1 (each p ≥ 0.22) | 0.70 vs 1.61 |
  | terra xhigh vs sol xhigh, items ≤ 023 (30 defects) | 28 vs 28, 27, 26 | 1–3 / 0–1 | 1.32 vs 2.91 |
  | terra low vs sol xhigh | 35 vs 36, 35, 34 | 1–3 / 2 | 0.70 vs 2.91 |

  Terra low matches sol xhigh's recall at 0.24× its credits. Sol raises fewer unmatched findings (0.27–0.43 an item).
- **Outside benchmarks disagree for code.** On Artificial Analysis's live per-effort pages (Intelligence Index v5.0,
  rows in `public.json`), terra trails sol by 4–8 points at every effort, and on Terminal-Bench 4.0 hard tasks by
  16 points at low and medium:

  | Effort | Index, terra vs sol | TB4 hard, terra vs sol | $ / task, terra vs sol |
  |---|---|---|---|
  | low | 29 vs 35 | 15% vs 31% | 0.07 vs 0.16 |
  | medium | 38 vs 46 | 32% vs 48% | 0.17 vs 0.36 |
  | high | 42 vs 50 | 42% vs 52% | 0.26 vs 0.59 |
  | xhigh | 45 vs 52 | 46% vs 54% | 0.40 vs 0.76 |
  | max | 51 vs 55 | 56% vs 56% | 0.96 vs 1.27 |

  At matched cost terra equals sol one effort lower: sol medium beats terra xhigh for less money, and sol xhigh
  matches terra max for less. Terra costs 0.44–0.53× sol up to xhigh, which agrees with our 0.43×, but 0.76× at max,
  where it writes almost as much as sol. The earlier "48 vs 52 at half the cost" (Intelligence Index before its
  v5.0 rescale) is superseded. OpenAI's own Terminal-Bench 4.0 figure for terra is 50.3%; a coding-agent index of
  48 vs 54 appears only in blogs.
- **What changed in the catalog.** Terra low serves review (with mechanical and research), and its measured
  review block replaces the estimate. Terra xhigh and max are retired: they cost more than a stronger sol arm. Terra
  medium and high keep substantive work as a cheap middle rung below sol, with priors re-based on the v5.0 ratios.
  Code quality rests on public numbers until reviewed real units decide; terra has 13 so far (§13).
- **Harness, not model.** The first grading scored terra almost blind: 103 of 116 findings files began with a
  byte-order mark, which PowerShell's `Set-Content -Encoding UTF8` writes, and the grader skipped them. `lane-bench`
  now reads findings with `utf-8-sig`. A first pass also lost 4 of 24 terra-low files: `exec_command` returns after
  about 10 s, a busy host's PowerShell took up to 15.7 s to start, and the worker ended its turn on the empty output
  before the write. The brief now asks the worker to read its file back, and `lane` adds the same rule to every
  Codex brief on Windows (LANES.md, Orchestration lessons).
- **The 49 runs not taken** (13 xhigh, 36 max) would only confirm the two retirements. They stay approved but optional.

## 13. Real work on a second machine (2026-10-22 to 2026-10-28)

A Windows machine's Claude sessions sent 124 lane runs of real project work after the §11 snapshot: n8n
workflow-replica builds, a mobile app (mostly reviews and hard units), a CLI port, specs and audits, and a custom
n8n node. 112 were reviewed and 106 were usable (95%); 80 merged as-is, and Claude fixed the rest in 163 minutes in
all. They used 1,282 Codex credits (15% of a Pro Lite week) and $139 list on the Claude lanes (9% of Claude's week).
Left out: Suite R (§12), the n8n app evals (§14), n8n workflow executions and smoke runs. Rows by lane, effort and class: `ledger/reviewed-runs-2026-10-28.{md,json}`.

| Lane | Runs | Reviewed | Merged as-is | Usable | Cost per usable unit | Claude fix min |
|---|---:|---:|---:|---:|---|---:|
| haiku | 59 | 50 | 43 | 50 | $1.37 list (0.09% of Claude's week) | 37 |
| sol | 30 | 27 | 17 | 26 | 27.3 credits | 63 |
| terra | 13 | 13 | 6 | 12 | 5.6 credits | 30 |
| sonnet | 9 | 9 | 7 | 9 | $7.12 list | 16 |
| luna | 9 | 9 | 4 | 5 | 8.0 credits | 12 |
| opus | 2 | 2 | 2 | 2 | $3.26 list | 0 |
| astra | 2 | 2 | 1 | 2 | 232 credits | 5 |

By class: review 24/24 usable, substantive 63/68, hard 9/9 (4 merged as-is), mechanical 5/5, research 5/6.

- **Haiku did most of the work.** It built most of the workflow replicas and did every app review: 50/50 usable,
  about $0.19–0.29 list per review at low and medium.
- **Sol was reliable but dear.** 26 of 27 were usable but only 17 merged as-is, it needed the most fix time, and it
  took 55% of the credits. The two astra runs were pair runners-up: 36% of all credits for two units.
- **Luna was 5 of 9 usable, and all four failures were at medium or high** (xhigh and max 5/5). Two quit early, after
  12 and 20 tool calls, and two were harness failures on Windows: the Codex sandbox refused a nested process
  spawn (EPERM), and the other read UTF-8 files as ANSI and wrote garbled names. Across both snapshots luna medium
  substantive is 1 of 5 usable and low/medium research 1 of 3, against 12 of 13 at xhigh and max outside review.
  So luna low and medium now serve mechanical work only, and `lane` handles the harness side (LANES.md, Orchestration lessons).
- **The lane verdict missed every failure.** It said OK on all six unusable runs; only Claude's review caught them.
  Each was recovered one rung up (luna to haiku xhigh, sonnet medium or sol xhigh; terra low to sol xhigh; one sol
  medium resumed).
- **Wall time** was 58 lane-hours, of which about 26 were two overnight network stalls, not model time.
- **On Plus** this machine's six days of Codex work would fill 88% of a Plus week, 56% without the astra pair, and
  about 29% with sol's share moved to terra at 0.45× its cost. Real units cost 15–40× a Suite R item, so a Plus week
  binds on code units, not reviews; pairs and astra do not fit.

Compared with §11 (the first machine): there the Claude-lane units were cheaper (haiku 0.014% of the week per
usable unit, against 0.09% here) and the Codex units dearer (sol 1.24% against 0.33%). The work differed (porting and
reviews there; large workflow builds on haiku and sonnet here), and so did the method: §11 used whole-percent meter
jumps, this section uses card credits and list prices.

The next window on the same machine, split by local process, subagent and cloud, is §18.

## 14. Classification through the lanes (2026-10-24)

Three labelled classification tasks from n8n app replicas (abstract screening, email classification, transaction
categorisation), about 150 items per arm, each item one `lane` call scored against its label. Per task, lane and
effort: `app-evals/classification-2026-10-28.{md,json}`.

| Lane (efforts pooled) | Accuracy | Cost per call | Median seconds |
|---|---|---|---:|
| opus (medium, high) | 97.7% (293/300) | $0.046 list | 7–9 |
| gemini (default) | 96.7% (145/150) | free | 15–20 |
| sol (medium, xhigh) | 96.7% (290/300) | 0.19 credits | 22–32 |
| sonnet (medium, high) | 95.0% (285/300) | $0.023 list | 7–8 |
| luna (low, medium) | 94.3% (283/300) | 0.011 credits | 21–23 |
| haiku (low–xhigh) | 94.1% (570/606) | $0.0014 list | 7–10 |

Every arm lands within 94–98%, inside about ±3.5 points of sampling noise at 150 items, and effort changes nothing
measurable. A call's cost is mostly the CLI's fixed prompt, so the cheap arms win: gemini when the data may leave
the machine and latency does not matter, otherwise haiku or luna low. Opus buys at most 2–3 points for about 30×
haiku's price.

## 15. What a week buys, per arm and plan (2026-10-28)

Review items a week = 100 / (Suite R weekly % per item), from `suite-r/by-arm.md`; Plus = Pro Lite × 1,450 / 8,400.
Real units a week = the window / cost per usable unit in §13, with Claude in Sonnet-equivalent dollars ($1,525) and
Opus divided by its weekly weight 0.67. The real-unit column mixes whatever work each lane did, so it is a budget
guide, not a ranking.

| Arm | Review items: Pro Lite / Plus | Real units (lane overall): Pro Lite / Plus |
|---|---|---|
| luna xhigh | 43,700 / 7,500 | 1,050 / 181 |
| terra low | 12,100 / 2,080 | 1,500 / 259 |
| terra high | 9,200 / 1,580 | (as above) |
| sol medium | 4,300 / 750 | 308 / 53 |
| sol xhigh | 2,900 / 500 | (as above) |
| astra xhigh | 500 / 87 | 36 / 6 |

| Arm (Claude Max 20x) | Review items a week | Real units a week (lane overall) |
|---|---|---|
| haiku low | 186,000 | 1,110 |
| sonnet high | 11,000 | 214 |
| opus | see `by-arm.md` | about 700 (2 runs only) |
| Fable | capped at about $530 a week (§1) | not measured |

Gemini (free) holds at least about 100M flash tokens a week (§3): about 11,000 classification calls were well
inside it, and real units on it are too few to size.

## 16. Time: how long work takes, and how well it can be estimated (2026-10-29)

From release 2026-10-29.1, time is the third value tracked beside accuracy and cost. Every lane run records the ETA it
was given at start (`eta_s`) beside its `duration_s`, and Claude's turns record Claude's own estimates
(`turn-meter eta`). Data (one machine, 2026-10-17 to 10-29): `time/real-units-2026-10-29.{json,md}` and
`time/turns-2026-10-29.json`.

**Real units by class** (152 untagged runs; QUOTA and BUSY runs left out):

| Class | Runs | Median min | p80 min |
|---|---|---|---|
| substantive | 88 | 15.5 | 29.7 |
| review | 40 | 3.7 | 5.2 |
| research | 11 | 9.1 | 17.4 |
| mechanical | 7 | 3.9 | 6.9 |
| hard | 6 | 28.6 | 63.4 |

Tagged runs (bench items and classification calls) are a different population: 2,593 runs with a median of 0.2 min.
A lane estimate therefore uses only runs with the same tag. Substantive medians are 13–21 min on every lane except
terra (5.3 min, n=8). A ridge fit of log time on class, effort and lane put terra at 0.39x the other lanes, but it
could not separate effort from lane: low effort came out slower than high, because the lane that ran it confounds
it. The priors therefore use mild effort factors (0.8–1.5x). The longest unit ran 13 hours (a hung worker); on the
log scale one such run moves an estimate little.

**The estimator** (`lane-stats eta`) works in two steps:

1. A prior: class minutes × effort factor × lane factor × (brief bytes / 6,000)^0.8 (`arms.json`
   `explore.time`).
2. Shrunk log residuals, applied in turn for this machine's runs with the same tag, then the same class, the same
   arm, and the same arm and class (pseudo-count 2, 60-day half-life).

The p80 comes from the arm-and-class spread, shrunk toward a log-sd of 1.0.

**Backtest.** Each of 308 real units (this machine's plus imported runs) was predicted from the runs that had ended
before it started:

| Estimator | Median actual/predicted | Median error factor | Within 2x |
|---|---|---|---|
| `eta` as shipped | 0.93 | 1.70 | 63% |
| Catalog prior only, no brief term | 1.13 | 1.81 | 54% |
| Median of all earlier units | 0.96 | 1.98 | 50% |

- **Coverage:** the p80 held 82% of units (the target is 80%), and on the later half the bias was 1.02.
- **Brief size makes the difference.** Without the brief term the model was no better than the class prior (1.89
  against 1.83): a unit's time is mostly its scope, and per-arm history adds little on top of class. Brief size was
  the strongest single predictor found: correlation 0.40 with the log error over the 183 units with a saved brief, a
  slope of 0.8 per doubling.
- **Caveat:** the exponent was chosen on the same data, so 1.70 is mildly optimistic.
- **Shrinkage strength barely mattered:** pseudo-counts from 0.5 to 30 gave 1.83–1.94.
- **In practice,** a unit's ETA is off by a factor of about 1.7 either way at the median, so plan around the p80.

**Claude's turns.** The data are 431 turns closed by the Stop hook; the 287 that the next prompt closed are left out,
because their end time is unknown.
- **Length:** median 1.3 min, p75 3.9, p90 7.9 and p99 37. The 16 turns over 15 minutes hold 36% of all turn time.
- **Time left given time so far:** after 5 minutes the median turn has 3.4 min left, after 10 minutes 6.3, and after
  15 minutes 16.5. `turn-meter current` uses this as its default: the median of longer past turns, minus the time
  so far, or "as long again" when fewer than 8 turns ran longer.
- **Sessions:** 17, with a median of 21 active minutes and a maximum of 10.4 hours.
- **Claude's own estimates:** none recorded yet. From the third finished estimate, `turn-meter calibrate` reports
  their actual/estimate factor, and `current` applies it.

**What changes:** time is shown, logged and checked against what happened, but it does not choose arms
(IMPROVING §10).

How the estimates fared by place, 2026-10-28 to 10-31, is in §18.

## 17. Context re-reading and when to compact (2026-10-30)

Every model call re-reads the whole conversation from the prompt cache, so a session's cost grows with its context.
Data: the main Claude Code sessions on one machine over 7 days (117 sessions, 12,288 model calls, $776 at list
price, mostly Opus 5.5), with each API message counted once and priced at the published list prices (Opus 5.5: cache
read $0.20, 1-hour cache write $8, output $20 per million tokens). Statistics only; no transcript content is kept.

- **Context is most of the bill.** Cache reads were 53% of list spend, and context reads and writes together were
  79%. The calls with 200–400k of context cost the most ($453 of the $776).
- **What compaction left.** 46 compactions happened at a median of 384k (the window was 450k on most of these
  sessions), and the next call carried a median of 87k. A fresh session's first call carries 23k (system prompt,
  tools, CLAUDE.md and the policy). The difference of about 64k is the summary plus what Claude Code re-injects:
  up to five recent files of up to 5k tokens each, and invoked skill bodies up to 25k in all.

**Replay.** Each session was replayed with its real context growth. A compaction costs one call reading the
context, a 12k-token summary and a 1-hour cache write of the 87k that is left. Each threshold below is a percentage
of actual spend:

| Policy | Compactions | List $ vs actual | At a turn's start | Mid-turn | p99 context |
|---|---|---|---|---|---|
| single 450k (the kit until 2026-10-29.2) | 16 | −3.2% | 0 | 16 | 425k |
| single 300k | 91 | −8.5% | 4 | 87 | 296k |
| single 250k | 127 | −9.7% | 5 | 122 | 248k |
| single 200k | 196 | −9.3% | — | — | — |
| single 150k | 391 | +0.3% | — | — | — |
| soft 200k, hard 300k | 113 | −9.6% | 64 | 49 | 291k |
| soft 200k, hard 350k | 98 | −9.0% | 65 | 33 | 336k |
| **soft 250k, hard 350k** (from 2026-10-29.3) | 79 | −8.5% | 42 | 37 | 338k |

The curve is flat from 200k to 300k and turns up below about 175k, where each summary costs more than the
re-reading it saves. With soft and hard thresholds, compaction waits for the next turn's first call unless the
context reaches the hard ceiling. At soft 200k and hard 350k, two-thirds of compactions land between answers, and a
long turn (the p90 turn makes 55 calls) keeps its working context up to 350k. The cost is 0.6 points of the saving.
The kit ships soft 250k: about half of its compactions land between answers, and with the `compact-at-rest` mod
more do, because it compacts right after an answer once the context reaches 90% of the window.
The replay leaves out two effects: Claude re-reading files the summary dropped, which makes low thresholds dearer,
and summary quality.

A later replay of the same machine's last 7 days ($803 list) checked a soft threshold of 300k for a bigger carried
history:

| Soft / hard | Saving | Compactions | At turn start | Mid-turn |
|---|---|---|---|---|
| 300k / 350k | −6.3% | 73 | 31 | 42 |
| 300k / 400k | −4.8% | 64 | 35 | 29 |

On those days 200k / 350k came out at −8.9% (100 compactions, 33 mid-turn) and 250k / 350k at −8.5% (80, 37).

- **A narrow band overflows.** With only 50k between soft and hard, turns that start near 300k overflow mid-turn,
  the worst place for a cut.
- **A higher ceiling halves the saving.** Lifting the ceiling to 400k fixes the overflow but halves the saving.
- **The user chose 250k / 350k.** About 160k tokens of verbatim history are carried between turns, against
  about 110k at 200k. Both sit above the roughly 87k floor of system, tools, summary and live state. The cost is
  0.4 points of the saving and a fifth fewer lossy summaries. Within a turn the gate keeps everything up to 350k.

**The mechanism (measured with a `claude -p` probe on Haiku and a 100k window, Claude Code 2.1.312).**
- A `PreCompact` hook that returns `{"decision": "block"}` skips that compaction, and Claude Code asks again before
  every later model call over the window.
- The first call of the next turn compacted once the hook allowed it.
- A `SessionStart` hook with source `compact` put a marker into the context, and the model reported it back after
  the compaction.
- When the hook runs, the transcript holds the newest tool results, but the last assistant usage predates them: it
  showed 26k while the context was 169k. An estimate must add the entries written since.

**Compacting right after an answer (the `compact-at-rest` mod, Claude Code 2.1.314, an interactive Haiku session
through `lane-term`, 2026-10-30).**
- A mod's `turn.complete` hook can read the context (`$.session.usage()`, and the compaction window from
  `usage({ breakdown: 'summary' })`, with no API call) and start the same compaction as `/compact` with
  `$.session.compact()` from a 1.5 s timer once the turn has ended.
- In the probe it fired 1.5 s after the answer and took 14 s: 211k tokens became 6.5k, with a 5k-character summary.
- The summarizer call read 141k of its 212k input tokens from the prompt cache (71k uncached, 2.2k output). Compacting
  while the cache is warm is the cheap moment; after an idle longer than the cache TTL the same call pays for every
  token.
- The transcript labels such a compaction `manual`, as for a typed `/compact`. The `PreCompact` gate, which acts on
  `auto` only, never blocks it, and `turn-meter compactions` counts it with the user's own.
- Haiku 5.5's model window is 1M tokens. `$.session.usage().context.window` gives that, while the breakdown's
  `rawMaxTokens` gives the compaction window that matters.

## 18. Real work by place, arm and class (2026-10-28 to 2026-10-31)

Since the §13 snapshot (2026-10-28 16:22) the same Windows machine sent real work to three places: a local process,
a Claude subagent and a cloud session. Window: to 2026-10-31 13:10. Of 470 runs, 176 are real work; left out are 159
Suite R capability runs, 131 app-eval runs (a translation app's evals and their judge runs) and 4 probes. By place the
176 are 129 local, 21 subagent and 26 cloud. 158 were reviewed and 153 were usable (97%); 84 merged as-is (53%).
Rows: `ledger/reviewed-runs-2026-10-31.{md,json}` (lane, effort, class), `ledger/places-2026-10-31.{md,json}` (lane
and class by place), `time/eta-2026-10-31.json`. Merged as-is and usable are reviewed × accepted% and × usable%, taken
per row and rounded to whole runs (every sum came out whole). Cost is the meter share the report attributes to the
runs, divided by usable runs; unreviewed runs add cost but no usable unit, so cloud's rate is conservative.

| Lane | Runs | Reviewed | Merged as-is | Usable | Cost per usable unit |
|---|---:|---:|---:|---:|---|
| haiku | 64 | 58 | 48 | 57 | $0.24 list (0.045% of Claude's week) |
| sol | 49 | 49 | 15 | 49 | 12.1 credits (0.144% of Codex's week) |
| sonnet | 23 | 19 | 8 | 18 | $0.72 list (0.12%) |
| opus | 24 | 16 | 11 | 16 | $3.16 list (0.27%) |
| terra | 11 | 11 | 1 | 9 | 8.7 credits (0.104%) |
| luna | 5 | 5 | 1 | 4 | not measured (the meter did not move) |

Credits = weekly % × 8,400 / 100 (the pre-doubling Pro Lite window, §1–2); Claude weekly % uses the $1,525 window, as the JSON does. That basis is wrong for runs from 2026-10-30 on: since the doubling a Pro Lite point is about 168 credits (§2), so for those runs the credit figures in this section are about half their true value. The table is not recomputed here; the Codex credit figures (the lane rows and the local place's 672) mix both bases. List $ is
over the usable runs that have a list price (cloud has none: haiku 54 of 57, opus 11 of 16, sonnet 16 of 18). A
Claude lane's weekly % is the meter's rise during its wave of overlapping runs, split among them (`attribute_usage`).
The meter is account-wide, so that rise also holds the main session's and other machines' spend in the same minutes:
that is why haiku's share runs about 3× its list-price share and opus's only 1.3× (the cheaper the run, the larger
the borrowed part), and why subagents, which run while the main session works, show it most (haiku 0.106% per usable
unit as a subagent against 0.030% local). Read a Claude lane's weekly % as an upper bound and its list $ as its price.
Against §13 per usable unit: haiku $1.37 → $0.24, sol 27.3 → 12.1 credits, terra 5.6 → 8.7 credits, sonnet $7.12 →
$0.72, opus $3.26 → $3.16, luna 8.0 credits → unmeasured. The work changed more than the arms: §13's haiku and sonnet
units were large workflow builds, and sol's runs here were mostly substantive units at low and medium effort (36 of
49, median 13 min). These rows do not separate the mix from the price.

**By place** (Claude % is of Claude's week, Codex credits come from the Codex meter):

| Place | Runs | Reviewed | Merged as-is | Usable | Claude weekly % | Codex credits | List $ per usable |
|---|---:|---:|---:|---:|---:|---:|---|
| local | 129 | 127 | 62 | 123 | 5.61 | 672 | $0.76 |
| subagent | 21 | 21 | 12 | 20 | 2.55 | none | $0.50 |
| cloud | 26 | 10 | 10 | 10 | 0.84 | none | — |

**By class** (weekly % is of whichever provider's week the run used):

| Class | Runs | Reviewed | Merged as-is | Usable | Weekly % / usable | List $ / usable |
|---|---:|---:|---:|---:|---:|---|
| substantive | 98 | 89 | 30 | 87 | 0.115 | $0.66 |
| review | 33 | 31 | 31 | 31 | 0.038 | $0.11 |
| hard | 13 | 12 | 4 | 11 | 0.261 | $2.68 |
| research | 12 | 12 | 7 | 10 | 0.170 | $1.17 |
| design | 14 | 8 | 7 | 8 | 0.159 | $1.29 (1 run) |
| mechanical | 6 | 6 | 5 | 6 | 0.004 | $0.08 (3 runs) |

Against §13 usable rates: review 31/31 (24/24), substantive 87/89 (63/68), hard 11/12 (9/9), mechanical 6/6 (5/5),
research 10/12 (5/6). Merged as-is is still low for substantive work (30 of 89, 34%).

- **Local was the bulk and the most reliable.** 123 OK of 129 runs (4 NOOP, 1 FAILED, 1 UNKNOWN); 123 of 127 reviewed
  were usable. Sol made 49 of the 129, all usable, 15 merged as-is.
- **Subagents were usable but their verdicts are cautious.** 16 OK, 4 PARTIAL, 1 NOOP of 21, yet 20 of 21 were
  usable (12 merged as-is). A PARTIAL from a subagent is not a reason to redo the unit.
- **Cloud looks bad and was not.** 11 OK, 6 FAILED, 1 PARTIAL and 8 with no verdict. The 6 FAILED (opus high, design)
  were the first cloud runs on a repository whose organization lacked the Claude GitHub App: each session started
  from an uploaded bundle, could not push, and timed out at 600 s (LANES.md "Cloud runs" describes the preflight
  added afterwards). The 8 unknown were started together by another session around 03:00 and never finished their
  records; `lane --recover` would finish them, nobody has run it, so they stay unknown, not failed. All 10 reviewed
  cloud runs (7 design, 3 mechanical) were usable and merged as-is. Their billing is a separate question: on 2026-10-31 a lane-started Opus cloud session (its own work $28.86 Opus list, six subagents) moved Claude's 5h meter +6 and weekly +2, and `claude -p` in the cloud VM ($8.55 Sonnet list) moved the 5h meter +3; other sessions ran too, so both are upper bounds (LANES.md, "Billing of cloud runs"). The two cloud units that wrote this section and
  the 2026-10-31 benchmark note ran 8–9 min each; in the VM the whole kit suite (433 tests) took 151 s and
  `tests/test_lane_stats.py` 7.3 s, against 40 s on this PC while it was short of memory.
- **Haiku's ETAs ran short locally.** 5 of the 7 haiku local runs with an ETA took over 2× it: three high-effort
  substantive units estimated at 9–10 min took 37–45 min, and a research and a review unit took 4.6× and 2.5×. The
  estimator pools only runs with the same tag (`estimate_eta`), so Suite R and eval runs never fed these estimates.
  The three long units' briefs (6.5–7.5 KB) were barely larger than that of a same-tag unit that took 8 min (5.8 KB),
  so nothing the estimator sees told them apart [INFERRED].
- **Sol substantive finished early.** 31 runs, median actual 0.63× the ETA, 19 within 0.5–2×.

**Time.** 73 runs carry an ETA (recorded from 2026-10-29.1), all local or subagent: 40 (55%) landed within 0.5–2× of
it, against 63% within 2× in the §16 backtest. By class: substantive 28 of 54, research 8 of 10, review 4 of 5, hard
0 of 4. The two luna hard runs show a fault in the estimator, not in luna. One luna max unit stopped after 19 s with
no verdict against a 60-min ETA; `estimate_eta` skipped only QUOTA and BUSY runs, so it learned from that one, and
the next luna max hard unit was given 1 min and took 19 (the row's median ratio 9.7 is the mean of 0.01 and 19.5).
From 2026-10-31.6 the estimator learns only from runs that did work. The opus hard runs finished at 0.44× (local)
and 0.36× (subagent). Terra substantive (4 runs) ran at 1.11×, all four within range.

**Claude's own turn estimates** (`turn-meter`, 24 finished) ran ×0.53: Claude overestimates its own remaining time
about 2×.

**The Claude meter against §1.** `turn-meter calibrate` gives 0.0371% of the weekly meter per list dollar over 2
weekly windows: $1,374 list on this machine's main sessions and subagents, meter up 51%. The meter is account-wide and
also moved with `claude -p` lane runs and other machines, so 0.0371%/$ is an upper bound and the implied window,
about $2,700 list a week, a lower bound. Those are mostly Opus dollars (the main loop is Opus), and §1's $1,525 is in
Sonnet dollars: at Opus's weekly weight of 0.67 it predicts $2.2–2.3k of Opus a week, as the 10-28 cross-check found
($22.3 per 1%). This lower bound sits about 20% above that, so the week holds at least what §1 says, possibly more; a
window probe (`measure/`) would settle it, and §1 stands until one does. The Claude percentages in this section use
the $1,525 window.

**Census** (`turn-meter census --since 2026-10-28`): interactive Claude Code 18 sessions, 69.8 active hours, with
an interactive session open for 38.9 h; `claude -p` workers 82 sessions, 7.6 h; subagents 98 sessions, 5.0 h; Codex
`codex exec` 355 sessions, 22.8 h (terra 234 turns, sol 108, luna 14; includes Suite R and app evals).

**`lane-stats recommend`** (2026-10-31, all runs, all time): mechanical leans luna medium (P(best) 0.77, 152
reviewed); substantive leans haiku xhigh (0.52, 17); hard is still exploring opus high (0.44, 2); design leans opus
high (0.95, 6); review is locked on haiku low (0.98, 17); research leans haiku medium (0.87, 6).

## 19. Plan subsidy factors (2026-10-31)

A subsidy factor is the API value that a plan's allowance holds in a month, divided by the plan's monthly price. A month is 4.345 weeks, and the factor assumes the whole weekly allowance is used every week. Plan cost per task is the API cost per task divided by the factor. The values and intervals are in `findings/findings.json` (`subsidy`), and `findings/aa-cli-rate/index.html` shows the same table (generated by `tools/make-aa-cli-rate.py`, checked by `tools/check-aa-cli-rate.py`).

| Plan | Price / month | API value / month (interval) | Factor (interval) | Status |
|---|---:|---:|---:|---|
| Claude Max 20x, Sonnet | $200 | $6,626 ($4,419 to $13,252) | 33.1× (22.1 to 66.3) | measured |
| Claude Max 20x, Opus | $200 | $11,732 ($11,732 to $60,238) | >= 58.7× (58.7 to 301.2) | lower bound |
| Claude Max 20x, Haiku | $200 | $3,852 ($1,178 or more) | 19.3× (5.9 or more) | pending |
| Claude Max 20x, Fable | $200 | $1,960 ($492 to $8,835) | 9.8× (2.5 to 44.2) | measured |
| Codex Pro Lite, now | $100 | $2,920 ($2,711 to $3,198) | 29.2× (27.1 to 32.0) | 2× the measured week, not re-measured |
| Codex Pro Lite, before 2026-10-29 | $100 | $1,460 ($1,356 to $1,599) | 14.6× (13.6 to 16.0) | measured |
| Codex Plus | $20 | $252 ($236 to $259) | 12.6× (11.8 to 12.9) | measured |
| Google AI Pro | $19.99 | $348 or more | >= 17.4× (17.4 or more) | lower bound |

- Claude models share one weekly allowance on Max 20x and draw it down at different weights (`claude.weights`: Sonnet 1, Opus 0.67 weekly, Fable 1.69 weekly). Each model's factor is the Sonnet-based allowance divided by its weight.
- Opus is a lower bound. Its point and low use the $2,700 a week calibration floor (§18); the weight alone gives $2,276 a week.
- Haiku's weekly weight is pending (`claude.weights.haiku.weekly` is empty). Its factor uses the 5h weight (1.72, interval 0 to 3.75), so it has no upper bound. It resolves once `findings.json` `claude.weights.haiku.weekly` has a value.
- Fable may take at most half the shared week (Anthropic; §1), so its weekly API value is half of Sonnet's, divided by Fable's weekly weight (1.69, interval 0.75 to 4.49).
- Pro Lite now is two times the measured week, since the 2026-10-29 doubling (§2). It has not been re-measured in credits.
- Codex prices every model on one credit card, so each Codex plan has one factor. Sol is charged 1.19 to 1.36 times its card price (§2), so its plan cost is likely higher than the table implies.
- Google AI Pro is a lower bound: at least about 100M gemini-3.8-flash tokens a week, about $80 at list (§3).
- Example: a task that lists at $10 of Sonnet API value costs about $0.30 of plan dollars on Max 20x (10 ÷ 33.1), if the whole allowance is used.
