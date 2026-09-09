# Exact NumPy sorting and checksum

The agent now uses NumPy for sorting and bounded weighted subtotals when NumPy is installed. It preserves the Python implementation as a fallback. Startup calibration calls `sort_fast`, so estimates automatically measure the selected backend on the current machine.

## Why the answer is unchanged

Input generation still uses `Random(seed).getrandbits(32)`, rejecting values at or above `2**31`, exactly as the reference's `randrange(0, 2**31)` does on the supported CPython runtimes. `fromiter` consumes precisely `n` accepted values. No NumPy random generator or saved task answers are used.

All values fit exactly in signed int64. Sorting those integers gives the same ordered values as Python sorting. Stability does not affect the checksum because equal values are indistinguishable.

The weighted sum can exceed int64 for large tasks. To prevent overflow, we split it into chunks of at most 512 entries. Admission and execution limit `n` to five million, and every generated value is at most `2**31 - 1`. Therefore every chunk sum is at most:

```text
512 × 5,000,000 × (2**31 − 1) < 2**63 − 1
```

All products and partial sums are nonnegative and below this bound. Each NumPy subtotal is converted to an unbounded Python integer before adding it to the total. We apply `% ((1 << 61) - 1)` only after accumulation, preserving the reference's modular weighted sum exactly. `_sort_checksum64` is an internal helper whose input limits are enforced by `sort_fast`.

The main array uses 40 MB at the maximum size, plus small chunk arrays and sorting overhead. It does not construct a Python list of all generated integers on the NumPy path.

## Offline measurements

On Python 3.12.13 with NumPy 2.0.2, three alternating trials compared the new backend with our previous optimized Python executor:

| Values | Previous Python | NumPy | Less computation time |
| ---: | ---: | ---: | ---: |
| 50,000 | 0.0173 s | 0.0069 s | 60% |
| 500,000 | 0.2283 s | 0.0711 s | 69% |
| 1,700,003 | 1.0626 s | 0.2466 s | 77% |

These are local computation measurements, not server delivery times or tournament profit. Network overhead remains relevant, especially for small tasks.

Run `contract-net/student/.venv312/bin/python validation/check_sort_numpy.py` from the repository root. The checks cover 145 seeded reference cases on both backends, rejection draws, chunk boundaries, invalid inputs, and a five-million-element checksum filled with maximum values to exercise the overflow bound. All five task types also pass through the unchanged SDK over a local WebSocket.

Evidence: [Python 3.12](validation/sort_numpy312_checks.json), [Python 3.9 fallback runtime](validation/sort_numpy39_checks.json). The existing competitive checks additionally exercise calibrated sort holdouts, pricing, lifecycle behavior, and integration. The supplied `verify.py` checks the five known answers.

The assignment explicitly permits faster exact implementations and NumPy in appendix A.6. The SDK, reference task definitions, actual runtime reporting, and dependency versions remain unchanged.
