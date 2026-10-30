"""Isolated same-binary ABBA comparison of experimental shared unpack rows."""
import hashlib,json,os,pathlib,re,statistics,subprocess,time
repo=pathlib.Path('/mnt/ssd/gpr_work/stock-row-cache-prototype-20261030')
out=repo/'diagnostic';out.mkdir(exist_ok=True)
exe=repo/'build-experiment/source/app/vc5_encoder_app/vc5_encoder_app'
source_root=pathlib.Path('/mnt/ssd/gpr_work/artifacts/mission1_all42_4k_raw_pi20fps_20260624/frames')
sources=[('GP017517.raw','e75aea542a2da413ff097bd1f1825b20e8723e56b1cda257ea4da4b8ed1121d9'),('GP017348.raw','6b286a10e816887c044640f220667173e7c0ccf31bb268ebb2b494e06ccb87c4')]
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for name,sha in sources:assert h(source_root/name)==sha
protocol=dict(schema='gpr.experimental_shared_rows.v1',binary_sha256=h(exe),source_files={str(p.relative_to(repo)):h(p) for p in [repo/'source/lib/vc5_encoder/encoder.c',repo/'source/lib/vc5_encoder/encoder.h',repo/'source/lib/vc5_encoder/raw.c']},sources=sources,order=['8','32','128'],runs_per_process=1,warmup_discard=0,scope='isolated reused-arena encoding; not capture/preview or strict deadlines',same_binary=True)
(out/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
rows=[];expected={}
for index,mode in enumerate(protocol['order']):
 for name,sha in sources:
  env={k:v for k,v in os.environ.items() if not k.startswith('GPR_')}
  env.update(GPR_STREAM_UNPACK='1',GPR_BAND_STREAM='1',GPR_CHANNEL_ASM='1',GPR_DIRECT_BANDS='1',GPR_COMPACT_BANDS='1',GPR_BENCH_ARENA='1',GPR_BENCH_RUNS='1',GPR_PIN_CHANNELS='1')
  env.update(GPR_UNPACK_ROW_CACHE='1',GPR_UNPACK_CACHE_ROWS=mode,GPR_UNPACK_CACHE_STATS='1')
  path=out/f'{index}-{mode}-{name}.vc5'
  cmd=[str(exe),'-i',str(source_root/name),'-o',str(path),'-w','4096','-h','3072','-p','8192']
  begin=time.monotonic();p=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=180)
  log=p.stdout+p.stderr;path.with_suffix('.log').write_text(log)
  assert p.returncode==0,(cmd,log[-3000:])
  samples=[float(x) for x in re.findall(r'Encode wall ([0-9.]+) seconds',log)];assert len(samples)==1
  digest=h(path)
  if name not in expected:expected[name]=digest
  assert digest==expected[name],(mode,name,digest,expected[name])
  row=dict(index=index,mode=mode,source=name,command=cmd,env={k:v for k,v in env.items() if k.startswith('GPR_')},output_sha256=digest,exact_baseline_payload=True,encode_s=samples,median_s=statistics.median(samples),process_wall_s=time.monotonic()-begin)
  rows.append(row);(out/'receipt.json').write_text(json.dumps(dict(protocol_sha256=h(out/'protocol.json'),complete=False,rows=rows),indent=2)+'\n');print(mode,name,row['median_s'],flush=True)
(out/'receipt.json').write_text(json.dumps(dict(protocol_sha256=h(out/'protocol.json'),complete=True,rows=rows),indent=2)+'\n')
