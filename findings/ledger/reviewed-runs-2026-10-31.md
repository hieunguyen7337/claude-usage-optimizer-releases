# Reviewed lane runs on real work (2026-10-28 to 2026-10-31)

One Windows machine's real work units dispatched through `lane` (local processes, subagents and cloud sessions) from 2026-10-28 16:22 (the FINDINGS §13 snapshot) to 2026-10-31 13:10 local time: 176 runs in 34 lane-by-effort-by-class rows, 158 reviewed, about 153 usable. Suite R capability runs, app-eval runs and probes are left out. Weekly % is the run's share of its provider's week at the measured windows (Codex Pro Lite 8,400 credits, Claude $1,525 list; FINDINGS §1); `—` means no value (a cloud run has no list price, and a row with no review has no usable rate). Usable = accepted + fixed. The ETA column is the median actual/ETA of the row's runs that carry an ETA. This file has no rework, rejected or fix-minute columns, because the source JSON has none. No run identifiers, tags, notes, projects or paths. The JSON copy has the same rows.

| Lane | Effort | Class | Runs | Reviewed | OK | Accepted | Usable | Median min | Actual / ETA | Weekly % / usable | List $ / usable |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| haiku | high | mechanical | 1 | 1 | 100.0% | 100.0% | 100.0% | 3.548 | — | 0.010 | — |
| haiku | high | research | 1 | 1 | 0.0% | 0.0% | 0.0% | 17.556 | 1.428 | — | — |
| haiku | high | substantive | 15 | 14 | 86.7% | 50.0% | 100.0% | 10.776 | 3.266 | 0.091 | 0.428 |
| haiku | low | mechanical | 4 | 4 | 75.0% | 100.0% | 100.0% | 3.443 | — | 0.004 | 0.012 |
| haiku | low | review | 4 | 2 | 25.0% | 100.0% | 100.0% | 2.674 | — | 0.000 | 0.090 |
| haiku | medium | research | 3 | 3 | 66.7% | 100.0% | 100.0% | 16.284 | 2.033 | 0.037 | 0.634 |
| haiku | medium | review | 28 | 28 | 96.4% | 100.0% | 100.0% | 2.837 | 1.402 | 0.036 | 0.091 |
| haiku | xhigh | hard | 1 | 1 | 100.0% | 0.0% | 100.0% | 12.765 | — | 0.110 | 0.531 |
| haiku | xhigh | substantive | 7 | 4 | 57.1% | 75.0% | 100.0% | 8.960 | 0.543 | 0.000 | 0.196 |
| luna | max | hard | 2 | 2 | 50.0% | 0.0% | 50.0% | 9.806 | 9.749 | 0.000 | 0.372 |
| luna | max | substantive | 2 | 2 | 100.0% | 50.0% | 100.0% | 19.936 | — | 0.000 | 0.119 |
| luna | xhigh | substantive | 1 | 1 | 100.0% | 0.0% | 100.0% | 6.323 | 0.400 | 0.000 | 0.041 |
| opus | high | design | 12 | 6 | 50.0% | 83.3% | 100.0% | 11.364 | — | 0.153 | 0.214 |
| opus | high | hard | 2 | 2 | 100.0% | 100.0% | 100.0% | 8.537 | 0.400 | 0.354 | 1.756 |
| opus | max | hard | 3 | 2 | 66.7% | 50.0% | 100.0% | 24.673 | — | 0.500 | 11.176 |
| opus | medium | substantive | 7 | 6 | 85.7% | 50.0% | 100.0% | 6.909 | 0.467 | 0.274 | 1.275 |
| sol | high | substantive | 2 | 2 | 100.0% | 50.0% | 100.0% | 14.556 | 1.469 | 0.000 | 0.932 |
| sol | low | substantive | 12 | 12 | 100.0% | 41.7% | 100.0% | 10.676 | 0.792 | 0.086 | 0.588 |
| sol | medium | hard | 3 | 3 | 100.0% | 0.0% | 100.0% | 15.127 | — | 0.289 | 0.717 |
| sol | medium | research | 6 | 6 | 100.0% | 50.0% | 100.0% | 12.629 | 0.898 | 0.189 | 1.084 |
| sol | medium | substantive | 24 | 24 | 100.0% | 16.7% | 100.0% | 13.876 | 0.580 | 0.144 | 0.840 |
| sol | xhigh | research | 1 | 1 | 100.0% | 100.0% | 100.0% | 20.844 | 1.755 | 0.409 | 2.124 |
| sol | xhigh | review | 1 | 1 | 100.0% | 100.0% | 100.0% | 11.989 | 1.146 | 0.166 | 0.654 |
| sonnet | high | substantive | 9 | 8 | 88.9% | 37.5% | 87.5% | 8.984 | 0.439 | 0.138 | 1.167 |
| sonnet | max | design | 1 | 1 | 100.0% | 100.0% | 100.0% | 71.922 | — | 0.199 | — |
| sonnet | medium | substantive | 11 | 9 | 81.8% | 33.3% | 100.0% | 3.361 | 0.613 | 0.093 | 0.366 |
| sonnet | xhigh | design | 1 | 1 | 100.0% | 100.0% | 100.0% | 57.215 | — | 0.158 | — |
| sonnet | xhigh | substantive | 1 | 0 | 0.0% | — | — | — | — | — | — |
| terra | high | hard | 1 | 1 | 100.0% | 100.0% | 100.0% | 8.087 | — | 0.000 | 0.300 |
| terra | high | substantive | 3 | 3 | 66.7% | 0.0% | 66.7% | 9.392 | 1.127 | 0.072 | 0.395 |
| terra | low | research | 1 | 1 | 100.0% | 0.0% | 0.0% | 2.322 | 0.730 | — | — |
| terra | medium | hard | 1 | 1 | 100.0% | 0.0% | 100.0% | 9.549 | — | 0.179 | 0.220 |
| terra | medium | mechanical | 1 | 1 | 100.0% | 0.0% | 100.0% | 5.611 | — | 0.000 | 0.181 |
| terra | medium | substantive | 4 | 4 | 100.0% | 0.0% | 100.0% | 9.372 | 1.094 | 0.153 | 0.309 |
