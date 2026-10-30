import contextlib
import signal
import atexit
import hashlib
import json
import os
from pathlib import Path
import resource
import statistics
import subprocess
import sys
import time

repo = Path('/mnt/ssd/gpr_work/stock-raw-media-runtime')
sys.path.insert(0, str(repo/'tools'))
import benchmark_mission1 as bench

root = Path('/mnt/ssd/gpr_work/pi-mission1-background-control-20261030')
root.mkdir()
seed = Path('/mnt/ssd/gpr_work/pi-mission1-writeback8-20261030')
inputs = json.loads((seed/'receipt.json').read_text())['inputs']
command = json.loads(Path('/mnt/ssd/gpr_work/pi-mission1-writeback1-perf-20261030/command.json').read_text())['command']
command.remove('--preview-foreground')
metadata = [json.loads(Path(command[i+1]).read_text()) for i,x in enumerate(command) if x == '--source-metadata']
payloads = [row['reference_payload_sha256'] for row in inputs]
offline = {row['index']: row for row in map(json.loads, (seed/'offline.jsonl').read_text().splitlines()) if row['event'] == 'preview'}
binary_hash = hashlib.sha256(Path(command[0]).read_bytes()).hexdigest()
def state():
    result = {}
    for name,path in [('temp','/sys/class/thermal/thermal_zone0/temp'),('clock','/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq'),('governor','/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor')]:
        result[name] = Path(path).read_text().strip()
    return result

def process(pid):
    text=Path('/proc')/str(pid)
    fields=(text/'stat').read_text().rsplit(')',1)[1].split()
    return dict(pid=pid,state=fields[0],ppid=int(fields[1]),start_ticks=int(fields[19]),
        cpu_ticks=int(fields[11])+int(fields[12]),command=(text/'cmdline').read_bytes().replace(b'\0',b' ').decode().strip())
def fully_stopped(pid):
    tasks=list((Path('/proc')/str(pid)/'task').glob('*/stat'))
    return bool(tasks) and all(path.read_text().rsplit(')',1)[1].split()[0] in ['T','t'] for path in tasks)
identities=[process(433759),process(433804)]
assert 'mission1_stream_source_encoder.py' in identities[0]['command']
assert 'labs_encoder_bench_cli' in identities[1]['command'] and identities[1]['ppid']==identities[0]['pid']
assert all(row['state'] not in ['T','t'] for row in identities)
fds={row['pid']:os.pidfd_open(row['pid']) for row in identities}
paused_here=[]
def resume():
    errors=[]
    for pid in list(reversed(paused_here)):
        try:signal.pidfd_send_signal(fds[pid],signal.SIGCONT)
        except ProcessLookupError:pass
        except BaseException as error:errors.append(error);continue
        paused_here.remove(pid)
    if errors:raise errors[0]
atexit.register(resume)
def interrupt(signum,frame):raise KeyboardInterrupt('signal '+str(signum))
for signum in [signal.SIGTERM,signal.SIGHUP,signal.SIGINT]:signal.signal(signum,interrupt)
@contextlib.contextmanager
def process_control(enabled):
    rows=[dict(before=process(row['pid'])) for row in identities]
    assert all(row['before']['start_ticks']==original['start_ticks'] for row,original in zip(rows,identities))
    try:
        if enabled:
            for row in rows:
                pid=row['before']['pid'];signal.pidfd_send_signal(fds[pid],signal.SIGSTOP);paused_here.append(pid)
            deadline=time.monotonic()+5
            for row in rows:
                pid=row['before']['pid']
                while not fully_stopped(pid):
                    if time.monotonic()>deadline:raise RuntimeError('SIGSTOP not observed')
                    time.sleep(.01)
                row['stopped']=process(pid)
                row['all_threads_stopped']=fully_stopped(pid)
        yield rows
        if enabled:
            for row in rows:
                row['end_stopped']=process(row['before']['pid'])
                assert row['end_stopped']['state'] in ['T','t']
                assert row['end_stopped']['cpu_ticks']==row['stopped']['cpu_ticks']
    finally:
        resume()
        deadline=time.monotonic()+5
        for row in rows:
            pid=row['before']['pid']
            while process(pid)['state'] in ['T','t']:
                if time.monotonic()>deadline:raise RuntimeError('SIGCONT not observed')
                time.sleep(.01)
            row['after']=process(pid)

receipt = dict(schema='gpr.preview_background_control_abba.v1', requested_frames_per_run=600,
    source_kind='still_derived_raw', sink='memory_crc', inputs=inputs,
    fsync_policy='page-aligned 1 MiB rolling writeback plus final fsync',
    same_executable_for_all_runs=True, background_processes_unchanged=False,
    camera_production_ready=False, quality_approval=False, runs=[])
for i,kind in enumerate(['active','paused','paused','active']):
    clip = root/f'{i}-{kind}.gvid'
    cmd = command.copy()
    cmd[cmd.index('--output')+1] = str(clip)
    cmd.append('--preview-sync-stages')
    (root/f'{i}-{kind}-command.json').write_text(json.dumps(dict(command=cmd),indent=2)+'\n')
    with process_control(kind=='paused') as controlled:
        before = state()
        usage0 = resource.getrusage(resource.RUSAGE_CHILDREN)
        started = time.monotonic()
        with (root/f'{i}-{kind}.jsonl').open('w') as stdout, (root/f'{i}-{kind}.stderr').open('w') as stderr:
            subprocess.run(cmd, stdout=stdout, stderr=stderr, check=True, timeout=300)
        wall = time.monotonic()-started
        usage1 = resource.getrusage(resource.RUSAGE_CHILDREN)
        after = state()
    events = [json.loads(line) for line in (root/f'{i}-{kind}.jsonl').read_text().splitlines() if line.startswith('{')]
    checked = bench.verify(clip, events, metadata, payloads, offline)
    previews = [row for row in events if row['event']=='preview']
    checked['source_render_medians_ms'] = {str(source): statistics.median(row['render_ms'] for row in previews if row['source_index']==source) for source in range(2)}
    checked.update(kind=kind, process_control=controlled, binary_sha256=binary_hash, before=before, after=after,
        process_user_s=usage1.ru_utime-usage0.ru_utime, process_system_s=usage1.ru_stime-usage0.ru_stime,
        process_wall_s=wall)
    receipt['runs'].append(checked)
    (root/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(dict(run=i,kind=kind,frames=checked['frames_verified'],durable_fps=checked['capture']['durable_fps'],preview=checked['preview'],floor=checked['floor'])),flush=True)

assert not paused_here
receipt["all_controlled_processes_resumed"]=all(process(row["pid"])["state"] not in ["T","t"] for row in identities)
(root/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
for fd in fds.values():os.close(fd)
