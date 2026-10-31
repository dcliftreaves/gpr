"""Validation-only signed residual diagnostic for an already rejected candidate."""
from pathlib import Path
import json,sys,hashlib,importlib.util
import numpy as np,torch
REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime');sys.path.insert(0,str(REPO/'tools'))
import stock_video,raw_media,benchmark_stock_sr
ROOT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_recipe_comparison_20261030');PARENT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_source_regions_20261030')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
full=json.loads((ROOT/'full-selection.json').read_text());protocol=json.loads((ROOT/'full-protocol.json').read_text());name='p1d1s1-step2000-alpha0.25';candidate=next(c for c in protocol['family'] if c['name']==name);index=3;source=protocol['validation_sources'][index]
p=dict(schema='gpr.stock_sr_shadow_analysis_protocol.v1',full_selection_sha256=sha(ROOT/'full-selection.json'),script_sha256=sha(Path(__file__)),candidate=name,source_index=index,diagnostic_only=True,final_references_used=False)
assert not (ROOT/'shadow-protocol.json').exists();(ROOT/'shadow-protocol.json').write_text(json.dumps(p,indent=2)+'\n')
spec=importlib.util.spec_from_file_location('comparison',ROOT/'train_stock_sr_recipe_comparison.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
cp=Path(candidate['path']);assert sha(cp)==candidate['candidate']['checkpoint_sha256'];data=torch.load(cp,map_location='cpu',weights_only=True);model=module.Adapter(True,True);model.load_state_dict(data['state']);model.to('mps').eval();torch.set_num_threads(4)
class Blend(torch.nn.Module):
 def forward(self,x):
  base=torch.nn.functional.interpolate(x,scale_factor=2,mode='bicubic',align_corners=False).clamp(0,1)
  return (base+.25*(model(x)-base)).clamp(0,1)
cache=PARENT/f'all-qualified/full-validation/validation-{index}';old=json.loads((cache/'benchmark.json').read_text());raw=cache/'decoded-low.raw';refpath=cache/'independent-sdk.raw';assert sha(Path(source['path']))==source['sha256'] and sha(raw)==old['low_decoded_raw_sha256'] and sha(refpath)==old['reference_raw_sha256']
meta=raw_media.extract(Path(source['path']),14);w,h=meta['width'],meta['height'];reference=np.fromfile(refpath,dtype='<u2').reshape(h,w)
base,_=stock_video.restore(raw,w//2,h//2,benchmark_stock_sr.Bicubic(),torch.device('mps'),256,64,2);output,_=stock_video.restore(raw,w//2,h//2,Blend().eval(),torch.device('mps'),256,64,2)
expected=next(c for c in full['sources'][index]['candidates'] if c['name']==name);assert hashlib.sha256(base.tobytes()).hexdigest()==old['bicubic_raw_sha256'] and hashlib.sha256(output.tobytes()).hexdigest()==expected['output_sha256']
t,l,b,r=old['bicubic_metrics']['active_area'];ref=reference[t:b,l:r].astype(np.int32);e=base[t:b,l:r].astype(np.float64)-ref;residual=output[t:b,l:r].astype(np.float64)-base[t:b,l:r];low,high=np.percentile(ref,[10,90]);grad=np.abs(ref[2:,:-2]-ref[:-2,:-2])+np.abs(ref[:-2,2:]-ref[:-2,:-2]);threshold=np.percentile(grad,90)
regions={'active':(e,residual,None),'shadow':(e,residual,ref<=low),'highlight':(e,residual,ref>=high),'detail':(e[:-2,:-2],residual[:-2,:-2],grad>=threshold)};rows={}
for key,(err,res,mask) in regions.items():
 if mask is not None:err=err[mask];res=res[mask]
 energy=float(np.mean(res**2));cross=float(np.mean(err*res));base_mse=float(np.mean(err**2));delta=2*cross+energy;actual=float(np.mean((err+res)**2))-base_mse
 assert abs(delta-actual)<1e-8*max(1.,abs(actual))
 rows[key]=dict(samples=err.size,baseline_mean_error_counts=float(err.mean()),mean_correction_counts=float(res.mean()),residual_mse=energy,error_residual_cross_mean=cross,delta_mse=delta,optimal_unconstrained_multiplier_for_this_count_residual=None if energy==0 else -cross/energy)
report=dict(schema='gpr.stock_sr_shadow_analysis.v1',complete=True,protocol_sha256=sha(ROOT/'shadow-protocol.json'),candidate=name,source=source,rows=rows,interpretation='Positive cross term means the measured residual aligns with existing error and any small positive continuous scaling worsens that region. This is diagnostic correlation on validation pixels, not an inference-time oracle or a selected correction.',quality_approval=False)
(ROOT/'shadow-analysis.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
