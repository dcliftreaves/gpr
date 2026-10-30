from pathlib import Path
import hashlib,json,os,statistics,sys
repo=Path('/mnt/ssd/gpr_work/stock-raw-media-runtime'); root=Path('/mnt/ssd/gpr_work/stock-channel-balance-prototype-20261030'); out=root/'stages';out.mkdir(exist_ok=True)
sys.path.insert(0,str(repo/'tools'));import benchmark_mission1 as bench
seed=Path('/mnt/ssd/gpr_work/pi-mission1-writeback8-20261030');inputs=json.loads((seed/'receipt.json').read_text())['inputs'];base=json.loads((root/'command-template.json').read_text())[1]['command'];metadata=[json.loads(Path(base[i+1]).read_text()) for i,s in enumerate(base) if s=='--source-metadata'];payloads=[s['reference_payload_sha256'] for s in inputs];offline={r['index']:r for r in map(json.loads,(seed/'offline.jsonl').read_text().splitlines()) if r['event']=='preview'}
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();exe=root/'build/gpr_capture_app'; rows=[]
protocol=dict(base='40aa476',schema='gpr.channel_entropy_stage_diagnostic.v1',scope='instrumented 120-frame replay; per-row thread-CPU brackets around entropy updates; includes timer overhead, excludes final band flush from stage subtotals; not acceptance timing',source_sha256=h(root/'source/lib/vc5_encoder/encoder.c'),binary_sha256=h(exe),production_binary_sha256=h(repo/'build-runtime/gpr_capture_app'),order=['unrestricted'],frames=120)
(out/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
for mode in protocol['order']:
 env={k:v for k,v in os.environ.items() if not k.startswith('GPR_')};env['GPR_CHANNEL_BALANCE']='1'
 if mode=='pinned':env['GPR_PIN_CHANNELS']='1'
 command=base.copy();command[0]=str(exe);command[command.index('--frames')+1]='120';clip=out/(mode+'.gvid');command[command.index('--output')+1]=str(clip);log=out/(mode+'.jsonl');events=bench.run(command,log,environment=env);verified=bench.verify(clip,events,metadata,payloads,offline)
 samples=[]
 for line in log.with_suffix(log.suffix+'.stderr').read_text().splitlines():
  if line.startswith('balance '):
   row={k:float(v) for k,v in (s.split('=') for s in line.split()[1:])};row['channel']=int(row['channel']);samples.append(row)
 assert len(samples)==480 and all(x['error']==0 for x in samples)
 channels=[]
 for channel in range(4):
  ss=[s for s in samples if s['channel']==channel];assert len(ss)==120
  channels.append(dict(channel=channel,samples=len(ss),median_wall_ms=statistics.median(s['wall'] for s in ss)*1000,median_cpu_ms=statistics.median(s['cpu'] for s in ss)*1000,median_start_ms=statistics.median(s['start'] for s in ss)*1000,median_finish_ms=statistics.median(s['finish'] for s in ss)*1000))
 last=[]
 for i in range(0,len(samples),4):
  frame=samples[i:i+4];assert [s['channel'] for s in frame]==[0,1,2,3];last.append(max(frame,key=lambda s:s['finish'])['channel'])
 row=dict(mode=mode,command=command,environment={k:v for k,v in env.items() if k.startswith('GPR_')},channels=channels,last_finish_counts={str(k):last.count(k) for k in range(4)},verified=verified);rows.append(row);(out/'receipt.json').write_text(json.dumps(dict(complete=False,protocol_sha256=h(out/'protocol.json'),rows=rows),indent=2)+'\n');print(mode,json.dumps(channels),row['last_finish_counts'],flush=True)
(out/'receipt.json').write_text(json.dumps(dict(complete=True,protocol_sha256=h(out/'protocol.json'),rows=rows),indent=2)+'\n')
