"""Exact NumPy sorting, worst-case overflow bounds, and fallback checks."""
import hashlib
import json
import platform
import random
import statistics
import time
from pathlib import Path
from unittest.mock import patch
from prove_optimizations import task_for, protocol_checks
from contractnet.tasks import run_task
import my_contractor as implementation


def main():
    np = implementation._np
    assert np is not None
    rng = random.Random(370)
    cases = [{"n": n, "seed": seed} for n in (0, 1, 2, 511, 512, 513, 1023, 1024, 1025)
             for seed in (-2**63, -1, 0, 1, 2**63)]
    cases += [{"n": rng.randrange(10000), "seed": rng.randrange(-2**63, 2**63)} for _ in range(100)]
    executor = implementation.MyContractor.__new__(implementation.MyContractor)
    for params in cases:
        expected = run_task("sort_checksum", params)
        assert executor.execute(task_for("sort_checksum", params)) == expected
        with patch.object(implementation, "_np", None):
            assert implementation.sort_fast(params) == expected
    # Saturate every value at its maximum, including the maximum position.
    # The full weighted sum exceeds int64, but no chunk can overflow it.
    maximum = 2**31 - 1
    assert 512 * 5_000_000 * maximum < 2**63
    for n in (0, 1, 511, 512, 513, 5_000_000):
        values = np.full(n, maximum, dtype=np.int64)
        expected = (maximum * n * (n+1)//2) % ((1 << 61)-1)
        assert implementation._sort_checksum64(values) == expected
    del values
    # Exact rejection draws, including rejected 32-bit values.
    class Draws:
        calls = 0
        def getrandbits(self, width):
            assert width == 32
            value = [2**32-1, 2**31, 9, 0, 3][self.calls % 5]
            self.calls += 1
            return value
    for backend in (np, None):
        draws = Draws()
        with patch.object(implementation, "_np", backend), patch.object(implementation.random, "Random", return_value=draws):
            assert implementation.sort_fast({"n": 3, "seed": 1}) == 33
        assert draws.calls == 5
    for params in ({"n": 5_000_001, "seed": 1}, {"n": True, "seed": 1}, {"n": 10, "seed": "1"}):
        for backend in (np, None):
            with patch.object(implementation, "_np", backend):
                try: implementation.sort_fast(params)
                except ValueError: pass
                else: raise AssertionError(params)
    rows = []
    for n in (50_000, 500_000, 1_700_003):
        params = {"n": n, "seed": 20260910}
        times = [[], []]
        for trial in range(3):
            answers = []
            for index in ([0, 1] if trial % 2 == 0 else [1, 0]):
                with patch.object(implementation, "_np", None if index == 0 else np):
                    start = time.perf_counter()
                    answers.append(implementation.sort_fast(params))
                    times[index].append(time.perf_counter()-start)
            assert answers[0] == answers[1]
        old, new = map(statistics.median, times)
        rows.append({"n": n, "previous_python_seconds": old, "numpy_seconds": new,
                     "runtime_reduction": 1-new/old})
    print(json.dumps({"python": platform.python_version(), "numpy": np.__version__,
                      "seeded_reference_cases_both_backends": len(cases),
                      "worst_case_checksum_sizes": [0, 1, 511, 512, 513, 5_000_000],
                      "rejection_draw_and_invalid_input_checks": "passed",
                      "benchmarks": rows, "protocol": protocol_checks("competitive"),
                      "source_sha256": hashlib.sha256(Path(implementation.__file__).read_bytes()).hexdigest(),
                      "limits": "Offline CPU timings, not server delivery times or tournament profit."}, indent=2))


if __name__ == "__main__": main()
