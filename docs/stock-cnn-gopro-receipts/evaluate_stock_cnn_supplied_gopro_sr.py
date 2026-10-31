"""Count-domain 2x simulation on supplied GPR with reversible full-frame GainMaps.
The down-map represents sampling centroids, not exact commutation of variable
radiometric gains with area averaging. Source references already contain GPR loss.
"""
from pathlib import Path
import sys,json,hashlib,struct,copy,datetime
import numpy as np,torch,tifffile
REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime');sys.path.insert(0,str(REPO/'tools'))
import raw_media,stock_still,stock_video,stock_cnn_metadata,benchmark_stock_sr
from benchmark_stills import quality
ROOT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_cnn_supplied_gopro_20261030');OUT=ROOT/'GP011689-inverse-gainmap';OUT.mkdir(exist_ok=False)
SOURCE=Path('/Users/dcliftreaves/Downloads/GP011689.GPR');SDK=REPO/'build-runtime/source/app/gpr_tools/gpr_tools';CP=REPO/'models/stock-q3-rggb14-sr-diagnostic/selected.pt';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
protocol=dict(schema='gpr.stock_cnn_camera_sr_gainmap_protocol.v1',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),parent_protocol_sha256=sha(ROOT/'protocol.json'),source_sha256=sha(SOURCE),checkpoint_sha256=sha(CP),driver_sha256=sha(Path(__file__)),sdk_sha256=sha(SDK),device='mps',tile=256,halo=64,source_reference='SDK decoded already compressed GPR counts; not lossless sensor truth',gainmap_scope='four full-active-frame pitch2 single-plane GainMaps only; inverse centered same-CFA geometry; require exact high-metadata roundtrip before inference',model_selection_or_retuning=False,quality_approval=False)
(OUT/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
meta=raw_media.extract(SOURCE,14);w,h=meta['width'],meta['height'];assert (w,h)==(8192,6144) and meta['cfa']=='RGGB'
tags={t['code']:t for t in meta['image']};assert 50829 not in tags or raw_media.values(tags[50829])==(0,0,h,w)
original=raw_media.unpack_record(tags[51009]);count,=struct.unpack_from('>I',original);assert count==4;pos=4;bodies=[];proof=[];phases=set()
def map_gain(body,y,x,H,W):
 rows,cols,dy,dx,oy,ox,planes=struct.unpack_from('>2I4dI',body,32);a=np.frombuffer(body,dtype='>f4',offset=76).reshape(rows,cols)
 gy=np.clip(((y+.5)/H-oy)/dy,0,rows-1);gx=np.clip(((x+.5)/W-ox)/dx,0,cols-1);iy=int(np.floor(gy));ix=int(np.floor(gx));fy=gy-iy;fx=gx-ix
 return float((1-fy)*((1-fx)*a[iy,ix]+fx*a[iy,min(ix+1,cols-1)])+fy*((1-fx)*a[min(iy+1,rows-1),ix]+fx*a[min(iy+1,rows-1),min(ix+1,cols-1)]))
for _ in range(count):
 op,version,flags,size=struct.unpack_from('>4I',original,pos);pos+=16;body=original[pos:pos+size];pos+=size
 assert op==9 and version<=0x01040000 and flags&~3==0
 t,l,b,r,plane,planes,rp,cp=struct.unpack_from('>8I',body);assert t in (0,1) and l in (0,1) and (b,r,plane,planes,rp,cp)==(h,w,0,1,2,2)
 phases.add((t,l));rows,cols,dy,dx,oy,ox,nplanes=struct.unpack_from('>2I4dI',body,32);assert nplanes==1 and len(body)==76+rows*cols*4
 low=struct.pack('>8I',t,l,h//2,w//2,0,1,2,2)+struct.pack('>2I4dI',rows,cols,dy,dx,oy+(t-.5)/h,ox+(l-.5)/w,1)+body[76:]
 errors=[]
 for j in [0,1,h//8,h//4-1]:
  for i in [0,1,w//8,w//4-1]:
   errors.append(abs(map_gain(low,2*j+t,2*i+l,h//2,w//2)-map_gain(body,4*j+t+1,4*i+l+1,h,w)))
 assert max(errors)<=1e-12
 proof.append(dict(phase=[t,l],centroid_checks=len(errors),max_gain_error=max(errors)))
 bodies.append(struct.pack('>4I',op,version,flags,len(low))+low)
assert pos==len(original) and len(phases)==4
# Existing simulation rejects every nonempty stage2 list. Supply the explicitly
# transformed list after its remaining geometry checks; nothing is discarded.
carrier=copy.deepcopy(meta);carrier['image']=[raw_media.record(51009,7,4,bytes(4)) if t['code']==51009 else t for t in carrier['image']]
lowmeta,omitted=benchmark_stock_sr.simulation_metadata(carrier);lowlist=struct.pack('>I',4)+b''.join(bodies)
lowmeta['image']=[raw_media.record(51009,7,len(lowlist),lowlist) if t['code']==51009 else t for t in lowmeta['image']]
expected,geometry=stock_cnn_metadata.scaled(lowmeta,2)
source_supported=copy.deepcopy(meta);source_supported['image']=[t for t in source_supported['image'] if t['code']!=700]
assert stock_still.canonical(expected)==stock_still.canonical(source_supported),'all supported high calibration must roundtrip byte exactly'
(OUT/'gainmap-proof.json').write_text(json.dumps(dict(complete=True,proof=proof,high_metadata_roundtrip_exact=True,source_opcode_sha256=hashlib.sha256(original).hexdigest(),low_opcode_sha256=hashlib.sha256(lowlist).hexdigest(),omissions=omitted),indent=2)+'\n')
with tifffile.TiffFile(ROOT/'GP011689/source.dng') as tf:reference=tf.asarray()
source_receipt=json.loads((ROOT/'GP011689/source.dng.json').read_text());assert sha(ROOT/'GP011689/direct-sdk.raw')==hashlib.sha256(reference.tobytes()).hexdigest()==source_receipt['raw_sha256']
planes=np.stack([reference[0::2,0::2],reference[0::2,1::2],reference[1::2,0::2],reference[1::2,1::2]]).astype(np.uint32)
down=((planes[:,0::2,0::2]+planes[:,0::2,1::2]+planes[:,1::2,0::2]+planes[:,1::2,1::2]+2)//4).astype('<u2');low=np.empty((h//2,w//2),dtype='<u2')
low[0::2,0::2]=down[0];low[0::2,1::2]=down[1];low[1::2,0::2]=down[2];low[1::2,1::2]=down[3];low.tofile(OUT/'input.raw')
encoded=stock_still.encode(OUT/'input.raw',lowmeta,3,SDK,OUT/'stock-q3.gpr');decoded=stock_still.decode(OUT/'stock-q3.gpr',14,SDK,OUT/'decoded.dng')
with tifffile.TiffFile(OUT/'decoded.dng') as tf:decoded_pixels=tf.asarray()
assert hashlib.sha256(decoded_pixels.tobytes()).hexdigest()==decoded['raw_sha256'];decoded_pixels.tofile(OUT/'decoded.raw');torch.set_num_threads(4)
baseline,_=stock_video.restore(OUT/'decoded.raw',w//2,h//2,benchmark_stock_sr.Bicubic(),torch.device('mps'),256,64,2)
restored=stock_still.decode(OUT/'stock-q3.gpr',14,SDK,OUT/'restored.dng',reconstruction=dict(root=None,checkpoint=CP,device='mps',tile=256,halo=64,scale=2))
assert restored['raw_sha256']==decoded['raw_sha256'] and restored['model']['checkpoint_sha256']==sha(CP)
with tifffile.TiffFile(OUT/'restored.dng') as tf:output=tf.asarray()
assert output.shape==(h,w) and hashlib.sha256(output.tobytes()).hexdigest()==restored['restored_raw_sha256']
assert stock_still.canonical(raw_media.extract(OUT/'restored.dng',14))==stock_still.canonical(expected)
bm=quality(reference,baseline,meta);metrics=quality(reference,output,meta);regions=['active','shadow_bottom_decile','highlight_top_decile','detail_top_decile'];failed=[k for k in regions if metrics[k]['rmse_counts']>bm[k]['rmse_counts']]
row=dict(source=SOURCE.name,source_sha256=sha(SOURCE),source_width=w,source_height=h,output_scale=2,reference_raw_sha256=source_receipt['raw_sha256'],reference_kind=protocol['source_reference'],source_dng_reader_matches_direct_sdk=True,checkpoint_sha256=sha(CP),encoded_payload_sha256=encoded['payload_sha256'],decoded_low_raw_sha256=decoded['raw_sha256'],baseline_metrics=bm,restored_metrics=metrics,active_gain_db=metrics['active']['psnr_db']-bm['active']['psnr_db'],regional_regressions=failed,changed_samples=int(np.count_nonzero(output!=baseline)),restored_raw_sha256=restored['restored_raw_sha256'],editable_calibration_verified=True,gainmap_roundtrip_exact=True,simulation_metadata_omissions=omitted,inference_s=restored['cnn_s'],quality_approval=False)
(OUT/'summary.json').write_text(json.dumps(dict(complete=True,protocol_sha256=sha(OUT/'protocol.json'),case=row,quality_approval=False),indent=2)+'\n')
parent=json.loads((ROOT/'summary.json').read_text());assert not parent['complete'] and len(parent['cases'])==2;parent['cases'].append(row);parent.update(complete=True,sr_followup_protocol_sha256=sha(OUT/'protocol.json'),initial_simulator_failure_preserved=True)
(ROOT/'summary-completed.json').write_text(json.dumps(parent,indent=2)+'\n');print(json.dumps(dict(source=SOURCE.name,scale=2,gain_db=row['active_gain_db'],regressions=failed,gainmap_roundtrip_exact=True)),flush=True)
