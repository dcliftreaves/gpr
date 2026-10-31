"""Frozen input-only correction family crossed with frame boundary policy."""
from pathlib import Path
import datetime,hashlib,json,shutil,sys,time
import numpy as np
import torch
import torch.nn.functional as F
import stock_sr_historical_boundary as boundary
REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime')
OLD=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_historical_global_shadow_20261030')
PARENT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_source_regions_20261030')
ROOT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_historical_boundary_20261031')
sys.path.insert(0,str(REPO/'tools'));sys.path.insert(0,str(OLD))
import train_stock_sr,stock_video,benchmark_stock_sr,raw_media,mission1_sr_models,mission1_sr_runtime
from benchmark_stills import quality
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,o):p.write_text(json.dumps(o,indent=2)+'\n')

def main():
    ROOT.mkdir(exist_ok=False);cp=OLD/'local_shadow/step-400.pt'
    old= json.loads((OLD/'training.json').read_text());assert old['complete']
    control=next(c for case in old['cases'] for c in case['candidates'] if c['name']=='local_shadow-step-400');assert sha(cp)==control['checkpoint_sha256']
    dataset=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_20261028/dataset');info=json.loads((dataset/'dataset.json').read_text())
    family=[dict(name=g+'-'+str(a),alpha=a,ramps=ramps) for g,ramps in [('none',None),('mild',[.001,.01,.95,.999]),('medium',[.01,.05,.8,.98]),('strong',[.03,.15,.65,.9])] for a in [1.,.5,.25,.125]]
    sources=json.loads((PARENT/'all-qualified/full-validation/protocol.json').read_text())['validation_sources']
    protocol=dict(schema='gpr.stock_sr_historical_boundary_protocol.v1',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),driver_sha256=sha(Path(__file__)),boundary_source_sha256=sha(Path(boundary.__file__)),model_sha256=sha(cp),model_config=control['name'],historical_model_source_sha256=sha(OLD/'mission1_sr_models.py'),historical_runtime_source_sha256=sha(OLD/'mission1_sr_runtime.py'),dataset_sha256=sha(dataset/'dataset.json'),input_sha256=sha(dataset/'inputs.npy'),target_sha256=sha(dataset/'targets.npy'),family=family,edge_policies=['historical','reflect32'],validation_sources=sources,
        gate='Per-site current bicubic normalized counts only; same three fixed ramp arrays as earlier BIBO gate study. Float64 postblend of rounded bicubic/model counts and half-up output rounding; differs from old float-network BIBO gate.',
        reflect_policy='Same historical tile512/overlap32 origins/crops; only actual frame-edge patches gain32 reflected low-plane samples. Coordinates extend linearly using original source dimensions.',
        selection='Unchanged patch pooled+group four-region nonregression/strict overall improvement, then every qualifying setting crossed with both boundary policies on all four full validation sources. Strict every-image active/shadow/highlight/detail nonregression and pooled improvement. Lowest eligible pooled active MSE; freeze before historical finals.',
        checkpoint_retuned=False,final_pixels_used=False,quality_approval=False,torch=torch.__version__,limitations=['Reused Nikon validation; historical pretraining overlap not excluded.','No blind, temporal, native GoPro or restored-detail approval.','Analysis-only 6-channel architecture; standard native loaders do not support it.'])
    save(ROOT/'protocol.json',protocol)
    for path in (Path(__file__),Path(boundary.__file__),OLD/'mission1_sr_models.py',OLD/'mission1_sr_runtime.py'):shutil.copy2(path,ROOT/path.name)
    torch.set_num_threads(4);device=torch.device('mps');checkpoint=torch.load(cp,map_location='cpu',weights_only=True)
    model=mission1_sr_models.make_model_from_config(checkpoint['config']).eval();model.load_state_dict(checkpoint['model'],strict=True)
    # Independent whole-image reflected forward pass on small nondivisible cases.
    rng=np.random.default_rng(20261106);checks=[]
    with torch.inference_mode():
        for h,w in [(97,113),(128,160),(160,192)]:
            planes=rng.integers(1000,5000,(4,h,w),dtype=np.uint16)
            historical,_=mission1_sr_runtime.run_tiles(model,planes,torch.device('cpu'),96,32,True,w*4,h*4,True)
            reproduced,_=boundary.tiled(model,planes,torch.device('cpu'),96,32,False)
            assert np.array_equal(historical,reproduced),'historical CPU tiler identity'
            actual,_=boundary.tiled(model,planes,torch.device('cpu'),96,32,True)
            padded=np.pad(planes.astype(np.float32)*(1./16383),((0,0),(32,32),(32,32)),mode='reflect')
            coordinates=boundary.coordinates(-32,-32,h+64,w+64,h,w)
            pred=model(torch.from_numpy(np.concatenate([padded,coordinates])[None]))[0,:,64:64+h*2,64:64+w*2].numpy()
            expected=np.clip(pred*16383+.5,0,16383).astype('<u2')
            delta=np.abs(actual.astype(np.int32)-expected.astype(np.int32));assert delta.max()<=1
            checks.append(dict(low_plane_hw=[h,w],historical_identity=True,full_reflected_max_counts=int(delta.max()),changed_counts=int(np.count_nonzero(delta))))
    save(ROOT/'tiler-checks.json',dict(complete=True,checks=checks))
    model.to(device);xs=np.load(dataset/'inputs.npy',mmap_mode='r');ys=np.load(dataset/'targets.npy',mmap_mode='r');indices=[];groups={};coords={}
    for s in info['sources']:
        if s['split']=='test':assert s['patch_count']==0;continue
        if s['split']!='validation':continue
        for offset,(y,x) in enumerate(s['low_plane_yx']):
            i=s['patch_start']+offset;indices.append(i);groups[i]=s['group'];coords[i]=boundary.coordinates(x,y,128,128,s['height']//4,s['width']//4)
    assert len(indices)==128
    totals=[{} for _ in range(len(family)+1)];core=slice(64,192)
    with torch.inference_mode():
        for start in range(0,128,8):
            ids=indices[start:start+8];x=torch.from_numpy(np.asarray(xs[ids],dtype=np.float32)/16383).to(device)
            inp=torch.cat([x,torch.from_numpy(np.stack([coords[i] for i in ids])).to(device)],1)
            b=F.interpolate(x,scale_factor=2,mode='bicubic',align_corners=False).clamp(0,1)
            b=np.clip(b[:,:,core,core].cpu().numpy()*16383+.5,0,16383).astype('<u2')
            p=np.clip(model(inp)[:,:,core,core].cpu().numpy()*16383+.5,0,16383).astype('<u2')
            for k,c in enumerate([None]+family):
                output=b if c is None else boundary.correction(b,p,c['alpha'],c['ramps'])
                for i,pred in zip(ids,output):
                    ref=np.asarray(ys[i,:,core,core],dtype=np.float64);m=train_stock_sr.region_totals(ref,pred.astype(np.float64)-ref)
                    for g in ['pooled','group:'+groups[i]]:
                        d=totals[k].setdefault(g,{})
                        for r,(value,count) in m.items():a,n=d.get(r,(0.,0));d[r]=(a+value,n+count)
    scores=[{g:{r:a/n for r,(a,n) in d.items()} for g,d in t.items()} for t in totals];baseline=scores[0]
    assert baseline==old['baseline'];assert scores[1]==control['metrics'],'ungated patch control exact'
    rows=[]
    for c,m in zip(family,scores[1:]):
        bad=[g+':'+r for g,d in baseline.items() for r,v in d.items() if m[g][r]>v]
        rows.append(dict(**c,metrics=m,regressions=bad,eligible=not bad and m['pooled']['overall']<baseline['pooled']['overall']))
    eligible=[r for r in rows if r['eligible']];save(ROOT/'patch-selection.json',dict(complete=True,baseline=baseline,rows=rows,protocol_sha256=sha(ROOT/'protocol.json')))
    candidates=[dict(**c,edge=edge,id=edge+'-'+c['name']) for c in eligible for edge in protocol['edge_policies']]
    assert candidates;print(json.dumps(dict(patch_eligible=len(eligible),full_candidates=len(candidates))),flush=True)
    report=dict(schema='gpr.stock_sr_historical_boundary_full.v1',complete=False,protocol_sha256=sha(ROOT/'protocol.json'),patch_sha256=sha(ROOT/'patch-selection.json'),quality_approval=False,sources=[])
    total={c['id']:0. for c in candidates};bad={c['id']:[] for c in candidates};bt=0.;samples_total=0;started=time.perf_counter()
    oldfull=json.loads((OLD/'full-validation/selection.json').read_text());regions=['active','shadow_bottom_decile','highlight_top_decile','detail_top_decile']
    for index,source in enumerate(sources):
        path=Path(source['path']);assert sha(path)==source['sha256'];meta=raw_media.extract(path,14);w,h=meta['width'],meta['height']
        cache=PARENT/f'all-qualified/full-validation/validation-{index}';previous=json.loads((cache/'benchmark.json').read_text())
        raw=cache/'decoded-low.raw';reference_path=cache/'independent-sdk.raw';assert sha(raw)==previous['low_decoded_raw_sha256'] and sha(reference_path)==previous['reference_raw_sha256']
        ref=np.fromfile(reference_path,dtype='<u2').reshape(h,w)
        base,_=stock_video.restore(raw,w//2,h//2,benchmark_stock_sr.Bicubic(),device,256,64,2);assert hashlib.sha256(base.tobytes()).hexdigest()==previous['bicubic_raw_sha256']
        bm=quality(ref,base,meta);assert json.loads(json.dumps(bm))==previous['bicubic_metrics']
        top,left,bottom,right=bm['active_area'];samples=(bottom-top)*(right-left);samples_total+=samples;bt+=bm['active']['rmse_counts']**2*samples
        prior=next(c for c in oldfull['sources'][index]['candidates'] if c['name']=='local_shadow-step-400')
        oldpath=OLD/f'full-validation/{index}-local_shadow-step-400.raw';assert sha(oldpath)==prior['output_sha256']
        historical=np.fromfile(oldpath,dtype='<u2').reshape(h,w)
        low=np.fromfile(raw,dtype='<u2').reshape(h//2,w//2);reflect,stats=boundary.tiled(model,mission1_sr_runtime.deinterleave(low),device,reflect=True);reflected=boundary.interleave(reflect);del reflect
        # Save prediction once per policy; candidate output arrays remain external.
        for label,array in [('historical',historical),('reflect32',reflected)]:array.tofile(ROOT/f'{index}-{label}-prediction.raw')
        row=dict(source=source,bicubic_metrics=bm,reflect_runtime=stats,candidates=[]);report['sources'].append(row)
        for c in candidates:
            pred=historical if c['edge']=='historical' else reflected
            output=boundary.correction(base,pred,c['alpha'],c['ramps']);metrics=quality(ref,output,meta)
            if c['id']=='historical-none-1.0':assert hashlib.sha256(output.tobytes()).hexdigest()==prior['output_sha256'] and json.loads(json.dumps(metrics))==prior['metrics']
            failed=[r for r in regions if metrics[r]['rmse_counts']>bm[r]['rmse_counts']]
            name=c['id'];total[name]+=metrics['active']['rmse_counts']**2*samples;bad[name].extend(dict(source_index=index,region=r) for r in failed)
            out=ROOT/f'{index}-{name}.raw';output.tofile(out)
            row['candidates'].append(dict(id=name,metrics=metrics,regressions=failed,output_sha256=sha(out)))
            save(ROOT/'full-selection.json',report)
            print(json.dumps(dict(source_index=index,id=name,regressions=failed,gain_db=metrics['active']['psnr_db']-bm['active']['psnr_db'],elapsed_s=time.perf_counter()-started)),flush=True)
        del ref,base,historical,reflected,output;torch.mps.empty_cache()
    results=[dict(id=c['id'],candidate=c,active_mse=total[c['id']]/samples_total,gain_db=float(10*np.log10(bt/total[c['id']])),regressions=bad[c['id']],eligible=not bad[c['id']] and total[c['id']]<bt) for c in candidates]
    selected=[r for r in results if r['eligible']]
    report.update(complete=True,results=results,selected=min(selected,key=lambda r:r['active_mse']) if selected else None,baseline_active_mse=bt/samples_total,active_samples=samples_total,elapsed_s=time.perf_counter()-started)
    save(ROOT/'full-selection.json',report);print(json.dumps(dict(complete=True,selected=report['selected'])),flush=True)

if __name__=='__main__':main()
