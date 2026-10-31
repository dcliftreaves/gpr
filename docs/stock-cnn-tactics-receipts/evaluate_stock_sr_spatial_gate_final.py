"""Evaluate one already frozen gate on historical final references, without tuning."""
from pathlib import Path
import sys,json,hashlib,time
import torch,numpy as np
REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime');sys.path.insert(0,str(REPO/'tools'))
import stock_video,raw_media,benchmark_stock_sr
from benchmark_stills import quality
ROOT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_spatial_gate_20261030');PARENT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_source_regions_20261030')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
frozen=json.loads((ROOT/'frozen.json').read_text());cp=PARENT/'train/step-3000.pt';assert sha(cp)==frozen['checkpoint_sha256']
p=dict(schema='gpr.stock_sr_spatial_gate_final_protocol.v1',freeze_sha256=sha(ROOT/'frozen.json'),driver_sha256=sha(Path(__file__)),devices=['mps','cpu'],references=['0001','0067','5323','6693'],historical_references_previously_used=True,selection_or_retuning=False,quality_approval=False)
assert not (ROOT/'final-protocol.json').exists();(ROOT/'final-protocol.json').write_text(json.dumps(p,indent=2)+'\n')
report=dict(schema='gpr.stock_sr_spatial_gate_final.v1',complete=False,quality_approval=False,protocol_sha256=sha(ROOT/'final-protocol.json'),results=[]);torch.set_num_threads(4);started=time.perf_counter()
for device in p['devices']:
 model,_=stock_video.load_cnn(None,cp,torch.device(device));backbone=model.backbone;candidate=frozen['candidate']
 class Gated(torch.nn.Module):
  def forward(self,x):
   base=torch.nn.functional.interpolate(x,scale_factor=2,mode='bicubic',align_corners=False).clamp(0,1)
   a,b,c,d=candidate['ramps'];gate=((base-a)/(b-a)).clamp(0,1)*((d-base)/(d-c)).clamp(0,1)
   return (base+(.01*candidate['alpha'])*gate*backbone(x)).clamp(0,1)
 total=0.;base_total=0.;samples_total=0
 for name in p['references']:
  cache=PARENT/('all-qualified/'+('cpu-final-' if device=='cpu' else 'final-')+name);old=json.loads((cache/'benchmark.json').read_text())
  source=Path('/Users/dcliftreaves/gpr_data/gate_dngs')/('Z8Z_'+name+'.dng');assert sha(source)==old['source_sha256']
  raw=cache/'decoded-low.raw';reference_path=cache/'independent-sdk.raw';assert sha(raw)==old['low_decoded_raw_sha256'] and sha(reference_path)==old['reference_raw_sha256']
  meta=raw_media.extract(source,14);w,h=meta['width'],meta['height'];reference=np.fromfile(reference_path,dtype='<u2').reshape(h,w)
  baseline,_=stock_video.restore(raw,w//2,h//2,benchmark_stock_sr.Bicubic(),torch.device(device),256,64,2)
  assert hashlib.sha256(baseline.tobytes()).hexdigest()==old['bicubic_raw_sha256'];bm=quality(reference,baseline,meta);assert json.loads(json.dumps(bm))==old['bicubic_metrics'];del baseline
  output,seconds=stock_video.restore(raw,w//2,h//2,Gated().eval(),torch.device(device),256,64,2);metrics=quality(reference,output,meta)
  out=ROOT/(device+'-'+name+'.raw');output.tofile(out);del output
  regions=['active','shadow_bottom_decile','highlight_top_decile','detail_top_decile'];failed=[r for r in regions if metrics[r]['rmse_counts']>bm[r]['rmse_counts']]
  top,left,bottom,right=bm['active_area'];samples=(bottom-top)*(right-left);samples_total+=samples;total+=metrics['active']['rmse_counts']**2*samples;base_total+=bm['active']['rmse_counts']**2*samples
  row=dict(device=device,name=name,source_sha256=sha(source),cache_benchmark_sha256=sha(cache/'benchmark.json'),metrics=metrics,bicubic_metrics=bm,regressions=failed,output_sha256=sha(out),inference_s=seconds)
  report['results'].append(row);(ROOT/'final-summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(device=device,name=name,regressions=failed,gain_db=metrics['active']['psnr_db']-bm['active']['psnr_db'],elapsed_s=time.perf_counter()-started)),flush=True)
 report[device+'_pooled_gain_db']=float(10*np.log10(base_total/total))
report.update(complete=True,all_regions_pass=all(not r['regressions'] for r in report['results']),elapsed_s=time.perf_counter()-started)
(ROOT/'final-summary.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(complete=True,all_regions_pass=report['all_regions_pass'],mps_gain_db=report['mps_pooled_gain_db'],cpu_gain_db=report['cpu_pooled_gain_db'])),flush=True)
