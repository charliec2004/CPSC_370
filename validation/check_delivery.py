"""Offline delivery learning checks and chronological replay of saved logs."""
from dataclasses import replace
import hashlib
import json
import math
import platform
import statistics
from pathlib import Path
from prove_optimizations import make_agent, task_for, protocol_checks
from contractnet.client import Settlement, _Commitment


def observe(agent, task_id, overhead, queue=0, verdict="correct"):
    agent._quotes[task_id] = {"queue": queue, "task_type": "hash_search"}
    agent._measurements.append((task_id, 1., 1.))
    agent.on_settled(Settlement(task_id, "hash_search", verdict, 2, 1, 0, 1,
                               1 + overhead, 1.2))


def main():
    agent = make_agent("DeliveryCheck", "", pricing="competitive", auto_calibrate=False, verbose=False)
    agent.rates = {"monte_carlo_pi": 100, "hash_search": 1_000_000}
    for i, value in enumerate((.08, .1, .09, .11)):
        observe(agent, i, value)
        assert agent.quoted_overhead == agent._network_seconds
    observe(agent, 4, .30)
    assert math.isclose(agent.quoted_overhead, .156)
    assert math.isclose(agent._network_seconds, .32)
    task = task_for("monte_carlo_pi", {"seed": 1, "samples": 100})
    task = replace(task, deadline_s=30)
    bid = agent.on_cfp(task)
    quote = agent._quotes[task.task_id]
    assert math.isclose(bid.est_seconds, 1.156, abs_tol=.00011)
    assert math.isclose(quote["safe_finish"], 1.32, abs_tol=.00011)
    history = agent._overheads.copy()
    agent._overheads.clear()
    conservative = agent.on_cfp(task)
    assert bid.price == conservative.price and bid.est_seconds < conservative.est_seconds
    agent._overheads.extend(history)
    task = replace(task, deadline_s=1.2)
    assert agent.on_cfp(task) is None  # A smaller quote never relaxes admission.
    task = replace(task, deadline_s=30)
    agent.on_cfp(task)
    agent._commitments[task.task_id] = _Commitment(task, bid.est_seconds)
    assert math.isclose(agent.queue_seconds, 1.32)
    agent._commitments.clear()
    hash_task = task_for("hash_search", {"seed": 370, "threshold": 65536})
    hash_task = replace(hash_task, deadline_s=.45)
    assert agent.on_cfp(hash_task) is None  # Safety overhead still governs risk.
    before = list(agent._overheads)
    for i, value in enumerate((float("nan"), float("inf"), -.1), 100):
        observe(agent, i, value)
    observe(agent, 104, .9, queue=1)
    observe(agent, 105, .9, verdict="timeout")
    assert list(agent._overheads) == before
    for i in range(30): observe(agent, 200+i, .1)
    assert len(agent._overheads) == 20 and math.isclose(agent.quoted_overhead, .12)
    for mode in ("markup", "adaptive"):
        agent._pricing = mode
        assert agent.quoted_overhead == agent._network_seconds

    replay = []
    for run in json.loads(Path("validation/delivery_samples.json").read_text()):
        values = run["overhead_seconds"]
        model = make_agent("Replay", "", pricing="competitive", auto_calibrate=False, verbose=False)
        errors, predictions = [[], []], [[], []]
        underestimates = [0, 0]
        for i, value in enumerate(values):
            if i >= 5:
                old = max(.05, sorted(model._overheads)[math.ceil(.9*len(model._overheads))-1]+.02)
                for j, prediction in enumerate((old, model.quoted_overhead)):
                    errors[j].append(abs(value-prediction))
                    predictions[j].append(prediction)
                    underestimates[j] += value > prediction
            observe(model, i, value)  # Learn only after predicting this observation.
        replay.append({"log": run["log"], "log_sha256": run["log_sha256"],
                       "samples": len(values), "predictions": len(errors[0]),
                       "old_mean_absolute_error": statistics.mean(errors[0]),
                       "new_mean_absolute_error": statistics.mean(errors[1]),
                       "old_mean_quote": statistics.mean(predictions[0]),
                       "new_mean_quote": statistics.mean(predictions[1]),
                       "old_underestimates": underestimates[0], "new_underestimates": underestimates[1]})
    print(json.dumps({"python": platform.python_version(), "checks": "cold start, cost floor, deadline, hash risk, queue reservation, invalid/queued/failed observations, rolling window, legacy modes",
                      "replay": replay, "protocol": protocol_checks("competitive"),
                      "source_sha256": hashlib.sha256(Path("contract-net/student/my_contractor.py").read_bytes()).hexdigest(),
                      "limits": "Historical successful unqueued jobs only; no prediction of tournament profit or failure rates. New estimate may be exceeded more often; conservative admission is separate."}, indent=2))


if __name__ == "__main__": main()
