"""Offline exact hash checks, fixed-work calibration, and SDK integration."""
import hashlib
import json
import platform
import random
import statistics
import time
from pathlib import Path
from unittest.mock import patch
from prove_optimizations import make_agent, task_for, protocol_checks
from contractnet.tasks import run_task
import my_contractor as implementation


def main():
    rng = random.Random(370)
    cases = [{"seed": seed, "threshold": threshold}
             for seed in (0, -370, "", "a:b", "é" * 128, "a" * 128)
             for threshold in (2**32, 2**32-1, 2**31, 2**24, 65536)]
    cases += [{"seed": str(rng.getrandbits(64)), "threshold": rng.randrange(2**20, 2**32)}
              for _ in range(150)]
    agent = implementation.MyContractor.__new__(implementation.MyContractor)
    for params in cases:
        assert agent.execute(task_for("hash_search", params)) == run_task("hash_search", params)
    # Strict '<', big-endian byte ordering, nonce ordering and full threshold.
    seen = []
    class Digest:
        def copy(self): return Digest()
        def update(self, value): self.nonce = int(value); seen.append(value)
        def digest(self): return (256 if self.nonce == 0 else 255).to_bytes(4, "big") + bytes(28)
    with patch.object(implementation.hashlib, "sha256", return_value=Digest()):
        assert implementation.hash_fast({"seed": "x", "threshold": 256}) == 1
        assert seen == [b"0", b"1"]
        assert implementation.hash_fast({"seed": "x", "threshold": 2**32}) == 0
    for params in ({"seed": True, "threshold": 1}, {"seed": "a"*129, "threshold": 1},
                   {"seed": 1, "threshold": 0}, {"seed": 1, "threshold": True},
                   {"seed": 1, "threshold": 2**32+1}):
        try: implementation.hash_fast(params)
        except ValueError: pass
        else: raise AssertionError(params)
    class Counted:
        calls = 0
        def __iter__(self):
            for nonce in range(150000):
                self.calls += 1
                yield nonce
    counted = Counted()
    assert implementation._hash_scan("calibrate", bytes(4), counted) is None
    assert counted.calls == 150000
    calibrated = make_agent("HashCheck", "", auto_calibrate=False, verbose=False)
    calibrated.calibrate_fast()
    task = task_for("hash_search", {"seed": 370, "threshold": 65536})
    assert calibrated._base_estimate(task) == 0.0005 + 65536 * calibrated._fast["hash"]
    rows = []
    for seed in (370, "a" * 120, "é" * 128):
        params = {"seed": seed, "threshold": 65536}
        times = [[], []]
        for trial in range(5):
            answers = []
            for index in ([0, 1] if trial % 2 == 0 else [1, 0]):
                start = time.perf_counter()
                answers.append(run_task("hash_search", params) if index == 0 else implementation.hash_fast(params))
                times[index].append(time.perf_counter() - start)
            assert answers[0] == answers[1]
        reference, candidate = map(statistics.median, times)
        rows.append({"seed": seed, "nonce": answers[0], "reference_seconds": reference,
                     "candidate_seconds": candidate, "runtime_reduction": 1-candidate/reference})
    result = {"python": platform.python_version(), "exact_cases": len(cases),
              "boundary_and_invalid_checks": "passed", "fixed_calibration_attempts": counted.calls,
              "seconds_per_attempt": calibrated._fast["hash"], "benchmarks": rows,
              "protocol": protocol_checks("competitive"),
              "source_sha256": hashlib.sha256(Path(implementation.__file__).read_bytes()).hexdigest(),
              "limits": "Offline measurements; geometric deadline risk remains modelled, not guaranteed."}
    print(json.dumps(result, indent=2))


if __name__ == "__main__": main()
