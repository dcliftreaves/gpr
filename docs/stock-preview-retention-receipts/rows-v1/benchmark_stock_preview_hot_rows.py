"""Fixed in-process none/retain/reconstruct modes; isolated codec cost, not camera rate."""
from pathlib import Path
import hashlib,json,os,statistics,subprocess,time
source_root=Path('/mnt/ssd/gpr_work/stock-preview-retention-20261030')
root=source_root/'hot-row-control';root.mkdir(exist_ok=False)
seed=Path('/mnt/ssd/gpr_work/stock-native12-gopro-20261030')
exe=source_root/'build/preview_retention_benchmark'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
save=lambda p,v:p.write_text(json.dumps(v,indent=2)+'\n')
assert not (root/'protocol.json').exists()
source=json.loads((seed/'protocol.json').read_text())
protocol=dict(schema='gpr.stock_preview_retention_modes.v1',diagnostic_only=True,acceptance_timing=False,
    base='779bb47',binary_sha256=sha(exe),harness_sha256=sha(source_root/'tests/preview_retention_benchmark.cpp'),
    cmake_sha256=sha(source_root/'CMakeLists.txt'),driver_sha256=sha(Path(__file__)),source_protocol_sha256=sha(seed/'protocol.json'),
    sources={name:sha(source_root/name) for name in ('source/lib/vc5_encoder/encoder.c','source/lib/vc5_encoder/encoder.h','source/lib/vc5_decoder/inverse.c','source/lib/vc5_decoder/vc5_decoder.c')},
    order=['none','retain','reconstruct','reconstruct','retain','none','retain','none','reconstruct','none','reconstruct','retain'],
    blocks=12,iterations_per_block=16,warmup_excluded_per_block=1,encoder_arena_bytes=192<<20,
    source_count=2,quality=3,geometry=[4096,3072],cfa='RGGB',sample_bits=14,
    scope='All modes in one executable/process per source with fixed reused arenas; no rendering, queue, pacing or storage. Retain-only observes one coefficient per band; reconstruct matches three independent entropy-decoded planes. Not acceptance timing.')
save(root/'protocol.json',protocol)
receipt=dict(complete=False,protocol_sha256=sha(root/'protocol.json'),rows=[])
save(root/'receipt.json',receipt)
env={k:v for k,v in os.environ.items() if not k.startswith('GPR_')}
flags=['GPR_STREAM_UNPACK=1','GPR_BAND_STREAM=1','GPR_CHANNEL_ASM=1','GPR_PIN_CHANNELS=1','GPR_DIRECT_BANDS=1','GPR_COMPACT_BANDS=1']
for index,item in enumerate(source['inputs']):
    launch=root/f'{index}-launch.json'
    raw=seed/item['raw_file'];reference=seed/f'reference-{index}.vc5'
    assert sha(raw)==item['raw_sha256'] and sha(reference)==source['reference_payloads'][index]['sha256']
    command=['sudo','-n','chrt','--fifo','1','/usr/bin/setpriv','--reuid=1000','--regid=1000','--init-groups','--reset-env',
        '/usr/bin/python3',str(seed/'launch_stock_policy_user.py'),str(launch),str(os.SCHED_FIFO),'/usr/bin/env',*flags,str(exe),str(raw),str(reference)]
    with (root/f'{index}.jsonl').open('w') as out,(root/f'{index}.stderr').open('w') as err:
        child=subprocess.Popen(command,stdout=out,stderr=err,env=env);deadline=time.monotonic()+10
        while not launch.exists():
            assert child.poll() is None
            if time.monotonic()>deadline:raise TimeoutError('Missing launch record; inspect process before retry')
            time.sleep(.005)
        settings=json.loads(launch.read_text());pid=settings['pid'];status=(Path('/proc')/str(pid)/'status').read_text()
        observed=dict(uids=list(map(int,next(s.split()[1:] for s in status.splitlines() if s.startswith('Uid:')))),
            nice=os.getpriority(os.PRIO_PROCESS,pid),policy=os.sched_getscheduler(pid),priority=os.sched_getparam(pid).sched_priority,
            capabilities=next(s.split()[1] for s in status.splitlines() if s.startswith('CapEff:')))
        assert observed==dict(uids=[1000]*4,nice=0,policy=os.SCHED_FIFO,priority=1,capabilities='0000000000000000')
        save(root/f'{index}-observed.json',observed)
        assert child.wait(timeout=120)==0
    events=[json.loads(s) for s in (root/f'{index}.jsonl').read_text().splitlines()]
    assert len(events)==192
    for block,mode in enumerate(protocol['order']):
        rows=events[block*16:block*16+16]
        assert all(r['block']==block and r['iteration']==i and r['mode']==mode and r['warmup']==(i==0) for i,r in enumerate(rows))
        assert all(r['all_payloads_exact_independent_stock'] and (mode!='reconstruct' or r['planes_exact_independent_decode']) for r in rows)
    modes={}
    for mode in ('none','retain','reconstruct'):
        rows=[r for r in events if r['mode']==mode and not r['warmup']]
        modes[mode]=dict(iterations=len(rows),median_ms=statistics.median(r['wall_s']*1000 for r in rows),
            minimum_ms=min(r['wall_s']*1000 for r in rows),maximum_ms=max(r['wall_s']*1000 for r in rows),
            block_median_ms=[statistics.median(r['wall_s']*1000 for r in rows if r['block']==block) for block,m in enumerate(protocol['order']) if m==mode],
            callback_median_ms=statistics.median(r['callback_s']*1000 for r in rows),encoder_used_bytes=sorted(set(r['encoder_used'] for r in rows)))
    row=dict(source=index,command=command,launch=settings,observed=observed,modes=modes,all_payloads_exact_independent_stock=True,reconstructed_planes_exact_independent_decode=True)
    receipt['rows'].append(row);save(root/'receipt.json',receipt)
    print(json.dumps(row),flush=True)
receipt['complete']=True;save(root/'receipt.json',receipt)
