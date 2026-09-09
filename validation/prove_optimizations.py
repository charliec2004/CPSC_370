"""Validation of the integrated contractor; no class-server connections.

Run with contract-net/student/.venv/bin/python validation/prove_optimizations.py.
Tests import the production executor and timing model from my_contractor.py.
"""
from __future__ import annotations

import asyncio
import hashlib
import itertools
import json
import math
from pathlib import Path
import platform
import random
import statistics
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "contract-net/student"))
from contractnet import Contractor, Rules, Task
from contractnet.tasks import run_task
from my_contractor import MyContractor, matrix_checksum, prime_sieve
from contractnet.benchmark import calibrate
from verify import GOLDEN
from websockets.asyncio.server import serve


Candidate = MyContractor


def make_agent(*args, **kwargs):
    kwargs.setdefault("pricing", "markup")  # Preserve explicit baseline checks.
    # Python 3.9 needs a construction loop even after an earlier asyncio.run
    # in this test process. Close it deliberately: _main must replace the
    # constructor's queue on its actual running loop.
    bootstrap = asyncio.new_event_loop()
    asyncio.set_event_loop(bootstrap)
    try:
        return Candidate(*args, **kwargs)
    finally:
        bootstrap.close()
        asyncio.set_event_loop(None)


def task_for(kind, params, task_id=1, budget=100, deadline=30):
    return Task(task_id, kind, dict(params), budget, deadline, 1000, 1)


def correctness():
    counts = {"matrix_reference_cases": 0, "prime_reference_cases": 0,
              "independent_algebra_cases": 0, "golden_cases": 0,
              "resource_rejections": 0}
    rng = random.Random(3702026)
    for _ in range(700):
        params = {"seed": rng.randrange(-2**32, 2**32), "n": rng.randrange(21),
                  "mod": rng.choice([1, 2, 17, 1000003, 2**63-1, 2**64-1])}
        assert matrix_checksum(params) == run_task("matmul_mod", params), params
        counts["matrix_reference_cases"] += 1
    # Direct matrix multiplication independently checks the rearrangement,
    # separate from the seeded implementation and reference task dispatcher.
    for values in itertools.product(range(2), repeat=8):
        a, b = [values[:2], values[2:4]], [values[4:6], values[6:8]]
        full = sum(sum(a[i][k] * b[k][j] for k in range(2))
                   for i in range(2) for j in range(2))
        reduced = sum(sum(a[i][k] for i in range(2)) * sum(b[k]) for k in range(2))
        assert full == reduced
        counts["independent_algebra_cases"] += 1
    ranges = [(lo, hi) for lo in range(-5, 65) for hi in range(lo, 65)]
    ranges += [(p*p-2, p*p+3) for p in (2, 3, 5, 7, 31, 101, 997)]
    for _ in range(500):
        lo = rng.randrange(0, 1_000_000)
        ranges.append((lo, lo+rng.randrange(1000)))
    ranges += [(0, 262145), (1_000_000, 1_524_300), (100, 0),
               (99_999_990, 100_000_010), (999_999_990, 1_000_000_010)]
    for lo, hi in ranges:
        params = {"lo": lo, "hi": hi}
        assert prime_sieve(params) == run_task("prime_count", params), params
        counts["prime_reference_cases"] += 1
    executor = Candidate.__new__(Candidate)  # Same construction as verify.py.
    for kind, params, expected in GOLDEN:
        assert executor.execute(task_for(kind, params)) == expected
        counts["golden_cases"] += 1
    for fn, params in [
        (matrix_checksum, {"n": 2049, "mod": 17, "seed": 1}),
        (matrix_checksum, {"n": 3, "mod": 0, "seed": 1}),
        (matrix_checksum, {"n": True, "mod": 17, "seed": 1}),
        (prime_sieve, {"lo": 10**12, "hi": 10**12+1}),
        (prime_sieve, {"lo": 2, "hi": 10_000_003}),
        (prime_sieve, {"lo": "2", "hi": 10}),
    ]:
        try:
            fn(params)
        except ValueError:
            counts["resource_rejections"] += 1
        else:
            raise AssertionError("Out-of-domain input accepted")
    return counts


def benchmarks():
    rows = []
    specs = [("matmul_mod", matrix_checksum, {"seed": 917+n, "n": n, "mod": 1000003})
             for n in (40, 70, 130, 260, 400)]
    specs += [("prime_count", prime_sieve, {"lo": lo, "hi": lo+width})
              for lo, width in ((1_000_000, 10_000), (2_000_000, 25_000),
                                (2_000_000, 250_000), (10_000_000, 300_000))]
    for kind, fn, params in specs:
        times = {"reference": [], "candidate": []}
        expected = run_task(kind, params)
        assert fn(params) == expected  # Warm both before timed trials.
        for repetition in range(3):
            order = ("reference", "candidate") if repetition % 2 == 0 else ("candidate", "reference")
            for implementation in order:
                loops = 1 if implementation == "reference" else (50 if kind == "prime_count" else 3)
                started = time.perf_counter()
                for _ in range(loops):
                    answer = run_task(kind, params) if implementation == "reference" else fn(params)
                    assert answer == expected
                times[implementation].append((time.perf_counter()-started)/loops)
        ref, fast = (statistics.median(times[k]) for k in ("reference", "candidate"))
        row = {"task_type": kind, "params": params, "reference_seconds": ref,
               "candidate_seconds": fast, "speedup": ref/fast, "trials": times}
        rows.append(row)
        print(f'{kind} {params}: {ref:.6f}s -> {fast:.6f}s ({ref/fast:.1f}x)', flush=True)
    return rows


def bidding_checks():
    agent = make_agent("OfflineCheck", "wss://example.invalid", auto_calibrate=False, verbose=False)
    agent.rates = {"monte_carlo_pi": 100}
    task = task_for("monte_carlo_pi", {"seed": 1, "samples": 100})
    bid = agent.on_cfp(task)
    assert 1.12 <= bid.est_seconds <= 1.1201
    assert round(bid.price / bid.est_seconds, 3) == 1.28
    agent.rules = Rules(cost_rate=3, time_weight=7)
    bid = agent.on_cfp(task)
    assert round(bid.price / (3 * bid.est_seconds), 3) == 1.28
    assert agent.on_cfp(task_for(task.task_type, task.params, budget=3)) is None
    assert agent.on_cfp(task_for(task.task_type, task.params, deadline=0.5)) is None
    with patch.object(Candidate, "queue_seconds", property(lambda _: 31)):
        assert agent.on_cfp(task) is None
    agent.rates = {}
    assert agent.on_cfp(task) is None
    return 6


def protocol_checks(pricing="markup"):
    # Construct OUTSIDE asyncio.run(), reproducing the Python 3.9 setup that
    # previously killed the waiting worker. Candidate inherits our queue fix.
    agent = make_agent("OfflineCheck", "", token="offline-test-only", auto_calibrate=False, verbose=False, pricing=pricing)
    agent.rates = calibrate(verbose=False)
    agent.calibrate_fast()
    results, connections = [], []

    async def run():
        async def manager(ws):
            registration = json.loads(await ws.recv())
            assert registration["type"] == "REGISTER"
            assert registration["name"] == "OfflineCheck"
            assert registration["token"] == "offline-test-only"
            connections.append(True)
            await ws.send(json.dumps({"type": "REGISTERED", "name": "OfflineCheck", "rules": {}}))
            await asyncio.sleep(0.02)  # Let worker wait before the first award.
            for task_id, (kind, params, expected) in enumerate(GOLDEN, 1):
                await ws.send(json.dumps({"type": "CFP", "task_id": task_id,
                    "task_type": kind, "params": params, "budget": 100,
                    "deadline_s": 30, "bid_window_ms": 1000, "attempt": 1}))
                bid = json.loads(await ws.recv())
                assert bid["type"] == "PROPOSE"
                if task_id == len(GOLDEN):
                    agent.request_stop()  # Pending bid must still be honored.
                await ws.send(json.dumps({"type": "ACCEPT_PROPOSAL", "task_id": task_id,
                    "price": bid["price"], "deadline_s": 30}))
                delivery = json.loads(await ws.recv())
                assert delivery["type"] == "INFORM", delivery
                assert delivery["result"] == str(expected)
                assert delivery["runtime"] >= 0
                await ws.send(json.dumps({"type": "SETTLED", "task_id": task_id,
                    "verdict": "correct", "revenue": 1, "cost": 0.1,
                    "penalty": 0, "profit": 0.9, "runtime": 0.1,
                    "est_seconds": bid["est_seconds"]}))
                results.append(kind)
            await asyncio.sleep(0.03)
            finished.set_result(True)

        finished = asyncio.get_running_loop().create_future()
        async with serve(manager, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            agent.url = f"ws://127.0.0.1:{port}"
            runner = asyncio.create_task(agent._main())
            try:
                await asyncio.wait_for(finished, timeout=15)
                assert len(agent.history) == 5
                assert not agent._commitments
                agent.request_stop()
                await asyncio.wait_for(runner, timeout=2)
            finally:
                runner.cancel()
                try:
                    await runner
                except asyncio.CancelledError:
                    pass
    asyncio.run(run())
    return {"transport": "real WebSocket on 127.0.0.1", "task_types_delivered": results,
            "settlements_recorded": len(agent.history), "registrations": len(connections),
            "limitation": "Artificial generous budgets, supplied rates, and settlements; not a profit or timing test."}


def timing_checks():
    agent = make_agent("TimingCheck", "wss://example.invalid", auto_calibrate=False, verbose=False)
    agent.calibrate_fast()
    rows = []
    cases = [("matmul_mod", {"seed": 800+n, "n": n, "mod": mod})
             for n, mod in ((53,17),(173,1000003),(319,1000003),(451,2**30),(227,2**63+1))]
    cases += [("prime_count", {"lo": lo, "hi": lo+width})
              for lo, width in ((3,1000),(7_000_000,130_003),(123_000_000,600_001),
                                (999_000_000,1_000_001),(10**12-1000,1000))]
    for kind, params in cases:
        task = task_for(kind, params)
        compute = agent.estimate(task)
        bid = agent.on_cfp(task)
        assert bid is not None
        durations = []
        for _ in range(3):
            started = time.perf_counter()
            agent.execute(task)
            durations.append(time.perf_counter()-started)
        actual = statistics.median(durations)
        assert actual < bid.est_seconds, (kind, params, actual, bid)
        rows.append({"task_type":kind,"params":params,"predicted_compute":compute,
                     "measured_compute":actual,"quoted_delivery":bid.est_seconds})
    print('Ten unseen-size timing holdouts fit within their quoted delivery allowance.', flush=True)
    return rows


def lifecycle_checks():
    from contractnet import Settlement
    agent = make_agent("LifecycleCheck", "wss://example.invalid", auto_calibrate=False, verbose=False)
    agent.rates = {"monte_carlo_pi": 100}
    async def run():
        agent._queue = asyncio.Queue()
        sent = []
        async def capture(message):
            sent.append(message)
        agent._send = capture
        for task_id in (800,801):
            await agent._handle_cfp({"task_id":task_id,"task_type":"monte_carlo_pi",
                "params":{"seed":1,"samples":100},"budget":100,"deadline_s":30})
        award={"type":"ACCEPT_PROPOSAL","task_id":801,"price":3,"deadline_s":30}
        await agent._dispatch(award)
        await agent._dispatch(award)
        assert agent._queue.qsize()==1
        agent.request_stop()
        assert agent.on_cfp(task_for("monte_carlo_pi", {"seed":1,"samples":100})) is None
        assert 801 in agent._commitments
        agent._draining=False
        await agent._dispatch({"type":"REGISTERED","name":"LifecycleCheck","rules":{}})
        assert 800 not in agent._commitments and 800 not in agent._quotes
        assert 801 in agent._commitments and 801 in agent._quotes
        with agent._timing_lock:
            agent._running=(801,time.perf_counter()-2,1)
        assert agent.on_cfp(task_for("monte_carlo_pi",{"seed":1,"samples":100})) is None
        with agent._timing_lock:
            agent._running=None
        # Delivery overhead is learned only from successful, unqueued work.
        for task_id in (900,901,902):
            agent._quotes[task_id]={"queue":0}
            agent._measurements.append((task_id,1.5,1.0))
            agent.on_settled(Settlement(task_id,"monte_carlo_pi","correct",2,1.55,0,.45,1.55,1.12))
        assert math.isclose(agent._network_seconds,0.07)
        assert 1 < agent._bias["monte_carlo_pi"] < 1.5
        previous=agent._network_seconds
        agent._quotes[903]={"queue":2}
        agent._measurements.append((903,1,1))
        agent.on_settled(Settlement(903,"hash_search","correct",4,3,0,1,3,3))
        assert agent._network_seconds==previous
        assert "hash_search" not in agent._bias
        await agent._dispatch({"type":"BID_INVALID","task_id":801,"reason":"test"})
        assert 801 not in agent._quotes and 801 not in agent._commitments
    asyncio.run(run())
    print('Lifecycle checks passed: duplicate award, reconnect, overrun refusal, and timing learning.',flush=True)
    return ["shutdown refuses new bids and preserves outstanding work", "duplicate award enqueues once", "reconnect drops only pending bids",
            "overrunning work prevents new promises", "compute bias learns from raw model",
            "overhead excludes known queued work", "hash variance does not train throughput",
            "invalid bids release local quote and commitment"]


def main():
    protected = list((ROOT / "contract-net/student/contractnet").glob("*.py"))
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    result = {"python": sys.version, "platform": platform.platform(),
              "candidate_status": "integrated production executor and timing model",
              "production_source_sha256": hashlib.sha256(
                  (ROOT / "contract-net/student/my_contractor.py").read_bytes()).hexdigest()}
    result["correctness"] = correctness()
    print(result["correctness"], flush=True)
    result["bidding_checks"] = bidding_checks()
    result["timing_holdouts"] = timing_checks()
    result["lifecycle_checks"] = lifecycle_checks()
    result["protocol"] = protocol_checks()
    print('Real localhost WebSocket: all five task types delivered and settled.', flush=True)
    result["benchmarks"] = benchmarks()
    assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    result["sdk_hashes_unchanged"] = before
    result["limitations"] = [
        "Finite testing complements the mathematical argument; it does not exhaust all parameters.",
        "Timing holdouts test local computation plus a delivery allowance, not real network conditions.",
        "No claims of optimal pricing, tournament wins, or hash-search tail safety are established.",
        "Reference and candidate alternate order; the practice agent is paused, but OS noise remains.",
    ]
    output = Path(__file__).with_name("optimization_results.json")
    output.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(f'All checks passed. Evidence: {output}', flush=True)


if __name__ == "__main__":
    main()
