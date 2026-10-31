"""Isolated source-only Pi QA; production executable and scheduling stay untouched."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,time
ROOT=Path(__file__).resolve().parent;BASE=Path('/mnt/ssd/gpr_work/stock-raw-media-runtime/build-runtime');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
paths=dict(sdk=BASE/'source/app/gpr_tools/gpr_tools',decoder=BASE/'source/app/stock_video/stock_video',capture=BASE/'gpr_capture_app',probe=BASE/'sdk_bayer_probe',bridge=BASE.parent/'build-mov/gpr_mov')
assert all(p.is_file() for p in paths.values()),paths
manifest=json.loads((ROOT/'source-manifest.json').read_text())
for name,digest in manifest.items():assert sha(ROOT/name)==digest,name
report=dict(schema='gpr.stock_gainmap_pi_qa.v1',complete=False,uid=os.geteuid(),source_manifest_sha256=sha(ROOT/'source-manifest.json'),production_capture_sha256=sha(paths['capture']),binary_sha256={name:sha(path) for name,path in paths.items()},tests=[],metadata_roundtrips=[])
assert report['uid']==1000
commands=[('raw-media',[sys.executable,str(ROOT/'tests/raw_media_test.py'),'--sdk',str(paths['sdk']),'--decoder',str(paths['decoder']),'--capture',str(paths['capture']),'--sdk-probe',str(paths['probe'])]),('cnn',[sys.executable,str(ROOT/'tests/stock_cnn_test.py'),'--sdk',str(paths['sdk']),'--capture',str(paths['capture']),'--decoder',str(paths['decoder'])]),('upres',[sys.executable,str(ROOT/'tests/stock_upres_test.py'),'--sdk',str(paths['sdk']),'--bridge',str(paths['bridge'])]),('sequence',[sys.executable,str(ROOT/'tests/stock_sequence_test.py'),'--sdk',str(paths['sdk']),'--bridge',str(paths['bridge'])])]
for name,cmd in commands:
 start=time.monotonic()
 with (ROOT/(name+'.log')).open('w') as log:p=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,cwd=ROOT)
 row=dict(name=name,returncode=p.returncode,elapsed_s=time.monotonic()-start,log_sha256=sha(ROOT/(name+'.log')));report['tests'].append(row);(ROOT/'receipt.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(row),flush=True)
sys.path.insert(0,str(ROOT/'tools'));import raw_media,stock_cnn_metadata,stock_still
for path in sorted((ROOT/'metadata').glob('*.json')):
 meta=json.loads(path.read_text());low,_=stock_cnn_metadata.simulated_half(meta);high,_=stock_cnn_metadata.scaled(low,2);expected=dict(meta);expected['image']=[t for t in meta['image'] if t['code']!=700]
 assert stock_still.canonical(high)==stock_still.canonical(expected),path.name
 report['metadata_roundtrips'].append(dict(name=path.name,metadata_file_sha256=sha(path),high_roundtrip_exact=True))
assert len(report['metadata_roundtrips'])==3
report.update(complete=True,passed=all(r['returncode']==0 for r in report['tests']))
(ROOT/'receipt.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(complete=True,passed=report['passed'])),flush=True)
sys.exit(0 if report['passed'] else 1)
