"""Fixed two-repeat native-geometry GoPro replay; references prepared before timing."""
from pathlib import Path
import hashlib
import json
import os
import platform
import subprocess
import sys
import time

repo = Path('/mnt/ssd/gpr_work/stock-raw-media-runtime')
root = Path('/mnt/ssd/gpr_work/stock-native12-gopro-20261030')
sys.path.insert(0, str(repo/'tools'))
import benchmark_mission1 as bench
import raw_media
import stock_preview
import stock_video

def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()

def save(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n')

assert not (root/'protocol.json').exists(), 'Never restart an existing protocol'
manifest = json.loads((root/'inputs.json').read_text())
environment = {k:v for k,v in os.environ.items() if not k.startswith('GPR_')}
executables = dict(capture=repo/'build-runtime/gpr_capture_app',
                  compiler=repo/'build-runtime/gpr_preview_profile',
                  player=repo/'build-runtime/gpr_preview_app',
                  reference=Path('/mnt/ssd/gpr_work/stock-architecture-reference/build/source/app/vc5_encoder_app/vc5_encoder_app'))
hashes = {key:sha(path) for key,path in executables.items()}
assert hashes['capture']=='c576f5662ac605cc5719ae536308e9ff71cdcec4f4e714343a5a919a5711687c'
assert hashes['reference']=='05b1fac320aa772c14cc9812d9715684c997d1c4eb32027baa561edbb828117a'
metadata = []
expected = []
base = [str(executables['capture']), '--width','4096','--height','3072',
        '--cfa','RGGB','--sample-bits','14','--quality','3','--fps-num','20',
        '--fps-den','1','--queue','4','--workspace-mib','192','--leased','--writeback-mib','1']
for index,item in enumerate(manifest['inputs']):
    raw = root/item['raw_file']; meta = root/item['metadata_file']
    assert raw.stat().st_size==4096*3072*2 and sha(raw)==item['raw_sha256']
    assert sha(meta)==item['metadata_sha256']
    calibration = stock_video.decode_metadata(meta.read_bytes())
    raw_media.validate(calibration, dict(width=4096,height=3072,sample_bits=14,bayer='RGGB'))
    metadata.append(calibration)
    reference = root/f'reference-{index}.vc5'
    bench.run([executables['reference'],'-i',raw,'-o',reference,'-w',4096,'-h',3072,'-p',8192],
              root/f'reference-{index}.log',dict(environment,GPR_BENCH_QUALITY='3'))
    expected.append(sha(reference))
    base += ['--input',str(raw),'--source-metadata',str(meta)]
seed = root/'sources.gvid'
events = bench.run(base+['--output',seed,'--frames',2,'--submit-timeout-ms',10000],root/'sources.jsonl',environment)
seed_verified = bench.verify(seed,events,metadata,expected)
profiles = root/'profiles'
stock_preview.prepare(seed,profiles,executables['compiler'],4)
events = bench.run([executables['player'],'--input',seed,'--profile-dir',profiles],root/'offline.jsonl',environment)
offline = {row['index']:row for row in events if row['event']=='preview'}
assert set(offline)=={0,1}
command = base+['--output','REPLACE_OUTPUT','--frames','600','--paced','--preview-every','1',
               '--preview-from-encoder','--preview-sync-stages','--preview-foreground']
for index in range(2):
    command += ['--preview-profile',str(profiles/f'{index:06}.gprp')]
protocol = dict(schema='gpr.stock_native12_gopro_timing.v1',
    published_revision='3a52439bebdd93d86a6233c1e0258d8f1004015c',
    scope='Native 12MP geometry, supplied camera GPR SDK-decoded counts; already compressed source, file-backed warm-cache replay, memory CRC sink; not sensor/DMA or physical display qualification',
    frames=600,repeat_count=2,quality=3,fps=20,policy='SCHED_FIFO',priority=1,nice=0,
    uid=1000,capabilities=0,writeback_mib=1,final_fsync=True,
    realtime_runtime_us=Path('/proc/sys/kernel/sched_rt_runtime_us').read_text().strip(),
    realtime_period_us=Path('/proc/sys/kernel/sched_rt_period_us').read_text().strip(),
    platform=platform.platform(),inputs=manifest['inputs'],binaries={k:dict(path=str(p),sha256=hashes[k]) for k,p in executables.items()},
    driver_sha256=sha(Path(__file__)),launcher_sha256=sha(root/'launch_stock_policy_user.py'),
    verifier_sources={name:sha(repo/'tools'/name) for name in ('benchmark_mission1.py','raw_media.py','stock_video.py','stock_preview.py','stock_still.py')},
    reference_payloads=[dict(sha256=expected[i],bytes=(root/f'reference-{i}.vc5').stat().st_size) for i in range(2)],
    profile_sha256=[sha(profiles/f'{i:06}.gprp') for i in range(2)],offline_sha256=sha(root/'offline.jsonl'),
    seed_verified=seed_verified,command_template=command)
save(root/'protocol.json',protocol)
receipt = dict(complete=False,protocol_sha256=sha(root/'protocol.json'),rows=[])
save(root/'receipt.json',receipt)
print('Prepared independent references and offline previews; starting fixed repeats',flush=True)
for index in range(2):
    assert all(sha(p)==hashes[k] for k,p in executables.items())
    clip = root/f'{index}.gvid'; launch = root/f'{index}-launch.json'
    capture = command.copy(); capture[capture.index('--output')+1]=str(clip)
    invocation = ['sudo','-n','chrt','--fifo','1','/usr/bin/setpriv','--reuid=1000','--regid=1000',
                  '--init-groups','--reset-env','/usr/bin/python3',str(root/'launch_stock_policy_user.py'),
                  str(launch),str(os.SCHED_FIFO)]+capture
    with (root/f'{index}.jsonl').open('w') as out,(root/f'{index}.stderr').open('w') as err:
        process = subprocess.Popen(invocation,stdout=out,stderr=err,env=environment)
        deadline = time.monotonic()+10
        while not launch.exists():
            assert process.poll() is None, ('failed before launch',process.returncode)
            if time.monotonic()>deadline:
                raise TimeoutError('Missing launch receipt; do not restart capture')
            time.sleep(.005)
        settings = json.loads(launch.read_text()); pid = settings['pid']
        status = (Path('/proc')/str(pid)/'status').read_text()
        uids = list(map(int,next(s.split()[1:] for s in status.splitlines() if s.startswith('Uid:'))))
        observed = dict(uids=uids,nice=os.getpriority(os.PRIO_PROCESS,pid),policy=os.sched_getscheduler(pid),
                        priority=os.sched_getparam(pid).sched_priority,
                        capabilities=next(s.split()[1] for s in status.splitlines() if s.startswith('CapEff:')))
        assert observed==dict(uids=[1000]*4,nice=0,policy=os.SCHED_FIFO,priority=1,capabilities='0000000000000000')
        assert not settings['gpr_environment']
        save(root/f'{index}-observed.json',observed)
        assert process.wait(timeout=300)==0
    events = [json.loads(s) for s in (root/f'{index}.jsonl').read_text().splitlines() if s.startswith('{')]
    verified = bench.verify(clip,events,metadata,expected,offline)
    assert verified['preview']['background_requested']==0
    previews = [e for e in events if e['event']=='preview']
    per_source = {str(i):dict(delivered=sum(e['source_index']==i for e in previews),
        late=sum(e['source_index']==i and e['capture_to_sink_ms']>50 for e in previews),
        maximum_capture_to_sink_ms=max(e['capture_to_sink_ms'] for e in previews if e['source_index']==i)) for i in range(2)}
    row = dict(index=index,command=invocation,launch=settings,observed=observed,verified=verified,per_source_preview=per_source)
    receipt['rows'].append(row); save(root/'receipt.json',receipt)
    print(json.dumps(dict(index=index,frames=verified['frames_verified'],durable_fps=verified['capture']['durable_fps'],
                         encode_median_ms=verified['capture']['encode_median_ms'],floor=verified['floor'],per_source_preview=per_source)),flush=True)
receipt['complete']=True
receipt['all_fixed_repeats_passed']=all(r['verified']['floor']['recording'] and r['verified']['floor']['preview'] for r in receipt['rows'])
save(root/'receipt.json',receipt)
