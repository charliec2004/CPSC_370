# Team laptop timing comparison

**Team:** `Auctioneers`

This table preserves our original laptop comparison. We have selected Charles's M1 Pro. Lower times are faster; these small reference verification tasks are different from the optimized executor's current performance.

## Results

All times are in seconds. Replace the teammate placeholders with your names and results. A dash means not measured yet.

| Task / detail | Charles | Teammate 2 | Teammate 3 |
|---|---|---|---|
| Run date | 2026-09-08 | — | — |
| Laptop model / chip | MacBook Pro / Apple M1 Pro | — | — |
| Python for this recorded run | 3.9.6 | — | — |
| `monte_carlo_pi` | 0.010 | — | — |
| `prime_count` | 0.031 | — | — |
| `hash_search` | 0.060 | — | — |
| `sort_checksum` | 0.041 | — | — |
| `matmul_mod` | 0.005 | — | — |
| Verification result | All checks passed | — | — |
| Executor | Supplied reference | — | — |

Charles's results are from one successful `verify.py` run using the supplied reference executor. Current optimized benchmarks and live practice measurements are in [OPTIMIZATION_PROOF.md](OPTIMIZATION_PROOF.md).

## How to add your results

1. Pull the latest repository changes.
2. From `contract-net/student`, activate your virtual environment and run `python verify.py`.
3. Copy the five printed timings and overall pass/fail result into your column. Add your laptop model and run date.
4. Commit and push this file, or open a pull request. Pull again before editing if another teammate has just updated it.

For a fair comparison, use the same unmodified reference implementations, plug in your laptop, and close heavy background applications. Timings can vary between runs; record any repeat measurements separately instead of mixing the fastest result from each run.

## Practice checks and final choice

Compare estimated versus actual delivery times, profit, deadline failures, and connection stability on the promising machines. Coordinate runs so only one agent uses our shared team name at a time.

- **Selected tournament laptop:** Charles's laptop
- **Reason:** Team decision; tune and validate the final strategy on this machine.
- **Practice observations:** See [PRACTICE_NOTES.md](PRACTICE_NOTES.md) for experiment history and [OPTIMIZATION_PROOF.md](OPTIMIZATION_PROOF.md) for the integrated results.
