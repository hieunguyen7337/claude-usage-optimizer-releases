# Suite suite_r by arm

Suite suite_r (class review): 36 items, 38 defects.

Capability is this suite's review recall and precision; usage is what one item cost in the provider's weekly window. Public columns are Artificial Analysis numbers from `public.json`.

## Capability

| Lane | Model | Effort | Catalog | Runs | Recall [Wilson 95%] | Range over runs | Stable share | Precision | FA/planted | FA/control | Usable | Format fail | AA intelligence | AA coding-agent | TB4 hard |
|---|---|---|---|---|---|---|---|---:|---:|---:|---:|---|---:|---:|---:|
| opus | claude-fable-5-1 | low | absent | 1 | 0.95 [0.83, 0.99] | n/a | n/a | 0.82 | 0.20 | 0.33 | 1.00 | 0 (0.00) | 47 | n/a | n/a |
| opus | claude-fable-5-1 | medium | absent | 1 | 0.97 [0.87, 1.00] | n/a | n/a | 0.69 | 0.40 | 0.83 | 0.92 | 0 (0.00) | 49 | n/a | n/a |
| opus | claude-fable-5-1 | high | absent | 1 | 0.92 [0.79, 0.97] | n/a | n/a | 0.69 | 0.43 | 0.50 | 0.94 | 0 (0.00) | 51 | n/a | n/a |
| opus | claude-fable-5-1 | xhigh | absent | 1 | 0.95 [0.83, 0.99] | n/a | n/a | 0.69 | 0.50 | 0.17 | 1.00 | 0 (0.00) | 53 | n/a | n/a |
| opus | claude-fable-5-1 | max | absent | partial (18 of 36 items) | 0.58 [0.42, 0.72] | n/a | n/a | 0.69 | 0.56 | n/a | 0.50 | 0 (0.00) | 53 | 62 | 58 |
| haiku | claude-haiku-5-5 | low | active | 1 | 0.89 [0.76, 0.96] | n/a | n/a | 0.79 | 0.23 | 0.33 | 0.94 | 0 (0.00) | 29 | 28 | 6 |
| haiku | claude-haiku-5-5 | medium | active | 1 | 0.95 [0.83, 0.99] | n/a | n/a | 0.72 | 0.41 | 0.33 | 0.94 | 1 (0.03) | 34 | 34 | 12 |
| haiku | claude-haiku-5-5 | high | active | 1 | 0.95 [0.83, 0.99] | n/a | n/a | 0.55 | 0.93 | 0.33 | 0.89 | 0 (0.00) | 38 | 35 | 13 |
| haiku | claude-haiku-5-5 | xhigh | active | 1 | 1.00 [0.91, 1.00] | n/a | n/a | 0.51 | 1.03 | 0.83 | 0.83 | 0 (0.00) | 41 | 41 | 24 |
| haiku | claude-haiku-5-5 | max | retired | 1 | 0.97 [0.87, 1.00] | n/a | n/a | 0.47 | 1.20 | 0.83 | 0.83 | 0 (0.00) | 43 | 36 | 30 |
| opus | claude-opus-5-5 | low | absent | 1 | 0.92 [0.79, 0.97] | n/a | n/a | 0.80 | 0.27 | 0.17 | 0.94 | 0 (0.00) | 42 | n/a | n/a |
| opus | claude-opus-5-5 | medium | active | 1 | 0.95 [0.83, 0.99] | n/a | n/a | 0.69 | 0.43 | 0.50 | 0.97 | 0 (0.00) | 51 | n/a | n/a |
| opus | claude-opus-5-5 | high | active | 1 | 0.95 [0.83, 0.99] | n/a | n/a | 0.63 | 0.57 | 0.67 | 0.94 | 0 (0.00) | 54 | n/a | n/a |
| opus | claude-opus-5-5 | xhigh | active | 1 | 0.95 [0.83, 0.99] | n/a | n/a | 0.60 | 0.67 | 0.67 | 0.92 | 0 (0.00) | 56 | n/a | n/a |
| opus | claude-opus-5-5 | max | active | 1 | 1.00 [0.91, 1.00] | n/a | n/a | 0.59 | 0.80 | 0.33 | 0.89 | 0 (0.00) | 58 | 66 | 63 |
| sonnet | claude-sonnet-5-5 | low | absent | 1 | 0.84 [0.70, 0.93] | n/a | n/a | 0.97 | 0.03 | 0.00 | 0.92 | 0 (0.00) | 36 | 42 | 25 |
| sonnet | claude-sonnet-5-5 | medium | active | 1 | 0.87 [0.73, 0.94] | n/a | n/a | 0.92 | 0.10 | 0.00 | 0.94 | 0 (0.00) | 41 | 46 | 27 |
| sonnet | claude-sonnet-5-5 | high | active | 2 | 0.89 [0.81, 0.95] | 0.87-0.92 | 0.94 | 0.86 | 0.18 | 0.00 | 0.94 | 0 (0.00) | 47 | 55 | 42 |
| sonnet | claude-sonnet-5-5 | xhigh | active | 2 | 0.93 [0.86, 0.97] | 0.92-0.95 | 0.97 | 0.68 | 0.50 | 0.25 | 0.94 | 0 (0.00) | 52 | 63 | 58 |
| sonnet | claude-sonnet-5-5 | max | active | 2 | 0.97 [0.91, 0.99] | 0.97-0.97 | 1.00 | 0.82 | 0.27 | 0.00 | 1.00 | 0 (0.00) | 56 | 68 | 66 |
| luna | gpt-5.6-luna | * | manual | not run | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| astra | gpt-6-astra | low | absent | 2 | 0.92 [0.84, 0.96] | 0.92-0.92 | 1.00 | 0.76 | 0.37 | 0.00 | 0.97 | 0 (0.00) | 46 | n/a | n/a |
| astra | gpt-6-astra | medium | absent | 2 | 0.89 [0.81, 0.95] | 0.89-0.89 | 1.00 | 0.79 | 0.30 | 0.00 | 0.97 | 0 (0.00) | 50 | n/a | n/a |
| astra | gpt-6-astra | high | absent | 2 | 0.91 [0.82, 0.95] | 0.89-0.92 | 0.92 | 0.76 | 0.37 | 0.00 | 0.97 | 0 (0.00) | 51 | n/a | n/a |
| astra | gpt-6-astra | xhigh | active | 3 | 0.94 [0.88, 0.97] | 0.89-0.97 | 0.92 | 0.74 | 0.43 | 0.00 | 0.99 | 0 (0.00) | 52 | n/a | n/a |
| astra | gpt-6-astra | max | active | 3 | 0.98 [0.94, 1.00] | 0.97-1.00 | 0.97 | 0.77 | 0.38 | 0.00 | 1.00 | 0 (0.00) | 53 | 62 | 56 |
| luna | gpt-6-luna | low | active | 4 | 0.39 [0.31, 0.47] | 0.26-0.50 | 0.15 | 0.75 | 0.20 | 0.00 | 0.51 | 6 (0.04) | 22 | n/a | n/a |
| luna | gpt-6-luna | medium | active | 4 | 0.57 [0.49, 0.65] | 0.50-0.63 | 0.35 | 0.76 | 0.25 | 0.04 | 0.73 | 13 (0.09) | 30 | n/a | n/a |
| luna | gpt-6-luna | high | active | 4 | 0.72 [0.64, 0.78] | 0.61-0.79 | 0.59 | 0.77 | 0.28 | 0.00 | 0.85 | 7 (0.05) | 33 | n/a | n/a |
| luna | gpt-6-luna | xhigh | active | 4 | 0.78 [0.71, 0.84] | 0.76-0.84 | 0.58 | 0.72 | 0.41 | 0.08 | 0.87 | 13 (0.09) | 35 | n/a | n/a |
| luna | gpt-6-luna | max | active | 4 | 0.82 [0.75, 0.87] | 0.79-0.87 | 0.59 | 0.69 | 0.47 | 0.17 | 0.88 | 8 (0.06) | 38 | 41 | 15 |
| sol | gpt-6.1-sol | low | active | 3 | 0.84 [0.76, 0.90] | 0.82-0.87 | 0.91 | 0.77 | 0.32 | 0.00 | 0.94 | 0 (0.00) | 42 | 57 | 49 |
| sol | gpt-6.1-sol | medium | active | 3 | 0.88 [0.80, 0.93] | 0.87-0.89 | 0.94 | 0.78 | 0.32 | 0.00 | 0.95 | 0 (0.00) | 48 | 61 | 52 |
| sol | gpt-6.1-sol | high | active | 3 | 0.90 [0.84, 0.95] | 0.89-0.92 | 0.94 | 0.73 | 0.43 | 0.00 | 0.97 | 0 (0.00) | 50 | 60 | 50 |
| sol | gpt-6.1-sol | xhigh | active | 3 | 0.92 [0.86, 0.96] | 0.89-0.95 | 0.92 | 0.74 | 0.42 | 0.00 | 0.98 | 0 (0.00) | 51 | 63 | 55 |
| sol | gpt-6.1-sol | max | retired | 3 | 0.95 [0.89, 0.98] | 0.95-0.95 | 0.95 | 0.76 | 0.38 | 0.00 | 0.99 | 0 (0.00) | 52 | 60 | 53 |
| terra | gpt-6.1-terra | low | active | 1 | 0.92 [0.79, 0.97] | n/a | n/a | 0.73 | 0.43 | 0.00 | 0.92 | 0 (0.00) | n/a | n/a | n/a |
| terra | gpt-6.1-terra | medium | active | 1 | 0.92 [0.79, 0.97] | n/a | n/a | 0.67 | 0.57 | 0.00 | 0.94 | 0 (0.00) | n/a | n/a | n/a |
| terra | gpt-6.1-terra | high | active | 1 | 0.92 [0.79, 0.97] | n/a | n/a | 0.64 | 0.63 | 0.17 | 0.94 | 0 (0.00) | n/a | n/a | n/a |
| terra | gpt-6.1-terra | xhigh | retired | partial (23 of 36 items) | 0.74 [0.58, 0.85] | n/a | n/a | 0.57 | 0.95 | n/a | 0.61 | 0 (0.00) | n/a | n/a | n/a |
| terra | gpt-6.1-terra | max | retired | not run | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| gemini | gemini-3.8-flash-low | low | active | not run | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| gemini | gemini-3.8-flash-medium | medium | active | not run | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| gemini | gemini-3.8-flash-high | high | active | not run | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| glm | z-ai/glm-5.3-flash | * | manual | not run | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

## Usage

| Lane | Model | Effort | Tokens/item | Cost/item | API $/item | %week/item | %5h/item | Items per week | Wall median s | AA $/task (intelligence) | AA $/task (coding-agent) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| opus | claude-fable-5-1 | low | 206711 | 0.720 list $ | $0.720 | 0.0472 | 0.584 | 2119 | 35.3 | $2.37 | n/a |
| opus | claude-fable-5-1 | medium | 242383 | 0.811 list $ | $0.811 | 0.0531 | 0.657 | 1881 | 48.7 | $2.98 | n/a |
| opus | claude-fable-5-1 | high | 291172 | 1.09 list $ | $1.09 | 0.0715 | 0.885 | 1398 | 64.6 | $3.91 | n/a |
| opus | claude-fable-5-1 | xhigh | 335071 | 1.70 list $ | $1.70 | 0.112 | 1.38 | 895 | 151.0 | $5.98 | n/a |
| opus | claude-fable-5-1 | max | 473642 | 2.57 list $ | $2.57 | 0.168 | 2.08 | 594 | 246.2 | $7.63 | $12.4 |
| haiku | claude-haiku-5-5 | low | 160154 | 0.00819 list $ | $0.00819 | 0.000537 | 0.00554 | 186280 | 24.0 | $0.0200 | $0.140 |
| haiku | claude-haiku-5-5 | medium | 205780 | 0.0112 list $ | $0.0112 | 0.000737 | 0.00761 | 135634 | 34.6 | $0.0500 | $0.230 |
| haiku | claude-haiku-5-5 | high | 279037 | 0.0168 list $ | $0.0168 | 0.00110 | 0.0113 | 91008 | 66.3 | $0.0800 | $0.360 |
| haiku | claude-haiku-5-5 | xhigh | 512824 | 0.0506 list $ | $0.0506 | 0.00332 | 0.0343 | 30130 | 140.3 | $0.120 | $0.610 |
| haiku | claude-haiku-5-5 | max | 852734 | 0.161 list $ | $0.161 | 0.0106 | 0.109 | 9454 | 337.0 | $0.210 | $2.58 |
| opus | claude-opus-5-5 | low | 125812 | 0.229 list $ | $0.229 | 0.0150 | 0.0857 | 6653 | 19.8 | $0.550 | n/a |
| opus | claude-opus-5-5 | medium | 178979 | 0.288 list $ | $0.288 | 0.0189 | 0.108 | 5293 | 30.7 | $1.34 | n/a |
| opus | claude-opus-5-5 | high | 238164 | 0.346 list $ | $0.346 | 0.0227 | 0.129 | 4406 | 39.5 | $1.82 | n/a |
| opus | claude-opus-5-5 | xhigh | 370259 | 0.564 list $ | $0.564 | 0.0370 | 0.211 | 2703 | 72.3 | $3.46 | n/a |
| opus | claude-opus-5-5 | max | 724639 | 1.43 list $ | $1.43 | 0.0941 | 0.537 | 1063 | 313.0 | $5.98 | $13.0 |
| sonnet | claude-sonnet-5-5 | low | 130109 | 0.113 list $ | $0.113 | 0.00743 | 0.0446 | 13450 | 21.8 | $0.350 | $0.480 |
| sonnet | claude-sonnet-5-5 | medium | 133600 | 0.118 list $ | $0.118 | 0.00773 | 0.0464 | 12929 | 22.6 | $0.480 | $0.620 |
| sonnet | claude-sonnet-5-5 | high | 163250 | 0.139 list $ | $0.139 | 0.00911 | 0.0547 | 10978 | 23.7 | $0.880 | $1.24 |
| sonnet | claude-sonnet-5-5 | xhigh | 296275 | 0.234 list $ | $0.234 | 0.0153 | 0.0921 | 6520 | 50.6 | $2.01 | $3.33 |
| sonnet | claude-sonnet-5-5 | max | 902437 | 0.915 list $ | $0.915 | 0.0600 | 0.360 | 1666 | 308.1 | $5.46 | $14.2 |
| luna | gpt-5.6-luna | * | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| astra | gpt-6-astra | low | 22247 | 9.02 credits | $0.361 | 0.107 | n/a | 931 | 31.4 | $0.820 | n/a |
| astra | gpt-6-astra | medium | 23212 | 9.34 credits | $0.374 | 0.111 | n/a | 899 | 30.3 | $1.54 | n/a |
| astra | gpt-6-astra | high | 30178 | 12.0 credits | $0.479 | 0.143 | n/a | 701 | 37.4 | $1.73 | n/a |
| astra | gpt-6-astra | xhigh | 38281 | 16.7 credits | $0.668 | 0.199 | n/a | 503 | 65.7 | $2.31 | n/a |
| astra | gpt-6-astra | max | 41644 | 18.7 credits | $0.748 | 0.223 | n/a | 449 | 81.7 | $3.26 | $7.47 |
| luna | gpt-6-luna | low | 30196 | 0.127 credits | $0.00508 | 0.00151 | n/a | 66160 | 28.0 | $0.00450 | n/a |
| luna | gpt-6-luna | medium | 24236 | 0.0994 credits | $0.00398 | 0.00118 | n/a | 84465 | 28.2 | $0.0200 | n/a |
| luna | gpt-6-luna | high | 32640 | 0.141 credits | $0.00564 | 0.00168 | n/a | 59523 | 40.3 | $0.0300 | n/a |
| luna | gpt-6-luna | xhigh | 39206 | 0.192 credits | $0.00770 | 0.00229 | n/a | 43654 | 57.1 | $0.0400 | n/a |
| luna | gpt-6-luna | max | 42646 | 0.206 credits | $0.00826 | 0.00246 | n/a | 40695 | 62.6 | $0.0700 | $0.180 |
| sol | gpt-6.1-sol | low | 23194 | 1.61 credits | $0.0645 | 0.0192 | n/a | 5205 | 29.6 | $0.130 | $0.500 |
| sol | gpt-6.1-sol | medium | 29393 | 1.94 credits | $0.0775 | 0.0231 | n/a | 4336 | 33.0 | $0.210 | $0.700 |
| sol | gpt-6.1-sol | high | 35493 | 2.42 credits | $0.0969 | 0.0288 | n/a | 3468 | 43.6 | $0.320 | $0.890 |
| sol | gpt-6.1-sol | xhigh | 41618 | 2.91 credits | $0.117 | 0.0347 | n/a | 2883 | 60.6 | $0.390 | $1.04 |
| sol | gpt-6.1-sol | max | 43058 | 3.18 credits | $0.127 | 0.0378 | n/a | 2642 | 74.1 | $0.720 | $1.55 |
| terra | gpt-6.1-terra | low | 160800 | 0.696 credits | $0.0278 | 0.00829 | n/a | 12065 | 67.5 | n/a | n/a |
| terra | gpt-6.1-terra | medium | 172210 | 0.804 credits | $0.0322 | 0.00958 | n/a | 10442 | 65.0 | n/a | n/a |
| terra | gpt-6.1-terra | high | 214128 | 0.914 credits | $0.0366 | 0.0109 | n/a | 9188 | 71.1 | n/a | n/a |
| terra | gpt-6.1-terra | xhigh | 303479 | 1.32 credits | $0.0529 | 0.0158 | n/a | 6348 | 104.2 | n/a | n/a |
| terra | gpt-6.1-terra | max | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| gemini | gemini-3.8-flash-low | low | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| gemini | gemini-3.8-flash-medium | medium | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| gemini | gemini-3.8-flash-high | high | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| glm | z-ai/glm-5.3-flash | * | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
