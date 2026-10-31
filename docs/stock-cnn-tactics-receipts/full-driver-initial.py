"""Full validation only on hash-bound cached independent RAWs; no final images."""
from pathlib import Path
import hashlib,json,sys,time
import numpy as np
import torch
REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime');sys.path.insert(0,str(REPO/'tools'))
import raw_media,stock_video,benchmark_stock_sr
from benchmark_stills import quality
ROOT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_spatial_gate_20261030')
PARENT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_source_regions_20261030')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
patch=json.loads((ROOT/'selection.json').read_text());assert patch['complete']
candidates=[r for r in patch['rows'] if r['eligible']]
protocol=json.loads((PARENT/'all-qualified/full-validation/protocol.json').read_text())
cp=PARENT/'train/step-3000.pt'
p=dict(schema='gpr.stock_sr_spatial_gate_full_protocol.v1',patch_selection_sha256=sha(ROOT/'selection.json'),script_sha256=sha(Path(__file__)),checkpoint_sha256=sha(cp),candidates=candidates,
 validation_sources=protocol['validation_sources'],parent_full_protocol_sha256=sha(PARENT/'all-qualified/full-validation/protocol.json'),device='mps',tile=256,halo=64,
 selection='unchanged per-image active/shadow/highlight/detail RMSE nonregression and strict pooled active improvement; lowest eligible pooled active MSE',final_references_used=False,quality_approval=False)
assert not (ROOT/'full-protocol.json').exists()
(ROOT/'full-protocol.json').write_text(json.dumps(p,indent=2)+'\n')
checkpoint=torch.load(cp,map_location='cpu',weights_only=True)
model,_=stock_video.load_cnn(None,cp,torch.device('mps'));backbone=model.backbone
class Gated(torch.nn.Module):
 def __init__(self,c):super().__init__();self.c=c;self.backbone=backbone
 def forward(self,x):
  base=torch.nn.functional.interpolate(x,scale_factor=2,mode='bicubic',align_corners=False).clamp(0,1);gate=1.
  if self.c['ramps'] is not None:
   a,b,c,d=self.c['ramps'];gate=((base-a)/(b-a)).clamp(0,1)*((d-base)/(d-c)).clamp(0,1)
  return (base+(.01*self.c['alpha'])*gate*self.backbone(x)).clamp(0,1)
torch.set_num_threads(4);totals={c['name']:0. for c in candidates};regressions={c['name']:[] for c in candidates};baseline_total=0.;samples_total=0
report=dict(schema='gpr.stock_sr_spatial_gate_full.v1',complete=False,quality_approval=False,protocol_sha256=sha(ROOT/'full-protocol.json'),final_references_used=False,sources=[])
regions=['active','shadow_bottom_decile','highlight_top_decile','detail_top_decile'];started=time.perf_counter()
for index,source in enumerate(p['validation_sources']):
 path=Path(source['path']);assert sha(path)==source['sha256']
 cache=PARENT/f'all-qualified/full-validation/validation-{index}';previous=json.loads((cache/'benchmark.json').read_text());assert previous['source_sha256']==source['sha256']
 raw=cache/'decoded-low.raw';reference_path=cache/'independent-sdk.raw'
 assert sha(raw)==previous['low_decoded_raw_sha256'] and sha(reference_path)==previous['reference_raw_sha256']
 meta=raw_media.extract(path,14);w,h=meta['width'],meta['height'];reference=np.fromfile(reference_path,dtype='<u2').reshape(h,w)
 baseline,_=stock_video.restore(raw,w//2,h//2,benchmark_stock_sr.Bicubic(),torch.device('mps'),256,64,2)
 assert hashlib.sha256(baseline.tobytes()).hexdigest()==previous['bicubic_raw_sha256']
 bm=quality(reference,baseline,meta);assert bm==previous['bicubic_metrics'];del baseline
 top,left,bottom,right=bm['active_area'];samples=(bottom-top)*(right-left);samples_total+=samples;baseline_total+=bm['active']['rmse_counts']**2*samples
 row=dict(source=source,cache_benchmark_sha256=sha(cache/'benchmark.json'),candidates=[])
 report['sources'].append(row)
 for candidate in candidates:
  output,seconds=stock_video.restore(raw,w//2,h//2,Gated(candidate).eval(),torch.device('mps'),256,64,2)
  output_hash=hashlib.sha256(output.tobytes()).hexdigest()
  if candidate['name']=='control-1-32':
   old=next(r for r in previous['rows'] if r['model']['checkpoint_sha256']=='f7bda0449b94be4ebd3617297b9dee04506b00e38788dba2d0b04eb71fdaa2f4') if any(r['model']['checkpoint_sha256']=='f7bda0449b94be4ebd3617297b9dee04506b00e38788dba2d0b04eb71fdaa2f4' for r in previous['rows']) else None
   # Candidate files can have different metadata hashes; bind exact backbone/scale.
   if old is None:
    for prior in previous['rows']:
     q=next(x for x in protocol['candidates'] if x['sha256']==prior['model']['checkpoint_sha256'])
     c=torch.load(q['path'],map_location='cpu',weights_only=True)
     if c['step']==3000 and c['residual_scale']==.01/32:old=prior;break
   assert old is not None and output_hash==old['restored_raw_sha256'],'control pixel identity'
  metrics=quality(reference,output,meta);del output
  failed=[r for r in regions if metrics[r]['rmse_counts']>bm[r]['rmse_counts']]
  totals[candidate['name']]+=metrics['active']['rmse_counts']**2*samples;regressions[candidate['name']].extend(dict(source_index=index,region=r) for r in failed)
  result=dict(name=candidate['name'],metrics=metrics,regressions=failed,output_sha256=output_hash,inference_s=seconds)
  row['candidates'].append(result);(ROOT/'full-selection.json').write_text(json.dumps(report,indent=2)+'\n')
  print(json.dumps(dict(source_index=index,name=candidate['name'],regressions=failed,active_gain_db=metrics['active']['psnr_db']-bm['active']['psnr_db'],elapsed_s=time.perf_counter()-started)),flush=True)
baseline_mse=baseline_total/samples_total;results=[]
for candidate in candidates:
 name=candidate['name'];mse=totals[name]/samples_total
 results.append(dict(name=name,active_mse=mse,gain_db=10*np.log10(baseline_mse/mse),regressions=regressions[name],eligible=not regressions[name] and mse<baseline_mse))
qualified=[r for r in results if r['eligible']]
report.update(complete=True,results=results,selected=min(qualified,key=lambda r:r['active_mse']) if qualified else None,elapsed_s=time.perf_counter()-started)
(ROOT/'full-selection.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(complete=True,results=results,selected=report['selected'])),flush=True)
