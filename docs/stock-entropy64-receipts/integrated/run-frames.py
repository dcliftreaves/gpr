"""Fixed real-input palindrome across baseline, full64 and hybrid encoders."""
from pathlib import Path
import hashlib,json,os,re,statistics,subprocess,time
repo=Path('/mnt/ssd/gpr_work/stock-entropy64-prototype-20261030');out=repo/'frames-v2';out.mkdir(exist_ok=True)
source_root=Path('/mnt/ssd/gpr_work/artifacts/mission1_all42_4k_raw_pi20fps_20260624/frames')
sources=[dict(name='GP017517.raw',raw='e75aea542a2da413ff097bd1f1825b20e8723e56b1cda257ea4da4b8ed1121d9',payload='bd1966d35be26afdd5d676473427245f80d884bee911ed1c7c2c4ecbe93023b8'),dict(name='GP017348.raw',raw='6b286a10e816887c044640f220667173e7c0ccf31bb268ebb2b494e06ccb87c4',payload='13626758bf6bf1262412ad308ed07ccb6b5f3557d7d2356c6b5e6a02816ceddb')]
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for s in sources:assert h(source_root/s['name'])==s['raw']
builds=json.loads((repo/'builds-v2.json').read_text());env={k:v for k,v in os.environ.items() if not k.startswith('GPR_')};env.update(GPR_STREAM_UNPACK='1',GPR_BAND_STREAM='1',GPR_CHANNEL_ASM='1',GPR_DIRECT_BANDS='1',GPR_COMPACT_BANDS='1',GPR_BENCH_ARENA='1',GPR_BENCH_RUNS='31',GPR_BENCH_QUALITY='3',GPR_PIN_CHANNELS='1')
protocol=dict(schema='gpr.experimental_entropy64_frames.v1',base='9e51ea1',encoder_source_sha256=h(repo/'source/lib/vc5_encoder/encoder.c'),builds=builds,sources=sources,order=['baseline','full64','hybrid','hybrid','full64','baseline'],iterations=31,warmup_discard=1,env={k:v for k,v in env.items() if k.startswith('GPR_')},scope='standalone reused-arena actual Q3 encode wall; not capture/preview/durability')
(out/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n');rows=[]
for index,mode in enumerate(protocol['order']):
 exe=repo/('build-'+mode)/'source/app/vc5_encoder_app/vc5_encoder_app';assert h(exe)==next(b['encoder_sha256'] for b in builds if b['mode']==mode)
 for s in sources:
  output=out/f'{index}-{mode}-{s["name"]}.vc5';cmd=[str(exe),'-i',str(source_root/s['name']),'-o',str(output),'-w','4096','-h','3072','-p','8192'];start=time.monotonic();p=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=180);output.with_suffix('.log').write_text(p.stdout+p.stderr);assert p.returncode==0,(cmd,p.stdout[-3000:],p.stderr)
  timers=[float(x) for x in re.findall(r'Encode wall ([0-9.]+) seconds',p.stdout)];assert len(timers)==31
  digest=h(output);assert digest==s['payload'],(mode,s['name'],digest,s['payload'])
  row=dict(index=index,mode=mode,source=s['name'],command=cmd,encode_s=timers,median_s=statistics.median(timers[1:]),payload_sha256=digest,exact_independent_payload=True,process_wall_s=time.monotonic()-start);rows.append(row);(out/'receipt.json').write_text(json.dumps(dict(complete=False,protocol_sha256=h(out/'protocol.json'),rows=rows),indent=2)+'\n');print(mode,s['name'],row['median_s'],flush=True)
(out/'receipt.json').write_text(json.dumps(dict(complete=True,protocol_sha256=h(out/'protocol.json'),rows=rows),indent=2)+'\n')
