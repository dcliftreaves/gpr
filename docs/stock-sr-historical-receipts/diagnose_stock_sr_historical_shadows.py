"""Validation-only attribution of shadow residual error; no fitted inference rule."""
from pathlib import Path
import hashlib,json,sys
import numpy as np
import torch
REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime')
sys.path.insert(0,str(REPO/'tools'))
import stock_video,benchmark_stock_sr,raw_media
ROOT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_historical_global_shadow_20261030')
PARENT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_source_regions_20261030')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    full=ROOT/'full-validation/selection.json';selection=json.loads(full.read_text());assert selection['complete']
    names=['local_shadow-step-400','local_and_global_shadow-step-400','local_and_global_shadow-step-400-weight-interp-half']
    protocol=dict(schema='gpr.stock_sr_historical_shadow_attribution_protocol.v1',driver_sha256=sha(Path(__file__)),selection_sha256=sha(full),names=names,frame_border_width_bayer_pixels=64,
        purpose='Quantify shadow regression from existing complete validation outputs at frame edges versus interior. Report E squared, R squared, and2E.R; no fitted gate, threshold sweep, final pixels or model selection.',quality_approval=False)
    path=ROOT/'shadow-attribution-protocol.json';assert not path.exists();path.write_text(json.dumps(protocol,indent=2)+'\n')
    report=dict(schema='gpr.stock_sr_historical_shadow_attribution.v1',complete=False,protocol_sha256=sha(path),rows=[])
    torch.set_num_threads(4)
    for i,row in enumerate(selection['sources']):
        source=Path(row['source']['path']);assert sha(source)==row['source']['sha256']
        meta=raw_media.extract(source,14);w,h=meta['width'],meta['height']
        cache=PARENT/f'all-qualified/full-validation/validation-{i}';old=json.loads((cache/'benchmark.json').read_text())
        ref=np.fromfile(cache/'independent-sdk.raw',dtype='<u2').reshape(h,w);assert sha(cache/'independent-sdk.raw')==old['reference_raw_sha256']
        base,_=stock_video.restore(cache/'decoded-low.raw',w//2,h//2,benchmark_stock_sr.Bicubic(),torch.device('mps'),256,64,2)
        assert hashlib.sha256(base.tobytes()).hexdigest()==old['bicubic_raw_sha256']
        t,l,b,r=row['bicubic_metrics']['active_area'];reference=ref[t:b,l:r];threshold=float(np.percentile(reference,10));shadow=reference<=threshold
        edge=np.ones(reference.shape,dtype=bool);edge[64:-64,64:-64]=False
        E=base[t:b,l:r].astype(np.float64)-reference
        for name in names:
            c=next(c for c in row['candidates'] if c['name']==name)
            raw=ROOT/'full-validation'/(str(i)+'-'+name+'.raw');assert sha(raw)==c['output_sha256']
            pred=np.memmap(raw,dtype='<u2',mode='r',shape=(h,w));R=pred[t:b,l:r].astype(np.float64)-base[t:b,l:r]
            regions={}
            for label,mask in [('all_shadow',shadow),('frame_border_shadow',shadow&edge),('interior_shadow',shadow&~edge)]:
                ee=E[mask];rr=R[mask];n=int(mask.sum())
                regions[label]=dict(samples=n,baseline_mse=float(np.mean(ee*ee)),residual_mse=float(np.mean(rr*rr)),cross_2ER=float(2*np.mean(ee*rr)),model_mse=float(np.mean((ee+rr)**2)),summed_delta_squared_error=float(np.sum(rr*rr+2*ee*rr)))
            report['rows'].append(dict(source_index=i,source_sha256=row['source']['sha256'],candidate=name,output_sha256=sha(raw),shadow_threshold_counts=threshold,regions=regions))
        print(json.dumps(dict(source_index=i,rows=report['rows'][-3:])),flush=True)
    report['complete']=True;(ROOT/'shadow-attribution.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
