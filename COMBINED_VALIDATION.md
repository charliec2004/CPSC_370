# Combined offline validation

The combined executor, pricing, delivery-estimation, and queue implementation passed the full Python 3.12.13 regression suite and a new single-contractor stress test. No production fix was needed for a failed check in this pass. Auctioneers was not connected to a class room.

The nine regression scripts cover matrix/prime correctness, Monte Carlo and sorting on both backends, exact hash search, calibration holdouts, bid admission and pricing, queue behavior, delivery learning, launch configuration, and SDK integration. The [run manifest](validation/combined_regression.json) records the production source hash and successful script runs.

## Stress scenarios

The stress harness uses the production contractor and unchanged SDK over a real localhost WebSocket. It calibrates the actual executors, checks results against reference implementations, and injects a delay before each INFORM is sent. Workloads include 500,003 Monte Carlo samples, sorting 500,003 values, a 300,003-wide prime interval, a 173×173 matrix, and the golden hash search.

Python 3.12 results:

| Scenario | Jobs | Added delay per delivery | Deadline | Missed deadlines | Model profit |
| --- | ---: | ---: | ---: | ---: | ---: |
| Steady delivery | 10 | 30 ms | 3 s | 0 | +12.92 |
| Slower delivery | 10 | 150 ms | 3 s | 0 | +12.52 |
| Five overlapping awards | 5 | 120 ms | 3 s | 0 | +6.20 |
| Unexpected delay spike, overlapping awards | 5 | 700 ms | 1.5 s | 4 | −12.75 |

Every delivered answer was exact, including late results. Duplicate awards did not duplicate execution. Queue reservations, settlement profit totals, commitment cleanup, and graceful shutdown passed. Python 3.9 is checked separately with the same scenarios; consult its evidence for measured results.

The severe scenario deliberately exceeds what startup calibration can predict. Since execution and delivery are serial, the injected delay accumulates across awarded jobs. This demonstrates the remaining risk of accepting overlapping commitments before observing a slowdown. It does not justify changing margins based on this single artificial example.

## Accounting and limits

Budgets are fixed at 5 credits, cost rate at 1, penalty rate at 0.5, late credit at zero, and grace at 200 ms. Correct on-time deliveries receive their actual bid price. Late deliveries receive zero revenue and a 2.5-credit penalty. Timeouts use the promised runtime for cost, following the assignment's stated timeout accounting; other deliveries use server-observed elapsed time.

The mock manager evaluates deadlines when INFORM arrives. It does not reproduce the real server's early timeout notification, re-auction, disconnect/reconnect, or concurrent competing bidders. Existing deterministic queue checks separately exercise local computation continuing after a timeout. The profit totals are test accounting, not a prediction of tournament earnings. These tests are separate from the private many-team simulation and include none of its code or data.

Evidence: [Python 3.12 stress results](validation/combined312_checks.json), [Python 3.9 stress results](validation/combined39_checks.json).

To reproduce from the repository root:

```bash
contract-net/student/.venv312/bin/python validation/check_combined.py
```

The next useful evidence would be an authorized, bounded live trial of this exact version under competition. Until then, retain the validated implementation and treat sudden network or machine slowdowns as an unresolved operational risk.
