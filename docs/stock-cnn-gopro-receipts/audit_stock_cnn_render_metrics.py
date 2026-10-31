"""Independent chunked RGB/luma audit without matrix-multiply FP warnings."""
from pathlib import Path
import json,hashlib
import numpy as np,tifffile
ROOT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_cnn_supplied_gopro_shared_20261030/render-review');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();original=json.loads((ROOT/'summary.json').read_text());assert original['complete']
protocol=dict(schema='gpr.stock_cnn_render_audit_protocol.v1',render_summary_sha256=sha(ROOT/'summary.json'),driver_sha256=sha(Path(__file__)),strict_numpy_floating_errors=True,agreement_relative_tolerance=1e-10,initial_matmul_warnings_observed=True)
(ROOT/'audit-protocol.json').write_text(json.dumps(protocol,indent=2)+'\n');rows=[]
with np.errstate(all='raise'):
 for case in original['cases']:
  folder=ROOT/Path(case['source']).stem
  with tifffile.TiffFile(folder/'reference.tiff') as f:reference=f.asarray()
  metrics={}
  for name in ['stock','cnn']:
   with tifffile.TiffFile(folder/(name+'.tiff')) as f:value=f.asarray()
   assert value.shape==reference.shape
   total=0.;ytotal=0.;bias=np.zeros(3,np.float64);samples=0
   for start in range(0,reference.shape[0],128):
    e=value[start:start+128,:,:3].astype(np.float64)-reference[start:start+128,:,:3]
    y=e[...,0]*.2126+e[...,1]*.7152+e[...,2]*.0722
    assert np.isfinite(e).all() and np.isfinite(y).all()
    total+=float(np.sum(e*e));ytotal+=float(np.sum(y*y));bias+=e.sum(axis=(0,1));samples+=y.size
   result=dict(rgb_mse=total/(samples*3),y_prime_mse=ytotal/samples,rgb_bias_counts=(bias/samples).tolist())
   for key in ['rgb_mse','y_prime_mse']:
    previous=case[name][key];assert abs(result[key]-previous)<=protocol['agreement_relative_tolerance']*max(1.,abs(previous)),(case['source'],name,key)
   metrics[name]=result
  gain=float(10*np.log10(metrics['stock']['rgb_mse']/metrics['cnn']['rgb_mse']));ygain=float(10*np.log10(metrics['stock']['y_prime_mse']/metrics['cnn']['y_prime_mse']))
  rows.append(dict(source=case['source'],metrics=metrics,rgb_gain_db=gain,y_prime_gain_db=ygain,numeric_nonregression=metrics['cnn']['rgb_mse']<=metrics['stock']['rgb_mse'] and metrics['cnn']['y_prime_mse']<=metrics['stock']['y_prime_mse'],tiff_sha256={name:sha(folder/(name+'.tiff')) for name in ['reference','stock','cnn']}))
report=dict(schema='gpr.stock_cnn_render_audit.v1',complete=True,protocol_sha256=sha(ROOT/'audit-protocol.json'),cases=rows,all_numeric_nonregression=all(r['numeric_nonregression'] for r in rows),quality_approval=False)
(ROOT/'audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(complete=True,all_numeric_nonregression=report['all_numeric_nonregression'],gains=[(r['source'],r['rgb_gain_db'],r['y_prime_gain_db']) for r in rows])),flush=True)
