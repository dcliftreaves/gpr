"""Matched fresh renders and reference-chosen crops for frozen camera evaluation."""
from pathlib import Path
import hashlib,json,shutil,subprocess,sys
import numpy as np
import tifffile
from PIL import Image,ImageDraw
REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime');sys.path.insert(0,str(REPO/'tools'))
import raw_media,stock_still
ROOT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_historical_boundary_20261031')
CACHE=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_cnn_supplied_gopro_shared_20261030/render-review/GP011689')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,o):p.write_text(json.dumps(o,indent=2)+'\n')
def score(reference,value):
    sums=np.zeros(3,np.float64);squared=0.;ysquared=0.;count=0
    with np.errstate(all='raise'):
        for y in range(0,len(reference),64):
            e=value[y:y+64,:,:3].astype(np.float64)-reference[y:y+64,:,:3]
            squared+=float(np.square(e).sum());sums+=e.sum(axis=(0,1));luma=.2126*e[:,:,0]+.7152*e[:,:,1]+.0722*e[:,:,2];ysquared+=float(np.square(luma).sum());count+=e.shape[0]*e.shape[1]
    mse=squared/(count*3);ymse=ysquared/count
    return dict(rgb_mse=mse,y_prime_mse=ymse,rgb_psnr_db=float(10*np.log10(65535.**2/mse)),y_prime_psnr_db=float(10*np.log10(65535.**2/ymse)),rgb_bias_counts=(sums/count).tolist())
def main():
    root=ROOT/'render-review';root.mkdir(exist_ok=False);renderer=REPO/'build-runtime/gpr_render'
    inputs={name:CACHE/(name+'.dng') for name in ['reference','stock','cnn']};inputs['historical']=ROOT/'gopro/restored.dng'
    crops=[dict(name='paper text',x=1408,y=3072,side=384),dict(name='furniture edges',x=4608,y=2816,side=384),dict(name='rug texture',x=2560,y=4864,side=384)]
    protocol=dict(schema='gpr.stock_sr_historical_boundary_render_protocol.v1',driver_sha256=sha(Path(__file__)),freeze_sha256=sha(ROOT/'frozen.json'),gopro_summary_sha256=sha(ROOT/'gopro/summary.json'),renderer_sha256=sha(renderer),inputs={k:dict(path=str(v),sha256=sha(v)) for k,v in inputs.items()},crops=crops,crop_selection='Fixed from old reference-only overview before viewing new CNN render; no reference-adaptive inference or model selection.',comparison='All four renders fresh with identical supported calibration; exposure0/no adjustable enhancement, 16bit RGBA Rec709. Chunked RGB/Y-prime error versus rendered already-compressed camera reference; alpha excluded, not scene-linear or sensor truth.',quality_approval=False)
    save(root/'protocol.json',protocol);shutil.copy2(Path(__file__),root/Path(__file__).name)
    meta=raw_media.extract(inputs['reference'],14);records={};arrays={};icc=None
    for name,path in inputs.items():
        assert stock_still.canonical(raw_media.extract(path,14))==stock_still.canonical(meta)
        result=subprocess.run([str(renderer),str(path),str(root/(name+'.tiff'))],capture_output=True,text=True);(root/(name+'.stderr')).write_text(result.stderr);assert result.returncode==0
        record=json.loads(result.stdout);save(root/(name+'.json'),record);records[name]=record
        with tifffile.TiffFile(root/(name+'.tiff')) as f:
            values=f.asarray();profile=f.pages[0].tags.get(34675);icc=profile.value if profile else None
        assert values.dtype==np.uint16 and values.ndim==3 and values.shape[-1]==4
        assert record['bits_per_component']==16 and record['color_space']=='ITU-R BT.709';arrays[name]=values
        print(json.dumps(dict(rendered=name,width=values.shape[1],height=values.shape[0])),flush=True)
    for record in records.values():
        for k in ['width','height','decoder','baseline_exposure','neutral_temperature','neutral_tint','source_orientation','lens_correction_enabled']:assert record[k]==records['reference'][k]
    scores={name:score(arrays['reference'],arrays[name]) for name in ['stock','cnn','historical']}
    names=['reference','stock','cnn','historical'];labels=['Reference GPR counts','Bicubic','Supplied BIBO CNN','Frozen historical CNN']
    canvas=Image.new('RGB',(2048,384+28+len(crops)*412),'white');draw=ImageDraw.Draw(canvas)
    for index,name in enumerate(names):
        values=arrays[name];image=Image.fromarray(((values[:,:,:3].astype(np.uint32)+128)//257).astype(np.uint8));overview=image.copy();overview.thumbnail((512,384))
        draw.text((index*512+8,8),labels[index],fill='black');canvas.paste(overview,(index*512,28));overview.save(root/(name+'-overview.png'),icc_profile=icc)
        for j,crop in enumerate(crops):
            x,y,side=crop['x'],crop['y'],crop['side'];piece=image.crop((x,y,x+side,y+side));top=412+j*412
            draw.text((index*512+8,top+8),crop['name']+' (1:1)',fill='black');canvas.paste(piece,(index*512+64,top+28))
    canvas.save(root/'comparison.png',icc_profile=icc)
    result=dict(schema='gpr.stock_sr_historical_boundary_render.v1',complete=True,protocol_sha256=sha(root/'protocol.json'),scores=scores,new_rgb_gain_db=scores['historical']['rgb_psnr_db']-scores['stock']['rgb_psnr_db'],new_y_prime_gain_db=scores['historical']['y_prime_psnr_db']-scores['stock']['y_prime_psnr_db'],supplied_rgb_gain_db=scores['cnn']['rgb_psnr_db']-scores['stock']['rgb_psnr_db'],render_receipts=records,tiff_sha256={name:sha(root/(name+'.tiff')) for name in names},comparison_png_sha256=sha(root/'comparison.png'),quality_approval=False)
    save(root/'summary.json',result);print(json.dumps(dict(complete=True,rgb_gain_db=result['new_rgb_gain_db'],y_prime_gain_db=result['new_y_prime_gain_db'],old_rgb_gain_db=result['supplied_rgb_gain_db'])),flush=True)
if __name__=='__main__':main()
