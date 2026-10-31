"""Independent rendered-error audit and fixed gate-coverage accounting."""
from pathlib import Path
import hashlib,json,sys
import numpy as np
import tifffile
REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime');sys.path.insert(0,str(REPO/'tools'))
import raw_media
ROOT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_historical_boundary_20261031')
CACHE=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_cnn_supplied_gopro_shared_20261030/render-review/GP011689')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    root=ROOT/'render-review';prior=json.loads((root/'summary.json').read_text());assert prior['complete']
    protocol=dict(schema='gpr.stock_sr_historical_boundary_render_audit_protocol.v1',script_sha256=sha(Path(__file__)),summary_sha256=sha(root/'summary.json'),method='RGB channel sums separately; Y-prime square expanded into three diagonal and three cross terms, row chunks32, floating exceptions raised. Fixed frozen gate-zero count threshold; no new selection or tuning.',quality_approval=False)
    p=root/'audit-protocol.json';assert not p.exists();p.write_text(json.dumps(protocol,indent=2)+'\n')
    with tifffile.TiffFile(root/'reference.tiff') as f:reference=f.asarray()
    scores={};weights=[.2126,.7152,.0722]
    with np.errstate(all='raise'):
        for name in ['stock','cnn','historical']:
            path=root/(name+'.tiff');assert sha(path)==prior['tiff_sha256'][name]
            with tifffile.TiffFile(path) as f:value=f.asarray()
            rgb_total=0.;y_total=0.;samples=reference.shape[0]*reference.shape[1]
            for start in range(0,len(reference),32):
                e=[value[start:start+32,:,c].astype(np.float64)-reference[start:start+32,:,c] for c in range(3)]
                diagonal=[float(np.sum(c*c)) for c in e];rgb_total+=sum(diagonal);y_total+=sum(w*w*d for w,d in zip(weights,diagonal))
                for a,b in [(0,1),(0,2),(1,2)]:y_total+=2*weights[a]*weights[b]*float(np.sum(e[a]*e[b]))
            rgb=rgb_total/(samples*3);y=y_total/samples
            assert np.isclose(rgb,prior['scores'][name]['rgb_mse'],rtol=1e-10,atol=1e-8) and np.isclose(y,prior['scores'][name]['y_prime_mse'],rtol=1e-10,atol=1e-8)
            scores[name]=dict(rgb_mse=rgb,y_prime_mse=y,independent_agreement=True)
            del value
    with tifffile.TiffFile(CACHE/'stock.dng') as f:base=f.asarray()
    restored=np.fromfile(ROOT/'gopro/restored.raw',dtype='<u2').reshape(base.shape)
    frozen=json.loads((ROOT/'frozen.json').read_text());a,b,c,d=frozen['candidate']['ramps']
    zero=(base.astype(np.float64)/16383<=a)|(base.astype(np.float64)/16383>=d)
    assert np.array_equal(base[zero],restored[zero])
    meta=raw_media.extract(Path('/Users/dcliftreaves/Downloads/GP011689.GPR'),14);tags={t['code']:t for t in meta['image']}
    result=dict(schema='gpr.stock_sr_historical_boundary_render_audit.v1',complete=True,protocol_sha256=sha(p),scores=scores,gate_zero_samples=int(zero.sum()),samples=int(base.size),gate_zero_fraction=float(zero.mean()),changed_samples=int(np.count_nonzero(restored!=base)),changed_fraction=float(np.mean(restored!=base)),gate_zero_output_equals_bicubic=True,gopro_black_level=raw_media.values(tags[50714]),quality_approval=False)
    (root/'audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
