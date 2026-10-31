"""Instrumented current-source replay: attribution only, not acceptance timing."""
from pathlib import Path
import hashlib,json,os,resource,statistics,sys
repo=Path('/mnt/ssd/gpr_work/stock-raw-media-runtime');prototype=Path('/mnt/ssd/gpr_work/stock-latency-trace-prototype-20261030');root=prototype/'trace';root.mkdir(exist_ok=True);assert not (root/'protocol.json').exists(),'inspect existing run; do not restart'
sys.path.insert(0,str(repo/'tools'));import benchmark_mission1 as bench
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();exe=prototype/'build-diagnostic/gpr_capture_app';seed=Path('/mnt/ssd/gpr_work/pi-mission1-writeback8-20261030');inputs=json.loads((seed/'receipt.json').read_text())['inputs'];command=json.loads((prototype/'command-template.json').read_text())[1]['command'];command[0]=str(exe);command[command.index('--frames')+1]='600';clip=root/'trace.gvid';command[command.index('--output')+1]=str(clip)
metadata=[json.loads(Path(command[i+1]).read_text()) for i,v in enumerate(command) if v=='--source-metadata'];payloads=[s['reference_payload_sha256'] for s in inputs];offline={r['index']:r for r in map(json.loads,(seed/'offline.jsonl').read_text().splitlines()) if r['event']=='preview'};env={k:v for k,v in os.environ.items() if not k.startswith('GPR_')};env.update(GPR_CHANNEL_BALANCE='1',GPR_PROFILE='1')
protocol=dict(schema='gpr.stock_latency_diagnostic.v1',base='6efc5bd',scope='600-frame instrumented replay; worker CPU/wall/context switches plus reconstruction/cleanup intervals; logging overhead included; not acceptance timing',command=command,environment={k:v for k,v in env.items() if k.startswith('GPR_')},binary_sha256=h(exe),source_sha256={n:h(prototype/n) for n in ['source/lib/vc5_encoder/encoder.c','source/lib/gpr_video/gpr_capture.cpp']},production_binary_sha256=h(repo/'build-runtime/gpr_capture_app'))
assert protocol['production_binary_sha256']=='c576f5662ac605cc5719ae536308e9ff71cdcec4f4e714343a5a919a5711687c'
(root/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n');events=bench.run(command,root/'events.jsonl',environment=env);verified=bench.verify(clip,events,metadata,payloads,offline)
traces=[];pending={};workers=[]
for line in (root/'events.jsonl.stderr').read_text().splitlines():
 if line.startswith('balance '):workers.append({k:float(v) for k,v in (w.split('=') for w in line.split()[1:])})
 elif line.startswith(('unpack_wall=','encoding_end_wall=','after_preview_wall=','after_cleanup_wall=')):
  k,v=line.split('=');assert k not in pending;pending[k]=float(v)
 elif line.startswith('capture_diag '):
  row={k:int(v) for k,v in (w.split('=') for w in line.split()[1:])};assert row['clock_ok']==1 and row['error']==0
  assert len(workers)==4 and [int(w['channel']) for w in workers]==[0,1,2,3] and all(w['error']==0 and w['cpu']>0 for w in workers)
  assert set(pending)=={'unpack_wall','encoding_end_wall','after_preview_wall','after_cleanup_wall'}
  assert 0<=pending['unpack_wall']<=pending['encoding_end_wall']<=pending['after_preview_wall']<=pending['after_cleanup_wall']
  row.update(pending);row['workers']=workers;traces.append(row);pending={};workers=[]
assert not pending and not workers and len(traces)==verified['frames_verified']
frames={r['index']:r for r in events if r['event']=='frame'};previews={r['index']:r for r in events if r['event']=='preview'};rows=[]
for t in traces:
 i=t['frame'];f=frames[i];p=previews[i];w=max(t['workers'],key=lambda w:w['finish']);assert abs(t['wall_ns']/1e6-f['encode_ms'])<.001
 r=dict(index=i,source=p['source_index'],encode_ms=f['encode_ms'],main_cpu_ms=t['cpu_ns']/1e6,main_wall_minus_cpu_ms=(t['wall_ns']-t['cpu_ns'])/1e6,critical_channel=int(w['channel']),critical_wall_ms=w['wall']*1000,critical_cpu_ms=w['cpu']*1000,critical_wall_minus_cpu_ms=(w['wall']-w['cpu'])*1000,critical_involuntary=int(w['involuntary']),critical_voluntary=int(w['voluntary']),join_tail_ms=(w['joined']-w['finish'])*1000,reconstruction_callback_ms=(t['after_preview_wall']-t['encoding_end_wall'])*1000,cleanup_ms=(t['after_cleanup_wall']-t['after_preview_wall'])*1000,unpack_ms=t['unpack_wall']*1000,write_ms=f['write_ms'],capture_to_written_ms=f['capture_to_written_ms'],capture_to_preview_ms=p['capture_to_sink_ms'],late_write=f['deadline_missed'],late_preview=p['capture_to_sink_ms']>50)
 rows.append(r)
(root/'traces.json').write_text(json.dumps(traces,indent=2)+'\n');(root/'correlation.json').write_text(json.dumps(rows,indent=2)+'\n')
def summary(ss):
 if not ss:return dict(frames=0)
 fields=['encode_ms','main_cpu_ms','main_wall_minus_cpu_ms','critical_wall_ms','critical_cpu_ms','critical_wall_minus_cpu_ms','join_tail_ms','reconstruction_callback_ms','cleanup_ms','write_ms']
 return dict(frames=len(ss),late_writes=sum(x['late_write'] for x in ss),late_previews=sum(x['late_preview'] for x in ss),critical_counts={str(c):sum(x['critical_channel']==c for x in ss) for c in range(4)},metrics={k:dict(median=statistics.median(x[k] for x in ss),maximum=max(x[k] for x in ss)) for k in fields},critical_with_involuntary=sum(x['critical_involuntary']>0 for x in ss))
receipt=dict(complete=True,protocol_sha256=h(root/'protocol.json'),verified=verified,all=summary(rows),sources=[dict(source=i,all=summary([x for x in rows if x['source']==i]),late=summary([x for x in rows if x['source']==i and (x['late_write'] or x['late_preview'])]),on_time=summary([x for x in rows if x['source']==i and not (x['late_write'] or x['late_preview'])])) for i in [0,1]],slowest_encodes=sorted(rows,key=lambda x:x['encode_ms'],reverse=True)[:16])
(root/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(dict(verified_frames=verified['frames_verified'],verified_previews=verified['previews_verified'],all=receipt['all'],slowest=receipt['slowest_encodes'][:4]),indent=2),flush=True)
