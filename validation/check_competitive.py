"""Exact sorting, risk accounting, competitive feedback, and SDK integration."""
import hashlib
import json
import math
import random
import statistics
import time
from pathlib import Path
from prove_optimizations import make_agent, task_for, protocol_checks, lifecycle_checks, bidding_checks
from my_contractor import MyContractor, sort_fast, hash_success_probability
from contractnet import Settlement
from contractnet.tasks import run_task


def main():
    rng = random.Random(3700910)
    cases = [{'n': n, 'seed': seed} for n in (0, 1, 2, 31, 1000) for seed in (-2**63, -1, 0, 1, 2**63)]
    cases += [{'n': rng.randrange(5000), 'seed': rng.randrange(-2**63, 2**63)} for _ in range(200)]
    executor = MyContractor.__new__(MyContractor)
    for params in cases:
        assert executor.execute(task_for('sort_checksum', params)) == run_task('sort_checksum', params)
    for params in ({'n': True, 'seed': 1}, {'n': 5_000_001, 'seed': 1}, {'n': 1, 'seed': '1'}):
        try: sort_fast(params)
        except ValueError: pass
        else: raise AssertionError('Unsupported sort accepted')
    assert hash_success_probability(2**31, 2, 1) == .5
    assert hash_success_probability(2**31, 2, 2) == .75
    assert hash_success_probability(2**32, 1, 1) == 1
    assert hash_success_probability(2**32, 1, .99) == 0
    assert hash_success_probability(1, 1, 0) == 0
    assert .95 < hash_success_probability(1, 1, 3) < .951
    agent = make_agent('Check', '', auto_calibrate=False, verbose=False, pricing='competitive')
    agent.rates = {'hash_search': 2**32 / 10000, 'monte_carlo_pi': 100}
    h = lambda deadline, budget=10: task_for('hash_search', {'seed': 370, 'threshold': 10000}, deadline=deadline, budget=budget)
    assert agent.on_cfp(h(2)) is None
    tight = agent.on_cfp(h(3.2)); q = agent._quotes[1]
    assert tight is not None and q['model_success_probability'] >= .95
    assert q['baseline_price'] > round(tight.est_seconds * 1.28, 4)
    assert tight.price*q['model_success_probability'] - tight.est_seconds - (1-q['model_success_probability'])*5 > 0
    assert agent.on_cfp(h(5)).price < tight.price
    assert agent.on_cfp(h(3.2, 1.5)) is None
    task = task_for('monte_carlo_pi', {'samples': 100, 'seed': 1}, budget=10)
    bids=[]
    for _ in range(3):
        bids.append(agent.on_cfp(task).price)
        agent.on_reject(1, 'Peer', 1)
    assert bids[0] > bids[1] > bids[2]
    assert agent._price_shares[task.task_type] == .25**4
    before = agent._price_shares[task.task_type]
    for i in range(2):
        agent.on_cfp(task)
        agent.on_settled(Settlement(1, task.task_type, 'correct', 2, 1, 0, 1, 1, 1))
        assert agent._price_shares[task.task_type] == before + (.05 if i else 0)
    agent.on_cfp(task)
    agent.on_settled(Settlement(1, task.task_type, 'timeout', 0, 2, 5, -7, 2, 1))
    assert agent._price_wins[task.task_type] == 0
    assert 'hash_search' not in agent._price_shares
    agent.calibrate_fast()
    holdouts=[]
    benchmarks=[]
    for n in (37000, 173000, 617000, 1_700_003):
        params={'n': n, 'seed': 20260910}
        task=task_for('sort_checksum', params)
        bid=agent.on_cfp(task)
        timings=[[],[]]
        for trial in range(3):
            answers={}
            for index in ([0,1] if trial%2==0 else [1,0]):
                start=time.perf_counter()
                answers[index]=run_task('sort_checksum',params) if index==0 else agent.execute(task)
                timings[index].append(time.perf_counter()-start)
            assert answers[0]==answers[1]
        medians=[statistics.median(t) for t in timings]
        assert medians[1] < bid.est_seconds
        holdouts.append({'n':n,'measured_compute':medians[1],'quoted_delivery':bid.est_seconds})
        benchmarks.append({'n':n,'reference_seconds':medians[0],'candidate_seconds':medians[1],'speedup':medians[0]/medians[1]})
    result={'sort_reference_cases':len(cases), 'risk_checks':'geometric boundary cases, 95% admission, failure-adjusted price, budget refusal',
        'feedback_checks':'multiplicative reduction, two-win increase, failed-delivery reset, per-type isolation',
        'baseline_checks':bidding_checks(),'lifecycle':lifecycle_checks(),
        'competitive_protocol':protocol_checks('competitive'),'sort_holdouts':holdouts,'sort_benchmarks':benchmarks,
        'source_sha256':hashlib.sha256(Path('contract-net/student/my_contractor.py').read_bytes()).hexdigest(),
        'limits':'Finite exact-answer checks and local timing samples; hash probability assumes calibrated independent uniform hashing; no proof of tournament optimality.'}
    Path('validation/competitive_checks.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
