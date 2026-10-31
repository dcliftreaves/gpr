"""Evaluate one frozen boundary/correction candidate on reused historical finals."""
from pathlib import Path
import hashlib,json,shutil,sys,time
import numpy as np
import torch
ROOT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_historical_boundary_20261031')
PARENT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_source_regions_20261030')
REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime')
sys.path.insert(0,str(REPO/'tools'));sys.path.insert(0,str(ROOT))
import stock_sr_historical_boundary as boundary
import mission1_sr_models,mission1_sr_runtime,stock_video,benchmark_stock_sr,raw_media
from benchmark_stills import quality
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,o):p.write_text(json.dumps(o,indent=2)+'\n')

def main():
    frozen=json.loads((ROOT/'frozen.json').read_text());c=frozen['candidate'];cp=Path(frozen['checkpoint_path']);assert sha(cp)==frozen['checkpoint_sha256']
    assert sha(ROOT/'stock_sr_historical_boundary.py')==frozen['boundary_source_sha256']
    assert sha(ROOT/'mission1_sr_models.py')==frozen['model_source_sha256']
    assert sha(ROOT/'mission1_sr_runtime.py')==frozen['historical_runtime_source_sha256']
    p=dict(schema='gpr.stock_sr_historical_boundary_final_protocol.v1',freeze_sha256=sha(ROOT/'frozen.json'),driver_sha256=sha(Path(__file__)),devices=['mps','cpu'],references=['0001','0067','5323','6693'],historical_references_previously_used=True,selection_or_retuning=False,quality_approval=False,torch=torch.__version__,tile=512,overlap=32,halo=32,portability_max_counts=1)
    protocol=ROOT/'final-protocol.json';assert not protocol.exists();save(protocol,p);shutil.copy2(Path(__file__),ROOT/Path(__file__).name)
    report=dict(schema='gpr.stock_sr_historical_boundary_final.v1',complete=False,quality_approval=False,protocol_sha256=sha(protocol),results=[]);torch.set_num_threads(4);started=time.perf_counter()
    for device in p['devices']:
        checkpoint=torch.load(cp,map_location='cpu',weights_only=True);model=mission1_sr_models.make_model_from_config(checkpoint['config']);model.load_state_dict(checkpoint['model'],strict=True);model.to(device).eval()
        total=0.;bt=0.;samples_total=0
        for name in p['references']:
            cache=PARENT/('all-qualified/'+('cpu-final-' if device=='cpu' else 'final-')+name);old=json.loads((cache/'benchmark.json').read_text())
            source=Path('/Users/dcliftreaves/gpr_data/gate_dngs')/('Z8Z_'+name+'.dng');assert sha(source)==old['source_sha256']
            raw=cache/'decoded-low.raw';refpath=cache/'independent-sdk.raw';assert sha(raw)==old['low_decoded_raw_sha256'] and sha(refpath)==old['reference_raw_sha256']
            meta=raw_media.extract(source,14);w,h=meta['width'],meta['height'];reference=np.fromfile(refpath,dtype='<u2').reshape(h,w)
            base,_=stock_video.restore(raw,w//2,h//2,benchmark_stock_sr.Bicubic(),torch.device(device),256,64,2)
            assert hashlib.sha256(base.tobytes()).hexdigest()==old['bicubic_raw_sha256'];bm=quality(reference,base,meta);assert json.loads(json.dumps(bm))==old['bicubic_metrics']
            low=np.fromfile(raw,dtype='<u2').reshape(h//2,w//2);pred,stats=boundary.tiled(model,mission1_sr_runtime.deinterleave(low),torch.device(device),reflect=c['edge']=='reflect32')
            output=boundary.correction(base,boundary.interleave(pred),c['alpha'],c['ramps']);metrics=quality(reference,output,meta);path=ROOT/(device+'-'+name+'.raw');output.tofile(path)
            bad=[r for r in ['active','shadow_bottom_decile','highlight_top_decile','detail_top_decile'] if metrics[r]['rmse_counts']>bm[r]['rmse_counts']]
            t,l,b,r=bm['active_area'];samples=(b-t)*(r-l);samples_total+=samples;total+=metrics['active']['rmse_counts']**2*samples;bt+=bm['active']['rmse_counts']**2*samples
            report['results'].append(dict(device=device,name=name,source_sha256=sha(source),cache_benchmark_sha256=sha(cache/'benchmark.json'),metrics=metrics,bicubic_metrics=bm,regressions=bad,output_sha256=sha(path),runtime=stats))
            save(ROOT/'final-summary.json',report);print(json.dumps(dict(device=device,name=name,regressions=bad,gain_db=metrics['active']['psnr_db']-bm['active']['psnr_db'],elapsed_s=time.perf_counter()-started)),flush=True)
            del reference,base,pred,output
            if device=='mps':torch.mps.empty_cache()
        report[device+'_pooled_gain_db']=float(10*np.log10(bt/total))
        del model
    portability=[]
    for name in p['references']:
        cpu=np.fromfile(ROOT/('cpu-'+name+'.raw'),dtype='<u2');mps=np.fromfile(ROOT/('mps-'+name+'.raw'),dtype='<u2');assert cpu.shape==mps.shape
        difference=np.abs(cpu.astype(np.int32)-mps.astype(np.int32));portability.append(dict(reference=name,max_counts=int(difference.max()),changed_counts=int(np.count_nonzero(difference)),pass_budget=bool(difference.max()<=1)))
    report.update(complete=True,all_regions_pass=all(not r['regressions'] for r in report['results']),portability=portability,all_portability_pass=all(r['pass_budget'] for r in portability),elapsed_s=time.perf_counter()-started)
    save(ROOT/'final-summary.json',report);print(json.dumps(dict(complete=True,all_regions_pass=report['all_regions_pass'],all_portability_pass=report['all_portability_pass'],mps_gain_db=report['mps_pooled_gain_db'],cpu_gain_db=report['cpu_pooled_gain_db'])),flush=True)

if __name__=='__main__':main()
