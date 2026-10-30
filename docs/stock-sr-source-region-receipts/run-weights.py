"""Training-source-only full-image region weights; no validation/final decoding."""
from pathlib import Path
import gc,hashlib,json,sys,time
import numpy as np
import tifffile
import torch
REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime');sys.path.insert(0,str(REPO/'tools'))
from benchmark_stills import bayer_page,quality
from benchmark_stock_sr import Bicubic
import raw_media,stock_video
root=Path(__file__).resolve().parent;sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=json.loads((root/'protocol.json').read_text());assert sha(Path(__file__))==p['weight_builder_sha256']
dataset=Path(p['dataset']);info=json.loads((dataset/'dataset.json').read_text());assert sha(dataset/'dataset.json')==p['dataset_sha256']
assert sha(dataset/'inputs.npy')==p['dataset_input_sha256'] and sha(dataset/'targets.npy')==p['dataset_target_sha256']
targets=np.load(dataset/'targets.npy',mmap_mode='r',allow_pickle=False);patch=info['patch_plane_pixels'];core=patch//2
weights=np.lib.format.open_memmap(root/'weights.npy',mode='w+',dtype='<f4',shape=(targets.shape[0],4,patch,patch));weights[:]=0
report=dict(schema='gpr.stock_sr_source_region_weights.v1',complete=False,quality_approval=False,protocol_sha256=sha(root/'protocol.json'),training_sources_only=True,validation_and_final_decoded=False,rows=[],elapsed_s=None)
started=time.perf_counter();torch.set_num_threads(4)
for source_index,source in enumerate(info['sources']):
 if source['split']!='train':continue
 path=Path(source['path']);assert sha(path)==source['sha256'];meta=raw_media.extract(path,14)
 with tifffile.TiffFile(path) as f:
  page=bayer_page(f.pages);assert int(page.compression) in (1,7,8,32946);reference=page.asarray()
 assert reference.shape==(source['height'],source['width']) and reference.dtype==np.dtype('<u2') and reference.max()<=16383
 refhash=hashlib.sha256(reference.tobytes()).hexdigest();assert refhash==source['reference_raw_sha256']
 with tifffile.TiffFile(dataset/f'source-{source_index:03d}/decoded.dng') as f:low=f.asarray()
 assert hashlib.sha256(low.astype('<u2').tobytes()).hexdigest()==source['low_decoded_raw_sha256']
 raw=root/'temporary-low.raw';low.tofile(raw)
 base,elapsed=stock_video.restore(raw,source['width']//2,source['height']//2,Bicubic(),torch.device('mps'),256,64,scale=2);raw.unlink()
 expected=reference.astype(np.int32);tags={tag['code']:tag for tag in meta['image']}
 t,l,b,r=map(int,raw_media.values(tags[50829])) if 50829 in tags else (0,0,*reference.shape)
 active=expected[t:b,l:r];lo,hi=np.percentile(active,[10,90])
 gradient=np.abs(active[2:,:-2]-active[:-2,:-2])+np.abs(active[:-2,2:]-active[:-2,:-2]);threshold=float(np.percentile(gradient,90))
 masks=[np.zeros(reference.shape,dtype=bool) for _ in range(4)]
 masks[0][t:b,l:r]=True;masks[1][t:b,l:r]=active<=lo;masks[2][t:b,l:r]=active>=hi;masks[3][t:b-2,l:r-2]=gradient>=threshold
 squared=np.square(base.astype(np.float64)-reference);totals=[]
 for mask in masks:
  count=int(mask.sum());assert count
  mse=float(squared[mask].mean());totals.append(dict(samples=count,mse_counts=mse,weight=reference.size/(4*count*max(mse,1.))))
 # Independent existing evaluator must agree on all full-image regional errors.
 metrics=quality(reference,base,meta)
 for entry,name in zip(totals,['active','shadow_bottom_decile','highlight_top_decile','detail_top_decile']):
  assert np.isclose(entry['mse_counts'],metrics[name]['rmse_counts']**2,rtol=1e-12,atol=1e-8)
 overlap=dict(shadow=dict(local=0,source_wide=0,intersection=0),highlight=dict(local=0,source_wide=0,intersection=0))
 for offset,(y,x) in enumerate(source['low_plane_yx']):
  index=source['patch_start']+offset;assert offset<source['patch_count']
  yp=2*(2*y+core);xp=2*(2*x+core)
  ref=np.stack([reference[yp+site//2:yp+site//2+2*patch:2,xp+site%2:xp+site%2+2*patch:2] for site in range(4)])
  assert np.array_equal(ref,targets[index,:,core:core+patch,core:core+patch])
  slices=[np.stack([mask[yp+site//2:yp+site//2+2*patch:2,xp+site%2:xp+site%2+2*patch:2] for site in range(4)]) for mask in masks]
  for mask,entry in zip(slices,totals):weights[index]+=mask.astype(np.float32)*entry['weight']
  local_lo,local_hi=np.percentile(ref,[10,90])
  for name,local,global_mask in [('shadow',ref<=local_lo,slices[1]),('highlight',ref>=local_hi,slices[2])]:
   row=overlap[name];row['local']+=int(local.sum());row['source_wide']+=int(global_mask.sum());row['intersection']+=int(np.count_nonzero(local&global_mask))
 row=dict(source=source['path'],source_sha256=source['sha256'],reference_raw_sha256=refhash,group=source['group'],split='train',patches=source['patch_count'],active_area=[t,l,b,r],shadow_threshold_counts=float(lo),highlight_threshold_counts=float(hi),detail_threshold_counts=threshold,regions=totals,independent_metric_agreement=True,patch_target_coordinates_exact=True,mask_overlap=overlap,bicubic_s=elapsed)
 report['rows'].append(row);(root/'weight-audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(row),flush=True)
 del reference,low,base,expected,active,gradient,masks,squared,ref,slices,local,global_mask,mask;gc.collect()
weights.flush();del weights
train_indices=set(i for s in info['sources'] if s['split']=='train' for i in range(s['patch_start'],s['patch_start']+s['patch_count']))
loaded=np.load(root/'weights.npy',mmap_mode='r');assert loaded.shape==(640,4,128,128)
assert np.isfinite(loaded).all() and loaded.min()>=0 and np.count_nonzero(loaded[list(set(range(len(loaded)))-train_indices)])==0
report.update(complete=True,weights_sha256=sha(root/'weights.npy'),weights_shape=list(loaded.shape),weights_dtype=str(loaded.dtype),training_patches=len(train_indices),nontraining_weights_zero=True,elapsed_s=time.perf_counter()-started)
(root/'weight-audit.json').write_text(json.dumps(report,indent=2)+'\n');print('weight construction complete',report['elapsed_s'],report['weights_sha256'],flush=True)
