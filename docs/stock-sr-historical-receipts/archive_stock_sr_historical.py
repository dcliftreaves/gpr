"""Audit and archive only nonmedia evidence for historical stock SR studies."""
from pathlib import Path
import hashlib,json,math,shutil
import numpy as np
import torch

BASE=Path('/Volumes/OWC_8TB/gpr_work/artifacts')
DEST=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime/docs/stock-sr-historical-receipts')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def save(p,o):p.write_text(json.dumps(o,indent=2)+'\n')
def copy(source,dest):dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)

def main():
    report=dict(schema='gpr.stock_sr_historical_evidence_audit.v1',complete=False,quality_approval=False,studies=[],training_updates=0,full_image_candidate_inferences=0,
        checkpoint_serialization_note='Trainer writes step200/400 once with step/protocol metadata, then overwrites the same path with candidate metadata. Checkpoint-event hashes refer to the earlier serialization; final candidate hashes bind the actual evaluated files. Interpolation identities below use those final state dictionaries, not discarded serialization bytes.')
    baseline=None
    for label,name in [('recipe','stock_sr_historical_recipe_20261030'),('local-shadow','stock_sr_historical_shadow_20261030'),('global-shadow','stock_sr_historical_global_shadow_20261030')]:
        root=BASE/name;t=load(root/'training.json');p=load(root/'protocol.json')
        assert t['complete'] and not t['quality_approval'] and sha(root/'protocol.json')==t['protocol_sha256']
        assert sha(root/'mission1_sr_models.py')==p['old_model_source_sha256'] and sha(root/'mission1_sr_runtime.py')==p['old_runtime_source_sha256']
        driver=root/next(k.name for k in root.glob('train_stock_sr_historical*.py'));assert sha(driver)==p['driver_sha256']
        assert sha(root/'train_mission1_sr.py')==p['located_trainer_sha256']
        if baseline is None:baseline=t['baseline']
        assert baseline==t['baseline']
        rows=[];qualified=[]
        for case in t['cases']:
            report['training_updates']+=p['steps'];assert [s['step'] for s in case['checkpoints']]==[1,200,400]
            for c in case['candidates']:
                cp=Path(c['path']);assert sha(cp)==c['checkpoint_sha256'];ck=torch.load(cp,map_location='cpu',weights_only=True)
                assert ck['config']==p['config']
                if c['weight_interpolation']:
                    start=torch.load(cp.parent/'step-1.pt',map_location='cpu',weights_only=True)['model']
                    end=torch.load(cp.parent/f"step-{c['step']}.pt",map_location='cpu',weights_only=True)['model']
                    assert all(torch.equal((start[k]+end[k])*.5,v) for k,v in ck['model'].items())
                bad=[g+':'+r for g,regions in baseline.items() for r,x in regions.items() if c['metrics'][g][r]>x]
                assert c['regressions']==bad and c['eligible']==(not bad and c['metrics']['pooled']['overall']<baseline['pooled']['overall'])
                assert math.isclose(c['gain_db'],10*math.log10(baseline['pooled']['overall']/c['metrics']['pooled']['overall']),abs_tol=1e-11)
                if c['eligible']:qualified.append(c['name'])
                rows.append(dict(name=c['name'],gain_db=c['gain_db'],eligible=c['eligible'],regressions=bad))
        row=dict(study=label,torch=t['torch'],patch_candidates=rows,eligible_patch_candidates=qualified)
        files=['protocol.json','training.json','historical-receipt-extract.json',driver.name]
        if label!='recipe':
            a=load(root/'shadow-weight-audit.json')
            assert a['complete'] and a['nontraining_masks_zero'] and a['nontraining_norm_unset']
            assert sha(root/'training-shadow-masks.npy')==a['masks_sha256'] and sha(root/'training-shadow-norm.npy')==a['norm_sha256']
            files.append('shadow-weight-audit.json')
        if label=='global-shadow':
            a=load(root/'global-shadow-audit.json');assert a['complete'] and len(a['rows'])==8 and a['nontraining_masks_zero']
            assert sha(root/'training-global-shadow-masks.npy')==a['masks_sha256'] and sha(root/'training-global-shadow-norm.npy')==a['norm_sha256']
            assert all(r['source_pixels_and_crop_targets_exact'] for r in a['rows'])
            files.extend(['global-shadow-audit.json','shadow-attribution-protocol.json','shadow-attribution.json'])
        if qualified:
            fullroot=root/'full-validation';f=load(fullroot/'selection.json');fp=load(fullroot/'protocol.json')
            assert f['complete'] and len(f['sources'])==4 and f['protocol_sha256']==sha(fullroot/'protocol.json') and fp['training_sha256']==sha(root/'training.json')
            assert [c['name'] for c in fp['candidates']]==qualified
            count=0;bt=0.;ns=0;total={n:0. for n in qualified};bad={n:[] for n in qualified}
            for index,source in enumerate(f['sources']):
                assert [c['name'] for c in source['candidates']]==qualified
                bm=source['bicubic_metrics'];top,left,bottom,right=bm['active_area'];samples=(bottom-top)*(right-left);ns+=samples;bt+=samples*bm['active']['rmse_counts']**2
                for c in source['candidates']:
                    output=fullroot/(str(index)+'-'+c['name']+'.raw');assert sha(output)==c['output_sha256'];count+=1
                    names=['active','shadow_bottom_decile','highlight_top_decile','detail_top_decile']
                    reg=[r for r in names if c['metrics'][r]['rmse_counts']>bm[r]['rmse_counts']];assert reg==c['regressions']
                    total[c['name']]+=samples*c['metrics']['active']['rmse_counts']**2
                    bad[c['name']].extend(dict(source_index=index,region=r) for r in reg)
            assert count==4*len(qualified) and ns==f['active_samples'] and bt/ns==f['baseline_active_mse']
            for c in f['results']:
                assert bad[c['name']]==c['regressions'] and c['active_mse']==total[c['name']]/ns
                assert c['eligible']==(not bad[c['name']] and total[c['name']]<bt)
                assert math.isclose(c['gain_db'],10*math.log10(bt/total[c['name']]),abs_tol=1e-11)
            eligible=[r for r in f['results'] if r['eligible']]
            assert f['selected']==(min(eligible,key=lambda r:r['active_mse']) if eligible else None)
            row['full_results']=f['results'];row['selected']=f['selected'];report['full_image_candidate_inferences']+=count
            files.extend(['full-validation/protocol.json','full-validation/selection.json',next('full-validation/'+k.name for k in fullroot.glob('evaluate*.py'))])
        for file in files:copy(root/file,DEST/label/file)
        report['studies'].append(row)
    old=BASE/'stock_sr_historical_shadow_20261030'
    for name in ('mission1_sr_models.py','mission1_sr_runtime.py','train_mission1_sr.py'):copy(old/name,DEST/'historical-code'/name)
    for label,path,files in [
        ('initial-import-setup',BASE/'stock_sr_historical_recipe_20261030-initial-import-setup',['setup-error.txt','train_stock_sr_historical_recipe.py']),
        ('initial-missing-imagecodecs',BASE/'stock_sr_historical_global_shadow_20261030-initial-missing-imagecodecs',['protocol.json','initial.stderr','train_stock_sr_historical_global_shadow.py'])]:
        assert not (path/'training.json').exists()
        for file in files:copy(path/file,DEST/label/file)
    copy(Path(__file__),DEST/Path(__file__).name)
    copy(Path(__file__).with_name('diagnose_stock_sr_historical_shadows.py'),DEST/'diagnose_stock_sr_historical_shadows.py')
    report.update(complete=True,final_reference_evaluation=False,production_changed=False)
    save(DEST/'audit.json',report)
    entries=[]
    for path in sorted(DEST.rglob('*')):
        if path.is_file() and path.name!='manifest.json':
            assert path.suffix not in ('.raw','.dng','.gpr','.pt','.npy','.png','.jpg')
            entries.append(dict(path=str(path.relative_to(DEST)),sha256=sha(path),bytes=path.stat().st_size))
    save(DEST/'manifest.json',dict(schema='gpr.stock_sr_historical_manifest.v1',files=entries,media_and_weights_uploaded=False))
    print(json.dumps(dict(complete=True,training_updates=report['training_updates'],full_image_candidate_inferences=report['full_image_candidate_inferences'],archived_files=len(entries))))
if __name__=='__main__':main()
