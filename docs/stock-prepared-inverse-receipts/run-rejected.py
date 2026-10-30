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

root = Path('/mnt/ssd/gpr_work/pi-mission1-prepared-inverse-abba-20261030')
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

receipt = dict(schema='gpr.preview_prepared_inverse_abba.v1', requested_frames_per_run=600,
    source_kind='still_derived_raw', sink='memory_crc', inputs=inputs,
    fsync_policy='page-aligned 1 MiB rolling writeback plus final fsync',
    same_executable_for_all_runs=False, background_processes_unchanged=True,
    camera_production_ready=False, quality_approval=False, runs=[])
for i,kind in enumerate(['previous','prepared','prepared','previous']):
    clip = root/f'{i}-{kind}.gvid'
    cmd = command.copy()
    cmd[cmd.index('--output')+1] = str(clip)
    cmd.append('--preview-sync-stages')
    if kind == 'previous': cmd[0] = '/mnt/ssd/gpr_work/gpr_capture_pre_prepared_inverse_20261030'
    binary_hash = hashlib.sha256(Path(cmd[0]).read_bytes()).hexdigest()
    (root/f'{i}-{kind}-command.json').write_text(json.dumps(dict(command=cmd),indent=2)+'\n')
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
    checked.update(kind=kind, binary_sha256=binary_hash, before=before, after=after,
        process_user_s=usage1.ru_utime-usage0.ru_utime, process_system_s=usage1.ru_stime-usage0.ru_stime,
        process_wall_s=wall)
    receipt['runs'].append(checked)
    (root/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(dict(run=i,kind=kind,frames=checked['frames_verified'],durable_fps=checked['capture']['durable_fps'],preview=checked['preview'],floor=checked['floor'])),flush=True)
