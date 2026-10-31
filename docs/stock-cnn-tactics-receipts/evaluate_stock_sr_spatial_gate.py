"""Validation-only fixed-family diagnostic; never accesses final-reference pixels."""
from pathlib import Path
import hashlib,json,sys,time,datetime
import numpy as np
import torch
REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime')
sys.path.insert(0,str(REPO/'tools'))
import stock_cnn_models
import train_stock_sr as recipe
ROOT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_spatial_gate_20261030')
PARENT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_source_regions_20261030')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
ROOT.mkdir(exist_ok=False)
parent=json.loads((PARENT/'protocol.json').read_text());dataset=Path(parent['dataset']);cp=PARENT/'train/step-3000.pt'
family=[dict(name='control-1-32',alpha=1/32,ramps=None),dict(name='control-full',alpha=1.,ramps=None)]
for name,ramps in [('mild',[.001,.01,.95,.999]),('medium',[.01,.05,.8,.98]),('strong',[.03,.15,.65,.9])]:
 for alpha in [1.,.5,.25,.125,.0625,.03125]:family.append(dict(name=name+'-'+str(alpha),alpha=alpha,ramps=ramps))
protocol=dict(schema='gpr.stock_sr_spatial_gate_protocol.v1',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
 parent_protocol_sha256=sha(PARENT/'protocol.json'),dataset_sha256=sha(dataset/'dataset.json'),checkpoint_sha256=sha(cp),script_sha256=sha(Path(__file__)),
 family=family,gate='clamp((bicubic-a)/(b-a),0,1)*clamp((d-bicubic)/(d-c),0,1), independently per Bayer plane/site in normalized counts',
 selection='unchanged exact pooled and per-source-group patch overall/shadow/highlight/detail nonregression plus strict pooled overall improvement; lowest eligible count MSE',
 next_gate='all four complete validation images before any historical final reference',final_references_used=False,quality_approval=False)
(ROOT/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
info=json.loads((dataset/'dataset.json').read_text())
assert sha(dataset/'inputs.npy')==parent['dataset_input_sha256']
assert sha(dataset/'targets.npy')==parent['dataset_target_sha256']
xdata=np.load(dataset/'inputs.npy',mmap_mode='r');ydata=np.load(dataset/'targets.npy',mmap_mode='r')
indices=[];groups={}
for s in info['sources']:
 if s['split']=='test':assert s['patch_start'] is None and s['patch_count']==0
 if s['split']=='validation':
  for i in range(s['patch_start'],s['patch_start']+s['patch_count']):indices.append(i);groups[i]=s['group']
assert len(indices)==128
checkpoint=torch.load(cp,map_location='cpu',weights_only=True)
assert checkpoint['residual_scale']==.01 and checkpoint['variant']=='F_ane'
torch.set_num_threads(4);model=stock_cnn_models.build('F_ane').to('mps').eval();model.load_state_dict(checkpoint['backbone_state'],strict=True)
core=slice(xdata.shape[-1]//2,3*xdata.shape[-1]//2)
totals=[{} for _ in range(len(family)+1)];changes=[0]*len(totals);started=time.perf_counter()
with torch.inference_mode():
 for start in range(0,len(indices),8):
  batch=indices[start:start+8];x=torch.from_numpy(np.asarray(xdata[batch],dtype=np.float32)/recipe.PEAK).to('mps')
  base=torch.nn.functional.interpolate(x,scale_factor=2,mode='bicubic',align_corners=False).clamp(0,1)
  residual=model(x);ref=np.asarray(ydata[batch,:,core,core],dtype=np.float64)
  masks=[]
  for r in ref:
   low,high=np.percentile(r,[10,90]);gradient=np.zeros(r.shape,dtype=np.float64)
   gradient[...,1:]+=np.abs(np.diff(r,axis=-1));gradient[...,1:,:]+=np.abs(np.diff(r,axis=-2))
   masks.append(dict(overall=np.ones(r.shape,dtype=bool),shadow=r<=low,highlight=r>=high,detail=gradient>=np.percentile(gradient,90)))
  for pos,candidate in enumerate([None]+family):
   if candidate is None:value=base
   else:
    gate=1.
    if candidate['ramps'] is not None:
     a,b,c,d=candidate['ramps'];gate=((base-a)/(b-a)).clamp(0,1)*((d-base)/(d-c)).clamp(0,1)
    value=(base+.01*candidate['alpha']*gate*residual).clamp(0,1)
   counts=np.clip(value[:,:,core,core].cpu().numpy()*recipe.PEAK+.5,0,recipe.PEAK).astype('<u2')
   if pos==0:identity=counts.copy()
   changes[pos]+=int(np.count_nonzero(counts!=identity))
   for i,r,pred,mask in zip(batch,ref,counts,masks):
    square=np.square(pred.astype(np.float64)-r)
    # Independently check the cached-mask arithmetic against existing evaluator.
    if start==0 and pos==0:
     assert {k:(float(square[m].sum()),int(m.sum())) for k,m in mask.items()}==recipe.region_totals(r,pred.astype(np.float64)-r)
    for group in ['pooled','group:'+groups[i]]:
     dest=totals[pos].setdefault(group,{})
     for key,m in mask.items():
      s,n=dest.get(key,(0.,0));dest[key]=(s+float(square[m].sum()),n+int(m.sum()))
  print(json.dumps(dict(validation_patches=start+len(batch),elapsed_s=time.perf_counter()-started)),flush=True)
scores=[{g:{r:s/n for r,(s,n) in regs.items()} for g,regs in total.items()} for total in totals];baseline=scores[0]
old=json.loads((PARENT/'selection.json').read_text());assert baseline==old['baseline_regions']
control=next(r for r in old['history'] if r['step']==3000 and r['alpha']==1/32)
assert scores[1]==control['regions'],'unchanged weak control must exactly reproduce previous validation'
rows=[]
for candidate,metrics,changed in zip(family,scores[1:],changes[1:]):
 mse=metrics['pooled']['overall'];regressions=[g+':'+r for g,regs in baseline.items() for r,v in regs.items() if metrics[g][r]>v]
 rows.append(dict(**candidate,metrics=metrics,changed_samples=changed,regressions=regressions,eligible=not regressions and mse<baseline['pooled']['overall'],delta_db=recipe.delta(baseline['pooled']['overall'],mse)))
eligible=[r for r in rows if r['eligible']];best=min(eligible,key=lambda r:r['metrics']['pooled']['overall']) if eligible else None
report=dict(schema='gpr.stock_sr_spatial_gate_patch.v1',complete=True,quality_approval=False,protocol_sha256=sha(ROOT/'protocol.json'),final_references_used=False,baseline=baseline,rows=rows,selected=best,elapsed_s=time.perf_counter()-started)
(ROOT/'selection.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(complete=True,selected=best,elapsed_s=report['elapsed_s'])),flush=True)
