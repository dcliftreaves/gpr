"""ABBA isolated whole-codec modes on the two older downsampled controls."""
from pathlib import Path
import hashlib,json,os,statistics,subprocess,time
source=Path('/mnt/ssd/gpr_work/stock-preview-retention-20261030')
root=source/'legacy-control';root.mkdir(exist_ok=False)
seed=Path('/mnt/ssd/gpr_work/pi-mission1-writeback8-20261030')
launcher=Path('/mnt/ssd/gpr_work/stock-native12-gopro-20261030/launch_stock_policy_user.py')
raws=[Path('/mnt/ssd/gpr_work/artifacts/mission1_all42_4k_raw_pi20fps_20260624/frames')/name for name in ('GP017517.raw','GP017348.raw')]
executables=dict(baseline=source/'baseline/preview_retention_benchmark',candidate=source/'build/preview_retention_benchmark')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
save=lambda p,v:p.write_text(json.dumps(v,indent=2)+'\n')
protocol=dict(schema='gpr.stock_retention_legacy_control.v1',diagnostic_only=True,acceptance_timing=False,
    order=['baseline','candidate','candidate','baseline'],source_count=2,
    executables={k:dict(path=str(p),sha256=sha(p)) for k,p in executables.items()},
    inputs=[dict(raw=str(p),raw_sha256=sha(p),reference_sha256=sha(seed/f'reference-{i}.vc5')) for i,p in enumerate(raws)],
    driver_sha256=sha(Path(__file__)),scope='Older 50MP-downsampled controls, isolated none/retain/reconstruct modes only; no color rendering or capture durability; source metadata is not used by this codec-only benchmark')
save(root/'protocol.json',protocol)
receipt=dict(complete=False,protocol_sha256=sha(root/'protocol.json'),rows=[]);save(root/'receipt.json',receipt)
env={k:v for k,v in os.environ.items() if not k.startswith('GPR_')}
flags=['GPR_STREAM_UNPACK=1','GPR_BAND_STREAM=1','GPR_CHANNEL_ASM=1','GPR_PIN_CHANNELS=1','GPR_DIRECT_BANDS=1','GPR_COMPACT_BANDS=1']
for source_index,raw in enumerate(raws):
    for run,mode in enumerate(protocol['order']):
        name=f'{source_index}-{run}';launch=root/(name+'-launch.json')
        command=['sudo','-n','chrt','--fifo','1','/usr/bin/setpriv','--reuid=1000','--regid=1000','--init-groups','--reset-env',
            '/usr/bin/python3',str(launcher),str(launch),str(os.SCHED_FIFO),'/usr/bin/env',*flags,str(executables[mode]),str(raw),str(seed/f'reference-{source_index}.vc5')]
        with (root/(name+'.jsonl')).open('w') as out,(root/(name+'.stderr')).open('w') as err:
            child=subprocess.Popen(command,stdout=out,stderr=err,env=env);deadline=time.monotonic()+10
            while not launch.exists():
                assert child.poll() is None
                if time.monotonic()>deadline:raise TimeoutError('Missing startup report; inspect child before retry')
                time.sleep(.005)
            settings=json.loads(launch.read_text());pid=settings['pid'];status=(Path('/proc')/str(pid)/'status').read_text()
            observed=dict(uids=list(map(int,next(s.split()[1:] for s in status.splitlines() if s.startswith('Uid:')))),
                nice=os.getpriority(os.PRIO_PROCESS,pid),policy=os.sched_getscheduler(pid),priority=os.sched_getparam(pid).sched_priority,
                capabilities=next(s.split()[1] for s in status.splitlines() if s.startswith('CapEff:')))
            assert observed==dict(uids=[1000]*4,nice=0,policy=os.SCHED_FIFO,priority=1,capabilities='0000000000000000')
            save(root/(name+'-observed.json'),observed);assert child.wait(timeout=120)==0
        events=[json.loads(s) for s in (root/(name+'.jsonl')).read_text().splitlines()]
        assert len(events)==192 and all(r['all_payloads_exact_independent_stock'] for r in events)
        assert all(r['planes_exact_independent_decode'] for r in events if r['mode']=='reconstruct')
        modes={m:dict(median_ms=statistics.median(r['wall_s']*1000 for r in events if r['mode']==m and not r['warmup']),
                      block_median_ms=[statistics.median(r['wall_s']*1000 for r in events if r['mode']==m and r['block']==block and not r['warmup']) for block in sorted({r['block'] for r in events if r['mode']==m})]) for m in ('none','retain','reconstruct')}
        row=dict(source=source_index,run=run,mode=mode,command=command,launch=settings,observed=observed,modes=modes,
            payloads_verified=192,reconstructions_verified=64)
        receipt['rows'].append(row);save(root/'receipt.json',receipt)
        print(json.dumps(dict(source=source_index,run=run,mode=mode,modes=modes)),flush=True)
receipt['complete']=True;save(root/'receipt.json',receipt)
