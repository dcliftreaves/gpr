from pathlib import Path
import csv,hashlib,json,os,subprocess
root=Path('/mnt/ssd/gpr_work/stock-preview-color-prototype-20261030');out=root/'pmu';out.mkdir(exist_ok=True);seed=Path('/mnt/ssd/gpr_work/pi-mission1-writeback8-20261030');offline={r['index']:r for r in map(json.loads,(seed/'offline.jsonl').read_text().splitlines()) if r['event']=='preview'};env={k:v for k,v in os.environ.items() if not k.startswith('GPR_')};rows=[]
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();protocol=dict(schema='gpr.preview_color_pmu.v1',scope='separate user-mode counters; includes startup/one-time decode and 301 queue renders per process; not acceptance timing',order=['baseline','colored','colored','baseline'],events=['l1d_cache_refill:u','cycles:u','instructions:u'],iterations=301,builds=json.loads((root/'benchmark-builds.json').read_text()))
(out/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
for index,mode in enumerate(protocol['order']):
 exe=root/('build-'+mode)/'preview_color_benchmark';assert h(exe)==next(b['binary_sha256'] for b in protocol['builds'] if b['mode']==mode)
 for source in range(2):
  cmd=['perf','stat','-x',',']
  for event in protocol['events']:cmd+=['-e',event]
  cmd+=['--',str(exe),str(seed/f'reference-{source}.vc5'),str(seed/'profiles'/f'{source:06}.gprp'),str(offline[source]['rgb_crc32']),'301']
  p=subprocess.run(cmd,capture_output=True,text=True,env=env,timeout=120);(out/f'{index}-{mode}-{source}.stdout.jsonl').write_text(p.stdout);(out/f'{index}-{mode}-{source}.perf.txt').write_text(p.stderr);assert p.returncode==0,p.stderr
  frames=[json.loads(s) for s in p.stdout.splitlines()];assert len(frames)==301 and all(s['rgb_crc32']==offline[source]['rgb_crc32'] for s in frames)
  counters={}
  for line in csv.reader(p.stderr.splitlines()):
   if len(line)>2 and line[2] in protocol['events']:counters[line[2]]=int(float(line[0]))
  assert set(counters)==set(protocol['events'])
  rows.append(dict(index=index,mode=mode,source=source,command=cmd,counters=counters,all_pixels_exact_offline=True));(out/'receipt.json').write_text(json.dumps(dict(complete=False,protocol_sha256=h(out/'protocol.json'),rows=rows),indent=2)+'\n');print(mode,source,counters,flush=True)
(out/'receipt.json').write_text(json.dumps(dict(complete=True,protocol_sha256=h(out/'protocol.json'),rows=rows),indent=2)+'\n')
