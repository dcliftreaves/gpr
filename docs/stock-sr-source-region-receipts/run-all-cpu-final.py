"""Evaluate the frozen 2x candidate; never select strength from final results."""
import contextlib
import hashlib
import json
from pathlib import Path
import sys
import torch
torch.set_num_threads(4)

repo=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime')
sys.path.insert(0,str(repo/'tools'))
import benchmark_stock_sr

root=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_source_regions_20261030/all-qualified')
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
frozen=json.loads((root/'frozen.json').read_text())
assert digest(root/'selected.pt')==frozen['checkpoint_sha256']
sdk=repo/'build-runtime/source/app/gpr_tools/gpr_tools'
assert digest(sdk)==frozen['sdk_sha256']
progress=dict(schema='gpr.stock_sr_source_all_cpu_final.v1',complete=False,quality_approval=False,
    checkpoint_sha256=frozen['checkpoint_sha256'],freeze_sha256=digest(root/'frozen.json'),
    final_pixels_used_for_selection=False,results=[])
(root/'cpu-final-progress.json').write_text(json.dumps(progress,indent=2)+'\n')
for name in ['0001','0067','5323','6693']:
    source=Path('/Users/dcliftreaves/gpr_data/gate_dngs')/('Z8Z_'+name+'.dng')
    with (root/f'cpu-final-{name}.stdout').open('w') as out,contextlib.redirect_stdout(out):
        report=benchmark_stock_sr.evaluate(source,sdk,[root/'selected.pt'],root/f'cpu-final-{name}',device='cpu',tile=256,halo=64)
    previous=json.loads((repo/f'docs/stock-sr-training-receipts/test-{name}.json').read_text())
    assert report['low_decoded_raw_sha256']==previous['low_decoded_raw_sha256']
    assert report['reference_raw_sha256']==previous['reference_raw_sha256']
    row=report['rows'][0];assert row['model']['checkpoint_sha256']==frozen['checkpoint_sha256']
    baseline=report['bicubic_metrics'];metrics=row['metrics']
    regions=['active','shadow_bottom_decile','highlight_top_decile','detail_top_decile']
    regressions=[key for key in regions if metrics[key]['rmse_counts']>baseline[key]['rmse_counts']]
    result=dict(source=name,receipt_sha256=digest(root/f'cpu-final-{name}/benchmark.json'),
        active_psnr_delta_db=row['active_psnr_delta_vs_bicubic_db'],
        region_delta_db={key:metrics[key]['psnr_db']-baseline[key]['psnr_db'] for key in regions},
        regressions=regressions,passed_numeric_guard=not regressions)
    progress['results'].append(result)
    (root/'cpu-final-progress.json').write_text(json.dumps(progress,indent=2)+'\n')
    print(json.dumps(result),flush=True)
progress.update(complete=True,all_scenes_pass_numeric_guard=all(row['passed_numeric_guard'] for row in progress['results']))
(root/'cpu-final-summary.json').write_text(json.dumps(progress,indent=2)+'\n')
