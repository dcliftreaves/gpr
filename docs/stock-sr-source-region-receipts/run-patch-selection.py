"""Select only from preregistered snapshots/strengths using validation counts."""
import hashlib,json,math,sys,time
from pathlib import Path
import numpy as np
import torch
REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime')
sys.path.insert(0,str(REPO/'tools'))
import stock_cnn_models
import train_stock_sr as recipe
root=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_source_regions_20261030')
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=json.loads((root/'protocol.json').read_text());dataset=Path(p['dataset'])
assert digest(root/'run-training.py')==p['training_script_sha256']
info=json.loads((dataset/'dataset.json').read_text())
assert digest(dataset/'dataset.json')==p['dataset_sha256']
assert digest(dataset/'inputs.npy')==p['dataset_input_sha256']
assert digest(dataset/'targets.npy')==p['dataset_target_sha256']
inputs=np.load(dataset/'inputs.npy',mmap_mode='r',allow_pickle=False);targets=np.load(dataset/'targets.npy',mmap_mode='r',allow_pickle=False)
indices=[];groups={}
for s in info['sources']:
 if s['split']=='test':assert s['patch_start'] is None and s['patch_count']==0
 if s['split']=='validation':
  for i in range(s['patch_start'],s['patch_start']+s['patch_count']):indices.append(i);groups[i]=s['group']
assert len(indices)==128 and info['output_scale']==2
training=json.loads((root/'train/training.json').read_text());assert training['complete']
torch.set_num_threads(4);model=stock_cnn_models.build('F_ane').to('mps');model.eval()
core=slice(inputs.shape[-1]//2,3*inputs.shape[-1]//2)
best=float('inf');selected=None;history=[];started=time.perf_counter();reference_baseline=None
for step in p['checkpoint_steps']:
 cp=root/f'train/step-{step}.pt';checkpoint=torch.load(cp,map_location='cpu',weights_only=True)
 assert checkpoint['step']==step and checkpoint['variant']=='F_ane' and checkpoint['residual_scale']==p['training_residual_scale']
 model.load_state_dict(checkpoint['backbone_state'],strict=True)
 alphas=[0.]+p['strengths'];totals=[{} for _ in alphas];changes=[0 for _ in alphas]
 with torch.inference_mode():
  for start in range(0,len(indices),p['batch']):
   batch=indices[start:start+p['batch']];x=torch.from_numpy(np.asarray(inputs[batch],dtype=np.float32)/recipe.PEAK).to('mps')
   residual=model(x);base=torch.nn.functional.interpolate(x,scale_factor=2,mode='bicubic',align_corners=False).clamp(0,1)
   ref=np.asarray(targets[batch,:,core,core],dtype=np.float64)
   for pos,alpha in enumerate(alphas):
    value=(base+checkpoint['residual_scale']*alpha*residual).clamp(0,1)
    counts=np.clip(value[:,:,core,core].cpu().numpy()*recipe.PEAK+.5,0,recipe.PEAK).astype('<u2')
    if pos==0:identity=counts.copy()
    changes[pos]+=int(np.count_nonzero(counts!=identity))
    for i,r,pred in zip(batch,ref,counts):
     regions=recipe.region_totals(r,pred.astype(np.float64)-r)
     for group in ['pooled','group:'+groups[i]]:
      dest=totals[pos].setdefault(group,{})
      for region,(sse,count) in regions.items():
       a,b=dest.get(region,(0.,0));dest[region]=(a+sse,b+count)
 scores=[{g:{r:s/n for r,(s,n) in regs.items()} for g,regs in total.items()} for total in totals]
 baseline=scores[0]
 if reference_baseline is None:reference_baseline=baseline;best=baseline['pooled']['overall']
 assert baseline==reference_baseline
 assert baseline==training['baseline_validation_regions_mse']
 expected=next(row['validation_mse_counts'] for row in training['history'] if row['step']==step)
 assert scores[1]['pooled']['overall']==expected
 for alpha,metrics,changed in zip(alphas[1:],scores[1:],changes[1:]):
  mse=metrics['pooled']['overall'];eligible=recipe.region_guard(metrics,baseline) and mse<baseline['pooled']['overall']
  regressions=[g+':'+r for g,regions in baseline.items() for r,v in regions.items() if metrics[g][r]>v]
  row=dict(step=step,alpha=alpha,residual_scale=checkpoint['residual_scale']*alpha,validation_mse_counts=mse,delta_vs_bicubic_db=recipe.delta(baseline['pooled']['overall'],mse),regions=metrics,changed_validation_samples=changed,eligible=eligible,regressions=regressions,base_checkpoint_sha256=digest(cp))
  history.append(row)
  if eligible and mse<best:
   best=mse;selected=row
   out=dict(checkpoint);out.update(residual_scale=row['residual_scale'],quality_approval=False,strength_selection_protocol_sha256=digest(root/'protocol.json'),strength_base_checkpoint_sha256=digest(cp),validation_mse_counts=mse)
   torch.save(out,root/'selected.pt')
 report=dict(schema='gpr.stock_sr_source_regions_selection.v1',complete=step==p['checkpoint_steps'][-1],quality_approval=False,protocol_sha256=digest(root/'protocol.json'),selector_sha256=digest(Path(__file__)),training_sha256=digest(root/'train/training.json'),dataset_sha256=p['dataset_sha256'],validation_patches=len(indices),final_test_used_for_selection=False,baseline_regions=baseline,history=history,selected=selected,selected_checkpoint_sha256=digest(root/'selected.pt') if selected else None,elapsed_s=time.perf_counter()-started)
 (root/'selection.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(dict(step=step,eligible_candidates=sum(r['eligible'] for r in history),candidates=len(history),selected=selected,elapsed_s=report['elapsed_s'])),flush=True)
