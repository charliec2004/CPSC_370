"""Check configuration without connecting to any room."""
import contextlib,io,json,os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'contract-net/student'))
import my_contractor as agent

def main():
 with tempfile.TemporaryDirectory() as directory:
  env=Path(directory)/'.env'
  env.write_text('CLASS_TOKEN=dummy-test-token\nINSTRUCTOR_TOURNAMENT_WEBSOCKET_URL=\n')
  with patch.object(agent,'__file__',str(Path(directory)/'my_contractor.py')),patch.dict(os.environ,{},clear=True):
   def launch(args,expected=None):
    with patch.object(sys,'argv',['my_contractor.py','--name','Auctioneers']+args),patch.object(agent,'MyContractor') as constructor:
     with contextlib.redirect_stderr(io.StringIO()):
      if expected is None:
       try:agent.main()
       except SystemExit as err:assert err.code==2
       else:raise AssertionError('Invalid launch accepted')
       constructor.assert_not_called()
      else:
       agent.main();assert constructor.call_args.kwargs['url']==expected
       assert constructor.call_args.kwargs['token']=='dummy-test-token'
       assert 'machine' not in constructor.call_args.kwargs
       constructor.return_value.run.assert_called_once()
   launch([])
   launch(['--practice'],'wss://contractnet.blackdial.workers.dev/agent?room=practice')
   launch(['--url','wss://example.invalid/agent'],'wss://example.invalid/agent')
   launch(['--url','https://example.invalid'])
   launch(['--practice','--url','wss://example.invalid'])
   env.write_text('CLASS_TOKEN=dummy-test-token\nINSTRUCTOR_TOURNAMENT_WEBSOCKET_URL="wss://example.invalid/agent?room=class"\n')
   launch([],'wss://example.invalid/agent?room=class')
   with patch.dict(os.environ,{'INSTRUCTOR_TOURNAMENT_WEBSOCKET_URL':'wss://environment.invalid'}):
    launch([],'wss://environment.invalid')
    launch(['--url','wss://explicit.invalid'],'wss://explicit.invalid')
    launch(['--practice'],'wss://contractnet.blackdial.workers.dev/agent?room=practice')
 result={'checks':9,'result':'passed','network_connections':0}
 Path('validation/launch_checks.json').write_text(json.dumps(result,indent=2)+'\n');print(result)
if __name__=='__main__':main()
