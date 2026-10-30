"""Matched production-style Pi ABBA for bounded preview plane spacing."""
from pathlib import Path
import hashlib,json,os,resource,statistics,subprocess,sys,time
repo=Path('/mnt/ssd/gpr_work/stock-raw-media-runtime');prototype=Path('/mnt/ssd/gpr_work/stock-preview-color-prototype-20261030');root=prototype/'final-capture';root.mkdir(exist_ok=True)
sys.path.insert(0,str(repo/'tools'));import benchmark_mission1 as bench
seed=Path('/mnt/ssd/gpr_work/pi-mission1-writeback8-20261030');inputs=json.loads((seed/'receipt.json').read_text())['inputs']
base=json.loads((prototype/'command-template.json').read_text())[1]['command']
# Recorded command stores original direct-output production path; both measured binaries are fresh matched builds.
metadata=[json.loads(Path(base[i+1]).read_text()) for i,s in enumerate(base) if s=='--source-metadata'];payloads=[s['reference_payload_sha256'] for s in inputs];offline={r['index']:r for r in map(json.loads,(seed/'offline.jsonl').read_text().splitlines()) if r['event']=='preview'}
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();builds=[dict(mode='previous',path='/mnt/ssd/gpr_work/pre-preview-color-20261030/build-runtime/gpr_capture_app',binary_sha256='9fc7b823a088da3d6d5f5aa5985e710e4a00e9b39b4690d526ab99f9915ba80c'),dict(mode='final',path=str(repo/'build-runtime/gpr_capture_app'),binary_sha256='c576f5662ac605cc5719ae536308e9ff71cdcec4f4e714343a5a919a5711687c')];env={k:v for k,v in os.environ.items() if not k.startswith('GPR_')}
protocol=dict(schema='gpr.experimental_preview_color_capture.v1',base='f197f09',builds=builds,source_sha256=h(repo/'source/lib/gpr_video/gpr_preview_queue.cpp'),order=['previous','final','final','previous'],command_template=base,frames=600,scope='matched fresh builds, paced Q3 12MP capture plus every-frame exact 1024x768 preview, serialized compute and final fsync',production_binary_sha256=h(repo/'build-runtime/gpr_capture_app'),final_source_sha256={name:h(repo/name) for name in ['CMakeLists.txt','source/lib/gpr_video/gpr_preview_queue.cpp','source/lib/gpr_video/gpr_preview_queue.h','tests/preview_wavelet_queue_test.cpp']})
(root/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n');rows=[]
def state():
 values={}
 for name,path in [('temp','/sys/class/thermal/thermal_zone0/temp'),('clock','/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq'),('governor','/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor')]:values[name]=Path(path).read_text().strip()
 return values
for index,mode in enumerate(protocol['order']):
 command=base.copy();command[0]=next(b['path'] for b in builds if b['mode']==mode);assert h(Path(command[0]))==next(b['binary_sha256'] for b in builds if b['mode']==mode)
 clip=root/f'{index}-{mode}.gvid';command[command.index('--output')+1]=str(clip);command[command.index('--frames')+1]='600';assert '--preview-sync-stages' in command and '--preview-from-encoder' in command
 before=state();usage=resource.getrusage(resource.RUSAGE_CHILDREN);events=bench.run(command,root/f'{index}-{mode}.jsonl',environment=env);after=state();endusage=resource.getrusage(resource.RUSAGE_CHILDREN)
 verified=bench.verify(clip,events,metadata,payloads,offline)
 row=dict(index=index,mode=mode,command=command,before=before,after=after,child_user_s=endusage.ru_utime-usage.ru_utime,child_system_s=endusage.ru_stime-usage.ru_stime,verified=verified)
 rows.append(row);(root/'receipt.json').write_text(json.dumps(dict(complete=False,protocol_sha256=h(root/'protocol.json'),rows=rows),indent=2)+'\n');print(mode,verified['capture']['durable_fps'],verified['capture']['encode_median_ms'],verified['capture']['deadline_misses'],verified['floor']['preview_late_deliveries'],flush=True)
(root/'receipt.json').write_text(json.dumps(dict(complete=True,protocol_sha256=h(root/'protocol.json'),rows=rows),indent=2)+'\n')
