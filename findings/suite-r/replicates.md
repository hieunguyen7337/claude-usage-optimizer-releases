# Suite suite_r replicates

36 items; 38 defects. Recall is strict recall over every defect; false alarms are unmatched findings per suite item over all items. A rep is one complete run of an arm; partial arms are excluded: opus-max-claude-fable-5-1.

## Run-to-run spread

Pooled arms with at least two reps. SD is the sample SD (n-1) over reps. Stable share is the defects found by every rep divided by the defects found by any rep. Self-pair recall is the mean union recall over unordered pairs of reps of the same arm; self-pair gain is that minus the mean single-rep recall. The best partner is the other pooled arm with the largest size-2 panel gain over this arm's mean recall (the panels definition: every rep combination averaged), so the two gains are comparable.

| Pooled arm | Reps | Recall by rep | Mean | SD | Min | Max | False alarms/item | Stable share | Self-pair recall | Self-pair gain | Best partner | Pair recall | Pair gain |
|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---|---:|---:|
| astra\|gpt-6-astra\|high | 1,2 | 0.895, 0.921 | 0.908 | 0.019 | 0.895 | 0.921 | 0.306 | 0.917 (33/36) | 0.947 | 0.039 | haiku\|claude-haiku-5-5\|medium | 1.000 | 0.092 |
| astra\|gpt-6-astra\|low | 1,2 | 0.921, 0.921 | 0.921 | 0.000 | 0.921 | 0.921 | 0.306 | 1.000 (35/35) | 0.921 | 0.000 | haiku\|claude-haiku-5-5\|medium | 1.000 | 0.079 |
| astra\|gpt-6-astra\|max | 1,2,3 | 0.974, 0.974, 1.000 | 0.982 | 0.015 | 0.974 | 1.000 | 0.315 | 0.974 (37/38) | 0.991 | 0.009 | haiku\|claude-haiku-5-5\|medium | 1.000 | 0.018 |
| astra\|gpt-6-astra\|medium | 1,2 | 0.895, 0.895 | 0.895 | 0.000 | 0.895 | 0.895 | 0.250 | 1.000 (34/34) | 0.895 | 0.000 | haiku\|claude-haiku-5-5\|medium | 1.000 | 0.105 |
| astra\|gpt-6-astra\|xhigh | 1,2,3 | 0.947, 0.974, 0.895 | 0.939 | 0.040 | 0.895 | 0.974 | 0.352 | 0.919 (34/37) | 0.965 | 0.026 | haiku\|claude-haiku-5-5\|medium | 1.000 | 0.061 |
| luna\|gpt-6-luna\|high | 1,2,3,4 | 0.605, 0.763, 0.711, 0.789 | 0.717 | 0.081 | 0.605 | 0.789 | 0.222 | 0.594 (19/32) | 0.807 | 0.090 | haiku\|claude-haiku-5-5\|xhigh | 1.000 | 0.283 |
| luna\|gpt-6-luna\|low | 1,2,3,4 | 0.447, 0.342, 0.500, 0.263 | 0.388 | 0.106 | 0.263 | 0.500 | 0.139 | 0.154 (4/26) | 0.561 | 0.173 | haiku\|claude-haiku-5-5\|xhigh | 1.000 | 0.612 |
| luna\|gpt-6-luna\|max | 1,2,3,4 | 0.789, 0.789, 0.816, 0.868 | 0.816 | 0.037 | 0.789 | 0.868 | 0.396 | 0.595 (22/37) | 0.917 | 0.101 | haiku\|claude-haiku-5-5\|xhigh | 1.000 | 0.184 |
| luna\|gpt-6-luna\|medium | 1,2,3,4 | 0.526, 0.500, 0.632, 0.632 | 0.572 | 0.069 | 0.500 | 0.632 | 0.188 | 0.355 (11/31) | 0.711 | 0.138 | haiku\|claude-haiku-5-5\|xhigh | 1.000 | 0.428 |
| luna\|gpt-6-luna\|xhigh | 1,2,3,4 | 0.763, 0.842, 0.763, 0.763 | 0.783 | 0.039 | 0.763 | 0.842 | 0.319 | 0.583 (21/36) | 0.890 | 0.107 | haiku\|claude-haiku-5-5\|xhigh | 1.000 | 0.217 |
| sol\|gpt-6.1-sol\|high | 1,2,3 | 0.921, 0.895, 0.895 | 0.904 | 0.015 | 0.895 | 0.921 | 0.361 | 0.943 (33/35) | 0.921 | 0.018 | haiku\|claude-haiku-5-5\|medium | 1.000 | 0.096 |
| sol\|gpt-6.1-sol\|low | 1,2,3 | 0.816, 0.868, 0.842 | 0.842 | 0.026 | 0.816 | 0.868 | 0.269 | 0.909 (30/33) | 0.868 | 0.026 | haiku\|claude-haiku-5-5\|xhigh | 1.000 | 0.158 |
| sol\|gpt-6.1-sol\|max | 1,2,3 | 0.947, 0.947, 0.947 | 0.947 | 0.000 | 0.947 | 0.947 | 0.315 | 0.946 (35/37) | 0.965 | 0.018 | haiku\|claude-haiku-5-5\|medium | 1.000 | 0.053 |
| sol\|gpt-6.1-sol\|medium | 1,2,3 | 0.895, 0.868, 0.868 | 0.877 | 0.015 | 0.868 | 0.895 | 0.269 | 0.941 (32/34) | 0.895 | 0.018 | haiku\|claude-haiku-5-5\|xhigh | 1.000 | 0.123 |
| sol\|gpt-6.1-sol\|xhigh | 1,2,3 | 0.947, 0.921, 0.895 | 0.921 | 0.026 | 0.895 | 0.947 | 0.343 | 0.917 (33/36) | 0.947 | 0.026 | haiku\|claude-haiku-5-5\|medium | 1.000 | 0.079 |
| sonnet\|claude-sonnet-5-5\|high | 1,2 | 0.921, 0.868 | 0.895 | 0.037 | 0.868 | 0.921 | 0.153 | 0.943 (33/35) | 0.921 | 0.026 | haiku\|claude-haiku-5-5\|xhigh | 1.000 | 0.105 |
| sonnet\|claude-sonnet-5-5\|max | 1,2 | 0.974, 0.974 | 0.974 | 0.000 | 0.974 | 0.974 | 0.222 | 1.000 (37/37) | 0.974 | 0.000 | haiku\|claude-haiku-5-5\|medium | 1.000 | 0.026 |
| sonnet\|claude-sonnet-5-5\|xhigh | 1,2 | 0.947, 0.921 | 0.934 | 0.019 | 0.921 | 0.947 | 0.458 | 0.972 (35/36) | 0.947 | 0.013 | haiku\|claude-haiku-5-5\|xhigh | 1.000 | 0.066 |

## Hold-out

Panels are built from reps 1,2 (rep <= 2), then the training build's frontier panels and its cheapest panel for each recall target and size are re-scored on the held-out reps 3,4 (rep > 2). A member marked * is scored on its held-out reps alone; an unmarked member has none and keeps its training reps, so a panel with no marked member is not tested. Difference is held-out minus in-sample recall. 7 of 11 panels have a held-out member; their mean difference is 0.026.

| Roles | Members | In-sample recall | Held-out recall | Difference | In-sample false alarms/item | Held-out false alarms/item | Held-out reps used |
|---|---|---:|---:|---:|---:|---:|---|
| frontier | luna\|gpt-6-luna\|medium* | 0.513 | 0.632 | 0.118 | 0.181 | 0.194 | luna\|gpt-6-luna\|medium 3,4 |
| frontier | luna\|gpt-6-luna\|high* | 0.684 | 0.750 | 0.066 | 0.222 | 0.222 | luna\|gpt-6-luna\|high 3,4 |
| frontier | haiku\|claude-haiku-5-5\|low | 0.895 | 0.895 | 0.000 | 0.250 | 0.250 | none (not tested) |
| frontier | haiku\|claude-haiku-5-5\|medium | 0.947 | 0.947 | 0.000 | 0.389 | 0.389 | none (not tested) |
| frontier; target 0.95 size 2 | haiku\|claude-haiku-5-5\|medium, luna\|gpt-6-luna\|medium* | 0.961 | 0.961 | 0.000 | 0.569 | 0.583 | luna\|gpt-6-luna\|medium 3,4 |
| frontier; target 0.97 size 2 | haiku\|claude-haiku-5-5\|medium, luna\|gpt-6-luna\|high* | 0.974 | 0.974 | 0.000 | 0.611 | 0.611 | luna\|gpt-6-luna\|high 3,4 |
| frontier; target 1.00 size 2 | haiku\|claude-haiku-5-5\|high, haiku\|claude-haiku-5-5\|medium | 1.000 | 1.000 | 0.000 | 1.222 | 1.222 | none (not tested) |
| target 0.95 size 1; target 0.97 size 1; target 1.00 size 1 | haiku\|claude-haiku-5-5\|xhigh | 1.000 | 1.000 | 0.000 | 1.000 | 1.000 | none (not tested) |
| target 0.95 size 3 | haiku\|claude-haiku-5-5\|medium, luna\|gpt-6-luna\|low*, luna\|gpt-6-luna\|medium* | 0.961 | 0.961 | 0.000 | 0.694 | 0.736 | luna\|gpt-6-luna\|low 3,4; luna\|gpt-6-luna\|medium 3,4 |
| target 0.97 size 3 | haiku\|claude-haiku-5-5\|medium, luna\|gpt-6-luna\|high*, luna\|gpt-6-luna\|medium* | 0.974 | 0.974 | 0.000 | 0.792 | 0.806 | luna\|gpt-6-luna\|high 3,4; luna\|gpt-6-luna\|medium 3,4 |
| target 1.00 size 3 | haiku\|claude-haiku-5-5\|high, haiku\|claude-haiku-5-5\|medium, luna\|gpt-6-luna\|medium* | 1.000 | 1.000 | 0.000 | 1.403 | 1.417 | luna\|gpt-6-luna\|medium 3,4 |

### Does the training pick still meet its target when held out?

Each size's cheapest panel for the target, and the pick: the cheapest of those across sizes. Tested says whether the panel has any held-out member.

| Target | Size | Members | Tested | In-sample recall | Held-out recall | Meets held-out |
|---:|---|---|---|---:|---:|---|
| 0.95 | 1 | haiku\|claude-haiku-5-5\|xhigh | no | 1.000 | 1.000 | yes |
| 0.95 | 2 (pick) | haiku\|claude-haiku-5-5\|medium, luna\|gpt-6-luna\|medium | yes | 0.961 | 0.961 | yes |
| 0.95 | 3 | haiku\|claude-haiku-5-5\|medium, luna\|gpt-6-luna\|low, luna\|gpt-6-luna\|medium | yes | 0.961 | 0.961 | yes |
| 0.97 | 1 | haiku\|claude-haiku-5-5\|xhigh | no | 1.000 | 1.000 | yes |
| 0.97 | 2 (pick) | haiku\|claude-haiku-5-5\|medium, luna\|gpt-6-luna\|high | yes | 0.974 | 0.974 | yes |
| 0.97 | 3 | haiku\|claude-haiku-5-5\|medium, luna\|gpt-6-luna\|high, luna\|gpt-6-luna\|medium | yes | 0.974 | 0.974 | yes |
| 1.00 | 1 | haiku\|claude-haiku-5-5\|xhigh | no | 1.000 | 1.000 | yes |
| 1.00 | 2 (pick) | haiku\|claude-haiku-5-5\|high, haiku\|claude-haiku-5-5\|medium | no | 1.000 | 1.000 | yes |
| 1.00 | 3 | haiku\|claude-haiku-5-5\|high, haiku\|claude-haiku-5-5\|medium, luna\|gpt-6-luna\|medium | yes | 1.000 | 1.000 | yes |
