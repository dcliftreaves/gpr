"""Fixed native-input ABBA comparison; unprofiled children, verification after each."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,time
repo=Path('/mnt/ssd/gpr_work/stock-raw-media-runtime')
prototype=Path('/mnt/ssd/gpr_work/stock-horizontal-inverse-20261030')
seed=Path('/mnt/ssd/gpr_work/stock-native12-gopro-20261030')
root=prototype/'capture-abba';root.mkdir(exist_ok=False)
sys.path.insert(0,str(repo/'tools'))
import benchmark_mission1 as bench
import stock_video
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
save=lambda p,v:p.write_text(json.dumps(v,indent=2)+'\n')
source=json.loads((seed/'protocol.json').read_text());assert json.loads((seed/'receipt.json').read_text())['complete']
base=source['command_template']
executables=dict(baseline=repo/'build-runtime/gpr_capture_app',candidate=prototype/'build/gpr_capture_app')
hashes={k:sha(p) for k,p in executables.items()}
assert hashes==dict(baseline='c576f5662ac605cc5719ae536308e9ff71cdcec4f4e714343a5a919a5711687c',candidate='8cd50cc2ac9432fad179954274e688a383d4b1123648c36db77147aafc5b3dc6')
metadata=[stock_video.decode_metadata((seed/i['metadata_file']).read_bytes()) for i in source['inputs']]
payloads=[i['sha256'] for i in source['reference_payloads']]
offline={r['index']:r for r in map(json.loads,(seed/'offline.jsonl').read_text().splitlines()) if r['event']=='preview'}
protocol=dict(schema='gpr.stock_horizontal_native_abba.v1',order=['baseline','candidate','candidate','baseline'],
    frames=600,fps=20,quality=3,source_protocol_sha256=sha(seed/'protocol.json'),
    command_template=base,binaries={k:dict(path=str(p),sha256=hashes[k]) for k,p in executables.items()},
    driver_sha256=sha(Path(__file__)),launcher_sha256=sha(seed/'launch_stock_policy_user.py'),
    candidate_source_sha256=sha(prototype/'source/lib/vc5_decoder/inverse.c'),
    scope='Unprofiled fixed native12 GoPro combined capture/preview ABBA; same UID1000/cap0 FIFO1 nice0, leased Q3, serialized foreground preview, SSD1MiB writeback/final fsync. No other Pi build/test/profiler during measured children.')
save(root/'protocol.json',protocol)
receipt=dict(complete=False,protocol_sha256=sha(root/'protocol.json'),rows=[])
save(root/'receipt.json',receipt)
environment={k:v for k,v in os.environ.items() if not k.startswith('GPR_')}
for index,mode in enumerate(protocol['order']):
    assert all(sha(p)==hashes[k] for k,p in executables.items())
    command=base.copy();command[0]=str(executables[mode]);clip=root/f'{index}.gvid';launch=root/f'{index}-launch.json'
    command[command.index('--output')+1]=str(clip)
    invocation=['sudo','-n','chrt','--fifo','1','/usr/bin/setpriv','--reuid=1000','--regid=1000','--init-groups','--reset-env',
                '/usr/bin/python3',str(seed/'launch_stock_policy_user.py'),str(launch),str(os.SCHED_FIFO)]+command
    with (root/f'{index}.jsonl').open('w') as out,(root/f'{index}.stderr').open('w') as err:
        child=subprocess.Popen(invocation,stdout=out,stderr=err,env=environment)
        deadline=time.monotonic()+10
        while not launch.exists():
            assert child.poll() is None,('failed before launch',child.returncode)
            if time.monotonic()>deadline:raise TimeoutError('Missing launch receipt; inspect process before retry')
            time.sleep(.005)
        settings=json.loads(launch.read_text());pid=settings['pid'];status=(Path('/proc')/str(pid)/'status').read_text()
        observed=dict(uids=list(map(int,next(s.split()[1:] for s in status.splitlines() if s.startswith('Uid:')))),
            nice=os.getpriority(os.PRIO_PROCESS,pid),policy=os.sched_getscheduler(pid),priority=os.sched_getparam(pid).sched_priority,
            capabilities=next(s.split()[1] for s in status.splitlines() if s.startswith('CapEff:')))
        assert observed==dict(uids=[1000]*4,nice=0,policy=os.SCHED_FIFO,priority=1,capabilities='0000000000000000')
        assert not settings['gpr_environment'];save(root/f'{index}-observed.json',observed)
        assert child.wait(timeout=300)==0
    events=[json.loads(s) for s in (root/f'{index}.jsonl').read_text().splitlines() if s.startswith('{')]
    verified=bench.verify(clip,events,metadata,payloads,offline)
    row=dict(index=index,mode=mode,command=invocation,launch=settings,observed=observed,verified=verified)
    receipt['rows'].append(row);save(root/'receipt.json',receipt)
    print(json.dumps(dict(index=index,mode=mode,frames=verified['frames_verified'],durable_fps=verified['capture']['durable_fps'],
        encode_median_ms=verified['capture']['encode_median_ms'],render_median_ms=verified['preview']['render_median_ms'],
        deadline_misses=verified['capture']['deadline_misses'],floor=verified['floor'])),flush=True)
receipt['complete']=True;save(root/'receipt.json',receipt)
