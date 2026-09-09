"""Deterministic pricing boundaries, feedback, and actual SDK integration."""
import hashlib
import json
from pathlib import Path
import sys

from prove_optimizations import make_agent, task_for, bidding_checks, lifecycle_checks, protocol_checks
from contractnet.client import Settlement


def main():
    agent = make_agent("PricingCheck", "", auto_calibrate=False, verbose=False, pricing="adaptive")
    agent.rates = {"monte_carlo_pi": 100}
    params = {"seed": 1, "samples": 100}
    task = task_for("monte_carlo_pi", params, budget=10)
    bid = agent.on_cfp(task)
    floor = agent._quotes[1]["baseline_price"]
    assert bid.price == round(floor + .5*(10-floor), 4)
    agent.on_reject(1, "OtherTeam", 2)
    assert agent._price_shares[task.task_type] == .4
    assert agent.on_cfp(task).price < bid.price
    agent.on_settled(Settlement(1, task.task_type, "correct", 5, 1, 0, 4, 1, bid.est_seconds))
    assert agent._price_shares[task.task_type] == .45
    agent.on_cfp(task)
    agent.on_settled(Settlement(1, task.task_type, "timeout", 0, 10, 5, -15, 10, bid.est_seconds))
    assert agent._price_shares[task.task_type] == .45
    for winner, price in ((None, None), ("PricingCheck", 1), ("OtherTeam", float("nan"))):
        agent.on_cfp(task)
        agent.on_reject(1, winner, price)
        assert agent._price_shares[task.task_type] == .45
    for _ in range(30):
        agent.on_cfp(task)
        agent.on_reject(1, "OtherTeam", 1)
    assert agent._price_shares[task.task_type] == 0
    for _ in range(30):
        agent.on_cfp(task)
        agent.on_settled(Settlement(1, task.task_type, "correct", 5, 1, 0, 4, 1, bid.est_seconds))
    assert agent._price_shares[task.task_type] == .95
    assert "sort_checksum" not in agent._price_shares
    checks = 0
    for share in (0, .1, .5, .95):
        agent._price_shares[task.task_type] = share
        for budget in (.01, floor-.00001, floor, floor+.00001, 2, 10.123456, 100):
            candidate = agent.on_cfp(task_for(task.task_type, params, budget=budget))
            if candidate is None:
                assert budget < floor
            else:
                assert floor <= candidate.price <= budget
                assert candidate.price == round(candidate.price, 4)
                assert candidate.est_seconds == bid.est_seconds
            checks += 1
    results = {"python": sys.version, "price_boundary_cases": checks,
        "feedback": "decrease on loss; increase on correct delivery; bounded and per task type",
        "baseline_checks": bidding_checks(), "lifecycle": lifecycle_checks(),
        "adaptive_protocol": protocol_checks("adaptive"),
        "production_source_sha256": hashlib.sha256(Path("contract-net/student/my_contractor.py").read_bytes()).hexdigest(),
        "limitations": "Checks behavior and delivery, not optimality or competitive profit."}
    Path("validation/pricing_checks.json").write_text(json.dumps(results, indent=2)+"\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
