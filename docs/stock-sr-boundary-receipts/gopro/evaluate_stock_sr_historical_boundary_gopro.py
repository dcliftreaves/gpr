"""Fixed-candidate camera-file transfer; no tuning on this reused reference."""
from pathlib import Path
import hashlib,json,shutil,sys
import numpy as np
import torch,tifffile
ROOT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_historical_boundary_20261031')
CACHE=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_cnn_supplied_gopro_shared_20261030')
REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime')
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(REPO/'tools'))
import stock_sr_historical_boundary as boundary
import mission1_sr_models,mission1_sr_runtime,stock_video,benchmark_stock_sr,raw_media,stock_still,stock_cnn_metadata
from benchmark_stills import quality
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,o):p.write_text(json.dumps(o,indent=2)+'\n')
def main():
    frozen=json.loads((ROOT/'frozen.json').read_text());c=frozen['candidate'];cp=Path(frozen['checkpoint_path'])
    assert sha(cp)==frozen['checkpoint_sha256'] and sha(ROOT/'stock_sr_historical_boundary.py')==frozen['boundary_source_sha256']
    parent=json.loads((CACHE/'summary.json').read_text());old=next(r for r in parent['cases'] if r['source']=='GP011689.GPR')
    out=ROOT/'gopro';out.mkdir(exist_ok=False);source=Path('/Users/dcliftreaves/Downloads/GP011689.GPR');assert sha(source)==old['source_sha256']
    save(out/'protocol.json',dict(schema='gpr.stock_sr_historical_boundary_gopro_protocol.v1',driver_sha256=sha(Path(__file__)),freeze_sha256=sha(ROOT/'frozen.json'),parent_summary_sha256=sha(CACHE/'summary.json'),source_sha256=sha(source),checkpoint_sha256=sha(cp),selection_or_retuning=False,quality_approval=False,reference_kind=old['reference_kind'],limitations=['Reused household scene/camera reference, not blind or lossless sensor truth.','Area simulation plus actual stockQ3, not synchronized native12/50MP capture.','Nikon-only current fine-tuning; camera transfer remains to establish.']))
    shutil.copy2(Path(__file__),out/Path(__file__).name)
    meta=raw_media.extract(source,14);w,h=meta['width'],meta['height'];cache=CACHE/'GP011689';raw=cache/'decoded.raw'
    assert sha(raw)==old['decoded_low_raw_sha256'] and sha(cache/'direct-sdk.raw')==old['reference_raw_sha256']
    with tifffile.TiffFile(cache/'source.dng') as f:reference=f.asarray()
    assert hashlib.sha256(reference.tobytes()).hexdigest()==old['reference_raw_sha256']
    torch.set_num_threads(4);device=torch.device('mps')
    base,_=stock_video.restore(raw,w//2,h//2,benchmark_stock_sr.Bicubic(),device,256,64,2)
    bm=quality(reference,base,meta);assert json.loads(json.dumps(bm))==old['baseline_metrics']
    checkpoint=torch.load(cp,map_location='cpu',weights_only=True);model=mission1_sr_models.make_model_from_config(checkpoint['config']);model.load_state_dict(checkpoint['model'],strict=True);model.to(device).eval()
    low=np.fromfile(raw,dtype='<u2').reshape(h//2,w//2);pred,stats=boundary.tiled(model,mission1_sr_runtime.deinterleave(low),device,reflect=c['edge']=='reflect32')
    output=boundary.correction(base,boundary.interleave(pred),c['alpha'],c['ramps']);output.tofile(out/'restored.raw');metrics=quality(reference,output,meta)
    bad=[r for r in ['active','shadow_bottom_decile','highlight_top_decile','detail_top_decile'] if metrics[r]['rmse_counts']>bm[r]['rmse_counts']]
    lowmeta,omissions=benchmark_stock_sr.simulation_metadata(meta);expected,_=stock_cnn_metadata.scaled(lowmeta,2)
    original={**meta,'image':[r for r in meta['image'] if r['code']!=700]};assert stock_still.canonical(expected)==stock_still.canonical(original)
    raw_media.write(out/'restored.dng',expected,output.tobytes())
    with tifffile.TiffFile(out/'restored.dng') as f:independent=f.asarray()
    assert np.array_equal(independent,output) and stock_still.canonical(raw_media.extract(out/'restored.dng',14))==stock_still.canonical(expected)
    result=dict(schema='gpr.stock_sr_historical_boundary_gopro.v1',complete=True,protocol_sha256=sha(out/'protocol.json'),source_sha256=sha(source),checkpoint_sha256=sha(cp),baseline_metrics=bm,metrics=metrics,regressions=bad,active_gain_db=metrics['active']['psnr_db']-bm['active']['psnr_db'],baseline_raw_sha256=hashlib.sha256(base.tobytes()).hexdigest(),output_raw_sha256=sha(out/'restored.raw'),editable_dng_sha256=sha(out/'restored.dng'),independent_editable_pixels_exact=True,supported_high_calibration_exact=True,simulation_metadata_omissions=omissions,runtime=stats,quality_approval=False)
    save(out/'summary.json',result);print(json.dumps(dict(complete=True,gain_db=result['active_gain_db'],regressions=bad,editable_pixels_and_calibration_exact=True)),flush=True)
if __name__=='__main__':main()
