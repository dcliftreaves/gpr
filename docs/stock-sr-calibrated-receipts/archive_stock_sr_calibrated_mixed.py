"""Audit calibration study, bind Mac/Pi validation and archive nonmedia evidence."""
from pathlib import Path
import hashlib,json,math,shutil,subprocess
import numpy as np
import torch
REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime')
BASE=Path('/Volumes/OWC_8TB/gpr_work/artifacts');DATA=BASE/'stock_sr_mission_calibrated_20261031';TRAIN=BASE/'stock_sr_calibrated_mixed_20261031'
DEST=REPO/'docs/stock-sr-calibrated-receipts'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def save(p,o):p.write_text(json.dumps(o,indent=2)+'\n')
def copy(source,path):path.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,path)
def main():
    DEST.mkdir(exist_ok=False);p=load(TRAIN/'protocol.json');t=load(TRAIN/'training.json');b=load(TRAIN/'baseline.json');pairs=load(DATA/'pair-audit.json');info=load(DATA/'dataset/dataset.json');calib=load(DATA/'calibration-audit.json')
    assert t['complete'] and t['protocol_sha256']==sha(TRAIN/'protocol.json') and t['baseline_sha256']==sha(TRAIN/'baseline.json') and pairs['complete'] and pairs['patches_verified']==1088
    assert p['camera_dataset_sha256']==sha(DATA/'dataset/dataset.json')==pairs['dataset_sha256'] and calib['complete'] and calib['direct_source_corroborated']==10
    assert sha(DATA/'dataset/inputs.npy')==info['input_sha256']==pairs['input_sha256'] and sha(DATA/'dataset/targets.npy')==info['target_sha256']==pairs['target_sha256']
    assert len(info['sources'])==42 and all(s['patch_count']==0 and s['patch_start'] is None for s in info['sources'] if s['split']=='test')
    data2=BASE/'stock_sr_mission_calibrated_20261031-metadata-v2';corrected=load(data2/'dataset/dataset.json');carrier=load(data2/'carrier-proof.json');pairs2=load(data2/'pair-audit.json')
    assert corrected['complete'] and carrier['complete'] and carrier['all_arrays_byte_identical'] and carrier['training_features_and_coordinates_unchanged']
    assert pairs2['complete'] and pairs2['patches_verified']==1088
    assert corrected['input_sha256']==info['input_sha256']==sha(data2/'dataset/inputs.npy') and corrected['target_sha256']==info['target_sha256']==sha(data2/'dataset/targets.npy')
    assert load(data2/'protocol.json')['sdk_sha256']==sha(REPO/'build-runtime/source/app/gpr_tools/gpr_tools')
    prior=load(BASE/'stock_sr_source_regions_20261030/selection.json')['baseline_regions']
    for g,d in prior.items():
        if g.startswith('group:'):assert b['regions']['nikon:'+g.removeprefix('group:')]==d
    assert len(p['sources'])==46 and len(p['family'])==len(t['cases'])==4
    verdicts=[]
    for case in t['cases']:
        assert case['case'] in p['family'] and [r['step'] for r in case['checkpoints']]==[400,800]
        for c in case['checkpoints']:
            path=Path(c['path']);assert sha(path)==c['checkpoint_sha256'];checkpoint=torch.load(path,map_location='cpu',weights_only=True)
            assert checkpoint['case']==case['case'] and checkpoint['step']==c['step'] and checkpoint['protocol_sha256']==sha(TRAIN/'protocol.json')
            bad=[g+':'+r for g,d in b['regions'].items() for r,v in d.items() if c['metrics']['regions'][g][r]>v]
            tonebad=[g for g,v in b['tone_proxy_mse'].items() if c['metrics']['tone_proxy_mse'][g]>v]
            gain=10*math.log10(b['regions']['pooled']['overall']/c['metrics']['regions']['pooled']['overall'])
            assert bad==c['raw_regressions'] and tonebad==c['tone_proxy_regressions'] and math.isclose(gain,c['gain_db'],abs_tol=1e-11)
            assert c['eligible']==(not bad and not tonebad and gain>0)
            verdicts.append(dict(case=case['case']['name'],step=c['step'],gain_db=gain,tone_proxy_gain_db=10*math.log10(b['tone_proxy_mse']['pooled']/c['metrics']['tone_proxy_mse']['pooled']),raw_regressions=bad,tone_proxy_regressions=tonebad,eligible=c['eligible']))
    assert len(verdicts)==8 and not any(r['eligible'] for r in verdicts)
    pi=load(Path('/Users/dcliftreaves/Documents/slop/gpr_check/analysis/stock_sr_mission_pi_final_hashes.json'))
    assert pi['source/app/gpr_tools/gpr_parse_utils.cpp']==sha(REPO/'source/app/gpr_tools/gpr_parse_utils.cpp') and pi['tests/stock_still_test.py']==sha(REPO/'tests/stock_still_test.py')
    assert pi['build-runtime/gpr_capture_app']=='c576f5662ac605cc5719ae536308e9ff71cdcec4f4e714343a5a919a5711687c'
    for platform in ['mac','pi']:
        log=Path('/Users/dcliftreaves/Documents/slop/gpr_check/analysis')/('stock_sr_mission_'+platform+'_final_tests.stdout')
        assert '100% tests passed, 0 tests failed out of 3' in log.read_text()
        copy(log,DEST/'validation'/log.name);copy(log.with_suffix('.stderr'),DEST/'validation'/log.with_suffix('.stderr').name)
        for ending in ['stdout','stderr']:
            file=log.with_name('stock_sr_mission_'+platform+'_final_build.'+ending);copy(file,DEST/'validation'/file.name)
    validation=dict(schema='gpr.stock_sdk_gainmap_fix_validation.v1',complete=True,parser_source_sha256=sha(REPO/'source/app/gpr_tools/gpr_parse_utils.cpp'),test_source_sha256=sha(REPO/'tests/stock_still_test.py'),mac_sdk_sha256=sha(REPO/'build-runtime/source/app/gpr_tools/gpr_tools'),pi_hashes=pi,focused_ctests=['sdk_c_api','raw_media','stock_still'],mac_and_pi_all_three_passed=True,large_gainmap_sides=[9,65,97],exact_tested_pixels_and_opcode_bytes=True,dataset_producer_sdk_sha256=load(DATA/'protocol.json')['sdk_sha256'],dataset_producer_source_sha256=sha(DATA/'producer-gpr_parse_utils.cpp'),producer_executable_retained_external=sha(DATA/'producer-gpr_tools')==load(DATA/'protocol.json')['sdk_sha256'],producer_note='Dataset used vector-buffer fix before JSON ownership cleanup. Exact producer executable/source retained externally; final shipped CLI adds JSON cleanup and reruns all focused tests.')
    save(DEST/'validation/receipt.json',validation)
    for root,label,files in [(DATA,'camera-data',['protocol.json','calibration-audit.json','pair-audit.json','dataset/dataset.json','build_stock_sr_mission_calibrated.py','producer-gpr_parse_utils.cpp']),
                             (TRAIN,'training',['protocol.json','baseline.json','training.json','affine-audit.json','train_stock_sr_calibrated_mixed.py'])]:
        for file in files:copy(root/file,DEST/label/file)
    for file in ['protocol.json','calibration-audit.json','pair-audit.json','dataset/dataset.json','carrier-proof.json','build_stock_sr_mission_calibrated_v2.py']:
        copy(data2/file,DEST/'camera-data-v2'/file)
    copy(Path(__file__).with_name('audit_stock_sr_mission_calibrated_v2.py'),DEST/'audit_stock_sr_mission_calibrated_v2.py')
    for file in ['mission1_sr_models.py','mission1_sr_runtime.py','train_mission1_sr.py']:copy(TRAIN/file,DEST/'historical-code'/file)
    initial=DATA.with_name(DATA.name+'-initial-sdk-gainmap-overflow')
    for file in ['protocol.json','initial-reproduce.json','initial-reproduce.stderr','initial-driver.stderr','initial-gpr_parse_utils.cpp','build_stock_sr_mission_calibrated.py']:copy(initial/file,DEST/'initial-sdk-map-overflow'/file)
    copy(Path(__file__),DEST/Path(__file__).name)
    copy(Path(__file__).with_name('audit_stock_sr_mission_calibrated.py'),DEST/'audit_stock_sr_mission_calibrated.py')
    ci=json.loads(subprocess.check_output(['gh','run','view','41171261012','--repo','dcliftreaves/gpr','--json','headSha,status,conclusion,url,jobs']))
    assert ci['headSha']=='49042a283bad688c420409e8596e66590f88cb2f' and ci['conclusion']=='success' and len(ci['jobs'])==7 and all(r['conclusion']=='success' for r in ci['jobs']);save(DEST/'passed-49042a2.json',ci)
    report=dict(schema='gpr.stock_sr_calibrated_mixed_delivery_audit.v1',complete=True,source_calibration_archives=42,direct_source_corroborated=10,regenerated_non_test_references=34,independently_verified_camera_patches=1088,training_updates=3200,patch_checkpoints=8,eligible=0,full_or_final_evaluation=False,nikon_baseline_groups_exact=True,corrected_profile_carrier_verified=True,v1_v2_training_arrays_and_used_features_identical=True,verdicts=verdicts,quality_approval=False,original_gprs_freshly_decoded=False)
    save(DEST/'audit.json',report)
    entries=[]
    for file in sorted(DEST.rglob('*')):
        if file.is_file() and file.name!='manifest.json':
            assert file.suffix not in ['.raw','.pt','.npy','.dng','.GPR','.png','.jpg','.tiff']
            entries.append(dict(path=str(file.relative_to(DEST)),sha256=sha(file),bytes=file.stat().st_size))
    save(DEST/'manifest.json',dict(schema='gpr.stock_sr_calibrated_mixed_manifest.v1',files=entries,media_and_weights_uploaded=False))
    print(json.dumps(dict(complete=True,training_updates=3200,patch_checkpoints=8,eligible=0,archived_files=len(entries))))
if __name__=='__main__':main()
