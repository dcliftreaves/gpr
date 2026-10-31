"""Frozen current models on supplied camera GPR count references; not sensor truth."""
from pathlib import Path
import sys,json,hashlib,datetime,platform
import numpy as np,torch,tifffile
REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime');sys.path.insert(0,str(REPO/'tools'))
import stock_still,stock_video,raw_media,stock_cnn_metadata,benchmark_stock_sr
from benchmark_stills import quality
ROOT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_cnn_supplied_gopro_20261030');ROOT.mkdir(exist_ok=False)
SDK=REPO/'build-runtime/source/app/gpr_tools/gpr_tools';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
cases=[dict(source='GP011728.GPR',scale=1,checkpoint='stock-q3-rggb14-cleanup'),dict(source='GPAB1094.GPR',scale=1,checkpoint='stock-q3-rggb14-cleanup'),dict(source='GP011689.GPR',scale=2,checkpoint='stock-q3-rggb14-sr-diagnostic')]
for c in cases:
 c['source_sha256']=sha(Path('/Users/dcliftreaves/Downloads')/c['source']);c['checkpoint_sha256']=sha(REPO/'models'/c['checkpoint']/'selected.pt')
p=dict(schema='gpr.stock_cnn_supplied_camera_protocol.v1',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),script_sha256=sha(Path(__file__)),sdk_sha256=sha(SDK),cases=cases,quality=3,device='mps',tile=256,halo=64,reference_kind='SDK decoded supplied camera GPR counts, already compressed; not lossless sensor truth',model_selection_or_retuning=False,quality_approval=False)
(ROOT/'protocol.json').write_text(json.dumps(p,indent=2)+'\n');report=dict(schema='gpr.stock_cnn_supplied_camera.v1',complete=False,quality_approval=False,protocol_sha256=sha(ROOT/'protocol.json'),torch=torch.__version__,host=platform.platform(),cases=[]);torch.set_num_threads(4)
for case in cases:
 source=Path('/Users/dcliftreaves/Downloads')/case['source'];cp=REPO/'models'/case['checkpoint']/'selected.pt';assert sha(source)==case['source_sha256'] and sha(cp)==case['checkpoint_sha256'];root=ROOT/source.stem;root.mkdir()
 reference_receipt=stock_still.decode(source,14,SDK,root/'source.dng')
 meta=raw_media.extract(source,14);w,h=meta['width'],meta['height'];assert meta['cfa']=='RGGB'
 with tifffile.TiffFile(root/'source.dng') as tf:reference=tf.asarray()
 assert reference.shape==(h,w) and reference.dtype==np.dtype('<u2')
 stock_still.run(SDK,['-i',source,'-o',root/'direct-sdk.raw'],None)
 assert sha(root/'direct-sdk.raw')==hashlib.sha256(reference.tobytes()).hexdigest()==reference_receipt['raw_sha256']
 assert stock_still.canonical(raw_media.extract(root/'source.dng',14))==stock_still.canonical(meta)
 scale=case['scale'];omitted=[]
 if scale==1:low=reference;lowmeta=meta
 else:
  lowmeta,omitted=benchmark_stock_sr.simulation_metadata(meta)
  planes=np.stack([reference[0::2,0::2],reference[0::2,1::2],reference[1::2,0::2],reference[1::2,1::2]]).astype(np.uint32)
  down=((planes[:,0::2,0::2]+planes[:,0::2,1::2]+planes[:,1::2,0::2]+planes[:,1::2,1::2]+2)//4).astype('<u2')
  low=np.empty((h//2,w//2),dtype='<u2');low[0::2,0::2]=down[0];low[0::2,1::2]=down[1];low[1::2,0::2]=down[2];low[1::2,1::2]=down[3]
 low.tofile(root/'input.raw');encoded=stock_still.encode(root/'input.raw',lowmeta,3,SDK,root/'stock-q3.gpr')
 decoded=stock_still.decode(root/'stock-q3.gpr',14,SDK,root/'decoded.dng')
 with tifffile.TiffFile(root/'decoded.dng') as tf:decoded_pixels=tf.asarray()
 assert hashlib.sha256(decoded_pixels.tobytes()).hexdigest()==decoded['raw_sha256'];decoded_pixels.tofile(root/'decoded.raw')
 if scale==1:baseline=decoded_pixels
 else:baseline,_=stock_video.restore(root/'decoded.raw',w//2,h//2,benchmark_stock_sr.Bicubic(),torch.device('mps'),256,64,2)
 restored=stock_still.decode(root/'stock-q3.gpr',14,SDK,root/'restored.dng',reconstruction=dict(root=None,checkpoint=cp,device='mps',tile=256,halo=64,scale=scale))
 assert restored['raw_sha256']==decoded['raw_sha256'] and restored['model']['checkpoint_sha256']==case['checkpoint_sha256']
 with tifffile.TiffFile(root/'restored.dng') as tf:output=tf.asarray()
 assert output.shape==(h,w) and hashlib.sha256(output.tobytes()).hexdigest()==restored['restored_raw_sha256']
 expected,_=stock_cnn_metadata.scaled(lowmeta,scale);assert stock_still.canonical(raw_media.extract(root/'restored.dng',14))==stock_still.canonical(expected)
 base=quality(reference,baseline,meta);metrics=quality(reference,output,meta);regions=['active','shadow_bottom_decile','highlight_top_decile','detail_top_decile'];failed=[key for key in regions if metrics[key]['rmse_counts']>base[key]['rmse_counts']]
 row=dict(source=case['source'],source_sha256=case['source_sha256'],source_width=w,source_height=h,output_scale=scale,reference_raw_sha256=reference_receipt['raw_sha256'],reference_kind=p['reference_kind'],source_dng_reader_matches_direct_sdk=True,checkpoint_sha256=case['checkpoint_sha256'],source_metadata_sha256=reference_receipt['metadata_sha256'],encoded_payload_sha256=encoded['payload_sha256'],decoded_low_raw_sha256=decoded['raw_sha256'],baseline_metrics=base,restored_metrics=metrics,active_gain_db=metrics['active']['psnr_db']-base['active']['psnr_db'],regional_regressions=failed,changed_samples=int(np.count_nonzero(output!=baseline)),restored_raw_sha256=restored['restored_raw_sha256'],editable_calibration_verified=True,simulation_metadata_omissions=omitted,inference_s=restored['cnn_s'],quality_approval=False)
 report['cases'].append(row);(ROOT/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(source=row['source'],scale=scale,gain_db=row['active_gain_db'],regressions=failed,inference_s=row['inference_s'])),flush=True)
report['complete']=True;(ROOT/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
