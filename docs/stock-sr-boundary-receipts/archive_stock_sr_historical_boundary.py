"""Verify frozen outputs and archive nonmedia evidence only."""
from pathlib import Path
import hashlib,json,math,shutil,subprocess,sys
import numpy as np
ROOT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_historical_boundary_20261031')
REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime');sys.path.insert(0,str(REPO/'tools'))
import raw_media
DEST=REPO/'docs/stock-sr-boundary-receipts'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def save(p,o):p.write_text(json.dumps(o,indent=2)+'\n')
def main():
    DEST.mkdir(exist_ok=False);full=load(ROOT/'full-selection.json');audit=load(ROOT/'selection-audit.json');frozen=load(ROOT/'frozen.json');final=load(ROOT/'final-summary.json');fp=load(ROOT/'final-protocol.json')
    assert full['complete'] and audit['complete'] and audit['full_image_outputs']==104 and audit['full_candidates']==26 and audit['patch_qualified']==13
    assert audit['full_selection_sha256']==sha(ROOT/'full-selection.json')==frozen['full_selection_sha256']
    assert fp['freeze_sha256']==sha(ROOT/'frozen.json') and final['protocol_sha256']==sha(ROOT/'final-protocol.json') and final['complete']
    for source_index,s in enumerate(full['sources']):
        assert len(s['candidates'])==26
        for r in s['candidates']:assert sha(ROOT/f"{source_index}-{r['id']}.raw")==r['output_sha256']
    assert len(final['results'])==8
    for device in ['mps','cpu']:
        total=0.;bt=0.
        for r in [r for r in final['results'] if r['device']==device]:
            assert sha(ROOT/(device+'-'+r['name']+'.raw'))==r['output_sha256']
            t,l,b,right=r['bicubic_metrics']['active_area'];n=(b-t)*(right-l)
            total+=n*r['metrics']['active']['rmse_counts']**2;bt+=n*r['bicubic_metrics']['active']['rmse_counts']**2
            bad=[key for key in ['active','shadow_bottom_decile','highlight_top_decile','detail_top_decile'] if r['metrics'][key]['rmse_counts']>r['bicubic_metrics'][key]['rmse_counts']];assert bad==r['regressions']
        assert math.isclose(final[device+'_pooled_gain_db'],10*math.log10(bt/total),abs_tol=1e-11)
    assert final['all_regions_pass']==all(not r['regressions'] for r in final['results'])
    for r in final['portability']:
        a=np.fromfile(ROOT/('cpu-'+r['reference']+'.raw'),dtype='<u2');b=np.fromfile(ROOT/('mps-'+r['reference']+'.raw'),dtype='<u2');delta=np.abs(a.astype(np.int32)-b.astype(np.int32))
        assert int(delta.max())==r['max_counts'] and int(np.count_nonzero(delta))==r['changed_counts'] and r['pass_budget']==bool(delta.max()<=1)
    gopro=load(ROOT/'gopro/summary.json');assert gopro['complete'] and sha(ROOT/'gopro/restored.raw')==gopro['output_raw_sha256'] and sha(ROOT/'gopro/restored.dng')==gopro['editable_dng_sha256']
    assert not gopro['regressions'] and gopro['independent_editable_pixels_exact'] and gopro['supported_high_calibration_exact']
    render=load(ROOT/'render-review/summary.json');ra=load(ROOT/'render-review/audit.json');assert render['complete'] and ra['complete'] and ra['gate_zero_output_equals_bicubic']
    for name,s in ra['scores'].items():
        assert s['independent_agreement'] and sha(ROOT/'render-review'/(name+'.tiff'))==render['tiff_sha256'][name]
        for key in ['rgb_mse','y_prime_mse']:assert math.isclose(s[key],render['scores'][name][key],rel_tol=1e-10)
    assert sha(ROOT/'render-review/comparison.png')==render['comparison_png_sha256']
    # Source metadata audit: established datasets, no new training/selection.
    dataset=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_20261028/dataset/dataset.json');metadata=[]
    for source in load(dataset)['sources']:
        if source['split']!='train':continue
        path=Path(source['path']);assert sha(path)==source['sha256'];m=raw_media.extract(path,14);tags={t['code']:t for t in m['image']}
        metadata.append(dict(source_sha256=sha(path),split='train',black_level=raw_media.values(tags[50714]),white_level=raw_media.values(tags[50717])))
    calibration=dict(complete=True,dataset_sha256=sha(dataset),training_sources=metadata,gopro_black_level=ra['gopro_black_level'],gate_black_level_normalized=False,gate_zero_fraction=ra['gate_zero_fraction'],gate_zero_output_equals_bicubic=True,quality_approval=False)
    save(ROOT/'calibration-audit.json',calibration)
    for path in [Path(__file__),Path(__file__).with_name('freeze_stock_sr_historical_boundary.py'),Path(__file__).with_name('audit_stock_sr_historical_boundary_render.py')]:shutil.copy2(path,ROOT/path.name)
    # Only explicit nonmedia suffixes, never model weights, TIFFs, PNGs or RAWs.
    for directory in [ROOT,ROOT/'gopro',ROOT/'render-review']:
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.suffix in ('.json','.py','.stderr'):
                target=DEST/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
    ci=json.loads(subprocess.check_output(['gh','run','view','41170318072','--repo','dcliftreaves/gpr','--json','headSha,status,conclusion,url,jobs']))
    assert ci['headSha']=='c7125abd8799a36ba88a0533cf7ad938afc4750a' and ci['conclusion']=='success' and len(ci['jobs'])==7 and all(r['conclusion']=='success' for r in ci['jobs'])
    save(DEST/'passed-c7125ab.json',ci)
    report=dict(schema='gpr.stock_sr_historical_boundary_delivery_audit.v1',complete=True,full_candidates=26,full_image_candidate_outputs_verified=104,final_reference_device_outputs_verified=8,final_regional_checks=32,goPro_regional_checks=4,selected=full['selected']['id'],full_gain_db=full['selected']['gain_db'],historical_final_gain_db=final['mps_pooled_gain_db'],goPro_raw_gain_db=gopro['active_gain_db'],goPro_rendered_rgb_gain_db=render['new_rgb_gain_db'],supplied_model_rendered_rgb_gain_db=render['supplied_rgb_gain_db'],production_changed=False,quality_approval=False,scope='RAW-fidelity diagnostic passes declared numeric guards; rendered result inferior to supplied model, no quality replacement or production/native promotion.')
    save(DEST/'delivery-audit.json',report)
    entries=[dict(path=str(p.relative_to(DEST)),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(DEST.rglob('*')) if p.is_file() and p.name!='manifest.json']
    save(DEST/'manifest.json',dict(schema='gpr.stock_sr_historical_boundary_manifest.v1',files=entries,media_or_model_weights_uploaded=False))
    print(json.dumps(report))
if __name__=='__main__':main()
