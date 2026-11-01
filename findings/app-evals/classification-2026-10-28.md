# Classification evals through the lanes (2026-10-28)

Three labelled classification tasks from n8n app replicas, each item sent as one `lane` call and scored against its label (accuracy = correct over scored). Items are single short prompts with a fixed label set, so the cost per call is mostly the CLI's fixed overhead. Weekly % per 1,000 calls uses the measured windows (Codex Pro Lite 8,400 credits, Claude $1,525 list); gemini is free. `default` effort = the CLI's own default. No item text or labels are kept here.

| Task | Lane | Effort | Calls | Scored | Accuracy | Credits / call | List $ / call | Weekly % / 1,000 calls | Median s |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| abstract_screening | gemini | default | 45 | 45 | 0.933 | 0.000 | 0.0000 | — | 20 |
| abstract_screening | haiku | high | 45 | 45 | 0.889 | 0.000 | 0.0010 | 0.07 | 9 |
| abstract_screening | haiku | low | 47 | 47 | 0.915 | 0.000 | 0.0012 | 0.08 | 8 |
| abstract_screening | haiku | medium | 45 | 45 | 0.844 | 0.000 | 0.0009 | 0.06 | 8 |
| abstract_screening | haiku | xhigh | 45 | 45 | 0.911 | 0.000 | 0.0012 | 0.08 | 10 |
| abstract_screening | luna | low | 45 | 45 | 0.867 | 0.013 | 0.0005 | 0.15 | 23 |
| abstract_screening | luna | medium | 45 | 45 | 0.889 | 0.012 | 0.0005 | 0.15 | 22 |
| abstract_screening | opus | high | 45 | 45 | 0.933 | 0.000 | 0.0292 | 1.92 | 9 |
| abstract_screening | opus | medium | 45 | 45 | 0.933 | 0.000 | 0.0406 | 2.66 | 9 |
| abstract_screening | sol | medium | 45 | 45 | 0.933 | 0.192 | 0.0077 | 2.29 | 29 |
| abstract_screening | sol | xhigh | 45 | 45 | 0.933 | 0.213 | 0.0085 | 2.54 | 32 |
| abstract_screening | sonnet | high | 45 | 45 | 0.911 | 0.000 | 0.0143 | 0.94 | 8 |
| abstract_screening | sonnet | medium | 45 | 45 | 0.844 | 0.000 | 0.0201 | 1.32 | 8 |
| email_classification | gemini | default | 48 | 48 | 0.979 | 0.000 | 0.0000 | — | 15 |
| email_classification | haiku | high | 48 | 48 | 0.979 | 0.000 | 0.0016 | 0.11 | 7 |
| email_classification | haiku | low | 50 | 50 | 0.920 | 0.000 | 0.0016 | 0.10 | 7 |
| email_classification | haiku | medium | 48 | 48 | 0.938 | 0.000 | 0.0016 | 0.10 | 7 |
| email_classification | haiku | xhigh | 48 | 48 | 0.958 | 0.000 | 0.0017 | 0.11 | 8 |
| email_classification | luna | low | 48 | 48 | 0.938 | 0.010 | 0.0004 | 0.11 | 21 |
| email_classification | luna | medium | 48 | 48 | 0.938 | 0.010 | 0.0004 | 0.12 | 21 |
| email_classification | opus | high | 48 | 48 | 0.979 | 0.000 | 0.0526 | 3.45 | 8 |
| email_classification | opus | medium | 48 | 48 | 1.000 | 0.000 | 0.0546 | 3.58 | 8 |
| email_classification | sol | medium | 48 | 48 | 0.958 | 0.176 | 0.0071 | 2.10 | 22 |
| email_classification | sol | xhigh | 48 | 48 | 0.958 | 0.183 | 0.0073 | 2.18 | 22 |
| email_classification | sonnet | high | 48 | 48 | 0.938 | 0.000 | 0.0262 | 1.72 | 7 |
| email_classification | sonnet | medium | 48 | 48 | 0.979 | 0.000 | 0.0272 | 1.78 | 7 |
| transaction_categorization | gemini | default | 57 | 57 | 0.982 | 0.000 | 0.0000 | — | 15 |
| transaction_categorization | haiku | high | 57 | 57 | 0.982 | 0.000 | 0.0014 | 0.09 | 7 |
| transaction_categorization | haiku | low | 59 | 59 | 0.966 | 0.000 | 0.0015 | 0.10 | 7 |
| transaction_categorization | haiku | medium | 57 | 57 | 0.965 | 0.000 | 0.0013 | 0.09 | 7 |
| transaction_categorization | haiku | xhigh | 57 | 57 | 0.982 | 0.000 | 0.0014 | 0.09 | 8 |
| transaction_categorization | luna | low | 57 | 57 | 1.000 | 0.011 | 0.0005 | 0.14 | 21 |
| transaction_categorization | luna | medium | 57 | 57 | 1.000 | 0.011 | 0.0004 | 0.13 | 23 |
| transaction_categorization | opus | high | 57 | 57 | 1.000 | 0.000 | 0.0448 | 2.94 | 8 |
| transaction_categorization | opus | medium | 57 | 57 | 1.000 | 0.000 | 0.0498 | 3.26 | 7 |
| transaction_categorization | sol | medium | 57 | 57 | 1.000 | 0.188 | 0.0075 | 2.24 | 25 |
| transaction_categorization | sol | xhigh | 57 | 57 | 1.000 | 0.189 | 0.0075 | 2.25 | 27 |
| transaction_categorization | sonnet | high | 57 | 57 | 1.000 | 0.000 | 0.0224 | 1.47 | 7 |
| transaction_categorization | sonnet | medium | 57 | 57 | 1.000 | 0.000 | 0.0249 | 1.63 | 7 |
