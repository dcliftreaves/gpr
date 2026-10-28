#!/usr/bin/env python3
"""Build audited stock-Q3 2x pairs and train a fresh optional BIBO candidate.

Development dependencies: numpy, Torch, tifffile/imagecodecs and gpr_tools.
Training, validation and final-test source groups must be declared separately.
Final-test images are hashed but never decoded into the training patch arrays.
No training result automatically receives production or visual approval.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import time

import numpy as np
import tifffile
import torch
import torch.nn.functional as functional

from benchmark_stills import bayer_page
from benchmark_stock_sr import simulation_metadata
import raw_media
import stock_cnn_models
import stock_still

PEAK=16383.


def psnr(mse):
    return None if mse==0 else 10*math.log10(PEAK**2/mse)


def delta(baseline,mse):
    if baseline==0 or mse==0: return 0. if baseline==mse else None
    return 10*math.log10(baseline/mse)


def sources(manifest):
    if manifest.get('schema')!='gpr.stock_sr_sources.v1' or not isinstance(manifest.get('sources'),list):
        raise ValueError('requires gpr.stock_sr_sources.v1 sources')
    groups={}; hashes=set(); result=[]; splits=set()
    for item in manifest['sources']:
        path=Path(item['path']).resolve(); group=item['group']; split=item['split']
        if not isinstance(group,str) or not group or split not in ('train','validation','test'):
            raise ValueError('invalid source group/split')
        if group in groups and groups[group]!=split: raise ValueError('source group crosses dataset splits')
        groups[group]=split; splits.add(split)
        digest=stock_still.digest(path)
        if digest in hashes: raise ValueError('duplicate source bytes across the dataset')
        if 'sha256' in item and item['sha256']!=digest: raise ValueError('declared source hash differs')
        hashes.add(digest)
        result.append(dict(path=str(path),group=group,split=split,sha256=digest))
    if splits!={'train','validation','test'}: raise ValueError('requires separate train, validation and final-test sources')
    return result


def deinterleave(image):
    return np.stack([image[0::2,0::2],image[0::2,1::2],image[1::2,0::2],image[1::2,1::2]])


def downsample(planes):
    value=planes.astype(np.uint32)
    return ((value[:,0::2,0::2]+value[:,0::2,1::2]+value[:,1::2,0::2]+value[:,1::2,1::2]+2)//4).astype('<u2')


def tool_hashes():
    return {name:stock_still.digest(Path(__file__).parent/name) for name in
            ('train_stock_sr.py','benchmark_stock_sr.py','stock_still.py','stock_video.py',
             'raw_media.py','stock_cnn_metadata.py','stock_cnn_models.py')}


def build(manifest_path,sdk,output_dir,patch=128,train_patches=64,validation_patches=32,seed=20261028):
    if patch<64 or patch%8 or train_patches<1 or validation_patches<1:
        raise ValueError('patch must be a multiple of eight >=64; patch counts must be positive')
    manifest=json.loads(Path(manifest_path).read_text()); selected=sources(manifest)
    count=sum(train_patches if r['split']=='train' else validation_patches if r['split']=='validation' else 0 for r in selected)
    root=Path(output_dir).resolve();root.mkdir(parents=True,exist_ok=False)
    report=dict(schema='gpr.stock_sr_dataset.v1',complete=False,seed=seed,patch_plane_pixels=patch,
                source_manifest_sha256=stock_still.digest(manifest_path),sources=selected,
                input_shape=[count,4,patch,patch],target_shape=[count,4,patch*2,patch*2],
                dtype='<u2',cfa='RGGB',sample_bits=14,stock_quality=3,output_scale=2,
                simulation='same-site rounded 2x2 area averaging, followed by whole-frame stock-Q3 encode/decode',
                split_contract='Declared groups are disjoint and source bytes unique; final-test pixels are not read into dataset arrays. Scene-group labels are caller supplied.',
                source_files=tool_hashes(),sdk_sha256=stock_still.digest(sdk))
    log=root/'dataset.json';log.write_text(json.dumps(report,indent=2)+'\n')
    inputs=np.lib.format.open_memmap(root/'inputs.npy',mode='w+',dtype='<u2',shape=tuple(report['input_shape']))
    targets=np.lib.format.open_memmap(root/'targets.npy',mode='w+',dtype='<u2',shape=tuple(report['target_shape']))
    rng=np.random.default_rng(seed);cursor=0
    for index,row in enumerate(selected):
        if row['split']=='test':
            row.update(patch_start=None,patch_count=0)
            continue
        source=Path(row['path']);meta=raw_media.extract(source,14);w,h=meta['width'],meta['height']
        if meta['cfa']!='RGGB' or w%4 or h%4 or w//4<patch or h//4<patch:
            raise ValueError('source must be RGGB14, divisible by four, and large enough for complete patches')
        with tifffile.TiffFile(source) as file:
            page=bayer_page(file.pages)
            if int(page.compression) not in (1,7,8,32946): raise ValueError('requires lossless source DNG')
            reference=page.asarray()
        if reference.shape!=(h,w) or reference.dtype!=np.dtype('<u2') or np.any(reference>PEAK):
            raise ValueError('source count/geometry contract differs')
        work=root/f'source-{index:03d}';work.mkdir()
        independent=work/'reference.raw'
        stock_still.run(sdk,['-i',source,'-o',independent],None)
        if not np.array_equal(np.fromfile(independent,dtype='<u2').reshape(h,w),reference):
            raise ValueError('independent lossless source decoders disagree')
        high=deinterleave(reference);small=downsample(high)
        low=np.empty((h//2,w//2),dtype='<u2')
        for site in range(4):low[site//2::2,site%2::2]=small[site]
        low_meta,omitted=simulation_metadata(meta)
        raw=work/'input.raw';low.tofile(raw)
        gpr=work/'input-q3.gpr';encoded=stock_still.encode(raw,low_meta,3,sdk,gpr)
        dng=work/'decoded.dng';decoded=stock_still.decode(gpr,14,sdk,dng)
        with tifffile.TiffFile(dng) as file: decoded_planes=deinterleave(file.asarray())
        n=train_patches if row['split']=='train' else validation_patches
        coordinates=[]
        for _ in range(n):
            # Multiples of eight preserve the three-level U-Net's grid phase.
            y=int(rng.integers(0,(h//4-patch)//8+1))*8
            x=int(rng.integers(0,(w//4-patch)//8+1))*8
            inputs[cursor]=decoded_planes[:,y:y+patch,x:x+patch]
            targets[cursor]=high[:,2*y:2*(y+patch),2*x:2*(x+patch)]
            coordinates.append([y,x]);cursor+=1
        row.update(width=w,height=h,patch_start=cursor-n,patch_count=n,low_plane_yx=coordinates,
                   independent_source_decode_verified=True,reference_raw_sha256=stock_still.digest(independent),
                   low_input_raw_sha256=stock_still.digest(raw),low_gpr_sha256=encoded['output_sha256'],
                   low_decoded_raw_sha256=decoded['raw_sha256'],simulation_metadata_omissions=omitted)
        independent.unlink()
        print(json.dumps(dict(source=source.name,split=row['split'],patches=n,total_written=cursor)),flush=True)
        log.write_text(json.dumps(report,indent=2)+'\n')
    assert cursor==count
    inputs.flush();targets.flush();del inputs,targets
    report.update(complete=True,input_sha256=stock_still.digest(root/'inputs.npy'),target_sha256=stock_still.digest(root/'targets.npy'))
    log.write_text(json.dumps(report,indent=2)+'\n')
    return report


def predict(backbone,x,residual_scale):
    base=functional.interpolate(x,scale_factor=2,mode='bicubic',align_corners=False).clamp(0,1)
    return (base+residual_scale*backbone(x)).clamp(0,1)


def train(dataset,output_dir,device='cpu',steps=1000,batch=8,learning_rate=.0003,validate_every=50,seed=20261028):
    if steps<1 or batch<1 or validate_every<1 or not math.isfinite(learning_rate) or learning_rate<=0:
        raise ValueError('invalid training schedule')
    dataset=Path(dataset).resolve(); info=json.loads((dataset/'dataset.json').read_text())
    if info.get('schema')!='gpr.stock_sr_dataset.v1' or info.get('complete') is not True:
        raise ValueError('requires a completed audited stock-SR dataset')
    if tuple(info.get(k) for k in ('cfa','sample_bits','stock_quality','output_scale','dtype'))!=('RGGB',14,3,2,'<u2'):
        raise ValueError('dataset is outside the stock-Q3 RGGB14 2x contract')
    for name,key in (('inputs.npy','input_sha256'),('targets.npy','target_sha256')):
        if stock_still.digest(dataset/name)!=info[key]:raise ValueError('dataset array hash differs')
    inputs=np.load(dataset/'inputs.npy',mmap_mode='r',allow_pickle=False)
    targets=np.load(dataset/'targets.npy',mmap_mode='r',allow_pickle=False)
    if list(inputs.shape)!=info['input_shape'] or list(targets.shape)!=info['target_shape'] or inputs.dtype!=np.dtype('<u2') or targets.dtype!=np.dtype('<u2'):
        raise ValueError('dataset shape/count format differs')
    if (inputs.ndim!=4 or inputs.shape[1]!=4 or inputs.shape[-1]!=inputs.shape[-2] or
        inputs.shape[-1]<64 or inputs.shape[-1]%8 or
        targets.shape!=(inputs.shape[0],4,inputs.shape[-2]*2,inputs.shape[-1]*2) or
        inputs.max(initial=0)>PEAK or targets.max(initial=0)>PEAK):
        raise ValueError('invalid dataset Bayer planes/count domain')
    groups={};train_indices=[];validation_indices=[];seen=set()
    for row in info['sources']:
        group,split=row['group'],row['split']
        if not isinstance(group,str) or not group or split not in ('train','validation','test'):
            raise ValueError('invalid dataset source group/split')
        if group in groups and groups[group]!=split:raise ValueError('dataset group leakage')
        groups[group]=split
        if row['sha256'] in seen:raise ValueError('duplicate dataset source')
        seen.add(row['sha256'])
        if split=='test':
            if row['patch_start'] is not None or row['patch_count']!=0:raise ValueError('final-test pixels leaked into patch arrays')
            continue
        indices=list(range(row['patch_start'],row['patch_start']+row['patch_count']))
        (train_indices if split=='train' else validation_indices).extend(indices)
    if set(groups.values())!={'train','validation','test'} or not train_indices or not validation_indices or set(train_indices)&set(validation_indices) or sorted(train_indices+validation_indices)!=list(range(len(inputs))):
        raise ValueError('invalid train/validation patch partition')
    root=Path(output_dir).resolve();root.mkdir(parents=True,exist_ok=False)
    torch.manual_seed(seed);rng=np.random.default_rng(seed);torch.set_num_threads(4)
    device=torch.device(device);backbone=stock_cnn_models.build('F_ane').to(device)
    with torch.no_grad():
        backbone.subpixel[0].weight.zero_();backbone.subpixel[0].bias.zero_()
    residual_scale=.01
    optimizer=torch.optim.AdamW(backbone.parameters(),lr=learning_rate,weight_decay=.0001)
    patch=inputs.shape[-1];margin=patch//2  # high-plane pixels: 128 in -> 64 core -> 128 out
    core=slice(margin,patch*2-margin)
    def tensors(indices):
        return (torch.from_numpy(np.asarray(inputs[indices],dtype=np.float32)/PEAK).to(device),
                torch.from_numpy(np.asarray(targets[indices],dtype=np.float32)).to(device))
    def validation(baseline=False):
        backbone.eval(); squared=0.;samples=0
        with torch.inference_mode():
            for start in range(0,len(validation_indices),batch):
                x,target=tensors(validation_indices[start:start+batch])
                value=functional.interpolate(x,scale_factor=2,mode='bicubic',align_corners=False).clamp(0,1) if baseline else predict(backbone,x,residual_scale)
                # Match deployed NumPy count quantization, and accumulate on
                # CPU: MPS does not implement float64 tensor arithmetic.
                counts=np.clip(value[:,:,core,core].cpu().numpy()*PEAK+.5,0,PEAK).astype('<u2')
                error=counts.astype(np.float64)-target[:,:,core,core].cpu().numpy()
                squared+=float(np.square(error).sum());samples+=error.size
        return squared/samples
    baseline=validation(True);best=baseline;best_step=0;started=time.perf_counter()
    report=dict(schema='gpr.stock_sr_training.v1',complete=False,quality_approval=False,
                fresh_initialization=True,pretrained_weights=False,seed=seed,torch=torch.__version__,host=platform.platform(),
                device=str(device),dataset_sha256=stock_still.digest(dataset/'dataset.json'),dataset_input_sha256=info['input_sha256'],
                dataset_target_sha256=info['target_sha256'],groups=groups,train_patches=len(train_indices),validation_patches=len(validation_indices),
                final_test_used_for_training_or_selection=False,steps=steps,batch=batch,learning_rate=learning_rate,
                loss='normalized MSE * 10000 on central output core; rounded count MSE for checkpoint selection',
                patch_plane_pixels=patch,core_output_plane_pixels=patch,source_files=tool_hashes(),
                baseline_validation_mse_counts=baseline,baseline_validation_psnr_db=psnr(baseline),history=[])
    checkpoint=root/'best.pt';log=root/'training.json'
    def save(step,mse):
        state={k:v.detach().cpu() for k,v in backbone.state_dict().items()}
        value=dict(backbone_state=state,variant='F_ane',width=16,depth=3,residual_scale=residual_scale,raw_norm=PEAK,
                   kind='superres',stock_codec='historical_vc5',stock_quality=3,step=step,
                   dataset_sha256=report['dataset_sha256'],fresh_initialization=True,quality_approval=False,
                   validation_mse_counts=mse)
        temporary=root/'best.pt.tmp';torch.save(value,temporary);temporary.replace(checkpoint)
    save(0,baseline)
    for step in range(1,steps+1):
        backbone.train();indices=rng.choice(train_indices,size=min(batch,len(train_indices)),replace=False)
        x,target=tensors(indices);optimizer.zero_grad(set_to_none=True)
        value=predict(backbone,x,residual_scale)
        loss=functional.mse_loss(value[:,:,core,core],target[:,:,core,core]/PEAK)*10000
        if not torch.isfinite(loss).item():raise ValueError('nonfinite training loss')
        loss.backward();optimizer.step()
        if step%validate_every==0 or step==steps:
            mse=validation()
            if mse<best:best=mse;best_step=step;save(step,mse)
            row=dict(step=step,loss=float(loss.item()),validation_mse_counts=mse,
                     validation_psnr_db=psnr(mse),delta_vs_bicubic_db=delta(baseline,mse),
                     best_step=best_step,elapsed_s=time.perf_counter()-started)
            report['history'].append(row)
            report.update(best_step=best_step,best_validation_mse_counts=best,best_checkpoint_sha256=stock_still.digest(checkpoint))
            log.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(row),flush=True)
    report.update(complete=True,elapsed_s=time.perf_counter()-started)
    log.write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    data=sub.add_parser('build');data.add_argument('--sources',type=Path,required=True);data.add_argument('--sdk',type=Path,required=True)
    data.add_argument('--patch',type=int,default=128);data.add_argument('--train-patches',type=int,default=64);data.add_argument('--validation-patches',type=int,default=32)
    fit=sub.add_parser('train');fit.add_argument('--dataset',type=Path,required=True);fit.add_argument('--device',choices=('cpu','mps','cuda'),default='cpu')
    fit.add_argument('--steps',type=int,default=1000);fit.add_argument('--batch',type=int,default=8)
    fit.add_argument('--learning-rate',type=float,default=.0003);fit.add_argument('--validate-every',type=int,default=50)
    for command in (data,fit):
        command.add_argument('--output-dir',type=Path,required=True);command.add_argument('--seed',type=int,default=20261028)
    args=parser.parse_args()
    if args.action=='build':build(args.sources,args.sdk,args.output_dir,args.patch,args.train_patches,args.validation_patches,args.seed)
    else:train(args.dataset,args.output_dir,args.device,args.steps,args.batch,args.learning_rate,args.validate_every,args.seed)


if __name__=='__main__':main()
