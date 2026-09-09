# Auctioneers practice notes

## Starter baseline — September 8, 2026, about 5:00 p.m. Pacific

Machine: Charles's laptop, Darwin arm64. Runtime: Python 3.9.6 in `contract-net/student/.venv`. Strategy: unchanged starter, charging estimated computation cost times 1.6 and quoting queue time plus estimated computation time.

Source: the public practice dashboard and `/api/state?room=practice`. This is a point-in-time observation, not a completed tournament result.

| Metric | Observed value |
|---|---:|
| Submitted bids | 37 |
| Refusals | 0 |
| Contracts won | 0 |
| Completed jobs | 0 |
| Failed jobs | 0 |
| Profit | 0 credits |

The agent registered successfully and is sending bids. With no awards yet, we have no actual delivery times or settlement evidence for our own agent. Zero failures does not demonstrate reliable delivery when no contracts were won.

### Examples from the public bid record

The live policy scores bids as `price + 2 * est_seconds`; lower wins.

| Task | Our price | Our estimate | Our score | Winner | Winning price | Winning estimate | Winning score |
|---|---:|---:|---:|---|---:|---:|---:|
| #16 `sort_checksum` | 2.4853 | 1.5533 s | 5.5919 | CEBidders_A1 | 1.4243 | 0.8902 s | 3.2047 |
| #15 `hash_search` | 0.8765 | 0.5478 s | 1.9721 | team_abudabi | 1.1192 | 0.2798 s | 1.6788 |

Task #15 illustrates why lowering price alone is not the whole strategy: the winner charged more than us but quoted a shorter time. The trace reports that winner delivering correctly in 0.32 seconds. Task #16's winner delivered correctly in 1.13 seconds versus its 0.89-second estimate.

Task IDs repeat in the looping practice room; these examples refer to the observations around 5:00 p.m., not all occurrences of those IDs.

### Runtime experiment

Python 3.13.12 is already installed on Charles's laptop. A separate local run of the supplied calibration measured the following throughputs. The Python 3.9 figures are from the agent's startup at 4:55 p.m.; measurements were not simultaneous or repeated, so this is preliminary evidence only.

| Task | Python 3.9.6 work units/s | Python 3.13.12 work units/s |
|---|---:|---:|
| `monte_carlo_pi` | 5,529,030 | 8,244,462 |
| `prime_count` | 180,546,426 | 191,314,551 |
| `hash_search` | 1,961,540 | 1,699,650 |
| `sort_checksum` | 19,495,231 | 26,348,039 |
| `matmul_mod` | 15,064,286 | 18,001,942 |

The newer runtime improved four calibration measurements but reduced hash throughput. The running agent remains on Python 3.9.6; these measurements do not justify assuming every task gets faster.

## Next experiment

Before reducing prices, measure the reference executor on representative larger inputs and compare predicted computation time with measured computation time. Use fresh synthetic inputs for offline experiments and keep actual practice delivery measurements separate, because server billing includes network and queue delay. Then choose one change to test and record the resulting awards, costs, penalties, and profit.

Do not invent delivery estimates to win auctions. Faster execution or better measured estimates must support any shorter promise. Preserve these baseline observations when recording later strategies.

## 1.28 multiplier trial and Python 3.9 queue fix

At about 5:09 p.m., the starter had reached 102 bids and zero wins. We changed the cost multiplier from 1.6 to 1.28 (28% markup), retaining Python 3.9.6 and the reference executor.

The first trial exposed a runtime compatibility failure: the SDK constructs its asyncio queue before `asyncio.run()` creates the running loop. Under Python 3.9.6, a waiting worker raises `RuntimeError` because the queue belongs to a different loop. Offline reproduction confirmed this. Four awarded contracts timed out, producing a cumulative loss of 9.45 credits. These failures cannot be used to judge the profitability of the price change.

We added an override in `MyContractor._main()` that initializes the empty queue on the running loop before delegating to the SDK. No SDK files or task implementations were changed. An offline integration check exercised a waiting worker, a 1.28 bid, an award, reference computation, and a correct `INFORM`; all reference verification checks also passed. The original Python 3.9.6 environment remains in use.

The corrected agent restarted at about 5:12 p.m. Its first award, task #17 (`hash_search`), completed correctly in 0.33 seconds against a 0.64-second estimate, earning 0.48 credits. The public leaderboard retains the earlier failures, so compare new-run profit separately from the lifetime total. Recalibration and changing competitors also mean this is not a controlled comparison of markup alone.

### Later observation

At server timestamp `1788913495060`, lifetime totals were 163 bids, 51 awards, 47 correct completions, four failures, and 12.05 credits profit. All four failures preceded the queue fix. The corrected run therefore earned 21.50 credits relative to the -9.45 restart baseline. Several recent auctions had only our bid, so these wins are not evidence of an advantage against active competing bidders. At least one correctly delivered job lost money: task #1 at about 5:18 p.m. took 3.20 seconds versus a 2.09-second estimate and lost 0.53 credits.

## Offline algorithm investigation — same Python 3.9.6 environment

These candidates were tested separately from the live agent. They have not been installed in its executor. No answer keys, admin endpoints, cached answers, or additional packages were used.

| Candidate | Synthetic input | Reference time | Candidate time | Speedup |
|---|---|---:|---:|---:|
| Matrix checksum via column/row sums | seed 370, n=260, mod=1000003 | 1.001794 s | 0.050595 s | 19.8x |
| Segmented prime sieve | [2000000, 2250000) | 0.991977 s | 0.000658 s | 1508.0x |

Each reference was timed once; candidate times are medians of three runs. Measurements were taken while the practice agent was running and are preliminary, not isolated benchmarks or end-to-end network delivery times. All timed answers matched exactly. Additional comparisons passed on 100 seeded matrix cases and 107 prime ranges, including empty ranges, negative lower bounds, perfect-square boundaries, and segment boundaries. Matrix cases included modulus 1 and a large modulus to check integer arithmetic.

### Why the matrix method works

The task returns the sum of every element of A times B, modulo m. By distributing the finite sums:

`sum_i,j (A B)[i,j] = sum_k (sum_i A[i,k]) * (sum_j B[k,j])`.

Generate A and B with precisely the reference's random draw order, accumulating column sums of A and row sums of B. The final dot product gives the identical checksum. Reducing each product entry before summing, as the reference does, gives the same final remainder. This takes quadratic work rather than cubic work and uses Python integers without fixed-width overflow.

### Why the prime method works

Every composite below hi has a prime factor no larger than `isqrt(hi - 1)`. Build those base primes, mark their multiples in fixed-size segments of [max(lo, 2), hi), and count unmarked entries. Start marking at the larger of p squared and the first multiple within the segment, so a prime never marks itself. This replaces repeated trial division with bulk marking. A production version still needs explicit bounds for the base-prime allocation as well as the segment allocation.

### Strategy implications

- Calibrate the actual custom algorithms; the SDK's cubic matrix and trial-division work models would no longer describe them. Include measured network delay in delivery estimates and costs.
- Treat 1.28 times expected billed cost as a proposed minimum price, not the whole pricing policy. A much faster executor can charge a meaningful share of the available budget while still having a competitive price-plus-time score. Test budget-based prices empirically.
- Separate hash-search tail risk from predictable workloads. Correct results on repeated practice seeds do not establish reliability on new tournament seeds. Use available deadline slack and the runtime distribution when deciding whether the expected profit covers the budget-based penalty.
- Track results by task type and separate competition changes from our code changes. Preserve honest estimates, and refuse bids that cannot cover costs or delivery risk.

## Integrated run — September 8, 2026

The optimized executors are now implemented in `my_contractor.py`. The validation harness imports that implementation directly; its earlier duplicate prototypes have been removed. Calibration uses quadratic matrix work and a separate sieve setup/marking model. Pricing remains 1.28 times the complete predicted billed interval, including delivery overhead, which is learned from unqueued successful settlements.

From 17:56:04 through 18:02:21 Pacific, the measured run delivered 49 jobs correctly, with zero failures in its own records and 19.68 credits profit. This includes nine matrix jobs and ten prime jobs. The sampled public auctions contained no competing valid bids in 27 observed auctions, so this is a delivery/profit observation rather than proof of competitive superiority.

During the earlier stop/restart transition, a standing bid from the reference agent timed out after that process was stopped, adding a fifth lifetime failure. It is not part of the optimized run's measurement records. The final code now supports graceful shutdown: refuse new work, honor already pending bids, and wait for outstanding work to settle. This behavior passed a real local WebSocket test with a stop requested before an outstanding bid was awarded.

The final version has been restarted on the same Python 3.9.6 environment. See [OPTIMIZATION_PROOF.md](OPTIMIZATION_PROOF.md) and [validation/live_results.json](validation/live_results.json) for the final evidence and its limitations. At this markup, matrix and prime jobs together earned only 1.16 credits across 19 correct deliveries; budget-aware pricing remains the next experiment, not a proven improvement.

## Adaptive pricing trial — September 8, 2026

The subsequent experiment added optional `--pricing adaptive` while preserving the default 1.28 markup mode. It asks for half the budget remaining above that minimum, then adjusts the fraction separately by task type: up after correct delivery, down after losing to another contractor. Runtime estimates and executors are unchanged.

The baseline process stopped gracefully before the adaptive process connected. A snapshot from 18:28:24 through 18:30:11 Pacific recorded 14 correct deliveries across all five types, zero failures, and 26.93 credits profit. The adaptive process continues beyond this snapshot. This was not a controlled comparison and competing bids were not sampled. See [PRICING_EXPERIMENT.md](PRICING_EXPERIMENT.md) for the exact policy, local checks, evidence, and remaining runtime-risk work.
