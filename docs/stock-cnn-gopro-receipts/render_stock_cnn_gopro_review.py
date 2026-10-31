"""Matched calibrated Rec.709 still review; fixed weights, no model selection."""
from pathlib import Path
import sys,json,hashlib,subprocess,time
import numpy as np,torch,tifffile
from PIL import Image,ImageDraw
REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime');sys.path.insert(0,str(REPO/'tools'))
import raw_media,stock_still,stock_video,benchmark_stock_sr
DATA=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_cnn_supplied_gopro_shared_20261030');ROOT=DATA/'render-review';ROOT.mkdir(exist_ok=False)
RENDER=REPO/'build-runtime/gpr_render';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();summary=json.loads((DATA/'summary.json').read_text());assert summary['complete'];torch.set_num_threads(4)
protocol=dict(schema='gpr.stock_cnn_camera_render_protocol.v1',count_summary_sha256=sha(DATA/'summary.json'),renderer_sha256=sha(RENDER),driver_sha256=sha(Path(__file__)),comparison='same supported metadata for reference, stock and CNN; CIRAWFilter exposure0/no adjustable enhancement, 16bit RGBA Rec709 TIFF',metrics='encoded Rec709 RGB and Y-prime MSE versus SDK camera-GPR count reference render; alpha excluded; not linear scene radiance or sensor truth',model_selection_or_retuning=False,quality_approval=False)
(ROOT/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n');report=dict(schema='gpr.stock_cnn_camera_render.v1',complete=False,quality_approval=False,protocol_sha256=sha(ROOT/'protocol.json'),cases=[])
def score(ref,value):
 e=value[...,:3].astype(np.float64)-ref[...,:3];mse=float(np.mean(e**2));y=e@np.array([.2126,.7152,.0722]);ymse=float(np.mean(y**2));return dict(rgb_mse=mse,y_prime_mse=ymse,rgb_psnr_db=None if not mse else float(10*np.log10(65535.**2/mse)),y_prime_psnr_db=None if not ymse else float(10*np.log10(65535.**2/ymse)),rgb_bias_counts=e.mean(axis=(0,1)).tolist())
for row in summary['cases']:
 case=DATA/Path(row['source']).stem;out=ROOT/Path(row['source']).stem;out.mkdir();meta=raw_media.extract(case/'restored.dng',14)
 with tifffile.TiffFile(case/'source.dng') as f:reference=f.asarray()
 if row['output_scale']==1:
  with tifffile.TiffFile(case/'decoded.dng') as f:base=f.asarray()
 else:base,_=stock_video.restore(case/'decoded.raw',reference.shape[1]//2,reference.shape[0]//2,benchmark_stock_sr.Bicubic(),torch.device('mps'),256,64,2)
 with tifffile.TiffFile(case/'restored.dng') as f:cnn=f.asarray()
 renders={};records={}
 for name,pixels in [('reference',reference),('stock',base),('cnn',cnn)]:
  dng=out/(name+'.dng');raw_media.write(dng,meta,pixels.astype('<u2').tobytes());assert stock_still.canonical(raw_media.extract(dng,14))==stock_still.canonical(meta)
  p=subprocess.run([str(RENDER),str(dng),str(out/(name+'.tiff'))],capture_output=True,text=True)
  (out/(name+'.stderr')).write_text(p.stderr);assert p.returncode==0,(name,p.stderr)
  record=json.loads(p.stdout);(out/(name+'.json')).write_text(json.dumps(record,indent=2)+'\n')
  with tifffile.TiffFile(out/(name+'.tiff')) as f:
   values=f.asarray();icc=f.pages[0].tags.get(34675);icc=icc.value if icc else None
  assert values.dtype==np.dtype('uint16') and values.ndim==3 and values.shape[-1]==4
  assert record['bits_per_component']==16 and record['color_space']=='ITU-R BT.709'
  records[name]=record;renders[name]=values
  preview=Image.fromarray(((values[...,:3].astype(np.uint32)+128)//257).astype(np.uint8));preview.thumbnail((640,640));preview.save(out/(name+'.png'),icc_profile=icc)
 del reference,base,cnn
 ref=renders['reference'];assert all(a.shape==ref.shape for a in renders.values())
 for name,record in records.items():
  for key in ['width','height','decoder','baseline_exposure','neutral_temperature','neutral_tint','source_orientation','lens_correction_enabled']:
   assert record[key]==records['reference'][key],(name,key)
 stock=score(ref,renders['stock']);restored=score(ref,renders['cnn']);gain=restored['rgb_psnr_db']-stock['rgb_psnr_db'];ygain=restored['y_prime_psnr_db']-stock['y_prime_psnr_db']
 # Reference-only detail crop: maximum same-site RGB variation among a fixed
 # central grid, independent of whether the CNN improved that crop.
 H,W=ref.shape[:2];side=min(256,H,W);best=None
 yref=ref[...,:3].astype(np.float32)@np.array([.2126,.7152,.0722],np.float32)
 for y in range(H//8,max(H//8+1,7*H//8-side+1),max(1,side)):
  for x in range(W//8,max(W//8+1,7*W//8-side+1),max(1,side)):
   a=yref[y:y+side,x:x+side];energy=float(np.mean(abs(a[2:,:-2]-a[:-2,:-2]))+np.mean(abs(a[:-2,2:]-a[:-2,:-2])))
   if best is None or energy>best[0]:best=(energy,y,x)
 _,cy,cx=best;thumbs=[];crops=[]
 for name in ['reference','stock','cnn']:
  a=renders[name];im=Image.fromarray(((a[...,:3].astype(np.uint32)+128)//257).astype(np.uint8));im.thumbnail((512,512));thumbs.append(im)
  crop=Image.fromarray(((a[cy:cy+side,cx:cx+side,:3].astype(np.uint32)+128)//257).astype(np.uint8)).resize((512,512));crops.append(crop)
 top_h=max(im.height for im in thumbs);canvas=Image.new('RGB',(1536,top_h+560),'white');draw=ImageDraw.Draw(canvas)
 for i,name in enumerate(['Reference GPR counts','Stock Q3 / bicubic','Current CNN']):
  draw.text((i*512+8,8),name,fill='black');canvas.paste(thumbs[i],(i*512,28));canvas.paste(crops[i],(i*512,top_h+44))
 canvas.save(out/'comparison.png',icc_profile=icc)
 result=dict(source=row['source'],output_scale=row['output_scale'],rendered_width=ref.shape[1],rendered_height=ref.shape[0],stock=stock,cnn=restored,rgb_gain_db=gain,y_prime_gain_db=ygain,numeric_render_nonregression=restored['rgb_mse']<=stock['rgb_mse'] and restored['y_prime_mse']<=stock['y_prime_mse'],detail_crop=dict(x=cx,y=cy,width=side,height=side),render_receipts=records,tiff_sha256={name:sha(out/(name+'.tiff')) for name in records},comparison_png_sha256=sha(out/'comparison.png'),quality_approval=False)
 report['cases'].append(result);(ROOT/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(source=row['source'],rgb_gain_db=gain,y_prime_gain_db=ygain)),flush=True)
report['complete']=True;(ROOT/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
