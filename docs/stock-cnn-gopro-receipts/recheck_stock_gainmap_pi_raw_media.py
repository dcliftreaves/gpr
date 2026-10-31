from pathlib import Path
import hashlib,json,subprocess,sys,os,time
ROOT=Path(__file__).resolve().parent;OLD=ROOT/'initial-missing-fixtures';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
prior=json.loads((OLD/'receipt.json').read_text());before=json.loads((OLD/'source-manifest.json').read_text());after=json.loads((ROOT/'source-manifest.json').read_text());assert prior['complete'] and not prior['passed']
assert all(after[name]==digest for name,digest in before.items())
assert all(name.startswith('tests/fixtures/') for name in set(after)-set(before))
for name,digest in after.items():assert sha(ROOT/name)==digest
base=Path('/mnt/ssd/gpr_work/stock-raw-media-runtime/build-runtime');paths=dict(sdk=base/'source/app/gpr_tools/gpr_tools',decoder=base/'source/app/stock_video/stock_video',capture=base/'gpr_capture_app',probe=base/'sdk_bayer_probe',bridge=base.parent/'build-mov/gpr_mov')
assert {name:sha(path) for name,path in paths.items()}==prior['binary_sha256']
cmd=[sys.executable,str(ROOT/'tests/raw_media_test.py'),'--sdk',str(paths['sdk']),'--decoder',str(paths['decoder']),'--capture',str(paths['capture']),'--sdk-probe',str(paths['probe'])]
started=time.monotonic()
with (ROOT/'raw-media.log').open('w') as log:result=subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
row=dict(name='raw-media',returncode=result.returncode,elapsed_s=time.monotonic()-started,log_sha256=sha(ROOT/'raw-media.log'))
reused=[r for r in prior['tests'] if r['name']!='raw-media'];assert len(reused)==3 and all(r['returncode']==0 for r in reused)
for r in reused:assert sha(ROOT/(r['name']+'.log'))==r['log_sha256']
for r in prior['metadata_roundtrips']:assert sha(ROOT/'metadata'/r['name'])==r['metadata_file_sha256']
report=dict(prior,complete=True,passed=result.returncode==0,tests=[row]+reused,source_manifest_sha256=sha(ROOT/'source-manifest.json'),initial_receipt_sha256=sha(OLD/'receipt.json'),reused_passed_tests=[r['name'] for r in reused],recheck_driver_sha256=sha(Path(__file__)),fixture_fix='copy original test fixtures into isolated snapshot; source/binaries unchanged',observer_uid=os.geteuid(),observer_policy=os.sched_getscheduler(0),observer_nice=os.getpriority(os.PRIO_PROCESS,0),rt_runtime_us=Path('/proc/sys/kernel/sched_rt_runtime_us').read_text().strip())
assert report['observer_uid']==1000 and report['observer_policy']==0 and report['observer_nice']==0 and report['rt_runtime_us']=='950000'
assert {name:sha(path) for name,path in paths.items()}==prior['binary_sha256']
(ROOT/'receipt.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(raw_media=row,passed=report['passed'])),flush=True);sys.exit(0 if report['passed'] else 1)
