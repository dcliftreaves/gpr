"""Diagnostic-only sampled user-cycle profile; never an acceptance timing run."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,time
repo=Path('/mnt/ssd/gpr_work/stock-raw-media-runtime')
seed=Path('/mnt/ssd/gpr_work/stock-native12-gopro-20261030')
root=Path('/mnt/ssd/gpr_work/stock-native12-profile-20261030');root.mkdir(exist_ok=False)
sys.path.insert(0,str(repo/'tools'))
import benchmark_mission1 as bench
import stock_video
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
save=lambda p,v:p.write_text(json.dumps(v,indent=2)+'\n')
source=json.loads((seed/'protocol.json').read_text())
assert json.loads((seed/'receipt.json').read_text())['complete']
command=source['command_template'].copy()
command[command.index('--frames')+1]='120'
command[command.index('--output')+1]=str(root/'profile.gvid')
assert sha(Path(command[0]))==source['binaries']['capture']['sha256']
launch=root/'launch.json'
invocation=['sudo','-n','perf','record','-e','cycles:u','-F','499','--call-graph','dwarf,8192',
            '-o',str(root/'perf.data'),'--','chrt','--fifo','1','/usr/bin/setpriv','--reuid=1000','--regid=1000',
            '--init-groups','--reset-env','/usr/bin/python3',str(seed/'launch_stock_policy_user.py'),str(launch),str(os.SCHED_FIFO)]+command
protocol=dict(schema='gpr.stock_native12_preview_profile.v1',diagnostic_only=True,acceptance_timing=False,
    source_protocol_sha256=sha(seed/'protocol.json'),binary_sha256=sha(Path(command[0])),
    driver_sha256=sha(Path(__file__)),command=invocation,
    note='Root user-cycle sampling collector; capture drops to UID1000/cap0/FIFO1 before exec. Profiled timing is not acceptance evidence.')
save(root/'protocol.json',protocol)
environment={k:v for k,v in os.environ.items() if not k.startswith('GPR_')}
with (root/'capture.jsonl').open('w') as out,(root/'perf.stderr').open('w') as err:
    process=subprocess.Popen(invocation,stdout=out,stderr=err,env=environment)
    deadline=time.monotonic()+10
    while not launch.exists():
        assert process.poll() is None,('failed before capture launch',process.returncode)
        if time.monotonic()>deadline:raise TimeoutError('No launch receipt; inspect existing process before retry')
        time.sleep(.005)
    settings=json.loads(launch.read_text());pid=settings['pid']
    status=(Path('/proc')/str(pid)/'status').read_text()
    observed=dict(uids=list(map(int,next(s.split()[1:] for s in status.splitlines() if s.startswith('Uid:')))),
        policy=os.sched_getscheduler(pid),nice=os.getpriority(os.PRIO_PROCESS,pid),priority=os.sched_getparam(pid).sched_priority,
        capabilities=next(s.split()[1] for s in status.splitlines() if s.startswith('CapEff:')))
    assert observed==dict(uids=[1000]*4,policy=os.SCHED_FIFO,nice=0,priority=1,capabilities='0000000000000000')
    save(root/'observed.json',observed)
    result=process.wait(timeout=120)
    assert result==0,result
subprocess.run(['sudo','-n','chown','1000:1000',str(root/'perf.data')],check=True)
metadata=[stock_video.decode_metadata((seed/item['metadata_file']).read_bytes()) for item in source['inputs']]
payloads=[item['sha256'] for item in source['reference_payloads']]
offline={r['index']:r for r in map(json.loads,(seed/'offline.jsonl').read_text().splitlines()) if r['event']=='preview'}
events=[json.loads(s) for s in (root/'capture.jsonl').read_text().splitlines() if s.startswith('{')]
verified=bench.verify(root/'profile.gvid',events,metadata,payloads,offline)
for name,args in [('flat.txt',['--no-children','--sort','symbol','--percent-limit','0.4']),
                  ('callgraph.txt',['--children','--sort','symbol','--percent-limit','1'])]:
    with (root/name).open('w') as out,(root/(name+'.stderr')).open('w') as err:
        subprocess.run(['perf','report','--stdio','-i',str(root/'perf.data'),*args],stdout=out,stderr=err,check=True)
receipt=dict(complete=True,diagnostic_only=True,acceptance_timing=False,protocol_sha256=sha(root/'protocol.json'),
    launch=settings,observed=observed,verified=verified,perf_sha256=sha(root/'perf.data'),perf_bytes=(root/'perf.data').stat().st_size)
save(root/'receipt.json',receipt)
print(json.dumps(dict(complete=True,diagnostic_only=True,frames_verified=verified['frames_verified'],previews_verified=verified['previews_verified'],perf_bytes=receipt['perf_bytes'])),flush=True)
