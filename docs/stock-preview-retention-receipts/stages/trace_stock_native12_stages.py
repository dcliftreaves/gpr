"""Four fixed stage diagnostics using the previously hash-verified instrumented build."""
from pathlib import Path
import hashlib,json,os,statistics,subprocess,sys,time
repo=Path('/mnt/ssd/gpr_work/stock-raw-media-runtime')
seed=Path('/mnt/ssd/gpr_work/stock-native12-gopro-20261030')
root=Path('/mnt/ssd/gpr_work/stock-native12-stages-20261030');root.mkdir(exist_ok=False)
sys.path.insert(0,str(repo/'tools'))
import benchmark_mission1 as bench
import stock_video
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
save=lambda p,v:p.write_text(json.dumps(v,indent=2)+'\n')
source=json.loads((seed/'protocol.json').read_text())
exe=Path('/mnt/ssd/gpr_work/stock-scheduler-trace-prototype-20261030/build-diagnostic/gpr_capture_app')
assert sha(exe)=='ec7b0c9fc508bfcfca35513e6c4ee493e823a05a627005f3a7887873a40cd491'
assert sha(repo/'build-runtime/gpr_capture_app')==source['binaries']['capture']['sha256']
metadata=[stock_video.decode_metadata((seed/i['metadata_file']).read_bytes()) for i in source['inputs']]
payloads=[i['sha256'] for i in source['reference_payloads']]
offline={r['index']:r for r in map(json.loads,(seed/'offline.jsonl').read_text().splitlines()) if r['event']=='preview'}
base=source['command_template'].copy();base[0]=str(exe);base[base.index('--frames')+1]='120'
protocol=dict(schema='gpr.stock_native12_stages.v1',diagnostic_only=True,acceptance_timing=False,
    frames=120,repeat_count=4,source_protocol_sha256=sha(seed/'protocol.json'),binary_sha256=sha(exe),
    prior_instrumentation='docs/stock-scheduler-receipts/diagnostic.patch on cade228; kernel-trace/protocol.json binds exact executable',
    command_template=base,driver_sha256=sha(Path(__file__)),
    diagnostic_environment=dict(GPR_PROFILE='1',GPR_CHANNEL_BALANCE='1'),
    scope='Logging/timestamps add overhead; no kernel sampling collector; capture UID1000 cap0 nice0 FIFO1. Four fixed repeats, no selection/restart by observed speed. Not acceptance timing.')
save(root/'protocol.json',protocol)
receipt=dict(complete=False,diagnostic_only=True,acceptance_timing=False,protocol_sha256=sha(root/'protocol.json'),rows=[])
save(root/'receipt.json',receipt)
environment={k:v for k,v in os.environ.items() if not k.startswith('GPR_')}
def summarize(rows):
    keys=('encode_ms','worker_wall_ms','worker_cpu_ms','worker_wall_minus_cpu_ms','join_tail_ms','reconstruction_callback_ms','cleanup_ms','render_ms')
    return dict(frames=len(rows),metrics={k:dict(median=statistics.median(r[k] for r in rows),maximum=max(r[k] for r in rows)) for k in keys},
                critical_channels={str(c):sum(r['critical_channel']==c for r in rows) for c in range(4)})
for index in range(4):
    command=base.copy();clip=root/f'{index}.gvid';launch=root/f'{index}-launch.json';command[command.index('--output')+1]=str(clip)
    invocation=['sudo','-n','chrt','--fifo','1','/usr/bin/setpriv','--reuid=1000','--regid=1000','--init-groups','--reset-env',
                '/usr/bin/python3',str(seed/'launch_stock_policy_user.py'),str(launch),str(os.SCHED_FIFO),
                '/usr/bin/env','GPR_PROFILE=1','GPR_CHANNEL_BALANCE=1']+command
    with (root/f'{index}.jsonl').open('w') as out,(root/f'{index}.stderr').open('w') as err:
        child=subprocess.Popen(invocation,stdout=out,stderr=err,env=environment);deadline=time.monotonic()+10
        while not launch.exists():
            assert child.poll() is None
            if time.monotonic()>deadline:raise TimeoutError('Missing startup receipt; inspect existing child before retry')
            time.sleep(.005)
        settings=json.loads(launch.read_text());pid=settings['pid'];status=(Path('/proc')/str(pid)/'status').read_text()
        observed=dict(uids=list(map(int,next(s.split()[1:] for s in status.splitlines() if s.startswith('Uid:')))),
            nice=os.getpriority(os.PRIO_PROCESS,pid),policy=os.sched_getscheduler(pid),priority=os.sched_getparam(pid).sched_priority,
            capabilities=next(s.split()[1] for s in status.splitlines() if s.startswith('CapEff:')))
        assert observed==dict(uids=[1000]*4,nice=0,policy=os.SCHED_FIFO,priority=1,capabilities='0000000000000000')
        assert not settings['gpr_environment'];save(root/f'{index}-observed.json',observed)
        assert child.wait(timeout=120)==0
    events=[json.loads(s) for s in (root/f'{index}.jsonl').read_text().splitlines() if s.startswith('{')]
    verified=bench.verify(clip,events,metadata,payloads,offline)
    traces=[];pending={};workers=[]
    for line in (root/f'{index}.stderr').read_text().splitlines():
        if line.startswith('balance '):workers.append({k:float(v) for k,v in (w.split('=') for w in line.split()[1:])})
        elif line.startswith(('unpack_wall=','encoding_end_wall=','after_preview_wall=','after_cleanup_wall=')):
            k,v=line.split('=');assert k not in pending;pending[k]=float(v)
        elif line.startswith('capture_diag '):
            row={k:int(v) for k,v in (w.split('=') for w in line.split()[1:])}
            assert row['clock_ok']==1 and row['error']==0 and len(workers)==4
            assert [int(w['channel']) for w in workers]==[0,1,2,3] and all(w['error']==0 for w in workers)
            assert set(pending)=={'unpack_wall','encoding_end_wall','after_preview_wall','after_cleanup_wall'}
            assert 0<=pending['unpack_wall']<=pending['encoding_end_wall']<=pending['after_preview_wall']<=pending['after_cleanup_wall']
            row.update(pending);row['workers']=workers;traces.append(row);pending={};workers=[]
    assert not pending and not workers and len(traces)==verified['frames_verified']
    frames={r['index']:r for r in events if r['event']=='frame'};previews={r['index']:r for r in events if r['event']=='preview'};correlation=[]
    for t in traces:
        i=t['frame'];frame=frames[i];preview=previews[i];w=max(t['workers'],key=lambda w:w['finish'])
        assert abs(t['wall_ns']/1e6-frame['encode_ms'])<.001
        correlation.append(dict(index=i,source=preview['source_index'],encode_ms=frame['encode_ms'],
            worker_wall_ms=w['wall']*1000,worker_cpu_ms=w['cpu']*1000,worker_wall_minus_cpu_ms=(w['wall']-w['cpu'])*1000,
            critical_channel=int(w['channel']),join_tail_ms=(w['joined']-w['finish'])*1000,
            reconstruction_callback_ms=(t['after_preview_wall']-t['encoding_end_wall'])*1000,
            cleanup_ms=(t['after_cleanup_wall']-t['after_preview_wall'])*1000,render_ms=preview['render_ms'],
            main_cpu_ms=t['cpu_ns']/1e6,main_wall_minus_cpu_ms=(t['wall_ns']-t['cpu_ns'])/1e6,
            capture_to_written_ms=frame['capture_to_written_ms'],capture_to_sink_ms=preview['capture_to_sink_ms']))
    save(root/f'{index}-traces.json',traces);save(root/f'{index}-correlation.json',correlation)
    row=dict(index=index,command=invocation,launch=settings,observed=observed,verified=verified,summary=summarize(correlation),
        sources={str(source):summarize([r for r in correlation if r['source']==source]) for source in range(2)})
    receipt['rows'].append(row);save(root/'receipt.json',receipt)
    print(json.dumps(dict(index=index,frames=verified['frames_verified'],summary=row['summary'],sources=row['sources'])),flush=True)
receipt['complete']=True;save(root/'receipt.json',receipt)
