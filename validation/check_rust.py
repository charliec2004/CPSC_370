#!/usr/bin/env python3
"""Compare the offline Rust executable with the unmodified Python reference.

Usage: python3.12 validation/check_rust.py [path/to/auctioneers]
Build first with cargo build --release --locked in contract-net/rust.
No dependencies or network connection required.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "reference_tasks", ROOT / "contract-net/student/contractnet/tasks.py"
)
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)


def main():
    binary = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "contract-net/rust/target/release/auctioneers"
    cases = []

    def add(kind, **params):
        cases.append({"task_type": kind, "params": params})

    for seed in [0, 1, -1, 370, 2**32 - 1, 2**32, -(2**64 - 1), 2**64 - 1]:
        for n in [0, 1, 17, 1000]:
            add("monte_carlo_pi", seed=seed, samples=n)
            add("sort_checksum", seed=seed, n=n)
        for modulus in [1, 2, 2**31, 2**32 + 1, 2**63, 2**64 - 1]:
            for n in [0, 1, 7]:
                add("matmul_mod", seed=seed, n=n, mod=modulus)
    for lo, hi in [(-20, 3), (0, 0), (10, 2), (2, 3), (3, 4), (48, 50), (1000, 5000), (2, 262150)]:
        add("prime_count", lo=lo, hi=hi)
    for seed in ["", "cpsc370-golden", "é🐍", 370, -370, 2**100]:
        for threshold in [2**32, 2**31, 65536]:
            add("hash_search", seed=seed, threshold=threshold)
    # Assignment golden cases, including checksum wraparound.
    golden = [
        ("monte_carlo_pi", {"seed": 12345, "samples": 50000}, 39336),
        ("prime_count", {"lo": 1000000, "hi": 1010000}, 753),
        ("hash_search", {"seed": "cpsc370-golden", "threshold": 65536}, 90984),
        ("sort_checksum", {"seed": 99, "n": 50000}, 1785318802179667385),
        ("matmul_mod", {"seed": 2026, "n": 40, "mod": 1000003}, 629524),
    ]
    for kind, params, expected in golden:
        assert reference.run_task(kind, params) == expected
        add(kind, **params)

    invalid = [
        {"task_type": "unknown", "params": {}},
        {"task_type": "sort_checksum", "params": {"seed": True, "n": 1}},
        {"task_type": "sort_checksum", "params": {"seed": 2**64, "n": 1}},
        {"task_type": "sort_checksum", "params": {"seed": 1, "n": 5000001}},
        {"task_type": "monte_carlo_pi", "params": {"seed": 1, "samples": -1}},
        {"task_type": "matmul_mod", "params": {"seed": 1, "n": 1, "mod": 0}},
        {"task_type": "hash_search", "params": {"seed": 1.5, "threshold": 1}},
        {"task_type": "hash_search", "params": {"seed": "x", "threshold": 0}},
        {"task_type": "prime_count", "params": {"lo": 0, "hi": 10**12 + 1}},
        {"task_type": "prime_count", "params": {"lo": 0, "hi": 20000000}},
        {"task_type": "prime_count", "params": None},
        {"task_type": "prime_count", "params": {}, "timeout_ms": 0},
    ]
    requests = cases + invalid
    completed = subprocess.run(
        [str(binary)], input="".join(json.dumps(c) + "\n" for c in requests),
        capture_output=True, text=True, check=True, timeout=120,
    )
    replies = [json.loads(line) for line in completed.stdout.splitlines()]
    assert len(replies) == len(requests)
    for case, reply in zip(cases, replies):
        expected = reference.run_task(case["task_type"], case["params"])
        assert reply == {"result": str(expected)}, (case, reply, expected)
    for reply in replies[len(cases):]:
        assert "error" in reply, reply
    malformed = subprocess.run([str(binary)], input="{\n" + json.dumps(cases[0]) + "\n",
                               text=True, capture_output=True, check=True, timeout=10)
    assert "error" in json.loads(malformed.stdout.splitlines()[0])
    assert "result" in json.loads(malformed.stdout.splitlines()[1])
    oversized = subprocess.run([str(binary)], input="x" * 16385, text=True,
                               capture_output=True, timeout=10)
    assert oversized.returncode == 2
    assert json.loads(oversized.stdout) == {"error": "request too large"}
    print(f"PASS: {len(cases)} reference comparisons, {len(invalid)} invalid requests, malformed/oversized input")


if __name__ == "__main__":
    main()
