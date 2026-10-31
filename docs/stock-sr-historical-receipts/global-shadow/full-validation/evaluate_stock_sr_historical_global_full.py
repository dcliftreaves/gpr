"""Complete-image validation of every patch-qualified historical-architecture candidate."""
from pathlib import Path
import datetime, hashlib, json, shutil, sys, time
import numpy as np
import torch

REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime')
ROOT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_historical_global_shadow_20261030')
PARENT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_source_regions_20261030')
sys.path.insert(0,str(REPO/'tools'));sys.path.insert(0,str(ROOT))
import raw_media, stock_video, benchmark_stock_sr, mission1_sr_models, mission1_sr_runtime
from benchmark_stills import quality

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):path.write_text(json.dumps(value,indent=2)+'\n')

def main():
    training=json.loads((ROOT/'training.json').read_text());assert training['complete']
    candidates=[row for case in training['cases'] for row in case['candidates'] if row['eligible']]
    assert candidates and len(candidates)<=8 and all(row['name'].startswith(('local_shadow-','local_and_global_shadow-')) for row in candidates)
    previous_protocol=PARENT/'all-qualified/full-validation/protocol.json'
    sources=json.loads(previous_protocol.read_text())['validation_sources']
    directory=ROOT/'full-validation';directory.mkdir(exist_ok=False)
    shutil.copy2(Path(__file__),directory/Path(__file__).name)
    protocol=dict(schema='gpr.stock_sr_historical_global_full_protocol.v1',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        driver_sha256=sha(Path(__file__)),training_sha256=sha(ROOT/'training.json'),training_protocol_sha256=sha(ROOT/'protocol.json'),
        parent_full_protocol_sha256=sha(previous_protocol),candidates=candidates,validation_sources=sources,
        torch=torch.__version__,device='mps',threads=4,tile=512,overlap=32,coordinate_channels=True,
        model_source_sha256=sha(ROOT/'mission1_sr_models.py'),runtime_source_sha256=sha(ROOT/'mission1_sr_runtime.py'),
        metric_source_sha256=sha(REPO/'tools/benchmark_stills.py'),baseline_source_sha256=sha(REPO/'tools/stock_video.py'),
        tiling='Exact archived historical run_tiles: global coordinates; crop half-overlap; original zero-convolution frame edges. Current bicubic comparison keeps its original reflect-halo runtime.',
        selection='Every candidate on all four complete validation sources; every per-image active/shadow/highlight/detail RMSE must not increase; strict pooled active MSE improvement; select lowest eligible pooled active MSE.',
        final_reference_pixels_used=False,quality_approval=False,
        limitations=['Validation held out from these updates only; historical pretraining overlap not excluded.','Reused small Nikon dataset; not native GoPro/temporal or visible-detail approval.','No reference masks at inference; all region masks used only for scoring.'])
    save(directory/'protocol.json',protocol)
    torch.set_num_threads(4);device=torch.device('mps');regions=['active','shadow_bottom_decile','highlight_top_decile','detail_top_decile']
    totals={c['name']:0. for c in candidates};regressions={c['name']:[] for c in candidates}
    baseline_total=0.;samples_total=0;started=time.perf_counter()
    report=dict(schema='gpr.stock_sr_historical_global_full.v1',complete=False,quality_approval=False,protocol_sha256=sha(directory/'protocol.json'),sources=[])
    for index,source in enumerate(sources):
        path=Path(source['path']);assert sha(path)==source['sha256']
        cache=PARENT/f'all-qualified/full-validation/validation-{index}'
        old=json.loads((cache/'benchmark.json').read_text());assert old['source_sha256']==source['sha256']
        raw=cache/'decoded-low.raw';refpath=cache/'independent-sdk.raw'
        assert sha(raw)==old['low_decoded_raw_sha256'] and sha(refpath)==old['reference_raw_sha256']
        meta=raw_media.extract(path,14);w,h=meta['width'],meta['height']
        reference=np.fromfile(refpath,dtype='<u2').reshape(h,w)
        baseline,_=stock_video.restore(raw,w//2,h//2,benchmark_stock_sr.Bicubic(),device,256,64,2)
        assert hashlib.sha256(baseline.tobytes()).hexdigest()==old['bicubic_raw_sha256'],'exact bicubic pixels'
        bm=quality(reference,baseline,meta);assert json.loads(json.dumps(bm))==old['bicubic_metrics'],'exact bicubic metrics'
        del baseline
        top,left,bottom,right=bm['active_area'];samples=(bottom-top)*(right-left)
        samples_total+=samples;baseline_total+=bm['active']['rmse_counts']**2*samples
        row=dict(source=source,cache_benchmark_sha256=sha(cache/'benchmark.json'),bicubic_metrics=bm,candidates=[]);report['sources'].append(row)
        low=np.fromfile(raw,dtype='<u2').reshape(h//2,w//2);planes=mission1_sr_runtime.deinterleave(low)
        for candidate in candidates:
            cp=Path(candidate['path']);assert sha(cp)==candidate['checkpoint_sha256']
            ckpt=torch.load(cp,map_location='cpu',weights_only=True)
            model=mission1_sr_models.make_model_from_config(ckpt['config']);model.load_state_dict(ckpt['model'],strict=True);model.to(device).eval()
            predicted,stats=mission1_sr_runtime.run_tiles(model,planes,device,512,32,True,w,h,True)
            assert predicted.shape==(4,h//2,w//2) and predicted.dtype==np.uint16 and predicted.max()<=16383
            output=np.empty((h,w),dtype='<u2')
            for site in range(4):output[site//2::2,site%2::2]=predicted[site]
            metrics=quality(reference,output,meta)
            output_path=directory/(str(index)+'-'+candidate['name']+'.raw');output.tofile(output_path)
            failed=[r for r in regions if metrics[r]['rmse_counts']>bm[r]['rmse_counts']]
            name=candidate['name'];totals[name]+=metrics['active']['rmse_counts']**2*samples
            regressions[name].extend(dict(source_index=index,region=r) for r in failed)
            row['candidates'].append(dict(name=name,checkpoint_sha256=sha(cp),metrics=metrics,regressions=failed,output_sha256=sha(output_path),runtime=stats))
            save(directory/'selection.json',report)
            print(json.dumps(dict(source_index=index,name=name,regressions=failed,gain_db=metrics['active']['psnr_db']-bm['active']['psnr_db'],elapsed_s=time.perf_counter()-started)),flush=True)
            del model,predicted,output;torch.mps.empty_cache()
    baseline_mse=baseline_total/samples_total
    results=[dict(name=c['name'],active_mse=totals[c['name']]/samples_total,gain_db=float(10*np.log10(baseline_mse/(totals[c['name']]/samples_total))),regressions=regressions[c['name']],eligible=not regressions[c['name']] and totals[c['name']]<baseline_total) for c in candidates]
    qualified=[r for r in results if r['eligible']]
    report.update(complete=True,baseline_active_mse=baseline_mse,active_samples=samples_total,results=results,selected=min(qualified,key=lambda r:r['active_mse']) if qualified else None,elapsed_s=time.perf_counter()-started)
    save(directory/'selection.json',report)
    print(json.dumps(dict(complete=True,results=results,selected=report['selected'])),flush=True)

if __name__=='__main__':main()
