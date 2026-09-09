"""Exact Monte Carlo comparisons, rounding boundaries, calibration and fallback."""
import hashlib
import json
import math
import platform
import random
import statistics
import time
from pathlib import Path
from unittest.mock import patch
from prove_optimizations import make_agent, task_for
import my_contractor as implementation
from contractnet.tasks import run_task


def main():
    assert implementation._np is not None, 'Install requirements-accelerated.txt to validate the accelerated path'
    rng=random.Random(3702026)
    cases=[{'samples':n,'seed':seed} for n in (0,1,2,17,1000) for seed in (-2**63,-1,0,1,2**63)]
    cases += [{'samples':rng.randrange(5000),'seed':rng.randrange(-2**63,2**63)} for _ in range(80)]
    cases += [{'samples':n,'seed':370} for n in (65535,65536,65537,131071,131072,131073)]
    executor=implementation.MyContractor.__new__(implementation.MyContractor)
    for p in cases:
        expected=run_task('monte_carlo_pi',p)
        assert executor.execute(task_for('monte_carlo_pi',p))==expected,p
        with patch.object(implementation,'_np',None):
            assert implementation.monte_carlo_fast(p)==expected,p
        if p['samples']>5000:time.sleep(.15)
    # Values around the circle exercise the exact <= boundary and float rounding.
    points=[(0.,1.),(1.,0.),(.6,.8),(.5,.5),(0.,0.)]
    for x in (.1,.3,.5,.7,.9):
        y=math.sqrt(1-x*x)
        points.extend((x,z) for z in (math.nextafter(y,0),y,math.nextafter(y,math.inf)))
    values=[v for point in points for v in point]
    class Draws:
        def __init__(self):self.calls=0
        def random(self):
            value=values[self.calls%len(values)];self.calls+=1;return value
    count=65537
    expected=sum(x*x+y*y<=1.0 for x,y in (points[i%len(points)] for i in range(count)))
    for numpy_backend in (implementation._np,None):
        draws=Draws()
        with patch.object(implementation.random,'Random',return_value=draws),patch.object(implementation,'_np',numpy_backend):
            assert implementation.monte_carlo_fast({'samples':count,'seed':1})==expected
        assert draws.calls==2*count
    for p in ({'samples':True,'seed':1},{'samples':50_000_001,'seed':1},{'samples':1,'seed':'1'}):
        try:implementation.monte_carlo_fast(p)
        except ValueError:pass
        else:raise AssertionError('Unsupported input accepted')
    agent=make_agent('MonCheck','',auto_calibrate=False,verbose=False)
    # Measure only the changed backend, leaving live practice connected.
    coefficients=[]
    for n in (100000,500000):
        times=[]
        for _ in range(3):
            started=time.perf_counter();implementation.monte_carlo_fast({'samples':n,'seed':370})
            times.append(time.perf_counter()-started);time.sleep(.15)
        coefficients.append(statistics.median(times)/n)
    agent._fast['monte']=max(coefficients)
    rows=[]
    for n in (173003,617003,2_000_003):
        p={'samples':n,'seed':20260910};task=task_for('monte_carlo_pi',p)
        bid=agent.on_cfp(task);timings=[[],[]]
        for trial in range(3):
            answers={}
            for index in ([0,1] if trial%2==0 else [1,0]):
                started=time.perf_counter()
                answers[index]=run_task('monte_carlo_pi',p) if index==0 else agent.execute(task)
                timings[index].append(time.perf_counter()-started)
                time.sleep(.15)
            assert answers[0]==answers[1]
        reference,candidate=map(statistics.median,timings)
        assert candidate<bid.est_seconds,(n,candidate,bid)
        rows.append({'samples':n,'reference_seconds':reference,'candidate_seconds':candidate,
            'speedup':reference/candidate,'quoted_delivery':bid.est_seconds})
    result={'python':platform.python_version(),'numpy':implementation._np.__version__,
        'seeded_cases_both_backends':len(cases),'boundary_checks':'circle boundary, adjacent floats, chunk boundary, exactly two draws per point',
        'resource_guards':3,'benchmarks':rows,'source_sha256':hashlib.sha256(Path('contract-net/student/my_contractor.py').read_bytes()).hexdigest(),
        'limits':'Low-priority measurements while practice remains online; OS scheduling and competing work affect timings. No guarantee of beating another machine.'}
    Path('validation/monte_checks.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
