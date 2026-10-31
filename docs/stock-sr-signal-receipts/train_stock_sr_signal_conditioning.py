"""Fixed 2x2 calibrated-feature/signal-gate stock comparison, training/validation only.
Uses the current stock BIBO backbone (Apache-2.0/MIT repository);
calibration/signal conditioning is explicit analysis-only behavior.
"""
from pathlib import Path
import sys,json,time,hashlib,itertools,datetime
import numpy as np
import torch
from torch import nn
import torch.nn.functional as F
REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime');sys.path.insert(0,str(REPO/'tools'))
import train_stock_sr as recipe
import stock_cnn_models
ROOT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_signal_conditioning_20261030')
PARENT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_source_regions_20261030')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
class Adapter(nn.Module):
 def __init__(self,normalized_input=False,signal_gate=False):
  super().__init__();self.normalized_input=normalized_input;self.signal_gate=signal_gate
  self.backbone=stock_cnn_models.build('F_ane');head=self.backbone.subpixel[0];nn.init.zeros_(head.weight);nn.init.zeros_(head.bias)
 def forward(self,x):
  base=F.interpolate(x,scale_factor=2,mode='bicubic',align_corners=False).clamp(0,1)
  black=1008./16383.;span=(15892.-1008.)/16383.
  features=(x-black)/span if self.normalized_input else x
  gate=1.
  if self.signal_gate:
   signal=((base-black)/span).clamp_min(0);gate=signal/(signal+.02)
  return (base+.01*gate*self.backbone(features)).clamp(0,1)
def lap(x):return x[...,1:-1,:-2]+x[...,1:-1,2:]+x[...,:-2,1:-1]+x[...,2:,1:-1]-4*x[...,1:-1,1:-1]
def gradient_mse(x):return (x[...,1:,:]-x[...,:-1,:]).square().mean((1,2,3))+(x[...,:,1:]-x[...,:,:-1]).square().mean((1,2,3))
def run():
 ROOT.mkdir(exist_ok=False);parent=json.loads((PARENT/'protocol.json').read_text());dataset=Path(parent['dataset']);info=json.loads((dataset/'dataset.json').read_text())
 configs=[dict(name=f'n{int(n)}g{int(g)}',normalized_input=n,signal_gate=g) for n,g in itertools.product([False,True],repeat=2)]
 protocol=dict(schema='gpr.stock_sr_signal_conditioning_protocol.v1',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),script_sha256=sha(Path(__file__)),parent_protocol_sha256=sha(PARENT/'protocol.json'),dataset_sha256=sha(dataset/'dataset.json'),weight_audit_sha256=sha(PARENT/'weight-audit.json'),configs=configs,steps=3000,checkpoint_steps=[1000,2000,3000],seed=20261103,batch=8,learning_rate=.0003,width=16,device='mps',strengths=[1.,.5,.25,.125,.0625,.03125,.015625,.0078125],source_sampling='one patch from each of eight train sources per step; same indices across variants',loss='unchanged audited training-source full-image region MSE ratio',feature_normalization='optional (input_counts-1008)/(15892-1008), no signal clipping',output_gate='optional s/(s+0.02), s=max((bicubic_counts-1008)/(15892-1008),0); fixed raw-domain residual scale0.01',calibration_audit_sha256=sha(Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_calibration_20261030/audit.json')),selection='unchanged exact pooled/group patch regional nonregression plus strict pooled overall improvement; ALL patch-qualified settings to complete-image validation',final_reference_pixels_used=False,quality_approval=False,limitations=['exploratory one-seed comparison','fixed audited black1008/white15892; no other camera-domain claim','reused validation sources','no temporal or visual approval'])
 (ROOT/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
 assert sha(dataset/'inputs.npy')==parent['dataset_input_sha256'] and sha(dataset/'targets.npy')==parent['dataset_target_sha256']
 audit=json.loads((PARENT/'weight-audit.json').read_text());assert audit['complete'] and audit['nontraining_weights_zero'] and sha(PARENT/'weights.npy')==audit['weights_sha256']
 inputs=np.load(dataset/'inputs.npy',mmap_mode='r');targets=np.load(dataset/'targets.npy',mmap_mode='r');weights=np.load(PARENT/'weights.npy',mmap_mode='r')
 train_sources=[];val=[];groups={}
 for source in info['sources']:
  if source['split']=='test':assert source['patch_start'] is None and source['patch_count']==0
  else:
   indices=list(range(source['patch_start'],source['patch_start']+source['patch_count']))
   if source['split']=='train':train_sources.append(indices)
   else:val.extend(indices);groups.update({i:source['group'] for i in indices})
 assert len(train_sources)==8 and sum(map(len,train_sources))==512 and len(val)==128
 torch.set_num_threads(4);core=slice(64,192);lowcore=slice(32,96)
 def tensor(array,idx,norm=1.):return torch.from_numpy(np.asarray(array[idx],dtype=np.float32)/norm).to('mps')
 # Precompute immutable validation masks and verify arithmetic independently.
 refs={};masks={}
 for i in val:
  r=np.asarray(targets[i,:,core,core],dtype=np.float64);refs[i]=r;l,h=np.percentile(r,[10,90]);g=np.zeros_like(r);g[...,1:]+=abs(np.diff(r,axis=-1));g[...,1:,:]+=abs(np.diff(r,axis=-2))
  masks[i]=dict(overall=np.ones(r.shape,bool),shadow=r<=l,highlight=r>=h,detail=g>=np.percentile(g,90))
 def validate(model,alphas):
  model.eval();totals=[{} for _ in alphas]
  with torch.inference_mode():
   for start in range(0,len(val),8):
    idx=val[start:start+8];x=tensor(inputs,idx,recipe.PEAK);base=F.interpolate(x,scale_factor=2,mode='bicubic',align_corners=False).clamp(0,1);pred=model(x);residual=pred-base
    for pos,alpha in enumerate(alphas):
     counts=np.clip((base+alpha*residual).clamp(0,1)[:,:,core,core].cpu().numpy()*recipe.PEAK+.5,0,recipe.PEAK).astype('<u2')
     for i,value in zip(idx,counts):
      error=value.astype(np.float64)-refs[i];square=error**2
      regions={r:(float(square[m].sum()),int(m.sum())) for r,m in masks[i].items()}
      if start==0 and pos==0:assert regions==recipe.region_totals(refs[i],error)
      for group in ['pooled','group:'+groups[i]]:
       dest=totals[pos].setdefault(group,{})
       for key,(s,n) in regions.items():a,b=dest.get(key,(0.,0));dest[key]=(a+s,b+n)
  return [{g:{r:s/n for r,(s,n) in regs.items()} for g,regs in t.items()} for t in totals]
 report=dict(schema='gpr.stock_sr_signal_conditioning.v1',complete=False,quality_approval=False,protocol_sha256=sha(ROOT/'protocol.json'),cases=[],torch=torch.__version__);started=time.perf_counter()
 baseline=None
 for config in configs:
  torch.manual_seed(protocol['seed']);rng=np.random.default_rng(protocol['seed']);model=Adapter(config['normalized_input'],config['signal_gate']).to('mps');optimizer=torch.optim.AdamW(model.parameters(),lr=.0003,weight_decay=.0001)
  scores=validate(model,[0.,1.]);assert scores[0]==scores[1],'zero-head identity'
  if baseline is None:baseline=scores[0];assert baseline==json.loads((PARENT/'selection.json').read_text())['baseline_regions']
  assert scores[0]==baseline
  row=dict(config=config,parameters=sum(p.numel() for p in model.parameters()),history=[],candidates=[]);report['cases'].append(row);out=ROOT/config['name'];out.mkdir()
  for step in range(1,3001):
   model.train();idx=[int(rng.choice(indices)) for indices in train_sources];x=tensor(inputs,idx,recipe.PEAK);target=tensor(targets,idx);weight=tensor(weights,idx)
   optimizer.zero_grad(set_to_none=True);prediction=model(x);error=prediction[:,:,core,core]*recipe.PEAK-target[:,:,core,core];loss=(error.square()*weight).mean()
   assert torch.isfinite(loss).item();loss.backward();optimizer.step()
   if step in protocol['checkpoint_steps']:
    cp=out/f'step-{step}.pt';torch.save(dict(state={k:v.detach().cpu() for k,v in model.state_dict().items()},config=config,step=step,protocol_sha256=sha(ROOT/'protocol.json'),quality_approval=False),cp)
    scores=validate(model,[0.]+protocol['strengths']);assert scores[0]==baseline
    for alpha,metrics in zip(protocol['strengths'],scores[1:]):
     regressions=[g+':'+r for g,regs in baseline.items() for r,v in regs.items() if metrics[g][r]>v];mse=metrics['pooled']['overall'];eligible=not regressions and mse<baseline['pooled']['overall']
     row['candidates'].append(dict(step=step,alpha=alpha,metrics=metrics,regressions=regressions,eligible=eligible,gain_db=recipe.delta(baseline['pooled']['overall'],mse),checkpoint_sha256=sha(cp)))
    row['history'].append(dict(step=step,loss=float(loss.item()),elapsed_s=time.perf_counter()-started));(ROOT/'training.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(config=config['name'],step=step,eligible=sum(c['eligible'] for c in row['candidates']),elapsed_s=time.perf_counter()-started)),flush=True)
  row['qualified']=sorted([c for c in row['candidates'] if c['eligible']],key=lambda c:c['metrics']['pooled']['overall'])
 report.update(complete=True,baseline=baseline,elapsed_s=time.perf_counter()-started);(ROOT/'training.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(complete=True,elapsed_s=report['elapsed_s'])),flush=True)
if __name__=='__main__':run()
