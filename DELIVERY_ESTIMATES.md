# Delivery estimates and safety allowances

Competitive bids now distinguish a predicted delivery time from the conservative time used for admission and pricing. Both include the same computation estimate and conservative queue reservation.

For the first five valid overhead samples, both use the existing allowance. After that, the quoted overhead is the mean of the last 20 samples plus 20 ms, with a 50 ms minimum. The safety allowance is the larger of that value and the 90th percentile plus 20 ms. Legacy pricing modes continue quoting the safety allowance.

A sample is server-measured runtime minus locally measured computation. Only correct jobs with no quoted queue and finite, nonnegative durations qualify; server runtime shorter than computation is excluded. This measures scheduling and delivery overhead together, not a network ping. Failed and queued jobs are excluded because their timing cannot reliably isolate this overhead. Consequently, the sample can underrepresent adverse conditions. Learning resets with the process, and the rolling window adapts as new jobs settle.

The conservative allowance still controls the deadline check, price floor, hash success model, and each job's queue reservation. A smaller quoted estimate therefore does not by itself admit a previously refused job or reduce its price. Bid logs record `quoted_overhead`, the conservative `overhead`, and `safe_finish` separately.

## Historical offline replay

Each prediction used only prior samples. Five initial observations were withheld from scoring, and the learning window was capped at 20. These were recorded practice runs, not the private many-team simulation.

| Saved run | Predictions | Old average absolute error | New average absolute error | Average quoted overhead reduction |
| --- | ---: | ---: | ---: | ---: |
| Matrix/queue run | 106 | 100 ms | 47 ms | 64 ms |
| Competitive run | 26 | 40 ms | 27 ms | 17 ms |

The new overhead prediction was exceeded in 23 of 106 observations versus 9 previously, and 3 of 26 versus 2 previously. These are overhead underestimates, not missed deadlines. A mean-based prediction is not an upper bound. The retained safety allowance is also an empirical model, not a guarantee.

At the previously observed scoring weight of 2, these average reductions would lower the time component of a bid score by about 0.128 and 0.033 credits respectively. No auction outcomes were replayed, so this is not a measured increase in wins or profit. The constants were evaluated on these two historical runs; fresh offline or authorized live evidence is needed to establish how well they generalize.

## Checks

Run `contract-net/student/.venv312/bin/python validation/check_delivery.py` from the repository root. It checks cold-start behavior, unchanged prices at equal safety allowances, deadline and hash-risk refusal, conservative queue reservations, invalid observations, window eviction, legacy modes, and five task types through the SDK over a local WebSocket.

Recorded evidence: [Python 3.12](validation/delivery312_checks.json), [Python 3.9 fallback](validation/delivery39_checks.json). The source logs remain local; a committed fixture contains only the extracted overhead durations and log hashes so teammates can reproduce the replay. No class-server connection is made by these checks.
