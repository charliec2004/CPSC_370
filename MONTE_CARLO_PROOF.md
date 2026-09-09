# Exact faster Monte Carlo execution

The current agent accelerates Monte Carlo with optional NumPy batching. It retains Python's `random.Random(seed)` and returns the identical integer count. On the team's Python 3.9.6 environment, NumPy 2.0.2 is installed. The interpreter and supplied SDK are unchanged.

## Why the answer stays the same

The reference draws x, then y, for every point and counts `x*x + y*y <= 1.0`. Our implementation draws those same Python float values, in that same order, into float64 arrays. It does not use NumPy's random generator or reuse results from earlier jobs.

Each x product and y product is calculated separately and stored as float64 before addition. The addition is a separate operation, followed by the same inclusive comparison. There is no fused multiply-add, algebraic rearrangement, or approximate circle test. On the tested platform this preserves the reference's separate binary64 rounding steps. Integer counts are accumulated exactly.

Chunks contain at most 65,536 points, bounding temporary array memory to roughly three megabytes. Chunk boundaries do not reset the random generator. The last chunk draws exactly its remaining number of points.

If NumPy is unavailable, a plain-Python path uses the same arithmetic and locally binds `Random.random` to reduce lookup overhead. Startup logs which backend is selected and calibrates that backend, so a teammate without NumPy does not inherit our accelerated timing rate.

## Checks and measurements

Run from the repository root:

```bash
contract-net/student/.venv/bin/python validation/check_monte.py
```

The [recorded checks](validation/monte_checks.json) cover 111 seeded cases for both NumPy and Python paths; zero and tiny workloads; positive and negative seeds; chunk boundaries; points on and adjacent to the circle boundary; exactly two draws per point; and invalid inputs. Three larger, independently seeded sizes compare exact answers and alternate benchmark order. The supplied `verify.py` also passed all five reference and custom-executor checks.

Larger benchmark runs measured roughly 2.0–2.4 times faster local computation. The JSON contains the current measured values. These tests ran at low scheduling priority while practice stayed online, so machine load affects timings. This is evidence of acceleration, not a promise to beat another laptop or a claim of equivalent end-to-end speedup.

In the initial live check, Monte Carlo tasks 24 and 25 returned correct answers with server-measured runtimes of 0.724 and 1.273 seconds respectively. These measurements include delivery overhead. The dashboard confirmed the SDK's standard `Darwin arm64` label.

## Setup and compatibility

For our tested Python 3.9.6 environment, from `contract-net/student`:

```bash
python -m pip install -r requirements-accelerated.txt
python verify.py
```

The optional file pins NumPy 2.0.2, which supports Python 3.9–3.12. See [NumPy's release notes](https://numpy.org/devdocs/release/2.0.2-notes.html). A newer interpreter needs a compatible NumPy release and fresh exact-answer and timing checks; this change does not upgrade Python. The [fromiter documentation](https://numpy.org/doc/stable/reference/generated/numpy.fromiter.html) describes the counted iterator conversion used here.

The assignment explicitly allows faster exact executors and NumPy in its “Going further” section and appendix A.6. No SDK or reference-task file was modified. The final course submission remains the agent file and the required report, as specified by the assignment.
