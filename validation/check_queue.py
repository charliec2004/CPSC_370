"""Replay overlapping CFPs through the SDK and verify incremental reservations."""
import asyncio
import json
import math
from pathlib import Path
from unittest.mock import patch
from prove_optimizations import make_agent


def main():
    agent = make_agent('QueueCheck', '', auto_calibrate=False, verbose=False)
    agent.rates = {'monte_carlo_pi': 100}
    async def run():
        sent=[]
        async def capture(message): sent.append(message)
        agent._send=capture
        for task_id in (1,2,3):
            await agent._handle_cfp({'task_id':task_id,'task_type':'monte_carlo_pi',
                'params':{'seed':1,'samples':100},'budget':100,'deadline_s':30})
        estimates=[m['est_seconds'] for m in sent]
        assert all(math.isclose(a,b,abs_tol=.0001) for a,b in zip(estimates,[1.12,2.24,3.36])),estimates
        assert math.isclose(agent.queue_seconds,3.36)
        # A quoted deadline includes predecessors; it must not be summed again.
        for c in agent._commitments.values(): assert c.started_at is None
        agent._commitments[1].started_at=100
        agent._running=(1,100,1)
        with patch('my_contractor.time.perf_counter',return_value=100.5):
            assert math.isclose(agent.queue_seconds,2.86)
        with patch('my_contractor.time.perf_counter',return_value=101.01):
            assert math.isinf(agent.queue_seconds)
        # A server timeout can release the contract while local CPU work remains.
        agent._commitments.pop(1)
        with patch('my_contractor.time.perf_counter',return_value=100.5):
            assert math.isclose(agent.queue_seconds,2.74)
        agent._running=None
        await agent._dispatch({'type':'REJECT_PROPOSAL','task_id':2,'winner':'Peer','winning_price':1})
        assert math.isclose(agent.queue_seconds,1.12)
        # Missing detail uses the full SDK reservation as a conservative fallback.
        agent._quotes.pop(3)
        assert math.isclose(agent.queue_seconds,estimates[2])
        # An auction can close between registration replay and PROPOSE arrival.
        await agent._dispatch({'type':'ERROR','code':'bidding_closed',
            'message':'task 3 is not accepting proposals'})
        assert 3 not in agent._commitments
        assert agent.queue_seconds==0
        await agent._handle_cfp({'task_id':4,'task_type':'monte_carlo_pi',
            'params':{'seed':1,'samples':100},'budget':100,'deadline_s':30})
        await agent._dispatch({'type':'ERROR','code':'bidding_closed','message':'unspecified task'})
        assert 4 in agent._commitments
        agent._awarded.add(4)
        await agent._dispatch({'type':'ERROR','code':'bidding_closed','task_id':4})
        assert 4 in agent._commitments
        agent._awarded.remove(4)
        await agent._dispatch({'type':'ERROR','code':'bidding_closed','task_id':4})
        assert agent.queue_seconds==0 and 4 not in agent._quotes
        return {'wire_estimates':estimates,'incremental_queue':3.36,
          'checks':['three overlapping CFPs','partial running work','overrun refusal',
                    'timed-out computation remains reserved','rejection releases reservation','missing quote fallback','closed auction clears only identified unawarded bids'],
          'limitation':'Deterministic SDK event replay, not live concurrent-server timing.'}
    result=asyncio.run(run())
    Path('validation/queue_checks.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
