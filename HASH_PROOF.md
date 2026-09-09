# Exact faster hash search

Each attempt hashes `seed:nonce`. We hash the fixed `seed:` prefix once, copy that SHA-256 state for each nonce, and append the same decimal nonce bytes. Incremental hashing produces the same digest as hashing the complete string. Nonces still start at zero and advance by one, so the first success is identical to the reference.

Comparing equal-length four-byte strings lexicographically is equivalent to comparing their unsigned big-endian integer values. The comparison remains strictly less than the threshold. At threshold `2**32`, every digest succeeds, so zero is necessarily the answer. Input limits match bid admission.

Startup calibration uses the execution loop for exactly 150,000 attempts, with an impossible zero target so a lucky success cannot shorten the measurement. It takes three timings for each of a short and long UTF-8 seed, then uses the larger median seconds per attempt. Expected compute time is that coefficient times `2**32 / threshold`, plus 0.0005 seconds. The existing 95% modelled deadline admission and failure-adjusted pricing remain in place. This improves measured throughput; it does not eliminate hash-search variance.

The Python 3.12.13 offline benchmark measured about 23% less runtime for seed `370` and 27% less for a 120-character ASCII seed. A long UTF-8 case benefited more. These are repeated local search timings, not tournament profit measurements. Calibration and CPU load can vary.

Run from the repository root:

```bash
contract-net/student/.venv312/bin/python validation/check_hash.py
```

The [3.12 evidence](validation/hash312_checks.json) and [3.9 fallback evidence](validation/hash39_checks.json) record 180 reference comparisons, strict comparison and nonce-order boundaries, invalid inputs, fixed-work calibration, and all five task types delivered through the unchanged SDK over a local WebSocket. The supplied `verify.py` and competitive pricing regression checks provide additional coverage. No class-room connection is needed.

This falls under the assignment's permission to implement faster exact executors (appendix A.6). We compute each search locally and retain actual SDK timing and reporting. No cached task answers or private simulation data are used.
