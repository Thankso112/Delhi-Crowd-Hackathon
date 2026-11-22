# Validation summary (real October 2026 data)

**Reliability (split-half, independent halves of the month)**: Spearman 0.935 on odd vs even days
(0.960 where each half has 30+ tickets); first half vs second half 0.911.

**Temporal holdout** (build from 1-21 Oct, test on unseen 22-31 Oct, cells with 10+ unseen tickets):
| predictor                     |   cells |   tier_agreement_pct |   MAE_people |   spearman |
|:------------------------------|--------:|---------------------:|-------------:|-----------:|
| City baseline (band average)  |  172773 |               68.366 |       19.057 |      0.186 |
| Route baseline (route x band) |  172773 |               73.902 |       12.638 |      0.697 |
| Our model (stretch, shrunk)   |  172773 |               83.535 |        7.351 |      0.875 |

**Sensitivity of the calibrated tiers (low / base / high scale):**
| scenario   |   scale |   seats_available |   standing_room |   crowded |   same_tier_as_base_pct |   same_tier_high_confidence_pct |
|:-----------|--------:|------------------:|----------------:|----------:|------------------------:|--------------------------------:|
| low        |    20   |              97.9 |             1.1 |       1   |                    92.6 |                            76.4 |
| base       |    42.9 |              91.6 |             3.5 |       4.9 |                   100   |                           100   |
| high       |    66.7 |              84.4 |             5.7 |      10   |                    89.2 |                            69.5 |

**Organizer curve check:**
| daytype   |   hour |   organizer |   ours |   difference_pct |
|:----------|-------:|------------:|-------:|-----------------:|
| weekday   |      9 |       13000 |  14327 |             10.2 |
| weekday   |     18 |        8500 |   9902 |             16.5 |
| weekend   |      9 |        8000 |   7971 |             -0.4 |
| weekend   |     18 |        4500 |   5168 |             14.8 |
