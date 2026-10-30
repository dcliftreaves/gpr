from pathlib import Path
import hashlib,json,os,statistics,sys
repo=Path('/mnt/ssd/gpr_work/stock-raw-media-runtime'); root=Path('/mnt/ssd/gpr_work/stock-entropy-handoff-rows32-20261030'); out=root/'smoke';out.mkdir(exist_ok=True)
sys.path.insert(0,str(repo/'tools'));import benchmark_mission1 as bench
seed=Path('/mnt/ssd/gpr_work/pi-mission1-writeback8-20261030');inputs=json.loads((seed/'receipt.json').read_text())['inputs'];base=json.loads((root/'command-template.json').read_text())[1]['command'];metadata=[json.loads(Path(base[i+1]).read_text()) for i,s in enumerate(base) if s=='--source-metadata'];payloads=[s['reference_payload_sha256'] for s in inputs];offline={r['index']:r for r in map(json.loads,(seed/'offline.jsonl').read_text().splitlines()) if r['event']=='preview'}
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();exe=root/'build/gpr_capture_app'; rows=[]
protocol=dict(base='a00ae4a',schema='gpr.entropy_handoff_smoke.v1',scope='16-frame correctness and actual helper participation, including no-created-threads fallback; statistics enabled, not acceptance timing',source_sha256={n:h(root/n) for n in ['source/lib/vc5_encoder/encoder.c','source/lib/vc5_encoder/entropy_handoff.h','tests/encoder_preview_probe.c']},binary_sha256=h(exe),production_binary_sha256=h(repo/'build-runtime/gpr_capture_app'),order=['helpers','no-created-threads'],frames=16,fps_by_mode={'helpers':20,'no-created-threads':5})
(out/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
for mode in protocol['order']:
 env={k:v for k,v in os.environ.items() if not k.startswith('GPR_')};env['GPR_ENTROPY_HANDOFF']='1';env['GPR_HANDOFF_STATS']='1'
 if mode=='no-created-threads':env['GPR_HANDOFF_NO_THREADS']='1'
 command=base.copy();command[0]=str(exe);command[command.index('--frames')+1]='16';command[command.index('--fps-num')+1]=str(protocol['fps_by_mode'][mode]);clip=out/(mode+'.gvid');command[command.index('--output')+1]=str(clip);log=out/(mode+'.jsonl');events=bench.run(command,log,environment=env);verified=bench.verify(clip,events,metadata,payloads,offline)
 samples=[]
 for line in log.with_suffix(log.suffix+'.stderr').read_text().splitlines():
  if line.startswith('handoff '):samples.append({k:int(v) for k,v in (w.split('=') for w in line.split()[1:])})
 assert verified['frames_verified']==verified['previews_verified']==16
 assert len(samples)==16 and all(x['error']==0 and x['chunks']==24 and sum(x['jobs'+str(c)] for c in range(4))==72 and x['bytes']==786432 for x in samples)
 helpers=sum(sum(s['jobs'+str(c)] for c in range(1,4)) for s in samples)
 assert helpers>0 if mode=='helpers' else helpers==0
 row=dict(mode=mode,command=command,environment={k:v for k,v in env.items() if k.startswith('GPR_')},helper_jobs=helpers,statistics=samples,verified=verified);rows.append(row);(out/'receipt.json').write_text(json.dumps(dict(complete=False,protocol_sha256=h(out/'protocol.json'),rows=rows),indent=2)+'\n');print(mode,'helper_jobs',helpers,'exact',verified['frames_verified'],verified['previews_verified'],'fallback_bytes',verified['capture']['workspace_fallback_peak_bytes'],flush=True)
(out/'receipt.json').write_text(json.dumps(dict(complete=True,protocol_sha256=h(out/'protocol.json'),rows=rows),indent=2)+'\n')
