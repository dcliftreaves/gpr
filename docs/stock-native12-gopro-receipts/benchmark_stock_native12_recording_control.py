"""Two fixed recording-only controls after the completed native GoPro preview repeats."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,time
repo=Path('/mnt/ssd/gpr_work/stock-raw-media-runtime')
seed=Path('/mnt/ssd/gpr_work/stock-native12-gopro-20261030')
root=seed/'recording-control'
root.mkdir(exist_ok=False)
sys.path.insert(0,str(repo/'tools'))
import benchmark_mission1 as bench
import stock_video
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
save=lambda p,v:p.write_text(json.dumps(v,indent=2)+'\n')
previous=json.loads((seed/'receipt.json').read_text());assert previous['complete']
source=json.loads((seed/'protocol.json').read_text())
command=source['command_template'][:source['command_template'].index('--preview-every')]
assert command[-1]=='--paced'
metadata=[stock_video.decode_metadata((seed/i['metadata_file']).read_bytes()) for i in source['inputs']]
expected=[r['sha256'] for r in source['reference_payloads']]
assert sha(Path(command[0]))==source['binaries']['capture']['sha256']
protocol=dict(schema='gpr.stock_native12_recording_control.v1',repeat_count=2,
    scope='Recording only; same native inputs, encoder, 600 attempts at 20fps, FIFO1 UID1000/nice0/cap0, writeback1MiB/final fsync; no camera preview',
    source_protocol_sha256=sha(seed/'protocol.json'),source_receipt_sha256=sha(seed/'receipt.json'),
    driver_sha256=sha(Path(__file__)),launcher_sha256=sha(seed/'launch_stock_policy_user.py'),
    command_template=command)
save(root/'protocol.json',protocol)
receipt=dict(complete=False,protocol_sha256=sha(root/'protocol.json'),rows=[])
save(root/'receipt.json',receipt)
environment={k:v for k,v in os.environ.items() if not k.startswith('GPR_')}
for index in range(2):
    clip=root/f'{index}.gvid';launch=root/f'{index}-launch.json'
    capture=command.copy();capture[capture.index('--output')+1]=str(clip)
    invocation=['sudo','-n','chrt','--fifo','1','/usr/bin/setpriv','--reuid=1000','--regid=1000','--init-groups','--reset-env',
                '/usr/bin/python3',str(seed/'launch_stock_policy_user.py'),str(launch),str(os.SCHED_FIFO)]+capture
    with (root/f'{index}.jsonl').open('w') as out,(root/f'{index}.stderr').open('w') as err:
        process=subprocess.Popen(invocation,stdout=out,stderr=err,env=environment)
        deadline=time.monotonic()+10
        while not launch.exists():
            assert process.poll() is None
            if time.monotonic()>deadline:raise TimeoutError('Missing startup report; do not restart capture')
            time.sleep(.005)
        settings=json.loads(launch.read_text());pid=settings['pid']
        status=(Path('/proc')/str(pid)/'status').read_text()
        observed=dict(uids=list(map(int,next(s.split()[1:] for s in status.splitlines() if s.startswith('Uid:')))),
            nice=os.getpriority(os.PRIO_PROCESS,pid),policy=os.sched_getscheduler(pid),priority=os.sched_getparam(pid).sched_priority,
            capabilities=next(s.split()[1] for s in status.splitlines() if s.startswith('CapEff:')))
        assert observed==dict(uids=[1000]*4,nice=0,policy=os.SCHED_FIFO,priority=1,capabilities='0000000000000000')
        assert not settings['gpr_environment']
        save(root/f'{index}-observed.json',observed)
        assert process.wait(timeout=300)==0
    events=[json.loads(s) for s in (root/f'{index}.jsonl').read_text().splitlines() if s.startswith('{')]
    verified=bench.verify(clip,events,metadata,expected)
    assert verified['preview'] is None
    receipt['rows'].append(dict(index=index,command=invocation,launch=settings,observed=observed,verified=verified))
    save(root/'receipt.json',receipt)
    print(json.dumps(dict(index=index,frames=verified['frames_verified'],capture=verified['capture'],floor=verified['floor'])),flush=True)
receipt['complete']=True
receipt['all_recording_floors_passed']=all(r['verified']['floor']['recording'] for r in receipt['rows'])
save(root/'receipt.json',receipt)
