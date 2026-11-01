# Reviewed lane runs on real work (2026-10-22 to 2026-10-28)

One machine's real work units dispatched through `lane` after the 2026-10-22 snapshot: 124 runs in 32 lane-by-effort-by-class rows with at least one review (112 reviewed, 106 usable). Capability tests (Suite R), n8n app evals, n8n workflow executions and smoke runs are left out; the app evals are in `findings/app-evals/`. Weekly % is the run's share of its provider's week at the measured windows (Codex Pro Lite 8,400 credits, Claude $1,525 list; FINDINGS §1); gemini is free and has no weekly share here. Usable = accepted + fixed. No run identifiers, tags, notes, projects or paths. The JSON copy has the same rows. `—` means no value.

| Lane | Effort | Class | Runs | Reviewed | Accepted | Usable | Rework | Rejected | Fix min | Median min | Weekly % / usable | List $ / usable |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| astra | xhigh | hard | 2 | 2 | 50.0% | 100.0% | 0 | 0 | 5 | 30.480 | 2.761 | 9.277 |
| haiku | high | research | 4 | 2 | 0.0% | 100.0% | 0 | 0 | 2 | 20.046 | 0.463 | 7.058 |
| haiku | high | substantive | 16 | 14 | 71.4% | 100.0% | 0 | 0 | 35 | 22.176 | 0.111 | 1.689 |
| haiku | low | review | 15 | 15 | 100.0% | 100.0% | 0 | 0 | 0 | 3.369 | 0.019 | 0.294 |
| haiku | medium | research | 3 | 2 | 100.0% | 100.0% | 0 | 0 | 0 | 1.717 | 0.070 | 1.074 |
| haiku | medium | review | 10 | 6 | 100.0% | 100.0% | 0 | 0 | 0 | 4.252 | 0.013 | 0.191 |
| haiku | xhigh | substantive | 11 | 11 | 90.9% | 100.0% | 0 | 0 | 0 | 27.052 | 0.138 | 2.107 |
| luna | high | substantive | 1 | 1 | 0.0% | 0.0% | 1 | 0 | 0 | 20.714 | — | — |
| luna | max | substantive | 4 | 4 | 75.0% | 100.0% | 0 | 0 | 12 | 43.738 | 0.087 | 0.291 |
| luna | medium | research | 1 | 1 | 0.0% | 0.0% | 1 | 0 | 0 | 3.270 | — | — |
| luna | medium | substantive | 2 | 2 | 0.0% | 0.0% | 0 | 2 | 0 | 6.409 | — | — |
| luna | xhigh | substantive | 1 | 1 | 100.0% | 100.0% | 0 | 0 | 0 | 19.594 | 0.041 | 0.139 |
| opus | medium | substantive | 2 | 2 | 100.0% | 100.0% | 0 | 0 | 0 | 10.541 | 0.214 | 3.263 |
| sol | high | substantive | 4 | 4 | 50.0% | 100.0% | 0 | 0 | 10 | 17.700 | 0.278 | 0.936 |
| sol | low | mechanical | 3 | 3 | 100.0% | 100.0% | 0 | 0 | 0 | 7.022 | 0.122 | 0.411 |
| sol | low | substantive | 3 | 3 | 100.0% | 100.0% | 0 | 0 | 0 | 20.456 | 0.412 | 1.383 |
| sol | medium | hard | 2 | 2 | 100.0% | 100.0% | 0 | 0 | 0 | 16.906 | 0.288 | 0.969 |
| sol | medium | review | 1 | 1 | 100.0% | 100.0% | 0 | 0 | 0 | 4.628 | 0.102 | 0.344 |
| sol | medium | substantive | 11 | 8 | 50.0% | 87.5% | 1 | 0 | 19 | 16.346 | 0.493 | 1.655 |
| sol | xhigh | hard | 3 | 3 | 0.0% | 100.0% | 0 | 0 | 30 | 15.513 | 0.225 | 0.755 |
| sol | xhigh | substantive | 3 | 3 | 66.7% | 100.0% | 0 | 0 | 4 | 11.252 | 0.314 | 1.056 |
| sonnet | max | hard | 2 | 2 | 50.0% | 100.0% | 0 | 0 | 15 | 83.087 | 1.313 | 20.025 |
| sonnet | medium | research | 1 | 1 | 0.0% | 100.0% | 0 | 0 | 1 | 14.539 | 0.274 | 4.179 |
| sonnet | medium | substantive | 6 | 6 | 100.0% | 100.0% | 0 | 0 | 0 | 19.651 | 0.217 | 3.307 |
| terra | high | substantive | 3 | 3 | 66.7% | 100.0% | 0 | 0 | 5 | 6.288 | 0.047 | 0.159 |
| terra | low | mechanical | 1 | 1 | 0.0% | 100.0% | 0 | 0 | 8 | 3.851 | 0.040 | 0.135 |
| terra | low | substantive | 2 | 2 | 0.0% | 50.0% | 1 | 0 | 1 | 3.758 | 0.077 | 0.257 |
| terra | max | review | 1 | 1 | 100.0% | 100.0% | 0 | 0 | 0 | 11.958 | 0.256 | 0.859 |
| terra | medium | mechanical | 1 | 1 | 0.0% | 100.0% | 0 | 0 | 7 | 3.708 | 0.032 | 0.107 |
| terra | medium | review | 1 | 1 | 100.0% | 100.0% | 0 | 0 | 0 | 1.128 | 0.029 | 0.096 |
| terra | medium | substantive | 2 | 2 | 50.0% | 100.0% | 0 | 0 | 6 | 4.071 | 0.035 | 0.119 |
| terra | xhigh | substantive | 2 | 2 | 50.0% | 100.0% | 0 | 0 | 3 | 7.738 | 0.078 | 0.260 |
