"""Complete-image validation of the preregistered patch-qualified top-three family."""
from pathlib import Path
import sys,json,hashlib,time,importlib.util
import torch,numpy as np
REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime');sys.path.insert(0,str(REPO/'tools'))
import raw_media,stock_video,benchmark_stock_sr
from benchmark_stills import quality
ROOT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_recipe_comparison_20261030');PARENT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_source_regions_20261030')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def run():
 training=json.loads((ROOT/'training.json').read_text());assert training['complete']
 spec=importlib.util.spec_from_file_location('comparison',ROOT/'train_stock_sr_recipe_comparison.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 old=json.loads((PARENT/'all-qualified/full-validation/protocol.json').read_text());family=[]
 for case in training['cases']:
  for candidate in case['qualified_top3']:
   family.append(dict(name=case['config']['name']+'-step'+str(candidate['step'])+'-alpha'+str(candidate['alpha']),config=case['config'],parameters=case['parameters'],candidate=candidate,path=str(ROOT/case['config']['name']/f"step-{candidate['step']}.pt")))
 p=dict(schema='gpr.stock_sr_recipe_full_protocol.v1',training_sha256=sha(ROOT/'training.json'),script_sha256=sha(Path(__file__)),architecture_sha256=sha(ROOT/'train_stock_sr_recipe_comparison.py'),family=family,validation_sources=old['validation_sources'],device='mps',tile=256,halo=64,selection='unchanged no per-image active/shadow/highlight/detail RMSE increase and strict pooled active improvement; minimum eligible pooled active MSE',final_reference_pixels_used=False,quality_approval=False)
 assert not (ROOT/'full-protocol.json').exists();(ROOT/'full-protocol.json').write_text(json.dumps(p,indent=2)+'\n')
 report=dict(schema='gpr.stock_sr_recipe_full.v1',complete=False,quality_approval=False,protocol_sha256=sha(ROOT/'full-protocol.json'),sources=[],final_reference_pixels_used=False)
 torch.set_num_threads(4);started=time.perf_counter();totals=[0.]*len(family);failed=[[] for c in family];samples_total=0;base_total=0.
 class Blend(torch.nn.Module):
  def __init__(self,model,alpha):super().__init__();self.model=model;self.alpha=alpha
  def forward(self,x):
   base=torch.nn.functional.interpolate(x,scale_factor=2,mode='bicubic',align_corners=False).clamp(0,1)
   return (base+self.alpha*(self.model(x)-base)).clamp(0,1)
 for index,source in enumerate(p['validation_sources']):
  path=Path(source['path']);assert sha(path)==source['sha256'];cache=PARENT/f'all-qualified/full-validation/validation-{index}';prior=json.loads((cache/'benchmark.json').read_text());assert prior['source_sha256']==source['sha256']
  raw=cache/'decoded-low.raw';refpath=cache/'independent-sdk.raw';assert sha(raw)==prior['low_decoded_raw_sha256'] and sha(refpath)==prior['reference_raw_sha256']
  meta=raw_media.extract(path,14);w,h=meta['width'],meta['height'];reference=np.fromfile(refpath,dtype='<u2').reshape(h,w)
  base,_=stock_video.restore(raw,w//2,h//2,benchmark_stock_sr.Bicubic(),torch.device('mps'),256,64,2);assert hashlib.sha256(base.tobytes()).hexdigest()==prior['bicubic_raw_sha256'];bm=quality(reference,base,meta);assert json.loads(json.dumps(bm))==prior['bicubic_metrics'];del base
  t,l,b,r=bm['active_area'];samples=(b-t)*(r-l);samples_total+=samples;base_total+=bm['active']['rmse_counts']**2*samples
  row=dict(source=source,cache_benchmark_sha256=sha(cache/'benchmark.json'),bicubic_metrics=bm,candidates=[]);report['sources'].append(row)
  for pos,c in enumerate(family):
   cp=Path(c['path']);assert sha(cp)==c['candidate']['checkpoint_sha256'];state=torch.load(cp,map_location='cpu',weights_only=True);assert state['config']==c['config']
   model=module.Adapter(c['config']['preclean'],c['config']['detail']);model.load_state_dict(state['state'],strict=True);model.to('mps').eval()
   output,seconds=stock_video.restore(raw,w//2,h//2,Blend(model,c['candidate']['alpha']).eval(),torch.device('mps'),256,64,2)
   metrics=quality(reference,output,meta);oh=hashlib.sha256(output.tobytes()).hexdigest();del output,model
   regressions=[key for key in ['active','shadow_bottom_decile','highlight_top_decile','detail_top_decile'] if metrics[key]['rmse_counts']>bm[key]['rmse_counts']]
   totals[pos]+=metrics['active']['rmse_counts']**2*samples;failed[pos].extend(dict(source_index=index,region=key) for key in regressions)
   row['candidates'].append(dict(name=c['name'],metrics=metrics,regressions=regressions,output_sha256=oh,inference_s=seconds));(ROOT/'full-selection.json').write_text(json.dumps(report,indent=2)+'\n')
   print(json.dumps(dict(source_index=index,name=c['name'],regressions=regressions,gain_db=metrics['active']['psnr_db']-bm['active']['psnr_db'],elapsed_s=time.perf_counter()-started)),flush=True)
 results=[dict(name=c['name'],active_mse=total/samples_total,gain_db=float(10*np.log10(base_total/total)),regressions=f,eligible=not f and total<base_total) for c,total,f in zip(family,totals,failed)]
 eligible=[r for r in results if r['eligible']];report.update(complete=True,results=results,selected=min(eligible,key=lambda r:r['active_mse']) if eligible else None,elapsed_s=time.perf_counter()-started)
 (ROOT/'full-selection.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(complete=True,selected=report['selected'],candidates=len(family),elapsed_s=report['elapsed_s'])),flush=True)
if __name__=='__main__':run()
