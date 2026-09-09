"""Single-contractor localhost stress checks; never connects to a class room."""
import asyncio
import hashlib
import json
import math
import platform
import time
from pathlib import Path
from prove_optimizations import make_agent
from contractnet.benchmark import calibrate
from contractnet.tasks import run_task
from websockets.asyncio.server import serve


CASES = [
    ("monte_carlo_pi", {"samples": 500003, "seed": 991}),
    ("sort_checksum", {"n": 500003, "seed": 992}),
    ("prime_count", {"lo": 7_000_000, "hi": 7_300_003}),
    ("matmul_mod", {"n": 173, "mod": 1000003, "seed": 993}),
    ("hash_search", {"seed": "cpsc370-golden", "threshold": 65536}),
]


async def scenario(name, fast, rates, expected, delay, overlap, deadline):
    agent = make_agent("OfflineStress", "", token="offline-test-only", pricing="competitive",
                       auto_calibrate=False, verbose=False)
    agent._fast = fast.copy()
    agent.rates = rates.copy()
    original_send = agent._send
    async def delayed_send(message):
        if message["type"] == "INFORM":
            await asyncio.sleep(delay)
        await original_send(message)
    agent._send = delayed_send
    rows = []
    done = asyncio.get_running_loop().create_future()

    async def manager(ws):
        try:
            registration = json.loads(await ws.recv())
            assert registration["type"] == "REGISTER"
            await ws.send(json.dumps({"type": "REGISTERED", "name": agent.name,
                "rules": {"cost_rate": 1, "penalty_rate": .5, "late_credit": 0,
                          "grace_ms": 200, "concurrency": 5 if overlap else 1}}))
            groups = [list(range(5))] if overlap else [[i] for i in range(10)]
            for group in groups:
                bids, awarded = {}, {}
                for task_id in group:
                    kind, params = CASES[task_id % 5]
                    await ws.send(json.dumps({"type": "CFP", "task_id": task_id,
                        "task_type": kind, "params": params, "budget": 5,
                        "deadline_s": deadline, "bid_window_ms": 1000, "attempt": 1}))
                    bid = json.loads(await asyncio.wait_for(ws.recv(), 3))
                    assert bid["type"] == "PROPOSE", bid
                    assert 0 <= bid["price"] <= 5 and 0 < bid["est_seconds"] <= deadline
                    bids[task_id] = bid
                if overlap:
                    assert len(agent._commitments) == 5
                    reserved = sum(q["compute"] + q["overhead"] for q in agent._quotes.values())
                    assert math.isclose(agent.queue_seconds, reserved)
                for task_id in group:
                    awarded[task_id] = time.perf_counter()
                    award = {"type": "ACCEPT_PROPOSAL", "task_id": task_id,
                             "price": bids[task_id]["price"], "deadline_s": deadline}
                    await ws.send(json.dumps(award))
                    if overlap: await ws.send(json.dumps(award))  # Duplicate must not execute twice.
                if group == groups[-1]: agent.request_stop()
                for task_id in group:
                    delivery = json.loads(await asyncio.wait_for(ws.recv(), 10))
                    runtime = time.perf_counter() - awarded[task_id]
                    assert delivery["type"] == "INFORM" and delivery["task_id"] == task_id
                    assert delivery["result"] == str(expected[task_id % 5])
                    assert 0 <= delivery["runtime"] <= runtime + .001
                    verdict = "correct" if runtime <= deadline else ("late" if runtime <= deadline+.2 else "timeout")
                    revenue = bids[task_id]["price"] if verdict == "correct" else 0
                    cost = bids[task_id]["est_seconds"] if verdict == "timeout" else runtime
                    penalty = 0 if verdict == "correct" else 2.5
                    profit = revenue-cost-penalty
                    await ws.send(json.dumps({"type": "SETTLED", "task_id": task_id,
                        "verdict": verdict, "runtime": runtime, "est_seconds": bids[task_id]["est_seconds"],
                        "revenue": revenue, "cost": cost, "penalty": penalty, "profit": profit}))
                    rows.append({"task_type": CASES[task_id % 5][0], "runtime": runtime,
                                 "quote": bids[task_id]["est_seconds"], "verdict": verdict,
                                 "price": bids[task_id]["price"], "cost": cost,
                                 "penalty": penalty, "profit": profit})
                await asyncio.sleep(.02)
            await asyncio.sleep(.05)
            assert len(agent.history) == len(rows)
            assert not agent._commitments and not agent._quotes and not agent._awarded
            assert math.isclose(agent.profit, sum(r["profit"] for r in rows))
            done.set_result(True)
        except Exception as error:
            if not done.done(): done.set_exception(error)

    async with serve(manager, "127.0.0.1", 0) as server:
        agent.url = f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"
        runner = asyncio.create_task(agent._main())
        try:
            await asyncio.wait_for(done, 45)
            await asyncio.wait_for(runner, 3)
        finally:
            runner.cancel()
            await asyncio.gather(runner, return_exceptions=True)
    return {"scenario": name, "injected_delay_per_delivery": delay,
            "deadline": deadline, "overlapping_awards": overlap, "jobs": rows,
            "total_profit_in_local_model": sum(r["profit"] for r in rows),
            "missed_deadlines": sum(r["verdict"] != "correct" for r in rows),
            "cleanup_and_graceful_stop": "passed"}


def main():
    calibration = make_agent("Calibration", "", auto_calibrate=False, verbose=False)
    calibration.calibrate_fast()
    rates = calibrate(verbose=False)
    expected = [run_task(kind, params) for kind, params in CASES]
    results = []
    for name, delay, overlap, deadline in [("steady", .03, False, 3),
            ("slower_delivery", .15, False, 3), ("overlapping_awards", .12, True, 3),
            ("unexpected_delay_spike", .7, True, 1.5)]:
        results.append(asyncio.run(scenario(name, calibration._fast, rates, expected, delay, overlap, deadline)))
    assert all(r["missed_deadlines"] == 0 for r in results[:3])
    assert results[-1]["missed_deadlines"] > 0  # A genuine adverse-condition test.
    print(json.dumps({"python": platform.python_version(), "scenarios": results,
        "source_sha256": hashlib.sha256(Path("contract-net/student/my_contractor.py").read_bytes()).hexdigest(),
        "limits": "One contractor, synthetic local accounting and transport delay; no competitors, tournament profit prediction, real network disconnects, or server timeout-before-INFORM handling."}, indent=2))


if __name__ == "__main__": main()
