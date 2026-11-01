# Suite suite_r against public numbers

Public numbers: findings/public.json. Correlations are Spearman rank over distinct pooled lane/model/effort points present in both; n/a below three points.

Skipped metrics (fewer than 3 arms in common): aa_fusion_cost_per_task_usd, aa_fusion_index, anthropic_reported_frontiercode_v11_main_pct, anthropic_reported_terminal_bench_4_pct, deepswe_datacurve_cost_per_task_usd, deepswe_datacurve_score_pct, endor_secpass_pct, frontiercode_v2_pct, hle_scale_score_pct, known_bugs_caught_pct_customer_quote, oss_aug80_precision_pct_cfg_max, oss_aug80_precision_pct_cfg_standard, oss_aug80_recall_pct_cfg_max, oss_aug80_recall_pct_cfg_standard, review_cost_per_task_usd, review_f1_like_score, reviewbench_grounded_f1, signal13_recall_pct_cfg_max, signal13_recall_pct_cfg_standard, swe_atlas_qna_score, swe_atlas_refactoring_score, vendor_cursorbench_4_pct, vendor_terminal_bench_4_pct

| Arm | Our recall | Wilson 95% | %week/item | Usable | Public entry | aa_cai_cost_per_task_usd | aa_cai_index | aa_cai_tb4_pct | aa_cai_tokens_per_task_m | aa_ii_cost_per_task_usd | aa_ii_score | aa_ii_v5_cost_per_task_usd | aa_ii_v5_score | aa_ii_v5_tb4_pct | aa_standalone_tb4_pct | deepswe_epoch_score_pct | frontiercode_cost_per_task_usd | frontiercode_score_pct | qodo_cost_per_task_usd | qodo_f1 | review review_precision_pct | review review_recall_pct | vendor vendor_frontiercode_v11_main_pct |
|---|---:|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| astra-high | 0.895 | [0.759, 0.958] | 0.14555 | 0.972 | astra high | n/a | n/a | n/a | n/a | 1.730 | 51.000 | n/a | n/a | n/a | n/a | 73.200 | n/a | n/a | 1.560 | 46.600 | n/a | n/a | n/a |
| astra-high-r2 | 0.921 | [0.792, 0.973] | 0.13962 | 0.972 | astra high | n/a | n/a | n/a | n/a | 1.730 | 51.000 | n/a | n/a | n/a | n/a | 73.200 | n/a | n/a | 1.560 | 46.600 | n/a | n/a | n/a |
| astra-low | 0.921 | [0.792, 0.973] | 0.10737 | 0.972 | astra low | n/a | n/a | n/a | n/a | 0.820 | 46.000 | n/a | n/a | n/a | n/a | 67.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| astra-low-r2 | 0.921 | [0.792, 0.973] | 0.10737 | 0.972 | astra low | n/a | n/a | n/a | n/a | 0.820 | 46.000 | n/a | n/a | n/a | n/a | 67.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| astra-max | 0.974 | [0.865, 0.995] | 0.20864 | 1.000 | astra max | 7.470 | 62.000 | 56.000 | 3.300 | 3.260 | 53.000 | n/a | n/a | n/a | 59.000 | 73.200 | 4.220 | 47.000 | n/a | n/a | 91.700 | 67.800 | n/a |
| astra-max-r2 | 0.974 | [0.865, 0.995] | 0.21056 | 1.000 | astra max | 7.470 | 62.000 | 56.000 | 3.300 | 3.260 | 53.000 | n/a | n/a | n/a | 59.000 | 73.200 | 4.220 | 47.000 | n/a | n/a | 91.700 | 67.800 | n/a |
| astra-max-r3 | 1.000 | [0.908, 1.000] | 0.24902 | 1.000 | astra max | 7.470 | 62.000 | 56.000 | 3.300 | 3.260 | 53.000 | n/a | n/a | n/a | 59.000 | 73.200 | 4.220 | 47.000 | n/a | n/a | 91.700 | 67.800 | n/a |
| astra-medium | 0.895 | [0.759, 0.958] | 0.10932 | 0.972 | astra medium | n/a | n/a | n/a | n/a | 1.540 | 50.000 | n/a | n/a | n/a | n/a | 72.800 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| astra-medium-r2 | 0.895 | [0.759, 0.958] | 0.11307 | 0.972 | astra medium | n/a | n/a | n/a | n/a | 1.540 | 50.000 | n/a | n/a | n/a | n/a | 72.800 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| astra-xhigh | 0.947 | [0.827, 0.985] | 0.18533 | 1.000 | astra xhigh | n/a | n/a | n/a | n/a | 2.310 | 52.000 | n/a | n/a | n/a | n/a | 74.100 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| astra-xhigh-r2 | 0.974 | [0.865, 0.995] | 0.18478 | 1.000 | astra xhigh | n/a | n/a | n/a | n/a | 2.310 | 52.000 | n/a | n/a | n/a | n/a | 74.100 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| astra-xhigh-r3 | 0.895 | [0.759, 0.958] | 0.22656 | 0.972 | astra xhigh | n/a | n/a | n/a | n/a | 2.310 | 52.000 | n/a | n/a | n/a | n/a | 74.100 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| haiku-high | 0.947 | [0.827, 0.985] | 0.00110 | 0.889 | haiku high | 0.360 | 35.000 | 13.000 | 5.100 | 0.080 | 38.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| haiku-low | 0.895 | [0.759, 0.958] | 0.00054 | 0.944 | haiku low | 0.140 | 28.000 | 6.000 | 2.400 | 0.020 | 29.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| haiku-max | 0.974 | [0.865, 0.995] | 0.01058 | 0.833 | haiku max | 2.580 | 36.000 | 30.000 | 13.800 | 0.210 | 43.000 | n/a | n/a | n/a | 33.000 | n/a | n/a | 46.400 | n/a | n/a | n/a | n/a | n/a |
| haiku-medium | 0.947 | [0.827, 0.985] | 0.00074 | 0.944 | haiku medium | 0.230 | 34.000 | 12.000 | 3.500 | 0.050 | 34.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| haiku-xhigh | 1.000 | [0.908, 1.000] | 0.00332 | 0.833 | haiku xhigh | 0.610 | 41.000 | 24.000 | 7.100 | 0.120 | 41.000 | n/a | n/a | n/a | n/a | n/a | n/a | 45.800 | n/a | n/a | n/a | n/a | n/a |
| luna-high | 0.605 | [0.447, 0.744] | 0.00181 | 0.722 | luna high | n/a | n/a | n/a | n/a | 0.030 | 33.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.020 | 42.200 | n/a | n/a | n/a |
| luna-high-r2 | 0.763 | [0.608, 0.870] | 0.00165 | 0.889 | luna high | n/a | n/a | n/a | n/a | 0.030 | 33.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.020 | 42.200 | n/a | n/a | n/a |
| luna-high-r3 | 0.711 | [0.552, 0.830] | 0.00160 | 0.889 | luna high | n/a | n/a | n/a | n/a | 0.030 | 33.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.020 | 42.200 | n/a | n/a | n/a |
| luna-high-r4 | 0.789 | [0.637, 0.889] | 0.00166 | 0.917 | luna high | n/a | n/a | n/a | n/a | 0.030 | 33.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.020 | 42.200 | n/a | n/a | n/a |
| luna-low | 0.447 | [0.301, 0.603] | 0.00152 | 0.639 | luna low | n/a | n/a | n/a | n/a | 0.004 | 22.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| luna-low-r2 | 0.342 | [0.212, 0.501] | 0.00156 | 0.444 | luna low | n/a | n/a | n/a | n/a | 0.004 | 22.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| luna-low-r3 | 0.500 | [0.348, 0.652] | 0.00145 | 0.583 | luna low | n/a | n/a | n/a | n/a | 0.004 | 22.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| luna-low-r4 | 0.263 | [0.150, 0.420] | 0.00151 | 0.389 | luna low | n/a | n/a | n/a | n/a | 0.004 | 22.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| luna-max | 0.789 | [0.637, 0.889] | 0.00260 | 0.861 | luna max | 0.180 | 41.000 | 15.000 | 10.200 | 0.070 | 38.000 | n/a | n/a | n/a | 13.000 | n/a | 0.090 | 42.000 | n/a | n/a | n/a | n/a | n/a |
| luna-max-r2 | 0.789 | [0.637, 0.889] | 0.00248 | 0.861 | luna max | 0.180 | 41.000 | 15.000 | 10.200 | 0.070 | 38.000 | n/a | n/a | n/a | 13.000 | n/a | 0.090 | 42.000 | n/a | n/a | n/a | n/a | n/a |
| luna-max-r3 | 0.816 | [0.666, 0.908] | 0.00235 | 0.861 | luna max | 0.180 | 41.000 | 15.000 | 10.200 | 0.070 | 38.000 | n/a | n/a | n/a | 13.000 | n/a | 0.090 | 42.000 | n/a | n/a | n/a | n/a | n/a |
| luna-max-r4 | 0.868 | [0.727, 0.942] | 0.00239 | 0.944 | luna max | 0.180 | 41.000 | 15.000 | 10.200 | 0.070 | 38.000 | n/a | n/a | n/a | 13.000 | n/a | 0.090 | 42.000 | n/a | n/a | n/a | n/a | n/a |
| luna-medium | 0.526 | [0.373, 0.675] | 0.00118 | 0.694 | luna medium | n/a | n/a | n/a | n/a | 0.020 | 30.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| luna-medium-r2 | 0.500 | [0.348, 0.652] | 0.00119 | 0.639 | luna medium | n/a | n/a | n/a | n/a | 0.020 | 30.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| luna-medium-r3 | 0.632 | [0.473, 0.766] | 0.00115 | 0.778 | luna medium | n/a | n/a | n/a | n/a | 0.020 | 30.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| luna-medium-r4 | 0.632 | [0.473, 0.766] | 0.00121 | 0.806 | luna medium | n/a | n/a | n/a | n/a | 0.020 | 30.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| luna-xhigh | 0.763 | [0.608, 0.870] | 0.00235 | 0.889 | luna xhigh | n/a | n/a | n/a | n/a | 0.040 | 35.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.020 | 41.700 | n/a | n/a | n/a |
| luna-xhigh-r2 | 0.842 | [0.696, 0.926] | 0.00228 | 0.889 | luna xhigh | n/a | n/a | n/a | n/a | 0.040 | 35.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.020 | 41.700 | n/a | n/a | n/a |
| luna-xhigh-r3 | 0.763 | [0.608, 0.870] | 0.00231 | 0.833 | luna xhigh | n/a | n/a | n/a | n/a | 0.040 | 35.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.020 | 41.700 | n/a | n/a | n/a |
| luna-xhigh-r4 | 0.763 | [0.608, 0.870] | 0.00223 | 0.861 | luna xhigh | n/a | n/a | n/a | n/a | 0.040 | 35.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.020 | 41.700 | n/a | n/a | n/a |
| opus-high | 0.947 | [0.827, 0.985] | 0.02270 | 0.944 | opus high | n/a | n/a | n/a | n/a | 1.820 | 54.000 | n/a | n/a | n/a | n/a | n/a | n/a | 54.000 | 1.000 | 56.800 | n/a | n/a | n/a |
| opus-high-claude-fable-5-1 | 0.921 | [0.792, 0.973] | 0.07152 | 0.944 | fable high | n/a | n/a | n/a | n/a | 3.910 | 51.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 2.310 | 53.500 | 36.400 | 57.100 | n/a |
| opus-low | 0.921 | [0.792, 0.973] | 0.01503 | 0.944 | opus low | n/a | n/a | n/a | n/a | 0.550 | 42.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| opus-low-claude-fable-5-1 | 0.947 | [0.827, 0.985] | 0.04718 | 1.000 | fable low | n/a | n/a | n/a | n/a | 2.370 | 47.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 53.400 | 37.300 | 61.000 | n/a |
| opus-max | 1.000 | [0.908, 1.000] | 0.09407 | 0.889 | opus max | 13.040 | 66.000 | 63.000 | 15.600 | 5.980 | 58.000 | n/a | n/a | n/a | 59.600 | n/a | 10.150 | 52.000 | n/a | n/a | n/a | n/a | n/a |
| opus-max-claude-fable-5-1 (partial) | 0.579 | [0.422, 0.721] | 0.16833 | 0.500 | - | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| opus-medium | 0.947 | [0.827, 0.985] | 0.01889 | 0.972 | opus medium | n/a | n/a | n/a | n/a | 1.340 | 51.000 | n/a | n/a | n/a | n/a | n/a | n/a | 57.100 | n/a | n/a | n/a | n/a | 54.600 |
| opus-medium-claude-fable-5-1 | 0.974 | [0.865, 0.995] | 0.05315 | 0.917 | fable medium | n/a | n/a | n/a | n/a | 2.980 | 49.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| opus-xhigh | 0.947 | [0.827, 0.985] | 0.03700 | 0.917 | opus xhigh | n/a | n/a | n/a | n/a | 3.460 | 56.000 | n/a | n/a | n/a | n/a | n/a | n/a | 53.500 | n/a | 54.000 | n/a | n/a | n/a |
| opus-xhigh-claude-fable-5-1 | 0.947 | [0.827, 0.985] | 0.11177 | 1.000 | fable xhigh | n/a | n/a | n/a | n/a | 5.980 | 53.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| sol-high | 0.921 | [0.792, 0.973] | 0.02995 | 0.972 | sol high | 0.890 | 60.000 | 50.000 | 2.800 | 0.320 | 50.000 | 0.590 | 50.000 | 52.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| sol-high-r2 | 0.895 | [0.759, 0.958] | 0.02751 | 0.972 | sol high | 0.890 | 60.000 | 50.000 | 2.800 | 0.320 | 50.000 | 0.590 | 50.000 | 52.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| sol-high-r3 | 0.895 | [0.759, 0.958] | 0.02904 | 0.972 | sol high | 0.890 | 60.000 | 50.000 | 2.800 | 0.320 | 50.000 | 0.590 | 50.000 | 52.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| sol-low | 0.816 | [0.666, 0.908] | 0.01906 | 0.917 | sol low | 0.500 | 57.000 | 49.000 | 1.700 | 0.130 | 42.000 | 0.160 | 35.000 | 31.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| sol-low-r2 | 0.868 | [0.727, 0.942] | 0.01803 | 0.944 | sol low | 0.500 | 57.000 | 49.000 | 1.700 | 0.130 | 42.000 | 0.160 | 35.000 | 31.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| sol-low-r3 | 0.842 | [0.696, 0.926] | 0.02055 | 0.944 | sol low | 0.500 | 57.000 | 49.000 | 1.700 | 0.130 | 42.000 | 0.160 | 35.000 | 31.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| sol-max | 0.947 | [0.827, 0.985] | 0.03683 | 0.972 | sol max | 1.550 | 60.000 | 53.000 | 4.000 | 0.720 | 52.000 | 1.270 | 55.000 | 56.000 | n/a | n/a | 0.810 | 49.000 | n/a | n/a | n/a | n/a | n/a |
| sol-max-r2 | 0.947 | [0.827, 0.985] | 0.03687 | 1.000 | sol max | 1.550 | 60.000 | 53.000 | 4.000 | 0.720 | 52.000 | 1.270 | 55.000 | 56.000 | n/a | n/a | 0.810 | 49.000 | n/a | n/a | n/a | n/a | n/a |
| sol-max-r3 | 0.947 | [0.827, 0.985] | 0.03985 | 1.000 | sol max | 1.550 | 60.000 | 53.000 | 4.000 | 0.720 | 52.000 | 1.270 | 55.000 | 56.000 | n/a | n/a | 0.810 | 49.000 | n/a | n/a | n/a | n/a | n/a |
| sol-medium | 0.895 | [0.759, 0.958] | 0.02392 | 0.972 | sol medium | 0.700 | 61.000 | 52.000 | 2.300 | 0.210 | 48.000 | 0.360 | 46.000 | 48.000 | n/a | n/a | n/a | n/a | 0.180 | 48.700 | n/a | n/a | n/a |
| sol-medium-r2 | 0.868 | [0.727, 0.942] | 0.02192 | 0.944 | sol medium | 0.700 | 61.000 | 52.000 | 2.300 | 0.210 | 48.000 | 0.360 | 46.000 | 48.000 | n/a | n/a | n/a | n/a | 0.180 | 48.700 | n/a | n/a | n/a |
| sol-medium-r3 | 0.868 | [0.727, 0.942] | 0.02335 | 0.944 | sol medium | 0.700 | 61.000 | 52.000 | 2.300 | 0.210 | 48.000 | 0.360 | 46.000 | 48.000 | n/a | n/a | n/a | n/a | 0.180 | 48.700 | n/a | n/a | n/a |
| sol-xhigh | 0.947 | [0.827, 0.985] | 0.03414 | 1.000 | sol xhigh | 1.040 | 63.000 | 55.000 | 3.200 | 0.390 | 51.000 | 0.760 | 52.000 | 54.000 | n/a | n/a | n/a | n/a | 0.510 | 48.400 | n/a | n/a | n/a |
| sol-xhigh-r2 | 0.921 | [0.792, 0.973] | 0.03494 | 1.000 | sol xhigh | 1.040 | 63.000 | 55.000 | 3.200 | 0.390 | 51.000 | 0.760 | 52.000 | 54.000 | n/a | n/a | n/a | n/a | 0.510 | 48.400 | n/a | n/a | n/a |
| sol-xhigh-r3 | 0.895 | [0.759, 0.958] | 0.03498 | 0.944 | sol xhigh | 1.040 | 63.000 | 55.000 | 3.200 | 0.390 | 51.000 | 0.760 | 52.000 | 54.000 | n/a | n/a | n/a | n/a | 0.510 | 48.400 | n/a | n/a | n/a |
| sonnet-high | 0.921 | [0.792, 0.973] | 0.00907 | 0.944 | sonnet high | 1.240 | 55.000 | 42.000 | 2.700 | 0.880 | 47.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.310 | 51.700 | n/a | n/a | n/a |
| sonnet-high-r2 | 0.868 | [0.727, 0.942] | 0.00915 | 0.944 | sonnet high | 1.240 | 55.000 | 42.000 | 2.700 | 0.880 | 47.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0.310 | 51.700 | n/a | n/a | n/a |
| sonnet-low | 0.842 | [0.696, 0.926] | 0.00743 | 0.917 | sonnet low | 0.480 | 42.000 | 25.000 | 0.977 | 0.350 | 36.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| sonnet-max | 0.974 | [0.865, 0.995] | 0.06187 | 1.000 | sonnet max | 14.190 | 68.000 | 66.000 | 27.700 | 5.460 | 56.000 | n/a | n/a | n/a | 63.600 | n/a | 8.260 | 46.200 | n/a | n/a | n/a | n/a | 46.200 |
| sonnet-max-r2 | 0.974 | [0.865, 0.995] | 0.05815 | 1.000 | sonnet max | 14.190 | 68.000 | 66.000 | 27.700 | 5.460 | 56.000 | n/a | n/a | n/a | 63.600 | n/a | 8.260 | 46.200 | n/a | n/a | n/a | n/a | 46.200 |
| sonnet-medium | 0.868 | [0.727, 0.942] | 0.00773 | 0.944 | sonnet medium | 0.620 | 46.000 | 27.000 | 1.300 | 0.480 | 41.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| sonnet-xhigh | 0.947 | [0.827, 0.985] | 0.01551 | 0.944 | sonnet xhigh | 3.330 | 63.000 | 58.000 | 7.100 | 2.010 | 52.000 | n/a | n/a | n/a | n/a | n/a | n/a | 52.100 | n/a | n/a | n/a | n/a | 52.100 |
| sonnet-xhigh-r2 | 0.921 | [0.792, 0.973] | 0.01516 | 0.944 | sonnet xhigh | 3.330 | 63.000 | 58.000 | 7.100 | 2.010 | 52.000 | n/a | n/a | n/a | n/a | n/a | n/a | 52.100 | n/a | n/a | n/a | n/a | 52.100 |
| terra-high | 0.921 | [0.792, 0.973] | 0.01088 | 0.944 | terra high | n/a | n/a | n/a | n/a | n/a | n/a | 0.260 | 42.000 | 42.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| terra-low | 0.921 | [0.792, 0.973] | 0.00829 | 0.917 | terra low | n/a | n/a | n/a | n/a | n/a | n/a | 0.070 | 29.000 | 15.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| terra-medium | 0.921 | [0.792, 0.973] | 0.00958 | 0.944 | terra medium | n/a | n/a | n/a | n/a | n/a | n/a | 0.170 | 38.000 | 32.000 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| terra-xhigh (partial) | 0.737 | [0.580, 0.850] | 0.01575 | 0.611 | - | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

Partial arms (excluded from curves, tests, Pareto, compare and priors): opus-max-claude-fable-5-1, terra-xhigh

## aa_cai_cost_per_task_usd

- Spearman, our recall against aa_cai_cost_per_task_usd: rho 0.571 (n=18)
- Spearman, our recall per %week against aa_cai_cost_per_task_usd per $: rho n/a (n=0)

Disagreements (public order opposite to ours, recall Wilson intervals disjoint):

- none

## aa_cai_index

- Spearman, our recall against aa_cai_index: rho 0.222 (n=18)
- Spearman, our recall per %week against aa_cai_index per $: rho 0.773 (n=18)

Disagreements (public order opposite to ours, recall Wilson intervals disjoint):

- haiku-xhigh vs sol-low, sol-low-r2, sol-low-r3: public 41.000 vs 57.000, recall 1.000 vs 0.842

## aa_cai_tb4_pct

- Spearman, our recall against aa_cai_tb4_pct: rho 0.341 (n=18)
- Spearman, our recall per %week against aa_cai_tb4_pct per $: rho 0.368 (n=18)

Disagreements (public order opposite to ours, recall Wilson intervals disjoint):

- haiku-xhigh vs sol-low, sol-low-r2, sol-low-r3: public 24.000 vs 49.000, recall 1.000 vs 0.842

## aa_cai_tokens_per_task_m

- Spearman, our recall against aa_cai_tokens_per_task_m: rho 0.684 (n=18)
- Spearman, our recall per %week against aa_cai_tokens_per_task_m per $: rho n/a (n=0)

Disagreements (public order opposite to ours, recall Wilson intervals disjoint):

- astra-max, astra-max-r2, astra-max-r3 vs luna-max, luna-max-r2, luna-max-r3, luna-max-r4: public 3.300 vs 10.200, recall 0.982 vs 0.816
- haiku-xhigh vs luna-max, luna-max-r2, luna-max-r3, luna-max-r4: public 7.100 vs 10.200, recall 1.000 vs 0.816
- luna-max, luna-max-r2, luna-max-r3, luna-max-r4 vs sol-max, sol-max-r2, sol-max-r3: public 10.200 vs 4.000, recall 0.816 vs 0.947

## aa_ii_cost_per_task_usd

- Spearman, our recall against aa_ii_cost_per_task_usd: rho 0.609 (n=34)
- Spearman, our recall per %week against aa_ii_cost_per_task_usd per $: rho n/a (n=0)

Disagreements (public order opposite to ours, recall Wilson intervals disjoint):

- haiku-xhigh vs sol-low, sol-low-r2, sol-low-r3: public 0.120 vs 0.130, recall 1.000 vs 0.842

## aa_ii_score

- Spearman, our recall against aa_ii_score: rho 0.618 (n=34)
- Spearman, our recall per %week against aa_ii_score per $: rho 0.829 (n=34)

Disagreements (public order opposite to ours, recall Wilson intervals disjoint):

- haiku-low vs luna-medium, luna-medium-r2, luna-medium-r3, luna-medium-r4: public 29.000 vs 30.000, recall 0.895 vs 0.572
- haiku-xhigh vs sol-low, sol-low-r2, sol-low-r3: public 41.000 vs 42.000, recall 1.000 vs 0.842

## aa_ii_v5_cost_per_task_usd

- Spearman, our recall against aa_ii_v5_cost_per_task_usd: rho 0.368 (n=8)
- Spearman, our recall per %week against aa_ii_v5_cost_per_task_usd per $: rho n/a (n=0)

Disagreements (public order opposite to ours, recall Wilson intervals disjoint):

- none

## aa_ii_v5_score

- Spearman, our recall against aa_ii_v5_score: rho 0.368 (n=8)
- Spearman, our recall per %week against aa_ii_v5_score per $: rho 1.000 (n=5)

Disagreements (public order opposite to ours, recall Wilson intervals disjoint):

- none

## aa_ii_v5_tb4_pct

- Spearman, our recall against aa_ii_v5_tb4_pct: rho 0.368 (n=8)
- Spearman, our recall per %week against aa_ii_v5_tb4_pct per $: rho 1.000 (n=5)

Disagreements (public order opposite to ours, recall Wilson intervals disjoint):

- none

## aa_standalone_tb4_pct

- Spearman, our recall against aa_standalone_tb4_pct: rho 0.564 (n=5)
- Spearman, our recall per %week against aa_standalone_tb4_pct per $: rho n/a (n=0)

Disagreements (public order opposite to ours, recall Wilson intervals disjoint):

- none

## deepswe_epoch_score_pct

- Spearman, our recall against deepswe_epoch_score_pct: rho 0.462 (n=5)
- Spearman, our recall per %week against deepswe_epoch_score_pct per $: rho n/a (n=0)

Disagreements (public order opposite to ours, recall Wilson intervals disjoint):

- none

## frontiercode_cost_per_task_usd

- Spearman, our recall against frontiercode_cost_per_task_usd: rho 0.900 (n=5)
- Spearman, our recall per %week against frontiercode_cost_per_task_usd per $: rho n/a (n=0)

Disagreements (public order opposite to ours, recall Wilson intervals disjoint):

- none

## frontiercode_score_pct

- Spearman, our recall against frontiercode_score_pct: rho -0.234 (n=11)
- Spearman, our recall per %week against frontiercode_score_pct per $: rho n/a (n=0)

Disagreements (public order opposite to ours, recall Wilson intervals disjoint):

- none

## qodo_cost_per_task_usd

- Spearman, our recall against qodo_cost_per_task_usd: rho 0.843 (n=8)
- Spearman, our recall per %week against qodo_cost_per_task_usd per $: rho n/a (n=0)

Disagreements (public order opposite to ours, recall Wilson intervals disjoint):

- none

## qodo_f1

- Spearman, our recall against qodo_f1: rho 0.831 (n=10)
- Spearman, our recall per %week against qodo_f1 per $: rho n/a (n=0)

Disagreements (public order opposite to ours, recall Wilson intervals disjoint):

- none

## review_precision_pct

- Spearman, our recall against review_precision_pct: rho 1.000 (n=3)
- Spearman, our recall per %week against review_precision_pct per $: rho n/a (n=0)

Disagreements (public order opposite to ours, recall Wilson intervals disjoint):

- none

## review_recall_pct

- Spearman, our recall against review_recall_pct: rho 1.000 (n=3)
- Spearman, our recall per %week against review_recall_pct per $: rho n/a (n=0)

Disagreements (public order opposite to ours, recall Wilson intervals disjoint):

- none

## vendor_frontiercode_v11_main_pct

- Spearman, our recall against vendor_frontiercode_v11_main_pct: rho -0.500 (n=3)
- Spearman, our recall per %week against vendor_frontiercode_v11_main_pct per $: rho n/a (n=0)

Disagreements (public order opposite to ours, recall Wilson intervals disjoint):

- none

Public entries with no matching arm: fable max, fable max, fable unspecified, haiku unspecified, luna unspecified, opus unspecified, sonnet unspecified, gemini high, gemini n/a, astra n/a, hybrid max + high, hybrid xhigh + medium, hybrid xhigh + medium, gemini medium, sonnet default, sonnet include-nits, opus n/s, fable max, terra xhigh, terra max

## Cost agreement

The per-$ correlations above share a price term on both sides, so they partly restate price; this section tests price alone.

| Public cost metric | Spearman our $/item vs public $/task | Median public $/task ÷ our $/item |
|---|---:|---:|
| aa_cai_cost_per_task_usd | 0.957 (n=18) | 11.017 |
| aa_ii_cost_per_task_usd | 0.976 (n=34) | 3.873 |
| aa_ii_v5_cost_per_task_usd | 0.929 (n=8) | 5.687 |
| frontiercode_cost_per_task_usd | 1.000 (n=5) | 7.075 |
| qodo_cost_per_task_usd | 0.970 (n=8) | 2.744 |
