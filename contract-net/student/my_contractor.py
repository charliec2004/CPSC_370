"""
CPSC 370, Assignment 1: your Contract Net contractor.

Exact optimized matrix and prime executors, calibrated timing, and a 28%
markup over predicted billed time. The SDK remains unchanged.

    python my_contractor.py --name Team_07 --url wss://contractnet.example.com/agent

Everything you need is on `self`:

    self.estimate(task)   predicted seconds for this task on this machine
    self.queue_seconds    seconds of work you are already committed to
    self.rules            the manager's published scoring rules
    self.history          every Settlement you have received so far
    self.profit           your running profit

And on `task`:

    task.task_type        "monte_carlo_pi", "prime_count", "hash_search",
                          "sort_checksum", or "matmul_mod"
    task.params           the parameters for this instance
    task.budget           the most the manager will pay; higher bids are void
    task.deadline_s       seconds you get, measured from the moment you win
    task.work             a proportional estimate of how much work this is
"""

from __future__ import annotations

import argparse
import asyncio
from collections import deque
import json
import math
import os
import random
import signal
import statistics
import threading
import time
from pathlib import Path

from contractnet import Bid, Contractor, Task


def matrix_parameters(params):
    n, mod, seed = (params[k] for k in ("n", "mod", "seed"))
    if (any(type(v) is not int for v in (n, mod, seed))
            or not 0 <= n <= 2048 or not 1 <= mod < 2**64
            or seed.bit_length() > 64):
        raise ValueError("Unsupported matrix parameters")
    return n, mod, seed


def matrix_checksum(params):
    """Sum(A B) = dot(column_sums(A), row_sums(B)), modulo m."""
    n, mod, seed = matrix_parameters(params)
    rng = random.Random(seed)
    columns = [0] * n
    # Preserve every random draw and the reference's row-major draw order.
    for _ in range(n):
        for k in range(n):
            columns[k] += rng.randrange(mod)
    total = 0
    for k in range(n):
        total += columns[k] * sum(rng.randrange(mod) for _ in range(n))
    return total % mod


def prime_parameters(params):
    lo, hi = params["lo"], params["hi"]
    if type(lo) is not int or type(hi) is not int:
        raise ValueError("Prime bounds must be integers")
    lo = max(lo, 2)
    if hi > 10**12 or hi - lo > 10_000_000:
        raise ValueError("Prime range exceeds resource bounds")
    return lo, hi


def prime_sieve(params):
    """Count primes in bounded segments, marking multiples of base primes."""
    lo, hi = prime_parameters(params)
    if hi <= lo:
        return 0
    limit = math.isqrt(hi - 1)
    base = bytearray(b"\x01") * (limit + 1)
    base[:2] = b"\x00\x00"
    for p in range(2, math.isqrt(limit) + 1):
        if base[p]:
            base[p*p:limit+1:p] = b"\x00" * ((limit-p*p)//p+1)
    primes = [p for p in range(2, limit+1) if base[p]]
    count = 0
    for start in range(lo, hi, 262144):
        stop = min(start+262144, hi)
        segment = bytearray(b"\x01") * (stop-start)
        for p in primes:
            first = max(p*p, ((start+p-1)//p)*p)
            if first < stop:
                segment[first-start:stop-start:p] = b"\x00" * ((stop-1-first)//p+1)
        count += segment.count(1)
    return count


class MyContractor(Contractor):
    """Exact fast executors, measured delivery estimates, and a 28% markup."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._fast = {}
        self._bias = {}
        self._overheads = deque(maxlen=20)
        self._network_seconds = 0.12  # Initial allowance; learn from settlements.
        self._quotes = {}
        self._awarded = set()
        self._measurements = deque(maxlen=128)
        self._timing_lock = threading.Lock()
        self._running = None
        self._draining = False
        self._stop_requested = None

    async def _main(self) -> None:
        # Python 3.9 requires constructing this queue on the running event loop.
        self._queue = asyncio.Queue()
        self._stop_requested = asyncio.Event()
        if self._auto_calibrate:
            self.calibrate_fast()
        runner = asyncio.create_task(super()._main())
        drainer = asyncio.create_task(self._drain(runner))
        loop = asyncio.get_running_loop()
        handlers = {}
        if self._auto_calibrate and threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGINT, signal.SIGTERM):
                previous = signal.getsignal(sig)
                try:
                    loop.add_signal_handler(sig, self.request_stop)
                except (NotImplementedError, RuntimeError):
                    continue
                handlers[sig] = previous
        try:
            await runner
        except asyncio.CancelledError:
            if not self._draining:
                raise
        finally:
            drainer.cancel()
            for sig, previous in handlers.items():
                loop.remove_signal_handler(sig)
                signal.signal(sig, previous)

    def request_stop(self):
        self._draining = True
        self._log("stopping after outstanding bids and awarded work settle")
        if self._stop_requested is not None:
            self._stop_requested.set()

    async def _drain(self, runner):
        await self._stop_requested.wait()
        while self._commitments or self._running is not None:
            await asyncio.sleep(0.05)
        runner.cancel()

    async def _dispatch(self, message):
        if message.get("type") == "ACCEPT_PROPOSAL":
            task_id = message["task_id"]
            if task_id in self._awarded:
                return  # A replay must not enqueue the same work twice.
            if task_id in self._commitments:
                self._awarded.add(task_id)
        await super()._dispatch(message)
        if message.get("type") == "SETTLED":
            self._awarded.discard(message["task_id"])

    def on_registered(self):
        # Reconnection invalidates pending bids, but awarded work must survive.
        # The SDK replays currently open CFPs after calling this hook.
        for task_id in list(self._commitments):
            if task_id not in self._awarded:
                self._commitments.pop(task_id)
                self._quotes.pop(task_id, None)

    def calibrate_fast(self):
        """Measure our actual algorithms, before connecting or accepting work.

        Matrix coefficients use n squared, with small/large modulus buckets.
        The prime envelope covers base-prime generation/segment setup plus
        interval marking. Maxima across representative cases are conservative.
        """
        def measure(fn, params, repeats=3):
            times = []
            for _ in range(repeats):
                started = time.perf_counter()
                fn(params)
                times.append(time.perf_counter() - started)
            return statistics.median(times)

        fast = {}
        for bucket, mods in ((32, (1000003, 2**20)), (64, (2**63-1, 2**63))):
            coefficients = [measure(matrix_checksum, {"n": n, "mod": mod, "seed": 370}) / n**2
                            for n in (96, 192) for mod in mods]
            fast["matrix" + str(bucket)] = max(coefficients)
        setup = []
        for hi in (2_000_000, 100_000_000, 10**12):
            elapsed = measure(prime_sieve, {"lo": hi-1, "hi": hi})
            setup.append(elapsed / (2 * math.isqrt(hi-1)))
        fast["prime_setup"] = max(setup)
        marking = []
        for lo, width in ((2_000_000, 262144), (10_000_000, 786432), (10**9, 262144)):
            elapsed = measure(prime_sieve, {"lo": lo, "hi": lo+width})
            marking.append(elapsed / width)
        fast["prime_marking"] = max(marking)
        self._fast = fast
        self._log("fast executor calibration complete (matrix n²; segmented prime sieve)")

    def _base_estimate(self, task):
        if task.task_type == "matmul_mod":
            n, mod, _ = matrix_parameters(task.params)
            coefficient = self._fast.get("matrix32" if mod.bit_length() <= 32 else "matrix64")
            return 0.0005 + n*n*coefficient if coefficient is not None else float("inf")
        if task.task_type == "prime_count":
            lo, hi = prime_parameters(task.params)
            if not self._fast:
                return float("inf")
            if hi <= lo:
                return 0.0005
            width = hi-lo
            segments = (width+262143)//262144
            setup = self._fast["prime_setup"] * math.isqrt(hi-1) * (1+segments)
            marking = self._fast["prime_marking"] * width
            return 0.0005 + setup + marking
        return super().estimate(task)

    def estimate(self, task):
        return self._base_estimate(task) * self._bias.get(task.task_type, 1.0)

    @property
    def queue_seconds(self):
        total = super().queue_seconds
        with self._timing_lock:
            running = self._running
        if running is not None:
            task_id, started, predicted = running
            remaining = predicted - (time.perf_counter() - started)
            # Once current work overruns its estimate, don't promise new jobs
            # based on the SDK's clamped-to-zero remaining time.
            if remaining <= 0:
                return float("inf")
            if task_id not in self._commitments:
                total += remaining  # Timed-out work may still be computing.
        return total

    def _supported(self, task):
        p = task.params
        if task.task_type == "matmul_mod":
            matrix_parameters(p)
        elif task.task_type == "prime_count":
            prime_parameters(p)
        elif task.task_type in ("monte_carlo_pi", "sort_checksum"):
            key, maximum = ("samples", 50_000_000) if task.task_type == "monte_carlo_pi" else ("n", 5_000_000)
            if (type(p[key]) is not int or not 0 <= p[key] <= maximum
                    or type(p["seed"]) is not int or p["seed"].bit_length() > 64):
                return False
        elif task.task_type == "hash_search":
            if (type(p["threshold"]) is not int or not 1 <= p["threshold"] <= 2**32
                    or type(p["seed"]) not in (str, int) or len(str(p["seed"])) > 128):
                return False
        else:
            return False
        return True

    def on_cfp(self, task: Task) -> Bid | None:
        if self._draining:
            return None
        try:
            if not self._supported(task):
                return None
            if any(not math.isfinite(v) or v <= 0 for v in (task.budget, task.deadline_s)):
                return None
            if not math.isfinite(self.rules.cost_rate) or self.rules.cost_rate < 0:
                return None
            compute = self.estimate(task)
            queue = self.queue_seconds
            finish = queue + compute + self._network_seconds
            if not math.isfinite(finish) or finish > task.deadline_s:
                return None
            # Match wire precision without rounding a promise down or sending
            # a bid that becomes invalid only after SDK serialization.
            finish = math.ceil(finish * 10000) / 10000
            if finish > task.deadline_s:
                return None
            # Keep 1.28, but charge for the whole predicted billed interval:
            # waiting, computation, worker scheduling, and delivery overhead.
            price = round(finish * self.rules.cost_rate * 1.28, 4)
            if not math.isfinite(price) or price > task.budget:
                return None
        except (KeyError, TypeError, ValueError, OverflowError):
            return None
        self._quotes[task.task_id] = {"task_type": task.task_type, "compute": compute,
            "queue": queue, "overhead": self._network_seconds, "estimate": finish,
            "price": price, "budget": task.budget}
        self._log("BID " + json.dumps({"task_id": task.task_id, **self._quotes[task.task_id]}))
        return Bid(price=price, est_seconds=finish)

    def execute(self, task: Task) -> int:
        # verify.py constructs the executor via __new__, so pure computation
        # must also work without networking/calibration/observation state.
        tracking = hasattr(self, "_timing_lock")
        if tracking:
            predicted = self.estimate(task)
            base_estimate = self._base_estimate(task)
            started = time.perf_counter()
            with self._timing_lock:
                self._running = (task.task_id, started, predicted)
        try:
            if task.task_type == "matmul_mod":
                result = matrix_checksum(task.params)
            elif task.task_type == "prime_count":
                result = prime_sieve(task.params)
            else:
                result = super().execute(task)
            if tracking:
                duration = time.perf_counter() - started
                with self._timing_lock:
                    self._measurements.append((task.task_id, duration, base_estimate))
            return result
        finally:
            if tracking:
                with self._timing_lock:
                    self._running = None

    def on_reject(self, task_id, winner, price):
        self._quotes.pop(task_id, None)

    def on_bid_invalid(self, task_id, reason):
        self._quotes.pop(task_id, None)

    def on_settled(self, settlement):
        quote = self._quotes.pop(settlement.task_id, None)
        with self._timing_lock:
            measurement = next((v for v in reversed(self._measurements)
                                if v[0] == settlement.task_id), None)
            self._measurements = deque((v for v in self._measurements
                if v[0] != settlement.task_id), maxlen=128)
        if quote and measurement and settlement.verdict == "correct":
            _, duration, base = measurement
            if math.isfinite(base) and base > 0 and settlement.task_type != "hash_search":
                old = self._bias.get(settlement.task_type, 1.0)
                # Compare compute time with the raw model, not an already
                # corrected quote. Hash variance must not distort throughput.
                ratio = min(4.0, max(0.5, duration/base))
                self._bias[settlement.task_type] = old*0.8 + ratio*0.2
            if quote["queue"] == 0 and settlement.runtime is not None:
                self._overheads.append(max(0, settlement.runtime-duration))
                if len(self._overheads) >= 3:
                    ordered = sorted(self._overheads)
                    self._network_seconds = max(0.05, ordered[math.ceil(0.9*len(ordered))-1] + 0.02)
        self._log("MEASUREMENT " + json.dumps({"task_id": settlement.task_id,
            "task_type": settlement.task_type, "verdict": settlement.verdict,
            "runtime": settlement.runtime, "estimate": settlement.est_seconds,
            "compute_seconds": measurement[1] if measurement else None,
            "revenue": settlement.revenue, "cost": settlement.cost,
            "penalty": settlement.penalty, "profit": settlement.profit,
            "delivery_allowance": self._network_seconds}))


def class_token() -> str | None:
    """Read CLASS_TOKEN from the environment, then the .env beside this file.

    The local file supports plain or quoted KEY=value lines and full-line
    comments. Values are literal: no shell commands or variable expansion.
    """
    if "CLASS_TOKEN" in os.environ:
        return os.environ["CLASS_TOKEN"] or None
    try:
        lines = Path(__file__).with_name(".env").read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if key.strip() != "CLASS_TOKEN":
            continue
        if not separator:
            raise ValueError("CLASS_TOKEN in .env must use KEY=value format")
        value = value.strip()
        if value.startswith(("'", '"')):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError("CLASS_TOKEN in .env has unmatched quotes")
            value = value[1:-1]
        return value or None
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="CPSC 370 Contract Net contractor")
    parser.add_argument("--name", required=True, help="your team name, e.g. Team_07")
    parser.add_argument("--url", required=True, help="wss://.../agent")
    parser.add_argument("--token", default=None, help="override CLASS_TOKEN from the environment or .env")
    parser.add_argument("--machine", default=None, help="label shown on the leaderboard")
    args = parser.parse_args()

    try:
        token = args.token if args.token is not None else class_token()
    except (OSError, UnicodeError, ValueError):
        parser.error("Could not load CLASS_TOKEN; check the local .env file format and permissions.")

    MyContractor(
        name=args.name,
        url=args.url,
        token=token,
        machine=args.machine,
    ).run()


if __name__ == "__main__":
    main()
