"""One offline timing sample using the actual contractor; emits JSON."""
import hashlib,json,platform,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'contract-net/student'))
from my_contractor import MyContractor
from contractnet import Task
from verify import GOLDEN
import numpy
agent=MyContractor.__new__(MyContractor)
for kind,params,answer in GOLDEN:
 assert agent.execute(Task(1,kind,params,100,30,1000,1))==answer
cases=[('monte_carlo_pi',{'seed':370,'samples':2_000_000}),('sort_checksum',{'seed':370,'n':500_000}),
       ('matmul_mod',{'seed':370,'n':260,'mod':1000003}),('prime_count',{'lo':2_000_000,'hi':2_250_000}),
       ('hash_search',next(p for k,p,a in GOLDEN if k=='hash_search'))]
rows=[]
for kind,params in cases:
 start=time.perf_counter();answer=agent.execute(Task(2,kind,params,100,30,1000,1));elapsed=time.perf_counter()-start
 rows.append({'task_type':kind,'params':params,'answer':str(answer),'seconds':elapsed})
print(json.dumps({'python':platform.python_version(),'machine':platform.machine(),'numpy':numpy.__version__,
 'executable':sys.executable,'rows':rows,'source_sha256':hashlib.sha256((ROOT/'contract-net/student/my_contractor.py').read_bytes()).hexdigest()}))
