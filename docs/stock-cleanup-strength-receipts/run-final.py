"""Evaluate the frozen candidate once; never select strengths from these results."""
import contextlib
import hashlib
import json
from pathlib import Path
import sys

REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime')
sys.path.insert(0,str(REPO/'tools'))
import benchmark_stock_cnn

root=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_cleanup_strength_20261030')
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
freeze=json.loads((root/'frozen.json').read_text())
assert digest(root/'selected.pt')==freeze['checkpoint_sha256']
sdk=REPO/'build-runtime/source/app/gpr_tools/gpr_tools'
assert digest(sdk)==freeze['sdk_sha256']
benchmarks=json.loads((root/'benchmark-inputs.json').read_text());results=[]
progress=dict(schema='gpr.stock_cleanup_strength_final.v1',complete=False,started=True,
    quality_approval=False,checkpoint_sha256=freeze['checkpoint_sha256'],
    freeze_sha256=digest(root/'frozen.json'),final_pixels_used_for_selection=False,results=results)
(root/'final-progress.json').write_text(json.dumps(progress,indent=2)+'\n')
for name,benchmark in benchmarks.items():
    source=Path('/Users/dcliftreaves/gpr_data/gate_dngs')/('Z8Z_'+name+'.dng')
    with (root/f'final-{name}.stdout').open('w') as log,contextlib.redirect_stdout(log):
        report=benchmark_stock_cnn.evaluate(source,benchmark,None,root/'selected.pt',root/f'final-{name}',
            sdk,'mps',qualities=(3,),tile=256,halo=64)
    row=report['rows'][0];assert report['model']['checkpoint_sha256']==freeze['checkpoint_sha256']
    old=json.loads((REPO/f'docs/stock-cleanup-receipts/final-{name}.json').read_text())
    assert row['input_raw_sha256']==old['rows'][0]['input_raw_sha256']
    regions=['active','shadow_bottom_decile','highlight_top_decile','detail_top_decile']
    regressions=[key for key in regions if row['restored'][key]['rmse_counts']>row['stock'][key]['rmse_counts']]
    item=dict(source=name,receipt_sha256=digest(root/f'final-{name}/benchmark.json'),
        active_psnr_delta_db=row['active_psnr_delta_db'],changed_samples=row['changed_samples'],
        region_delta_db={key:row['restored'][key]['psnr_db']-row['stock'][key]['psnr_db'] for key in regions},
        regressions=regressions,passed_numeric_guard=not regressions)
    results.append(item)
    (root/'final-progress.json').write_text(json.dumps(progress,indent=2)+'\n')
    print(json.dumps(item),flush=True)
progress.update(complete=True,all_scenes_pass_numeric_guard=all(row['passed_numeric_guard'] for row in results))
(root/'final-progress.json').write_text(json.dumps(progress,indent=2)+'\n')
