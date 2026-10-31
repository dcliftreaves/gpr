"""Audit train/validation count domains and calibration; final pixels excluded."""
from pathlib import Path
import sys,json,hashlib,datetime
import numpy as np
REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime');sys.path.insert(0,str(REPO/'tools'))
import raw_media
ROOT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_calibration_20261030');ROOT.mkdir(exist_ok=False)
DATA=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_20261028/dataset');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();info=json.loads((DATA/'dataset.json').read_text())
protocol=dict(schema='gpr.stock_sr_calibration_protocol.v1',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),dataset_sha256=sha(DATA/'dataset.json'),script_sha256=sha(Path(__file__)),splits=['train','validation'],final_source_pixels_or_calibration_read=False,count_domain='packed same-CFA planes, nominal 14bit; current model divides counts by16383, no metadata black subtraction',quantiles=[0,1,10,50,90,99,100],quality_approval=False)
(ROOT/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
assert sha(DATA/'inputs.npy')==info['input_sha256'] and sha(DATA/'targets.npy')==info['target_sha256']
x=np.load(DATA/'inputs.npy',mmap_mode='r');y=np.load(DATA/'targets.npy',mmap_mode='r');rows=[]
for source in info['sources']:
 if source['split']=='test':assert source['patch_start'] is None and source['patch_count']==0;continue
 p=Path(source['path']);assert sha(p)==source['sha256'];meta=raw_media.extract(p,14);tags={t['code']:t for t in meta['image']};exif={t['code']:t for t in meta['exif']}
 start=source['patch_start'];end=start+source['patch_count'];inputs=np.asarray(x[start:end]);target=np.asarray(y[start:end],dtype=np.uint32)
 clean=((target[:,:,0::2,0::2]+target[:,:,0::2,1::2]+target[:,:,1::2,0::2]+target[:,:,1::2,1::2]+2)//4).astype('<u2')
 inputs=inputs[:,:,32:96,32:96];clean=clean[:,:,32:96,32:96];err=inputs.astype(np.float64)-clean;low,high=np.percentile(clean,[10,90])
 row=dict(source=p.name,source_sha256=source['sha256'],split=source['split'],group=source['group'],patches=source['patch_count'],black_level=raw_media.values(tags[50714]) if 50714 in tags else None,black_repeat=raw_media.values(tags[50713]) if 50713 in tags else None,white_level=raw_media.values(tags[50717]) if 50717 in tags else None,exposure_seconds=raw_media.values(exif[33434]) if 33434 in exif else None,iso=raw_media.values(exif[34855]) if 34855 in exif else None,input_quantiles=np.percentile(inputs,protocol['quantiles']).tolist(),clean_low_quantiles=np.percentile(clean,protocol['quantiles']).tolist(),low_codec_error={})
 for name,mask in [('all',np.ones(clean.shape,bool)),('shadow',clean<=low),('highlight',clean>=high)]:
  e=err[mask];row['low_codec_error'][name]=dict(samples=e.size,mean_error_counts=float(e.mean()),mse_counts=float(np.mean(e**2)),mean_abs_error_counts=float(np.mean(abs(e))))
 rows.append(row);print(json.dumps(row),flush=True)
(ROOT/'audit.json').write_text(json.dumps(dict(schema='gpr.stock_sr_calibration_audit.v1',complete=True,protocol_sha256=sha(ROOT/'protocol.json'),sources=rows,final_sources_not_read=True),indent=2)+'\n')
