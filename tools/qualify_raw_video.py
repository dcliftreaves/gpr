#!/usr/bin/env python3
"""Qualify paced, non-CNN GVID recording on a chosen filesystem (stdlib only).

Reads real RAW fixture(s), records with final fsync, validates every frame and
writes a machine-readable receipt. This measures fixture replay, not sensor I/O.
The output directory must be new. Large clips are deleted only after validation,
unless --keep-clip is supplied; failed runs retain their files for diagnosis.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import time

import raw_media
import stock_video


def machine():
    result=dict(platform=platform.platform(), machine=platform.machine())
    for name,path in (('model','/proc/device-tree/model'),
                      ('temperature_millic','/sys/class/thermal/thermal_zone0/temp'),
                      ('governor','/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor')):
        try: result[name]=Path(path).read_text().strip('\0\n')
        except OSError: pass
    try:
        result['throttled']=subprocess.run(['vcgencmd','get_throttled'],capture_output=True,text=True,
                                          timeout=5,check=True).stdout.strip()
    except (OSError,subprocess.SubprocessError): pass
    return result


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture',type=Path,required=True)
    p.add_argument('--input',type=Path,action='append',required=True)
    p.add_argument('--metadata',type=Path,action='append',required=True)
    p.add_argument('--output',type=Path,required=True,help='new directory on storage under test')
    p.add_argument('--seconds',type=int,default=180)
    p.add_argument('--fps',type=int,default=24)
    p.add_argument('--quality',type=int,choices=range(6),default=3)
    p.add_argument('--queue',type=int,choices=range(1,17),default=4)
    p.add_argument('--workspace-mib',type=int,default=512)
    p.add_argument('--writeback-mib',type=int,default=8 if platform.system()=='Linux' else 0,help='Linux async writeback (default 8 MiB on Linux, 0 elsewhere)' )
    p.add_argument('--keep-clip',action='store_true')
    p.add_argument('--max-rate-shortfall',type=float,default=.01,help='allowed final-flush rate shortfall fraction')
    a=p.parse_args()
    if (not 1<=len(a.input)<=16 or len(a.input)!=len(a.metadata) or
        not 1<=a.fps<=240 or not 1<=a.seconds<=3600 or a.fps*a.seconds>1000000 or
        not 0<=a.workspace_mib<=2048 or not 0<=a.writeback_mib<=2048 or
        not math.isfinite(a.max_rate_shortfall) or not 0<=a.max_rate_shortfall<1):
        p.error('invalid frame count, inputs, duration, workspace or rate tolerance')
    meta=[json.loads(path.read_text()) for path in a.metadata]
    first=meta[0]
    for m,path in zip(meta,a.input):
        raw_media.validate(m)
        for field in ('width','height','sample_bits','cfa'):
            if m[field]!=first[field]:p.error('all inputs must share geometry and sample domain')
        if path.stat().st_size!=first['width']*first['height']*2:p.error('RAW size mismatch')
    a.output.mkdir(parents=True,exist_ok=False)
    clip=a.output/'recording.gvid';log=a.output/'capture.jsonl';err=a.output/'capture.stderr'
    frames=a.seconds*a.fps
    cmd=[str(a.capture.resolve()),'--output',str(clip),'--width',str(first['width']),
         '--height',str(first['height']),'--sample-bits',str(first['sample_bits']),
         '--cfa',first['cfa'],'--quality',str(a.quality),'--fps-num',str(a.fps),'--fps-den','1',
         '--frames',str(frames),'--queue',str(a.queue),'--workspace-mib',str(a.workspace_mib),
         '--writeback-mib',str(a.writeback_mib),'--paced','--leased']
    for path,sidecar in zip(a.input,a.metadata):
        cmd+=['--input',str(path.resolve()),'--source-metadata',str(sidecar.resolve())]
    before=machine(); started=time.monotonic()
    environment={k:v for k,v in os.environ.items() if not k.startswith('GPR_')}
    with log.open('w') as out,err.open('w') as stderr:
        result=subprocess.run(cmd,stdout=out,stderr=stderr,env=environment,
                              timeout=max(120,a.seconds*4))
    elapsed=time.monotonic()-started;after=machine()
    receipt=dict(schema='gpr.recording_qualification.v1',cnn=False,
        scope='paced RAW fixture replay with final fsync; not camera acquisition',
        before=before,after=after,requested_fps=a.fps,duration_seconds=a.seconds,
        quality=a.quality,workspace_mib=a.workspace_mib,writeback_mib=a.writeback_mib,
        required_durable_fps=a.fps*(1-a.max_rate_shortfall),process_seconds=elapsed,
        capture_binary_sha256=sha(a.capture),inputs=[dict(name=path.name,sha256=sha(path)) for path in a.input],
        width=first['width'],height=first['height'],sample_bits=first['sample_bits'],
        capture_returncode=result.returncode,qualified=False)
    def publish():
        (a.output/'qualification.json').write_text(json.dumps(receipt,indent=2)+'\n')
    publish()
    if result.returncode:raise SystemExit('capture failed; retained logs and partial recording')
    summaries=[]
    for line in log.read_text().splitlines():
        row=json.loads(line)
        if row.get('event')=='summary':summaries.append(row)
    if len(summaries)!=1:raise ValueError('missing/ambiguous capture summary')
    summary=summaries[0];receipt['capture']=summary;publish()
    seen={};count=0
    with clip.open('rb') as file:
        header=stock_video.read_header(file)
        for row in stock_video.records(file,header):
            source=row['metadata']['source_index']
            if type(source) is not int or not 0<=source<len(meta):raise ValueError('invalid source index')
            actual=row['metadata']['raw_metadata'];raw_media.validate(actual,header)
            if actual!=meta[source]:raise ValueError('calibration changed')
            digest=hashlib.sha256(row['payload']).hexdigest()
            if source in seen and seen[source]!=digest:raise ValueError('identical replay input changed payload')
            seen[source]=digest;count+=1
        if not header['_end_marker_verified']:raise ValueError('missing completion marker')
    if count!=summary['written'] or summary['written']!=summary['accepted']:
        raise ValueError('capture/recording frame counts differ')
    receipt.update(verified_frames=count,end_marker_verified=True,calibration_verified=True,
                   repeated_input_payloads_stable=True,clip_bytes=clip.stat().st_size)
    # Completeness, average durable rate and individual frame deadlines are
    # reported separately. A passing average is not a zero-latency-miss claim.
    receipt['qualified']=bool(summary['complete'] and count==frames and summary['overruns']==0 and
                              summary['durable_fps']>=receipt['required_durable_fps'])
    receipt['zero_deadline_misses']=summary['deadline_misses']==0
    receipt['clip_retained']=a.keep_clip or not receipt['qualified']
    publish()
    if not receipt['clip_retained']:clip.unlink()
    print(json.dumps(receipt,indent=2))
    raise SystemExit(0 if receipt['qualified'] else 2)

if __name__=='__main__':main()
