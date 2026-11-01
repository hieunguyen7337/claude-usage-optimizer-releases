# Suite suite_r reviewer panels

36 items; 38 defects; panels include up to 3 pooled arms.

Partial arms excluded: opus-max-claude-fable-5-1

## Pareto frontier

Members are pooled lane/model/effort groups; recall averages all replicate combinations; false alarms are unmatched findings per suite item; cost points are summed %week/item multiplied by provider scarcity; weekly shares are summed %week/item by provider.

| Members | Union recall | False alarms/item | Cost points/item | Weekly share by provider |
|---|---:|---:|---:|---|
| luna\|gpt-6-luna\|medium | 0.572 | 0.188 | 0.00036 | codex 0.00118% |
| luna\|gpt-6-luna\|high | 0.717 | 0.222 | 0.00050 | codex 0.00168% |
| haiku\|claude-haiku-5-5\|low | 0.895 | 0.250 | 0.00054 | claude 0.00054% |
| haiku\|claude-haiku-5-5\|medium | 0.947 | 0.389 | 0.00074 | claude 0.00074% |
| haiku\|claude-haiku-5-5\|medium, luna\|gpt-6-luna\|medium | 0.961 | 0.576 | 0.00109 | claude 0.00074%, codex 0.00118% |
| haiku\|claude-haiku-5-5\|medium, luna\|gpt-6-luna\|high | 0.974 | 0.611 | 0.00124 | claude 0.00074%, codex 0.00168% |
| haiku\|claude-haiku-5-5\|medium, luna\|gpt-6-luna\|max | 0.980 | 0.785 | 0.00147 | claude 0.00074%, codex 0.00246% |
| haiku\|claude-haiku-5-5\|high, haiku\|claude-haiku-5-5\|medium | 1.000 | 1.222 | 0.00184 | claude 0.00184% |

## Cheapest panels at each recall target

Size is the number of distinct pooled arms; cost and false alarms use the same definitions as above.

| Target | Size | Members | Union recall | Cost points/item | False alarms/item |
|---:|---:|---|---:|---:|---:|
| 0.95 | 1 | haiku\|claude-haiku-5-5\|xhigh | 1.000 | 0.00332 | 1.000 |
| 0.95 | 2 | haiku\|claude-haiku-5-5\|medium, luna\|gpt-6-luna\|medium | 0.961 | 0.00109 | 0.576 |
| 0.95 | 3 | haiku\|claude-haiku-5-5\|medium, luna\|gpt-6-luna\|low, luna\|gpt-6-luna\|medium | 0.961 | 0.00155 | 0.715 |
| 0.97 | 1 | haiku\|claude-haiku-5-5\|xhigh | 1.000 | 0.00332 | 1.000 |
| 0.97 | 2 | haiku\|claude-haiku-5-5\|medium, luna\|gpt-6-luna\|high | 0.974 | 0.00124 | 0.611 |
| 0.97 | 3 | haiku\|claude-haiku-5-5\|medium, luna\|gpt-6-luna\|high, luna\|gpt-6-luna\|medium | 0.974 | 0.00160 | 0.799 |
| 1.00 | 1 | haiku\|claude-haiku-5-5\|xhigh | 1.000 | 0.00332 | 1.000 |
| 1.00 | 2 | haiku\|claude-haiku-5-5\|high, haiku\|claude-haiku-5-5\|medium | 1.000 | 0.00184 | 1.222 |
| 1.00 | 3 | haiku\|claude-haiku-5-5\|high, haiku\|claude-haiku-5-5\|medium, luna\|gpt-6-luna\|medium | 1.000 | 0.00219 | 1.410 |

## Best partner for each pooled arm

Recall gain is pair union recall minus the single arm's replicate-averaged recall.

| Single arm | Best partner | Recall gain |
|---|---|---:|
| astra\|gpt-6-astra\|high | haiku\|claude-haiku-5-5\|medium | 0.092 |
| astra\|gpt-6-astra\|low | haiku\|claude-haiku-5-5\|medium | 0.079 |
| astra\|gpt-6-astra\|max | haiku\|claude-haiku-5-5\|medium | 0.018 |
| astra\|gpt-6-astra\|medium | haiku\|claude-haiku-5-5\|medium | 0.105 |
| astra\|gpt-6-astra\|xhigh | haiku\|claude-haiku-5-5\|medium | 0.061 |
| haiku\|claude-haiku-5-5\|high | haiku\|claude-haiku-5-5\|medium | 0.053 |
| haiku\|claude-haiku-5-5\|low | haiku\|claude-haiku-5-5\|xhigh | 0.105 |
| haiku\|claude-haiku-5-5\|max | haiku\|claude-haiku-5-5\|medium | 0.026 |
| haiku\|claude-haiku-5-5\|medium | haiku\|claude-haiku-5-5\|high | 0.053 |
| haiku\|claude-haiku-5-5\|xhigh | luna\|gpt-6-luna\|medium | 0.000 |
| luna\|gpt-6-luna\|high | haiku\|claude-haiku-5-5\|xhigh | 0.283 |
| luna\|gpt-6-luna\|low | haiku\|claude-haiku-5-5\|xhigh | 0.612 |
| luna\|gpt-6-luna\|max | haiku\|claude-haiku-5-5\|xhigh | 0.184 |
| luna\|gpt-6-luna\|medium | haiku\|claude-haiku-5-5\|xhigh | 0.428 |
| luna\|gpt-6-luna\|xhigh | haiku\|claude-haiku-5-5\|xhigh | 0.217 |
| opus\|claude-fable-5-1\|high | haiku\|claude-haiku-5-5\|medium | 0.079 |
| opus\|claude-fable-5-1\|low | haiku\|claude-haiku-5-5\|medium | 0.053 |
| opus\|claude-fable-5-1\|medium | haiku\|claude-haiku-5-5\|medium | 0.026 |
| opus\|claude-fable-5-1\|xhigh | haiku\|claude-haiku-5-5\|medium | 0.053 |
| opus\|claude-opus-5-5\|high | haiku\|claude-haiku-5-5\|xhigh | 0.053 |
| opus\|claude-opus-5-5\|low | haiku\|claude-haiku-5-5\|xhigh | 0.079 |
| opus\|claude-opus-5-5\|max | luna\|gpt-6-luna\|medium | 0.000 |
| opus\|claude-opus-5-5\|medium | haiku\|claude-haiku-5-5\|medium | 0.053 |
| opus\|claude-opus-5-5\|xhigh | haiku\|claude-haiku-5-5\|xhigh | 0.053 |
| sol\|gpt-6.1-sol\|high | haiku\|claude-haiku-5-5\|medium | 0.096 |
| sol\|gpt-6.1-sol\|low | haiku\|claude-haiku-5-5\|xhigh | 0.158 |
| sol\|gpt-6.1-sol\|max | haiku\|claude-haiku-5-5\|medium | 0.053 |
| sol\|gpt-6.1-sol\|medium | haiku\|claude-haiku-5-5\|xhigh | 0.123 |
| sol\|gpt-6.1-sol\|xhigh | haiku\|claude-haiku-5-5\|medium | 0.079 |
| sonnet\|claude-sonnet-5-5\|high | haiku\|claude-haiku-5-5\|xhigh | 0.105 |
| sonnet\|claude-sonnet-5-5\|low | haiku\|claude-haiku-5-5\|xhigh | 0.158 |
| sonnet\|claude-sonnet-5-5\|max | haiku\|claude-haiku-5-5\|medium | 0.026 |
| sonnet\|claude-sonnet-5-5\|medium | haiku\|claude-haiku-5-5\|xhigh | 0.132 |
| sonnet\|claude-sonnet-5-5\|xhigh | haiku\|claude-haiku-5-5\|xhigh | 0.066 |

## Defect coverage

Pooled arms found counts groups with at least one replicate that found the defect.

| Defect id | Pooled arms found |
|---|---:|
| 001:D2 | 34 |
| 002:D1 | 34 |
| 003:D2 | 34 |
| 004:D1 | 34 |
| 006:D1 | 34 |
| 007:D2 | 34 |
| 008:D1 | 34 |
| 009:D1 | 34 |
| 014:D1 | 34 |
| 014:D2 | 34 |
| 015:D1 | 34 |
| 019:D1 | 34 |
| 021:D1 | 34 |
| 022:D1 | 34 |
| 022:D2 | 34 |
| 023:D1 | 34 |
| 024:D1 | 34 |
| 027:D1 | 34 |
| 029:D1 | 34 |
| 030:D1 | 34 |
| 005:D1 | 33 |
| 007:D1 | 33 |
| 010:D1 | 33 |
| 011:D1 | 33 |
| 012:D1 | 33 |
| 017:D1 | 33 |
| 020:D1 | 33 |
| 001:D1 | 32 |
| 016:D1 | 32 |
| 025:D1 | 32 |
| 028:D1 | 32 |
| 013:D1 | 30 |
| 030:D2 | 30 |
| 005:D2 | 28 |
| 026:D1 | 24 |
| 018:D2 | 21 |
| 003:D1 | 18 |
| 018:D1 | 6 |

Never found: none
