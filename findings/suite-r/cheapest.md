# Cheapest Suite R arms that succeed

Candidates are pooled lane × model × effort groups; singleton groups represent one run. Cost efficiency is weekly-window share or API list USD per usable item.

## (a) recall_planted_v2 ≥ 0.90

Clearing arms: 26.

| Lane | Model | Effort | Runs | Recall v2 | Precision v2 | Usable v2 | Recall CI low | Precision CI low | % week / usable | API $ / usable |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| astra | gpt-6-astra | low | 2 | 0.947 | 1.000 | 0.972 | 0.865 | 1.000 | 0.11044 | 0.3711 |
| astra | gpt-6-astra | medium | 2 | 0.921 | 1.000 | 0.972 | 0.833 | 1.000 | 0.11437 | 0.3843 |
| astra | gpt-6-astra | high | 2 | 0.934 | 1.000 | 0.972 | 0.865 | 1.000 | 0.14666 | 0.4928 |
| astra | gpt-6-astra | xhigh | 3 | 0.956 | 0.986 | 0.991 | 0.892 | 0.955 | 0.20075 | 0.6745 |
| astra | gpt-6-astra | max | 3 | 0.974 | 0.993 | 1.000 | 0.917 | 0.977 | 0.22274 | 0.7484 |
| haiku | claude-haiku-5-5 | low | 1 | 0.921 | 0.884 | 0.944 | 0.800 | 0.766 | 0.00057 | 0.0087 |
| haiku | claude-haiku-5-5 | medium | 1 | 0.974 | 0.840 | 0.944 | 0.914 | 0.735 | 0.00078 | 0.0119 |
| haiku | claude-haiku-5-5 | high | 1 | 0.974 | 0.742 | 0.944 | 0.917 | 0.616 | 0.00116 | 0.0177 |
| haiku | claude-haiku-5-5 | xhigh | 1 | 0.974 | 0.703 | 0.917 | 0.917 | 0.581 | 0.00362 | 0.0552 |
| haiku | claude-haiku-5-5 | max | 1 | 0.974 | 0.782 | 0.944 | 0.917 | 0.680 | 0.01120 | 0.1708 |
| opus | claude-fable-5-1 | low | 1 | 0.974 | 0.864 | 1.000 | 0.917 | 0.766 | 0.04718 | 0.7195 |
| opus | claude-fable-5-1 | medium | 1 | 1.000 | 0.815 | 0.944 | 1.000 | 0.692 | 0.05628 | 0.8582 |
| opus | claude-fable-5-1 | high | 1 | 0.974 | 0.843 | 0.972 | 0.917 | 0.732 | 0.07357 | 1.1219 |
| opus | claude-fable-5-1 | xhigh | 1 | 0.974 | 0.885 | 1.000 | 0.917 | 0.788 | 0.11177 | 1.7045 |
| opus | claude-opus-5-5 | low | 1 | 0.974 | 0.886 | 1.000 | 0.917 | 0.786 | 0.01503 | 0.2292 |
| opus | claude-opus-5-5 | medium | 1 | 0.974 | 0.827 | 0.972 | 0.917 | 0.712 | 0.01943 | 0.2963 |
| opus | claude-opus-5-5 | high | 1 | 0.974 | 0.860 | 0.972 | 0.917 | 0.761 | 0.02334 | 0.3560 |
| opus | claude-opus-5-5 | xhigh | 1 | 0.974 | 0.833 | 0.972 | 0.917 | 0.731 | 0.03806 | 0.5804 |
| opus | claude-opus-5-5 | max | 1 | 1.000 | 0.859 | 0.972 | 1.000 | 0.754 | 0.09676 | 1.4756 |
| sol | gpt-6.1-sol | medium | 3 | 0.904 | 0.984 | 0.954 | 0.804 | 0.949 | 0.02418 | 0.0812 |
| sol | gpt-6.1-sol | high | 3 | 0.930 | 0.986 | 0.972 | 0.851 | 0.964 | 0.02965 | 0.0996 |
| sol | gpt-6.1-sol | xhigh | 3 | 0.947 | 1.000 | 0.991 | 0.884 | 1.000 | 0.03501 | 0.1176 |
| sol | gpt-6.1-sol | max | 3 | 0.947 | 1.000 | 0.991 | 0.884 | 1.000 | 0.03820 | 0.1284 |
| sonnet | claude-sonnet-5-5 | high | 2 | 0.947 | 0.975 | 0.986 | 0.861 | 0.939 | 0.00924 | 0.1409 |
| sonnet | claude-sonnet-5-5 | xhigh | 2 | 0.974 | 0.865 | 0.986 | 0.917 | 0.780 | 0.01555 | 0.2372 |
| sonnet | claude-sonnet-5-5 | max | 2 | 0.974 | 0.956 | 1.000 | 0.917 | 0.879 | 0.06001 | 0.9151 |

Cheapest by weekly window: **haiku|claude-haiku-5-5|low** (0.000568% per usable item).
Cheapest by API list USD: **haiku|claude-haiku-5-5|low** ($0.0087 per usable item).
Qualified standings based on one run: haiku|claude-haiku-5-5|high, haiku|claude-haiku-5-5|low, haiku|claude-haiku-5-5|max, haiku|claude-haiku-5-5|medium, haiku|claude-haiku-5-5|xhigh, opus|claude-fable-5-1|high, opus|claude-fable-5-1|low, opus|claude-fable-5-1|medium, opus|claude-fable-5-1|xhigh, opus|claude-opus-5-5|high, opus|claude-opus-5-5|low, opus|claude-opus-5-5|max, opus|claude-opus-5-5|medium, opus|claude-opus-5-5|xhigh.

## (b) (a) and precision_v2 ≥ 0.85

Clearing arms: 18.

| Lane | Model | Effort | Runs | Recall v2 | Precision v2 | Usable v2 | Recall CI low | Precision CI low | % week / usable | API $ / usable |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| astra | gpt-6-astra | low | 2 | 0.947 | 1.000 | 0.972 | 0.865 | 1.000 | 0.11044 | 0.3711 |
| astra | gpt-6-astra | medium | 2 | 0.921 | 1.000 | 0.972 | 0.833 | 1.000 | 0.11437 | 0.3843 |
| astra | gpt-6-astra | high | 2 | 0.934 | 1.000 | 0.972 | 0.865 | 1.000 | 0.14666 | 0.4928 |
| astra | gpt-6-astra | xhigh | 3 | 0.956 | 0.986 | 0.991 | 0.892 | 0.955 | 0.20075 | 0.6745 |
| astra | gpt-6-astra | max | 3 | 0.974 | 0.993 | 1.000 | 0.917 | 0.977 | 0.22274 | 0.7484 |
| haiku | claude-haiku-5-5 | low | 1 | 0.921 | 0.884 | 0.944 | 0.800 | 0.766 | 0.00057 | 0.0087 |
| opus | claude-fable-5-1 | low | 1 | 0.974 | 0.864 | 1.000 | 0.917 | 0.766 | 0.04718 | 0.7195 |
| opus | claude-fable-5-1 | xhigh | 1 | 0.974 | 0.885 | 1.000 | 0.917 | 0.788 | 0.11177 | 1.7045 |
| opus | claude-opus-5-5 | low | 1 | 0.974 | 0.886 | 1.000 | 0.917 | 0.786 | 0.01503 | 0.2292 |
| opus | claude-opus-5-5 | high | 1 | 0.974 | 0.860 | 0.972 | 0.917 | 0.761 | 0.02334 | 0.3560 |
| opus | claude-opus-5-5 | max | 1 | 1.000 | 0.859 | 0.972 | 1.000 | 0.754 | 0.09676 | 1.4756 |
| sol | gpt-6.1-sol | medium | 3 | 0.904 | 0.984 | 0.954 | 0.804 | 0.949 | 0.02418 | 0.0812 |
| sol | gpt-6.1-sol | high | 3 | 0.930 | 0.986 | 0.972 | 0.851 | 0.964 | 0.02965 | 0.0996 |
| sol | gpt-6.1-sol | xhigh | 3 | 0.947 | 1.000 | 0.991 | 0.884 | 1.000 | 0.03501 | 0.1176 |
| sol | gpt-6.1-sol | max | 3 | 0.947 | 1.000 | 0.991 | 0.884 | 1.000 | 0.03820 | 0.1284 |
| sonnet | claude-sonnet-5-5 | high | 2 | 0.947 | 0.975 | 0.986 | 0.861 | 0.939 | 0.00924 | 0.1409 |
| sonnet | claude-sonnet-5-5 | xhigh | 2 | 0.974 | 0.865 | 0.986 | 0.917 | 0.780 | 0.01555 | 0.2372 |
| sonnet | claude-sonnet-5-5 | max | 2 | 0.974 | 0.956 | 1.000 | 0.917 | 0.879 | 0.06001 | 0.9151 |

Cheapest by weekly window: **haiku|claude-haiku-5-5|low** (0.000568% per usable item).
Cheapest by API list USD: **haiku|claude-haiku-5-5|low** ($0.0087 per usable item).
Qualified standings based on one run: haiku|claude-haiku-5-5|low, opus|claude-fable-5-1|low, opus|claude-fable-5-1|xhigh, opus|claude-opus-5-5|high, opus|claude-opus-5-5|low, opus|claude-opus-5-5|max.

## (c) (b) and usable_v2 ≥ 0.90

Clearing arms: 18.

| Lane | Model | Effort | Runs | Recall v2 | Precision v2 | Usable v2 | Recall CI low | Precision CI low | % week / usable | API $ / usable |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| astra | gpt-6-astra | low | 2 | 0.947 | 1.000 | 0.972 | 0.865 | 1.000 | 0.11044 | 0.3711 |
| astra | gpt-6-astra | medium | 2 | 0.921 | 1.000 | 0.972 | 0.833 | 1.000 | 0.11437 | 0.3843 |
| astra | gpt-6-astra | high | 2 | 0.934 | 1.000 | 0.972 | 0.865 | 1.000 | 0.14666 | 0.4928 |
| astra | gpt-6-astra | xhigh | 3 | 0.956 | 0.986 | 0.991 | 0.892 | 0.955 | 0.20075 | 0.6745 |
| astra | gpt-6-astra | max | 3 | 0.974 | 0.993 | 1.000 | 0.917 | 0.977 | 0.22274 | 0.7484 |
| haiku | claude-haiku-5-5 | low | 1 | 0.921 | 0.884 | 0.944 | 0.800 | 0.766 | 0.00057 | 0.0087 |
| opus | claude-fable-5-1 | low | 1 | 0.974 | 0.864 | 1.000 | 0.917 | 0.766 | 0.04718 | 0.7195 |
| opus | claude-fable-5-1 | xhigh | 1 | 0.974 | 0.885 | 1.000 | 0.917 | 0.788 | 0.11177 | 1.7045 |
| opus | claude-opus-5-5 | low | 1 | 0.974 | 0.886 | 1.000 | 0.917 | 0.786 | 0.01503 | 0.2292 |
| opus | claude-opus-5-5 | high | 1 | 0.974 | 0.860 | 0.972 | 0.917 | 0.761 | 0.02334 | 0.3560 |
| opus | claude-opus-5-5 | max | 1 | 1.000 | 0.859 | 0.972 | 1.000 | 0.754 | 0.09676 | 1.4756 |
| sol | gpt-6.1-sol | medium | 3 | 0.904 | 0.984 | 0.954 | 0.804 | 0.949 | 0.02418 | 0.0812 |
| sol | gpt-6.1-sol | high | 3 | 0.930 | 0.986 | 0.972 | 0.851 | 0.964 | 0.02965 | 0.0996 |
| sol | gpt-6.1-sol | xhigh | 3 | 0.947 | 1.000 | 0.991 | 0.884 | 1.000 | 0.03501 | 0.1176 |
| sol | gpt-6.1-sol | max | 3 | 0.947 | 1.000 | 0.991 | 0.884 | 1.000 | 0.03820 | 0.1284 |
| sonnet | claude-sonnet-5-5 | high | 2 | 0.947 | 0.975 | 0.986 | 0.861 | 0.939 | 0.00924 | 0.1409 |
| sonnet | claude-sonnet-5-5 | xhigh | 2 | 0.974 | 0.865 | 0.986 | 0.917 | 0.780 | 0.01555 | 0.2372 |
| sonnet | claude-sonnet-5-5 | max | 2 | 0.974 | 0.956 | 1.000 | 0.917 | 0.879 | 0.06001 | 0.9151 |

Cheapest by weekly window: **haiku|claude-haiku-5-5|low** (0.000568% per usable item).
Cheapest by API list USD: **haiku|claude-haiku-5-5|low** ($0.0087 per usable item).
Qualified standings based on one run: haiku|claude-haiku-5-5|low, opus|claude-fable-5-1|low, opus|claude-fable-5-1|xhigh, opus|claude-opus-5-5|high, opus|claude-opus-5-5|low, opus|claude-opus-5-5|max.

## (d) 95% bootstrap lower bounds clear 0.90 recall and 0.85 precision, with usable_v2 ≥ 0.90

Clearing arms: 2.

| Lane | Model | Effort | Runs | Recall v2 | Precision v2 | Usable v2 | Recall CI low | Precision CI low | % week / usable | API $ / usable |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| astra | gpt-6-astra | max | 3 | 0.974 | 0.993 | 1.000 | 0.917 | 0.977 | 0.22274 | 0.7484 |
| sonnet | claude-sonnet-5-5 | max | 2 | 0.974 | 0.956 | 1.000 | 0.917 | 0.879 | 0.06001 | 0.9151 |

Cheapest by weekly window: **sonnet|claude-sonnet-5-5|max** (0.060009% per usable item).
Cheapest by API list USD: **astra|gpt-6-astra|max** ($0.7484 per usable item).
Qualified standings based on one run: none.

## One-run caveat

Every qualifying group with `Runs = 1` has a point estimate and bootstrap interval from a single execution. The `Runs` column identifies those candidates; the cheapest winners are listed above.
