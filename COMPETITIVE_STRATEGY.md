# Auctioneers: current competitive strategy

The default mode is now `competitive`. It combines exact faster matrix, prime, sorting, Monte Carlo, and hash-search algorithms with calibrated delivery estimates, faster price reductions after losses, and explicit hash-search risk admission. The recommended measured runtime is Python 3.12.13, with Python 3.9.6 retained as a tested fallback; NumPy 2.0.2 optionally accelerates Monte Carlo; SDK files are unchanged.

## What changed and why

### Monte Carlo: batch arithmetic, preserve every draw

The agent now uses optional NumPy float64 batches to evaluate Python's original seeded points, with separate multiplication and addition operations. It calibrates the chosen backend and retains a Python fallback. Read the [correctness proof and measurements](MONTE_CARLO_PROOF.md).

### Sorting: less overhead, identical answer

The reference generates each integer with `Random(seed).randrange(0, 2**31)`. On our supported CPython runtime that draws 32 random bits and rejects values at or above 2**31. Our executor performs those same draws and rejections directly. Using only 31 bits would change the seeded sequence and produce wrong answers; we do not do that.

After sorting, the answer is the weighted sum modulo `2**61 - 1`. Exact Python integer arithmetic lets us take the modulus once at the end instead of once per element. Both changes preserve the reference result. We retain all rejection draws, input ordering, sorting, and position weights.

Startup benchmarks the actual optimized sort at 100,000, 400,000, and 1,200,000 elements and uses the larger measured seconds-per-n-log-n coefficient. Per-task compute corrections still learn from successful local timings. This does not reuse answers or predict random outcomes.

### Matrices: faster generation without changing the random sequence

The checksum identity remains unchanged. Matrix input generation now also uses exact rejection sampling: draw `mod.bit_length()` bits, reject values greater than or equal to `mod`, and preserve all draws in reference order. This mirrors the supported CPython runtime's `randrange(mod)`, including power-of-two moduli, modulus one, and rejected draws. It removes repeated method dispatch while preserving every matrix entry.

Startup measures the new executor automatically. In the latest repeated 260×260 benchmark, reference computation took about 0.972 seconds and the new executor took 0.0105 seconds (about 93× faster than reference). Our earlier optimized executor took roughly 0.05 seconds on this case. The matrix reference comparisons and held-out timing cases are rerun against it. Performance is still limited by the laptop and delivery latency; faster local computation does not imply the same factor of improvement in server-measured delivery time.

### Queue reservations: count each job once

An original delivery quote includes the jobs ahead of it. Summing those full quotes again counts earlier work multiple times. Our queue now adds each pending/awarded job's own compute estimate and delivery allowance, subtracting elapsed execution for running work. The overrun guard remains, and a timed-out task that is still computing remains reserved.

For three one-second tasks with a 0.12-second delivery allowance, the estimates are approximately 1.12, 2.24, and 3.36 seconds. The previous third quote was approximately 4.48 seconds because it counted the first job again. Missing quote details retain the full SDK estimate as a conservative fallback.

The [queue checks](validation/queue_checks.json) exercise three overlapping CFPs through the actual SDK, partial running work, overrun refusal, ongoing computation after timeout, rejection cleanup, and fallback behavior. This can improve admission and auction scores when auctions overlap; the practice room's serial configuration does not demonstrate live concurrency behavior.

### Delivery estimates: separate prediction from safety

After five valid observations, competitive bids quote mean overhead plus 20 ms. Deadline admission, cost floors, hash risk, and queue reservations retain the larger mean/90th-percentile allowance plus 20 ms. The mean better predicted overhead in two historical offline replays, though it was exceeded more often. See the [method, checks, and limitations](DELIVERY_ESTIMATES.md).

### Pricing: react quickly to losing

For non-hash tasks, keep the existing minimum of `1.28 × predicted billed cost`. Let `share` be the fraction of budget remaining above that minimum:

```text
price = minimum + share × (budget − minimum)
```

The budget is rounded downward to wire precision. Each task type starts at a 0.25 share. After a valid loss to another contractor, multiply its share by 0.25 and reset its success counter. After two correct deliveries, increase the share by 0.05, capped at 0.95. Failed deliveries reset the success counter. Missing/invalid winning information does not train the price.

For example, a 0.25 share drops to 0.0625 after one loss and 0.015625 after two. The old adaptive mode would take many more losses to move from a near-budget price to its minimum. This still cannot beat every competitor: a faster or lower-margin bidder may win even when our share approaches zero. The policy never invents a shorter runtime to lower its score.

These constants are heuristics, not a proven optimal auction strategy. Feedback is separated by task type but still mixes different task sizes and competitor conditions. State resets when the process restarts. The policy uses the manager's own award/rejection messages and does not coordinate bids with anyone.

### Hash search: account for the distribution

The exact executor now reuses the fixed seed prefix in SHA-256 and compares four-byte digests directly. Calibration times fixed numbers of attempts through that same loop; it does not stop at a lucky success. See the [correctness proof and offline measurements](HASH_PROOF.md).

Under the independent uniform-hash model, each attempt succeeds with probability `p = threshold / 2**32`. Given expected compute time `m`, estimate seconds per attempt as `m × p`. After subtracting queued work and delivery allowance from the deadline, let `k` be the whole number of attempts that fit. The modelled chance of on-time success is:

```text
success = 1 − (1 − p)**k
```

Competitive mode refuses when this is below 0.95. That is a model threshold, not a promise of 95% measured reliability: CPU load, network variation, and calibration error still matter. Budgets and deadlines were generated from actual task measurements, so conditioning on them can also change the distribution; this simple model does not infer that relationship.

For admitted hash jobs, use a failure-adjusted minimum:

```text
mean cost = predicted billed time × live cost_rate
expected penalty = (1 − success) × live penalty_rate × task budget
minimum = 1.28 × (mean cost + expected penalty) / success
```

We count payment only on on-time success, conservatively ignoring possible late credit. Refuse if the resulting price cannot fit the budget. Queue occupancy and work continuing after timeout are additional reasons this is not a complete expected-profit model. Existing queue-overrun guards remain in place.

Legacy `markup` and `adaptive` modes preserve their earlier price/risk behavior for comparison. They now use the same faster executors as competitive mode, so changing the pricing flag does not reproduce old execution timings.

## Evidence and limits

Run from the repository root:

```bash
contract-net/student/.venv/bin/python validation/check_competitive.py
```

The [recorded checks](validation/competitive_checks.json) include 225 sort/reference comparisons, invalid-input checks, four held-out sorting sizes (up to 1,700,003 elements) with alternating reference/candidate timing order, geometric probability boundaries, risk-adjusted prices and refusal, competitive feedback, baseline behavior, lifecycle checks, and delivery of all five task types through the real SDK over a local WebSocket. Check the current file for measured speedups and source hash.

The supplied `verify.py` remains the quick exact-answer check. The broader `validation/prove_optimizations.py` retains the matrix/prime proofs and regressions. Finite tests support correctness and measured performance; they do not prove future deadlines or tournament wins.

The assignment's “Going further,” “Ground rules,” and appendix A.6 explicitly permit faster exact executors and independent adaptive bidding. The supplied SDK remains unchanged. Every awarded task is computed locally, and runtime reporting remains the SDK's actual measurement.

## Running

The usual command now selects competitive mode without extra flags:

```bash
python my_contractor.py --name Auctioneers --url 'wss://contractnet.blackdial.workers.dev/agent?room=practice'
```

Explicitly use `--pricing competitive`, `--pricing adaptive`, or `--pricing markup` to select a mode. Use only one process under the team name. Stop gracefully before starting another; outstanding bids must still be honored. See the [complete guide](AGENT_GUIDE.md) and [README](README.md) for configuration.
