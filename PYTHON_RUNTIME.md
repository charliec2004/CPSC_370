# Python version: rules, measurements, and recommendation

The supplied assignment PDF specifies no required Python version. It instructs students to create a Python environment, preserve the SDK, return exact answers, and permits faster executors and NumPy. A newer interpreter therefore appears permitted under the written rules; any separately issued instructor restriction still applies. Our earlier use of 3.9.6 followed Charles's request to retain the existing runtime, not a version mandate found in the PDF.

## Recommendation

Python **3.12.13** is the best balanced candidate among the installed builds measured here. It improved the median of all five sampled task types while retaining NumPy 2.0.2 and websockets 15.0.1. A separate `.venv312` is prepared on Charles's machine; the existing `.venv` remains available. Neither environment is running in practice.

| Task | Python 3.9.6 seconds | Python 3.12.13 seconds | Throughput ratio |
|---|---:|---:|---:|
| monte_carlo_pi | 0.158465 | 0.145415 | 1.09× |
| sort_checksum | 0.291255 | 0.278583 | 1.05× |
| matmul_mod | 0.011575 | 0.006968 | 1.66× |
| prime_count | 0.000799 | 0.000718 | 1.11× |
| hash_search | 0.059134 | 0.048096 | 1.23× |

The ratio is old time divided by new time. A 1.66× throughput ratio means about 40% less runtime, not 66% less runtime.

## What was compared

Five installed builds: Python 3.9.6, 3.11.8, 3.12.13, 3.13.12, and 3.14.0. Three sequential sweeps rotated runtime order to reduce order effects. Each probe verified all five supplied golden answers, then timed the actual contractor on five representative tasks; benchmark answers also matched across interpreters. All runs were on the same Apple Silicon machine, while Auctioneers was offline.

Python 3.9/3.11/3.12 used NumPy 2.0.2. Python 3.13/3.14 required a newer compatible NumPy and used 2.5.3. All used websockets 15.0.1. Thus the latter comparisons include a NumPy change, and every comparison includes interpreter build/compiler differences. These are comparisons of available environments, not isolated experiments on language version alone.

3.13 was fastest for the sampled Monte Carlo case but slower in sorting and hashing than the baseline. 3.14 was not uniformly faster either. The short samples do not establish a universally best interpreter or a tournament profit improvement.

Full timing samples, exact dependency versions, executable paths, and source hashes are in [runtime_comparison.json](validation/runtime_comparison.json). The probe can be rerun with any environment:

```bash
contract-net/student/.venv312/bin/python validation/runtime_probe.py
```

Python 3.12 additionally passed [full matrix/prime and SDK integration checks](validation/python312_full_checks.json), including 700 matrix reference cases, 2,997 prime cases, 256 algebra cases, timing holdouts, lifecycle checks, and all five tasks over a real localhost WebSocket. The [Monte Carlo checks](validation/monte312_checks.json) cover both NumPy and Python backends and float/chunk boundaries. No validation joined a course room.

## Use the prepared environment

From the repository root:

```bash
cd contract-net/student
source .venv312/bin/activate
python --version
python verify.py
```

For another machine with Python 3.12 installed, create the environment first:

```bash
python3.12 -m venv .venv312
source .venv312/bin/activate
python -m pip install -r requirements-validated.txt
python verify.py
```

Join only when ready:

```bash
# Practice
python my_contractor.py --name Auctioneers --practice

# Tournament: fill INSTRUCTOR_TOURNAMENT_WEBSOCKET_URL in .env first
python my_contractor.py --name Auctioneers
```

An explicit `--url` overrides the configured tournament URL. `--practice` explicitly selects practice. A blank tournament URL causes a configuration error without connecting. Machine labels remain the SDK standard.

## Remaining improvements

Further work should separate typical delivery latency from conservative cost/deadline allowances, validate fixed-work calibration for the faster hash prototype, and test price decisions against public competitive outcomes. Those are candidates, not changes bundled into this runtime comparison. The private many-team simulation remains outside Git.
