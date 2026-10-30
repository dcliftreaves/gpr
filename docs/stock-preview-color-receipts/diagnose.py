from pathlib import Path
import hashlib,json,os,subprocess,sys
repo=Path('/mnt/ssd/gpr_work/stock-raw-media-runtime');root=Path('/mnt/ssd/gpr_work/stock-preview-color-prototype-20261030');out=root/'diagnostic';out.mkdir(exist_ok=True);sys.path.insert(0,str(repo/'tools'));import benchmark_mission1 as bench
cache=dict(page_size=os.sysconf('SC_PAGE_SIZE'),caches=[])
for d in Path('/sys/devices/system/cpu/cpu0/cache').glob('index*'):cache['caches'].append({n:(d/n).read_text().strip() for n in ['level','type','size','coherency_line_size','number_of_sets','ways_of_associativity']})
(out/'cache.json').write_text(json.dumps(cache,indent=2)+'\n');base=json.loads((root/'command-template.json').read_text())[1]['command'];seed=Path('/mnt/ssd/gpr_work/pi-mission1-writeback8-20261030');inputs=json.loads((seed/'receipt.json').read_text())['inputs'];metadata=[json.loads(Path(base[i+1]).read_text()) for i,s in enumerate(base) if s=='--source-metadata'];offline={r['index']:r for r in map(json.loads,(seed/'offline.jsonl').read_text().splitlines()) if r['event']=='preview'}
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();rows=[];env={k:v for k,v in os.environ.items() if not k.startswith('GPR_')}
for mode in ['diagnostic-dense','diagnostic-colored']:
 cmd=base.copy();cmd[0]=str(root/('build-'+mode)/'gpr_capture_app');cmd[cmd.index('--frames')+1]='4';clip=out/(mode+'.gvid');cmd[cmd.index('--output')+1]=str(clip);events=bench.run(cmd,out/(mode+'.jsonl'),environment=env);v=bench.verify(clip,events,metadata,[s['reference_payload_sha256'] for s in inputs],offline)
 layouts=[json.loads(line) for line in (out/(mode+'.jsonl.stderr')).read_text().splitlines() if line.startswith('{"event":"layout"')];assert len(layouts)==4
 if mode=='diagnostic-dense':assert all(len(set(s['plane_mod16384']))==1 for s in layouts)
 else:assert all(s['plane_mod16384']==[(s['plane_mod16384'][0]+c*128)%16384 for c in range(3)] for s in layouts)
 rows.append(dict(mode=mode,binary_sha256=h(Path(cmd[0])),command=cmd,layout=layouts,verified=v));print(mode,layouts[0],flush=True)
(out/'receipt.json').write_text(json.dumps(dict(complete=True,scope='untimed pointer/correctness diagnostic, not performance evidence',rows=rows),indent=2)+'\n')
