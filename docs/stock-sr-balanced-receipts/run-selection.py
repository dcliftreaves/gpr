"""Execute the preregistered validation-only residual-strength selection."""
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import numpy as np
import torch

REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime')
sys.path.insert(0,str(REPO/'tools'))
import stock_cnn_models
import train_stock_sr as recipe

root=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_balanced_20261030')
protocol=json.loads((root/'protocol.json').read_text())
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
dataset=Path(protocol['dataset']);info=json.loads((dataset/'dataset.json').read_text())
assert digest(dataset/'dataset.json')==protocol['dataset_sha256']
assert digest(dataset/'inputs.npy')==protocol['dataset_input_sha256']
assert digest(dataset/'targets.npy')==protocol['dataset_target_sha256']
inputs=np.load(dataset/'inputs.npy',mmap_mode='r',allow_pickle=False)
targets=np.load(dataset/'targets.npy',mmap_mode='r',allow_pickle=False)
indices=[];groups={}
for source in info['sources']:
    if source['split']=='test':
        assert source['patch_start'] is None and not source['patch_count']
    if source['split']=='validation':
        for index in range(source['patch_start'],source['patch_start']+source['patch_count']):
            indices.append(index);groups[index]=source['group']
assert len(indices)==128 and len(set(groups.values()))==2 and info['output_scale']==2
training=json.loads(Path(protocol['base_training']).read_text());assert training['complete']
binding=json.loads((root/'training-binding.json').read_text())
assert digest(root/'protocol.json')==binding['protocol_sha256']
assert digest(Path(protocol['base_training']))==binding['training_sha256']
checkpoint_path=Path(protocol['base_checkpoint'])
assert digest(checkpoint_path)==training['best_checkpoint_sha256']
checkpoint=torch.load(checkpoint_path,map_location='cpu',weights_only=True)
assert checkpoint['variant']=='F_ane' and checkpoint['raw_norm']==16383
assert checkpoint['residual_scale']==protocol['training_residual_scale']
torch.set_num_threads(4)
model=stock_cnn_models.build(checkpoint['variant']).to('mps')
model.load_state_dict(checkpoint['backbone_state'],strict=True);model.eval()
core=slice(inputs.shape[-1]//2,3*inputs.shape[-1]//2)
alphas=[0.0]+protocol['strengths'];totals=[{} for _ in alphas]
changed=[0 for _ in alphas];started=time.perf_counter()
with torch.inference_mode():
    for start in range(0,len(indices),protocol['batch']):
        batch=indices[start:start+protocol['batch']]
        raw=np.asarray(inputs[batch],dtype=np.float32)
        x=torch.from_numpy(raw/recipe.PEAK).to('mps');residual=model(x)
        base=torch.nn.functional.interpolate(x,scale_factor=2,mode='bicubic',align_corners=False).clamp(0,1)
        reference=np.asarray(targets[batch,:,core,core],dtype=np.float64)
        identity=None
        for position,alpha in enumerate(alphas):
            value=(base+checkpoint['residual_scale']*alpha*residual).clamp(0,1)
            counts=np.clip(value[:,:,core,core].cpu().numpy()*recipe.PEAK+.5,0,recipe.PEAK).astype('<u2')
            if not alpha:identity=counts.copy()
            changed[position]+=int(np.count_nonzero(counts!=identity))
            for index,ref,prediction in zip(batch,reference,counts):
                error=prediction.astype(np.float64)-ref
                regions=recipe.region_totals(ref,error)
                for group in ['pooled','group:'+groups[index]]:
                    dest=totals[position].setdefault(group,{})
                    for region,(sse,count) in regions.items():
                        old_sse,old_count=dest.get(region,(0.,0))
                        dest[region]=(old_sse+sse,old_count+count)
scores=[{group:{region:sse/count for region,(sse,count) in regions.items()} for group,regions in total.items()} for total in totals]
baseline=scores[0];assert len(baseline)==3 and all(len(v)==4 for v in baseline.values())
assert baseline['pooled']['overall']==training['baseline_validation_mse_counts']
assert scores[1]['pooled']['overall']==training['best_validation_mse_counts']
best=baseline['pooled']['overall'];selected=None;history=[]
for alpha,metrics,changes in zip(alphas[1:],scores[1:],changed[1:]):
    mse=metrics['pooled']['overall'];eligible=recipe.region_guard(metrics,baseline) and mse<baseline['pooled']['overall']
    regressions=[group+':'+region for group,regions in baseline.items() for region,value in regions.items() if metrics[group][region]>value]
    row=dict(alpha=alpha,residual_scale=checkpoint['residual_scale']*alpha,validation_mse_counts=mse,
        delta_vs_bicubic_db=recipe.delta(baseline['pooled']['overall'],mse),regions=metrics,
        changed_validation_samples=changes,eligible=eligible,regressions=regressions)
    history.append(row)
    if eligible and mse<best:best=mse;selected=row
report=dict(schema='gpr.stock_sr_balanced_selection.v1',complete=True,quality_approval=False,
    protocol_sha256=digest(root/'protocol.json'),selector_sha256=digest(Path(__file__)),
    checkpoint_sha256=digest(checkpoint_path),training_sha256=digest(Path(protocol['base_training'])),
    dataset_sha256=protocol['dataset_sha256'],validation_patches=len(indices),
    final_test_used_for_selection=False,baseline_regions=baseline,history=history,selected=selected,
    elapsed_s=time.perf_counter()-started,selected_checkpoint_sha256=None)
if selected is not None:
    checkpoint['residual_scale']=selected['residual_scale']
    checkpoint['quality_approval']=False
    checkpoint['strength_selection_protocol_sha256']=report['protocol_sha256']
    checkpoint['strength_base_checkpoint_sha256']=report['checkpoint_sha256']
    checkpoint['validation_mse_counts']=selected['validation_mse_counts']
    torch.save(checkpoint,root/'selected.pt')
    report['selected_checkpoint_sha256']=digest(root/'selected.pt')
(root/'selection.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(selected=selected,selected_checkpoint_sha256=report['selected_checkpoint_sha256'],
    eligible_candidates=sum(row['eligible'] for row in history),candidates=len(history),elapsed_s=report['elapsed_s'])))
