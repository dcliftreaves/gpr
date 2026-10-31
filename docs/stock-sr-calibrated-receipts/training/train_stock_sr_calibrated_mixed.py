"""Matched 2x2 study: sensor canonicalization and a calibrated tone/WB loss."""
from pathlib import Path
import datetime,hashlib,importlib.util,json,shutil,sys,time
import numpy as np
import torch
import torch.nn.functional as F
REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime');sys.path.insert(0,str(REPO/'tools'))
import raw_media,train_stock_sr
BASE=Path('/Volumes/OWC_8TB/gpr_work/artifacts')
ROOT=BASE/'stock_sr_calibrated_mixed_20261031'
CAMERA=BASE/'stock_sr_mission_calibrated_20261031'
NIKON=BASE/'stock_sr_20261028/dataset'
OLD=BASE/'stock_sr_historical_global_shadow_20261030'
CP=OLD/'local_shadow/step-400.pt'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,o):p.write_text(json.dumps(o,indent=2)+'\n')
def module(name,p):
    spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
    ROOT.mkdir(exist_ok=False)
    for p in [Path(__file__),OLD/'mission1_sr_models.py',OLD/'mission1_sr_runtime.py',OLD/'train_mission1_sr.py']:shutil.copy2(p,ROOT/p.name)
    sys.path.insert(0,str(ROOT));models=module('models',ROOT/'mission1_sr_models.py');runtime=module('runtime',ROOT/'mission1_sr_runtime.py');losses=module('losses',ROOT/'train_mission1_sr.py')
    cp=torch.load(CP,map_location='cpu',weights_only=True)
    parent_freeze=json.loads((BASE/'stock_sr_historical_boundary_20261031/frozen.json').read_text());assert sha(CP)==parent_freeze['checkpoint_sha256']
    datasets=[];train_domains=[];validation=[];coordinates={};calibration={};source_audits=[]
    for domain,path in [('nikon',NIKON),('mission1',CAMERA/'dataset')]:
        info=json.loads((path/'dataset.json').read_text());assert info['complete'] and sha(path/'inputs.npy')==info['input_sha256'] and sha(path/'targets.npy')==info['target_sha256']
        data_index=len(datasets);datasets.append((np.load(path/'inputs.npy',mmap_mode='r'),np.load(path/'targets.npy',mmap_mode='r')));training=[]
        for source in info['sources']:
            if source['split']=='test':assert source['patch_start'] is None and source['patch_count']==0;continue
            source_path=Path(source['path']);assert sha(source_path)==source['sha256'];meta=raw_media.extract(source_path,14);tags={t['code']:t for t in meta['image']}
            black=np.array(raw_media.values(tags[50714]),np.float32);white=float(raw_media.values(tags[50717])[0]);neutral=np.array(raw_media.values(tags[50728]),np.float32)
            assert black.shape==(4,) and (white>black).all() and neutral.shape==(3,) and (neutral>0).all() and meta['cfa']=='RGGB'
            wb=neutral[1]/neutral;wbg=np.array([wb[0],wb[1],wb[1],wb[2]],np.float32)
            indices=[]
            for offset,(y,x) in enumerate(source['low_plane_yx']):
                i=source['patch_start']+offset;key=(data_index,i);indices.append(key)
                coordinates[key]=runtime.coord_channels(x0=x,y0=y,tile=128,low_plane_w=source['width']//4,low_plane_h=source['height']//4)
                calibration[key]=(black.copy(),white,wbg.copy(),domain+':'+source['group'])
            (training if source['split']=='train' else validation).append(indices)
            source_audits.append(dict(domain=domain,source_sha256=source['sha256'],split=source['split'],black_level=black.tolist(),white_level=white,wb_gains=wbg.tolist(),patches=len(indices),group=source['group']))
        train_domains.append(training)
    validation=[k for group in validation for k in group];assert len(validation)==320 and [len(x) for x in train_domains]==[8,28]
    family=[dict(name=f'canonical{int(c)}-tone{int(t)}',canonical=c,tone_weight=.1 if t else 0.) for c in [False,True] for t in [False,True]]
    protocol=dict(schema='gpr.stock_sr_calibrated_mixed_protocol.v1',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),driver_sha256=sha(Path(__file__)),checkpoint_sha256=sha(CP),config=cp['config'],sources=source_audits,nikon_dataset_sha256=sha(NIKON/'dataset.json'),camera_dataset_sha256=sha(CAMERA/'dataset/dataset.json'),camera_calibration_audit_sha256=sha(CAMERA/'calibration-audit.json'),code_sha256={n:sha(ROOT/n) for n in ['mission1_sr_models.py','mission1_sr_runtime.py','train_mission1_sr.py']},family=family,
        seed=20261108,steps=800,batch=8,learning_rate=.00003,weight_decay=.0001,checkpoints=[400,800],sampling='Each step4distinctNikon+4distinctMission1 training sources; one uniform patch per source; identical RNG sequence across all four cases',
        canonicalization='After actual native-count stockQ3 decode: gain=(15892-1008)/(white-black), offset=(1008-black*gain)/16383; affine all four raw input planes before old network, inverse affine+clip output to sensor counts. Nikon gain1/offset0 exact. Coordinates unchanged. No re-encoding normalized inputs.',
        base_losses='Original Charbonnier+4gradient+0.05Laplacian+0.1detailphase +0.02precleanAux+0.03precleanDetailAux. Preclean target rounded same-site2x2 sensor target, mapped to network domain for canonicalized cases. No hinge/gate/output-strength/interpolation sweep.',
        tone_proxy='Normalized (counts-black)/(white-black), per-source AsShotNeutral-derived white balance, 2x2 Bayer RGB proxy (mean green), clip0..1 and sqrt(signal+1e-4); Charbonnier error, weight0.1 in tone cases. Not actual demosaicing/CIRAWFilter, color-matrix conversion or perceptual/temporal approval.',
        selection='All pooled/per-source-group patch RAW overall/shadow/highlight/detail MSE nonincrease vs identical current bicubic, strict pooled overall improvement, plus tone-proxy MSE nonincrease in every group. Every qualified checkpoint must pass all complete validation images and matched actual rendering before any freeze/final evaluation.',
        final_reference_pixels_used=False,quality_approval=False,limitations=['Mission1 reference counts from archived compressed GPR, per-frame recovered calibration; not fresh originals or sensor truth.','Conservative venue splits, but old pretraining overlaps these historical sources; no blind/generalization claim.','Reused Nikon validation and previously observed GoPro final/reference results motivate this separate training study; no final pixels in arrays or losses.','Single seed, fixed budget, tone/WB proxy is approximate; direct renderer validation remains mandatory.'])
    save(ROOT/'protocol.json',protocol);torch.set_num_threads(4);device=torch.device('mps');core=slice(64,192);lowcore=slice(32,96)
    def tensors(keys):
        raw=np.stack([np.asarray(datasets[d][0][i],np.float32)/16383 for d,i in keys]);target=np.stack([np.asarray(datasets[d][1][i],np.float32)/16383 for d,i in keys])
        black=np.stack([calibration[k][0] for k in keys])[:,:,None,None];white=np.array([calibration[k][1] for k in keys],np.float32)[:,None,None,None];wb=np.stack([calibration[k][2] for k in keys])[:,:,None,None]
        return tuple(torch.from_numpy(v).to(device) for v in [raw,target,np.stack([coordinates[k] for k in keys]),black,white,wb])
    def affine(b,w,enabled):
        if not enabled:return torch.ones_like(b),torch.zeros_like(b)
        gain=(15892.-1008.)/(w-b);return gain,(1008.-b*gain)/16383.
    def tone(pred,b,w,wb):
        signal=((pred*16383.-b)/(w-b)*wb).clamp(0,1);rgb=torch.stack([signal[:,0],.5*(signal[:,1]+signal[:,2]),signal[:,3]],dim=1)
        return (rgb+1e-4).sqrt()
    def evaluate(model,case):
        model.eval() if model is not None else None;totals={};proxy={}
        with torch.inference_mode():
            for start in range(0,len(validation),8):
                keys=validation[start:start+8];x,y,co,b,w,wb=tensors(keys);gain,offset=affine(b,w,case['canonical'])
                pred=F.interpolate(x,scale_factor=2,mode='bicubic',align_corners=False).clamp(0,1) if model is None else ((model(torch.cat([x*gain+offset,co],1))-offset)/gain).clamp(0,1)
                counts=np.clip(pred[:,:,core,core].cpu().numpy()*16383+.5,0,16383).astype('<u2');reference=np.stack([np.asarray(datasets[d][1][i,:,core,core],np.float64) for d,i in keys])
                counted=torch.from_numpy(counts.astype(np.float32)/16383).to(device);target=torch.from_numpy(reference.astype(np.float32)/16383).to(device)
                proxy_error=(tone(counted,b,w,wb)-tone(target,b,w,wb)).square().cpu().numpy()
                for k,p,r,e in zip(keys,counts,reference,proxy_error):
                    m=train_stock_sr.region_totals(r,p.astype(np.float64)-r)
                    for g in ['pooled',calibration[k][3]]:
                        a,n=proxy.get(g,(0.,0));proxy[g]=(a+float(e.astype(np.float64).sum()),n+e.size)
                        dest=totals.setdefault(g,{})
                        for region,(value,count) in m.items():a,n=dest.get(region,(0.,0));dest[region]=(a+value,n+count)
        return dict(regions={g:{r:a/n for r,(a,n) in d.items()} for g,d in totals.items()},tone_proxy_mse={g:a/n for g,(a,n) in proxy.items()})
    baseline=evaluate(None,family[0]);save(ROOT/'baseline.json',baseline)
    report=dict(schema='gpr.stock_sr_calibrated_mixed.v1',complete=False,protocol_sha256=sha(ROOT/'protocol.json'),baseline_sha256=sha(ROOT/'baseline.json'),torch=torch.__version__,cases=[],quality_approval=False);started=time.perf_counter()
    for case in family:
        rng=np.random.default_rng(protocol['seed']);torch.manual_seed(protocol['seed']);model=models.make_model_from_config(cp['config']);model.load_state_dict(cp['model'],strict=True);model.to(device).train()
        optimizer=torch.optim.AdamW(model.parameters(),lr=protocol['learning_rate'],weight_decay=protocol['weight_decay']);directory=ROOT/case['name'];directory.mkdir();row=dict(case=case,checkpoints=[]);report['cases'].append(row)
        for step in range(1,protocol['steps']+1):
            indices=[]
            for domain in train_domains:
                for source_index in rng.choice(len(domain),size=4,replace=False):
                    source=domain[int(source_index)];indices.append(source[int(rng.integers(len(source)))])
            x,y,co,b,w,wb=tensors(indices);gain,offset=affine(b,w,case['canonical']);inputs=torch.cat([x*gain+offset,co],1);model.train();optimizer.zero_grad(set_to_none=True)
            pred=((model(inputs)-offset)/gain).clamp(0,1)[:,:,core,core];target=y[:,:,core,core]
            loss=losses.robust_l1(pred,target,'charbonnier')
            loss=loss+4*(losses.robust_l1(pred[:,:,:,1:]-pred[:,:,:,:-1],target[:,:,:,1:]-target[:,:,:,:-1],'charbonnier')+losses.robust_l1(pred[:,:,1:,:]-pred[:,:,:-1,:],target[:,:,1:,:]-target[:,:,:-1,:],'charbonnier'))
            loss=loss+.05*losses.robust_l1(losses.laplacian(pred),losses.laplacian(target),'charbonnier')+.1*losses.detail_phase_loss(pred,target,'charbonnier',threshold_counts=2.)
            clean=(F.avg_pool2d(y*16383.,2)+.5).floor()/16383.;clean=clean*gain+offset
            low=model.clean_low(inputs)[:,:,lowcore,lowcore];lowtarget=clean[:,:,lowcore,lowcore]
            loss=loss+.02*losses.robust_l1(low,lowtarget,'charbonnier')+.03*losses.detail_phase_loss(low,lowtarget,'charbonnier',threshold_counts=2.)
            if case['tone_weight']:loss=loss+case['tone_weight']*losses.robust_l1(tone(pred,b,w,wb),tone(target,b,w,wb),'charbonnier')
            assert torch.isfinite(loss).item();loss.backward();optimizer.step()
            if step in protocol['checkpoints']:
                path=directory/f'step-{step}.pt';torch.save(dict(model={k:v.detach().cpu() for k,v in model.state_dict().items()},config=cp['config'],case=case,step=step,protocol_sha256=sha(ROOT/'protocol.json'),quality_approval=False),path)
                scores=evaluate(model,case);bad=[g+':'+r for g,d in baseline['regions'].items() for r,v in d.items() if scores['regions'][g][r]>v];tonebad=[g for g,v in baseline['tone_proxy_mse'].items() if scores['tone_proxy_mse'][g]>v]
                gain_db=train_stock_sr.delta(baseline['regions']['pooled']['overall'],scores['regions']['pooled']['overall']);eligible=not bad and not tonebad and gain_db>0
                result=dict(step=step,path=str(path),checkpoint_sha256=sha(path),loss=float(loss.item()),metrics=scores,raw_regressions=bad,tone_proxy_regressions=tonebad,eligible=eligible,gain_db=gain_db,elapsed_s=time.perf_counter()-started)
                row['checkpoints'].append(result);save(ROOT/'training.json',report);print(json.dumps(dict(case=case['name'],step=step,gain_db=gain_db,eligible=eligible,raw_regressions=bad,tone_regressions=tonebad,elapsed_s=result['elapsed_s'])),flush=True)
        del model,optimizer;torch.mps.empty_cache()
    report.update(complete=True,elapsed_s=time.perf_counter()-started);save(ROOT/'training.json',report);print(json.dumps(dict(complete=True,elapsed_s=report['elapsed_s'])),flush=True)
if __name__=='__main__':main()
