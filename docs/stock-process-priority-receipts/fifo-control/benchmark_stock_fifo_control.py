"""Same production binary, normal UID, process-local SCHED_OTHER nice control."""
from pathlib import Path
import hashlib,json,os,statistics,subprocess,sys,time
repo=Path('/mnt/ssd/gpr_work/stock-raw-media-runtime');root=Path('/mnt/ssd/gpr_work/stock-fifo-control-20261030');root.mkdir(exist_ok=True);assert not (root/'protocol.json').exists()
sys.path.insert(0,str(repo/'tools'));import benchmark_mission1 as bench
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();exe=repo/'build-runtime/gpr_capture_app';assert h(exe)=='c576f5662ac605cc5719ae536308e9ff71cdcec4f4e714343a5a919a5711687c';seed=Path('/mnt/ssd/gpr_work/pi-mission1-writeback8-20261030');inputs=json.loads((seed/'receipt.json').read_text())['inputs'];base=json.loads((root/'command-template.json').read_text())[1]['command'];base[0]=str(exe);metadata=[json.loads(Path(base[i+1]).read_text()) for i,x in enumerate(base) if x=='--source-metadata'];payloads=[x['reference_payload_sha256'] for x in inputs];offline={r['index']:r for r in map(json.loads,(seed/'offline.jsonl').read_text().splitlines()) if r['event']=='preview'};rows=[];env={k:v for k,v in os.environ.items() if not k.startswith('GPR_')}
protocol=dict(schema='gpr.stock_fifo_process_control.v1',published_revision='cade228',source_revision='f197f09',scope='same production executable, UID1000/nice0 foreground preview, OTHER0/FIFO1/FIFO1/OTHER0; no system/device or realtime-limit changes; no profiler/diagnostic logging',binary_sha256=h(exe),launcher_sha256=h(root/'launch_stock_policy_user.py'),order=['other','fifo','fifo','other'],frames=600,command_template=base)
(root/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
for i,mode in enumerate(protocol['order']):
 nice=0;policy=os.SCHED_FIFO if mode=='fifo' else os.SCHED_OTHER;priority=1 if mode=='fifo' else 0
 cmd=base.copy();cmd.append('--preview-foreground');cmd[cmd.index('--frames')+1]='600';clip=root/f'{i}-nice{nice}.gvid';cmd[cmd.index('--output')+1]=str(clip);launch=root/f'{i}-launch.json';command=['sudo','-n','chrt','--fifo' if mode=='fifo' else '--other',str(priority),'/usr/bin/setpriv','--reuid=1000','--regid=1000','--init-groups','--reset-env','/usr/bin/python3',str(root/'launch_stock_policy_user.py'),str(launch),str(policy)]+cmd
 assert h(exe)==protocol['binary_sha256']
 with (root/f'{i}.jsonl').open('w') as stdout,(root/f'{i}.stderr').open('w') as stderr:
  p=subprocess.Popen(command,stdout=stdout,stderr=stderr,env=env);deadline=time.monotonic()+10
  while not launch.exists():
   assert p.poll() is None,('capture failed before launch report',p.returncode)
   if time.monotonic()>deadline:raise TimeoutError('no normal-user launch report')
   time.sleep(.005)
  settings=json.loads(launch.read_text());pid=settings['pid'];status=(Path('/proc')/str(pid)/'status').read_text();observed_uids=list(map(int,next(s.split()[1:] for s in status.splitlines() if s.startswith('Uid:'))));observed_nice=os.getpriority(os.PRIO_PROCESS,pid);observed_policy=os.sched_getscheduler(pid)
  assert observed_uids==[1000]*4 and observed_nice==nice and observed_policy==policy and settings['nice']==nice and settings['effective_capabilities']=='0000000000000000'
  assert p.wait(timeout=300)==0
 events=[json.loads(s) for s in (root/f'{i}.jsonl').read_text().splitlines() if s.startswith('{')];v=bench.verify(clip,events,metadata,payloads,offline);assert v['preview']['background_requested']==0
 row=dict(index=i,mode=mode,policy=policy,priority=priority,nice=nice,command=command,launch=settings,observed_uids=observed_uids,observed_nice=observed_nice,observed_policy=observed_policy,verified=v);rows.append(row);(root/'receipt.json').write_text(json.dumps(dict(complete=False,protocol_sha256=h(root/'protocol.json'),rows=rows),indent=2)+'\n');print(mode,v['frames_verified'],v['capture']['durable_fps'],v['capture']['encode_median_ms'],v['capture']['deadline_misses'],v['floor']['preview_late_deliveries'],flush=True)
(root/'receipt.json').write_text(json.dumps(dict(complete=True,protocol_sha256=h(root/'protocol.json'),rows=rows),indent=2)+'\n')
