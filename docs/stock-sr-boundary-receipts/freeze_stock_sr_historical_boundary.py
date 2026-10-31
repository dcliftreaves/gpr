"""Independently audit complete-family selection, then freeze once before finals."""
from pathlib import Path
import hashlib,json,math
ROOT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_historical_boundary_20261031')
OLD=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_historical_global_shadow_20261030')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def save(p,o):p.write_text(json.dumps(o,indent=2)+'\n')
def main():
    p=load(ROOT/'protocol.json');patch=load(ROOT/'patch-selection.json');full=load(ROOT/'full-selection.json')
    assert patch['complete'] and full['complete'] and full['patch_sha256']==sha(ROOT/'patch-selection.json')
    assert p['driver_sha256']==sha(ROOT/'evaluate_stock_sr_historical_boundary.py') and p['boundary_source_sha256']==sha(ROOT/'stock_sr_historical_boundary.py')
    assert full['protocol_sha256']==patch['protocol_sha256']==sha(ROOT/'protocol.json')
    eligible=[]
    for row in patch['rows']:
        bad=[g+':'+r for g,d in patch['baseline'].items() for r,v in d.items() if row['metrics'][g][r]>v]
        assert bad==row['regressions'] and row['eligible']==(not bad and row['metrics']['pooled']['overall']<patch['baseline']['pooled']['overall'])
        if row['eligible']:eligible.append(row)
    candidates=[dict(**c,edge=edge,id=edge+'-'+c['name']) for c in eligible for edge in p['edge_policies']]
    names=[c['id'] for c in candidates];assert len(full['sources'])==4
    totals={n:0. for n in names};bad={n:[] for n in names};bt=0.;samples_total=0;output_count=0
    for index,s in enumerate(full['sources']):
        assert [r['id'] for r in s['candidates']]==names
        b=s['bicubic_metrics'];t,l,bottom,right=b['active_area'];samples=(bottom-t)*(right-l);samples_total+=samples;bt+=samples*b['active']['rmse_counts']**2
        for r in s['candidates']:
            name=r['id'];assert sha(ROOT/f'{index}-{name}.raw')==r['output_sha256'];output_count+=1
            failed=[key for key in ['active','shadow_bottom_decile','highlight_top_decile','detail_top_decile'] if r['metrics'][key]['rmse_counts']>b[key]['rmse_counts']]
            assert failed==r['regressions'];bad[name].extend(dict(source_index=index,region=key) for key in failed);totals[name]+=samples*r['metrics']['active']['rmse_counts']**2
    assert samples_total==full['active_samples'] and bt/samples_total==full['baseline_active_mse']
    for r in full['results']:
        name=r['id'];assert r['regressions']==bad[name] and r['active_mse']==totals[name]/samples_total
        assert r['eligible']==(not bad[name] and totals[name]<bt) and math.isclose(r['gain_db'],10*math.log10(bt/totals[name]),abs_tol=1e-11)
    qualified=[r for r in full['results'] if r['eligible']];selected=min(qualified,key=lambda r:r['active_mse']) if qualified else None;assert selected==full['selected']
    cp=OLD/'local_shadow/step-400.pt';assert sha(cp)==p['model_sha256']
    checks=load(ROOT/'tiler-checks.json');assert checks['complete'] and len(checks['checks'])==3 and all(r['historical_identity'] and r['full_reflected_max_counts']<=1 for r in checks['checks'])
    audit=dict(schema='gpr.stock_sr_historical_boundary_selection_audit.v1',complete=True,driver_sha256=sha(Path(__file__)),full_selection_sha256=sha(ROOT/'full-selection.json'),patch_candidates=len(patch['rows']),patch_qualified=len(eligible),full_candidates=len(candidates),full_image_outputs=output_count,eligible_full_candidates=len(qualified),selected=selected,quality_approval=False)
    save(ROOT/'selection-audit.json',audit)
    if selected is not None:
        assert not (ROOT/'frozen.json').exists() and not (ROOT/'final-summary.json').exists() and not (ROOT/'final-protocol.json').exists()
        c=selected['candidate'];candidate={key:c[key] for key in ['name','id','alpha','ramps','edge']}
        save(ROOT/'frozen.json',dict(schema='gpr.stock_sr_historical_boundary_freeze.v1',candidate=candidate,checkpoint_path=str(cp),checkpoint_sha256=sha(cp),boundary_source_sha256=p['boundary_source_sha256'],model_source_sha256=sha(ROOT/'mission1_sr_models.py'),historical_runtime_source_sha256=sha(ROOT/'mission1_sr_runtime.py'),protocol_sha256=sha(ROOT/'protocol.json'),patch_selection_sha256=sha(ROOT/'patch-selection.json'),full_selection_sha256=sha(ROOT/'full-selection.json'),selection_audit_sha256=sha(ROOT/'selection-audit.json'),final_reference_pixels_used=False,quality_approval=False,scope='Frozen analysis-only Nikon diagnostic; no model/backend/native/Pi/visible-detail promotion.'))
    print(json.dumps(audit))
if __name__=='__main__':main()
