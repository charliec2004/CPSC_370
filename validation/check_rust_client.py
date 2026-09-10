#!/usr/bin/env python3
"""Exercise the real Rust process over local WebSockets; never joins a class room.

Run with the project's Python 3.12 environment (websockets 15.0.1).
"""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import time

from websockets.asyncio.server import serve

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / "contract-net/rust/target/release/auctioneers"
spec = importlib.util.spec_from_file_location("reference", ROOT / "contract-net/student/contractnet/tasks.py")
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)
RULES = {"award_policy": "best_value", "time_weight": 2, "cost_rate": 1,
         "penalty_rate": 0.5, "late_credit": 0, "concurrency": 3}


def cfp(task_id, kind="prime_count", params=None, **overrides):
    return {"type": "CFP", "task_id": task_id, "task_type": kind,
            "params": params or {"lo": 2, "hi": 100}, "budget": 20,
            "deadline_s": 5, "bid_window_ms": 1000, "attempt": 1, **overrides}


async def send(socket, message):
    await socket.send(json.dumps(message))


async def receive(socket):
    while True:
        raw = await asyncio.wait_for(socket.recv(), 8)
        if raw == "ping":
            await socket.send("pong")
            continue
        return json.loads(raw)


async def register(socket, offers=(), rules=None):
    message = await receive(socket)
    assert message["type"] == "REGISTER", message
    assert message["name"] == "RustOfflineTest"
    assert message["token"] == "offline-test-token"
    await send(socket, {"type": "REGISTERED", "now": time.time() * 1000 + 3600000,
                        "rules": rules or RULES, "open_cfps": list(offers)})


async def award(socket, task_id, seconds=5):
    await send(socket, {"type": "ACCEPT_PROPOSAL", "task_id": task_id, "price": 1,
                        "due_at": time.time() * 1000 + 3600000 + seconds * 1000,
                        "deadline_s": 5})


async def settled(socket, task_id, verdict="correct"):
    await send(socket, {"type": "SETTLED", "task_id": task_id, "verdict": verdict,
                        "revenue": 1, "cost": .1, "penalty": 0, "profit": .9, "runtime": .1})


async def result(socket, offer):
    message = await receive(socket)
    expected = reference.run_task(offer["task_type"], offer["params"])
    assert message["type"] == "INFORM", message
    assert message["task_id"] == offer["task_id"], message
    assert message["result"] == str(expected), message
    assert message["runtime"] >= 0
    return message


class Process:
    async def start(self, port):
        self.lines = []
        self.process = await asyncio.create_subprocess_exec(
            str(BINARY), "run", "--name", "RustOfflineTest", "--url", f"ws://127.0.0.1:{port}/agent",
            "--env-file", os.devnull, "--token", "offline-test-token",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        self.reader = asyncio.create_task(self.read())

    async def read(self):
        async for line in self.process.stderr:
            decoded = line.decode()
            assert "offline-test-token" not in decoded, "token leaked to logs"
            self.lines.append(decoded)

    async def wait_log(self, text):
        async with asyncio.timeout(5):
            while not any(text in line for line in self.lines):
                await asyncio.sleep(.02)

    async def stop(self):
        if self.process.returncode is None:
            self.process.kill()
        await self.process.wait()
        await self.reader


async def lifecycle():
    connections = asyncio.Queue()
    release = asyncio.Event()

    async def handler(socket):
        await connections.put(socket)
        await release.wait()

    process = Process()
    async with serve(handler, "127.0.0.1", 0) as server:
        await process.start(server.sockets[0].getsockname()[1])
        try:
            socket = await asyncio.wait_for(connections.get(), 30)
            offers = [cfp(1, "sort_checksum", {"seed": 99, "n": 50000}),
                      cfp(2, "monte_carlo_pi", {"seed": 12345, "samples": 50000}),
                      cfp(3, "matmul_mod", {"seed": 2026, "n": 40, "mod": 1000003})]
            await register(socket, offers)
            bids = [await receive(socket) for _ in offers]
            assert [b["task_id"] for b in bids] == [1, 2, 3], bids
            assert all(b["type"] == "PROPOSE" and b["price"] >= .01 for b in bids)
            # Each offer reserves its compute and delivery time immediately.
            assert bids[1]["est_seconds"] > bids[0]["est_seconds"]
            assert bids[2]["est_seconds"] > bids[1]["est_seconds"]
            await socket.send("not json")
            await send(socket, {"type": "CFP", "task_id": 99, "params": []})
            assert (await receive(socket))["type"] == "REFUSE"
            for task_id in [1, 2, 3, 1, 2, 3]:
                await award(socket, task_id)
            for offer in offers:
                await result(socket, offer)
                if offer["task_id"] != 3:
                    await settled(socket, offer["task_id"])
            # Result was sent, but acknowledgement is lost. Re-register before replay.
            await socket.close()
            socket = await asyncio.wait_for(connections.get(), 10)
            await register(socket)
            await result(socket, offers[2])
            await settled(socket, 3)
            await send(socket, cfp(4, "hash_search", {"seed": "slow", "threshold": 1}, deadline_s=.01))
            assert (await receive(socket))["type"] == "REFUSE"
            await send(socket, cfp(5))
            assert (await receive(socket))["type"] == "PROPOSE"
            await send(socket, {"type": "REJECT_PROPOSAL", "task_id": 5})
            await send(socket, cfp(5, attempt=2))
            assert (await receive(socket))["type"] == "PROPOSE"
            await award(socket, 5, seconds=-1)
            failure = await receive(socket)
            assert failure["type"] == "FAILURE" and failure["task_id"] == 5, failure
            await settled(socket, 5, "failure")

            # Work awarded immediately before connection loss completes offline.
            more = [cfp(6, "sort_checksum", {"seed": 370, "n": 200000}),
                    cfp(7, "monte_carlo_pi", {"seed": 370, "samples": 500000})]
            for offer in more:
                await send(socket, offer)
                assert (await receive(socket))["type"] == "PROPOSE"
                await award(socket, offer["task_id"])
                await award(socket, offer["task_id"])
            await socket.close()
            socket = await asyncio.wait_for(connections.get(), 10)
            await register(socket)
            # Retained deliveries may arrive in map order, so compare by task id.
            delivered = [await receive(socket) for _ in more]
            assert sorted(m["task_id"] for m in delivered) == [6, 7], delivered
            for message in delivered:
                offer = next(o for o in more if o["task_id"] == message["task_id"])
                assert message["type"] == "INFORM", message
                assert message["result"] == str(reference.run_task(offer["task_type"], offer["params"]))
                await settled(socket, message["task_id"])

            # Ctrl+C preserves a pending bid, accepts its award, refuses new offers.
            final_offer = cfp(8)
            await send(socket, final_offer)
            assert (await receive(socket))["type"] == "PROPOSE"
            process.process.send_signal(signal.SIGINT)
            await process.wait_log("draining")
            await send(socket, cfp(9))
            assert (await receive(socket))["type"] == "REFUSE"
            await award(socket, 8)
            await result(socket, final_offer)
            await settled(socket, 8)
            assert await asyncio.wait_for(process.process.wait(), 5) == 0, process.lines
        finally:
            release.set()
            await process.stop()
    print("PASS: three concurrent offers, exact results, duplicate awards, retries, expired award, offline delivery, reconnect replay, graceful drain")


async def fatal(mode):
    process = Process()
    count = 0

    async def handler(socket):
        nonlocal count
        count += 1
        assert (await receive(socket))["type"] == "REGISTER"
        if mode == "bad_token":
            await send(socket, {"type": "ERROR", "code": "bad_token", "message": "private server detail"})
        else:
            await socket.close(code=4001, reason="replaced")
        await socket.wait_closed()

    async with serve(handler, "127.0.0.1", 0) as server:
        await process.start(server.sockets[0].getsockname()[1])
        try:
            assert await asyncio.wait_for(process.process.wait(), 30) == 1
            assert count == 1, count
            assert not any("private server detail" in line for line in process.lines)
        finally:
            await process.stop()
    print(f"PASS: {mode} stops without reconnect loop or sensitive error output")


async def main():
    await lifecycle()
    await fatal("bad_token")
    await fatal("duplicate_name")


if __name__ == "__main__":
    asyncio.run(main())
