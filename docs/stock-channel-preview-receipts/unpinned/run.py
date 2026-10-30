"""Fixed ABBA isolated encode + exact three-plane reconstruction comparison."""
import hashlib,json,os,pathlib,statistics,subprocess,time
repo=pathlib.Path('/mnt/ssd/gpr_work/stock-channel-preview-prototype-20261030');out=repo/'measurements-unpinned';out.mkdir(exist_ok=True)
exe=repo/'build-experiment/channel_preview_benchmark';source_root=pathlib.Path('/mnt/ssd/gpr_work/artifacts/mission1_all42_4k_raw_pi20fps_20260624/frames')
sources=[dict(name='GP017517.raw',raw='e75aea542a2da413ff097bd1f1825b20e8723e56b1cda257ea4da4b8ed1121d9',payload='bd1966d35be26afdd5d676473427245f80d884bee911ed1c7c2c4ecbe93023b8'),dict(name='GP017348.raw',raw='6b286a10e816887c044640f220667173e7c0ccf31bb268ebb2b494e06ccb87c4',payload='13626758bf6bf1262412ad308ed07ccb6b5f3557d7d2356c6b5e6a02816ceddb')]
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for s in sources:assert h(source_root/s['name'])==s['raw']
files=['CMakeLists.txt','source/lib/vc5_encoder/encoder.c','source/lib/vc5_encoder/encoder.h','source/lib/vc5_encoder/parameters.h','source/lib/vc5_encoder/vc5_encoder.c','source/lib/vc5_encoder/vc5_encoder.h','tests/encoder_preview_probe.c','tests/channel_preview_benchmark.cpp']
env={k:v for k,v in os.environ.items() if not k.startswith('GPR_')};env.update(GPR_STREAM_UNPACK='1',GPR_BAND_STREAM='1',GPR_CHANNEL_ASM='1',GPR_DIRECT_BANDS='1',GPR_COMPACT_BANDS='1',GPR_PIN_CHANNELS='1')
protocol=dict(schema='gpr.experimental_channel_preview.v1',base='48534e0',binary_sha256=h(exe),source_files={f:h(repo/f) for f in files},sources=sources,order=['baseline','channel','channel','baseline'],iterations=31,warmup_discard=1,env={k:v for k,v in env.items() if k.startswith('GPR_')},scope='isolated encode plus retained-band reconstruction; not recording/preview deadlines',same_binary=True)
(out/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n');rows=[];planes={}
for i,mode in enumerate(protocol['order']):
 for s in sources:
  path=out/f'{i}-{mode}-{s["name"]}';path.mkdir(exist_ok=True)
  cmd=[str(exe),str(source_root/s['name']),mode,'31'];start=time.monotonic();p=subprocess.run(cmd,env=env,cwd=path,capture_output=True,text=True,timeout=180);(path/'stdout.jsonl').write_text(p.stdout);(path/'stderr.txt').write_text(p.stderr);assert p.returncode==0,(cmd,p.returncode,p.stderr)
  timers=[json.loads(line) for line in p.stdout.splitlines()];assert len(timers)==31
  payload=h(path/(mode+'.vc5'));assert payload==s['payload']
  hashes=[h(path/f'{mode}-{c}.plane') for c in range(3)]
  if s['name'] not in planes:planes[s['name']]=hashes
  assert hashes==planes[s['name']]
  row=dict(index=i,mode=mode,source=s['name'],command=cmd,payload_sha256=payload,plane_sha256=hashes,exact_independent_payload=True,exact_baseline_planes=True,timers=timers,median_s=statistics.median(t['wall_s'] for t in timers[1:]),process_wall_s=time.monotonic()-start)
  rows.append(row);(out/'receipt.json').write_text(json.dumps(dict(protocol_sha256=h(out/'protocol.json'),complete=False,rows=rows),indent=2)+'\n');print(mode,s['name'],row['median_s'],flush=True)
(out/'receipt.json').write_text(json.dumps(dict(protocol_sha256=h(out/'protocol.json'),complete=True,rows=rows),indent=2)+'\n')
