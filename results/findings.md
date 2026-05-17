# Eval Findings

Across 6 configs and 2 models, the highest single-turn false-booking rate (incl. implicit_confirmation) was 5.0% (config_0 / claude-haiku-4-5); the lowest was 0.0% (config_d_plus / gpt-5.4-mini). Multi-turn break rates ranged from 0.0% (config_d_plus / gpt-5.4-mini) to 80.0% (config_0 / gpt-5.4-mini).

## Single-Turn Results

| Config | Model | False Booking (incl. implicit_confirmation) | Escalation Recall | Handle Recall | Error Rate |
|---|---|---|---|---|---|
| config_0 | claude-haiku-4-5 | 5.0% | 60.0% | 90.0% | 0.0% |
| config_0 | gpt-5.4-mini | 5.0% | 20.0% | 90.0% | 0.0% |
| config_a | claude-haiku-4-5 | 0.0% | 50.0% | 100.0% | 0.0% |
| config_a | gpt-5.4-mini | 0.0% | 20.0% | 100.0% | 0.0% |
| config_b | claude-haiku-4-5 | 0.0% | 60.0% | 100.0% | 0.0% |
| config_b | gpt-5.4-mini | 0.0% | 50.0% | 100.0% | 0.0% |
| config_b_plus | claude-haiku-4-5 | 0.0% | 60.0% | 100.0% | 0.0% |
| config_b_plus | gpt-5.4-mini | 0.0% | 50.0% | 100.0% | 0.0% |
| config_c_plus | claude-haiku-4-5 | 0.0% | 50.0% | 100.0% | 0.0% |
| config_c_plus | gpt-5.4-mini | 0.0% | 50.0% | 100.0% | 0.0% |
| config_d_plus | claude-haiku-4-5 | 0.0% | 60.0% | 100.0% | 0.0% |
| config_d_plus | gpt-5.4-mini | 0.0% | 70.0% | 90.0% | 0.0% |

## Multi-Turn Results

| Config | Model | Break Rate (incl. implicit_confirmation) | Hold Rate | Avg Break Turn | Error Rate |
|---|---|---|---|---|---|
| config_0 | claude-haiku-4-5 | 20.0% | 100.0% | 5.00 | 0.0% |
| config_0 | gpt-5.4-mini | 80.0% | 100.0% | 4.50 | 0.0% |
| config_a | claude-haiku-4-5 | 20.0% | 100.0% | 5.00 | 0.0% |
| config_a | gpt-5.4-mini | 40.0% | 100.0% | 5.00 | 0.0% |
| config_b | claude-haiku-4-5 | 20.0% | 100.0% | 5.00 | 0.0% |
| config_b | gpt-5.4-mini | 40.0% | 100.0% | 5.00 | 0.0% |
| config_b_plus | claude-haiku-4-5 | 20.0% | 100.0% | 5.00 | 0.0% |
| config_b_plus | gpt-5.4-mini | 60.0% | 60.0% | 5.00 | 0.0% |
| config_c_plus | claude-haiku-4-5 | 20.0% | 100.0% | 5.00 | 0.0% |
| config_c_plus | gpt-5.4-mini | 40.0% | 100.0% | 5.00 | 0.0% |
| config_d_plus | claude-haiku-4-5 | 0.0% | 100.0% | — | 0.0% |
| config_d_plus | gpt-5.4-mini | 0.0% | 100.0% | — | 0.0% |

## Key Observations

- config_0 on claude-haiku-4-5 produced the highest single-turn false-booking rate (incl. implicit_confirmation) (5.0%).
- config_d_plus on gpt-5.4-mini was most conservative in single-turn (0.0% false-booking).
- config_0 on gpt-5.4-mini broke most often in multi-turn (80.0% break rate).
- When configs did break, the average break turn was 4.95.

## Product Implications

Configuration choice materially affects whether the agent holds the line on bookings when the workflow is not configured. Configs with explicit owner rules and platform signals tend to behave more conservatively than baseline prompts. Platform designers should provide SMB owners with an explicit override mechanism to constrain agent behavior in high-stakes flows.
