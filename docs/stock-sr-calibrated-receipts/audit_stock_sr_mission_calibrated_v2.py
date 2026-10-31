"""Audit every regenerated patch against archived RAW and actual stock decode."""
from pathlib import Path
import hashlib,json,sys
import numpy as np
REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime');sys.path.insert(0,str(REPO/'tools'))
import raw_media
ROOT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_mission_calibrated_20261031-metadata-v2')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    root=ROOT/'dataset';info=json.loads((root/'dataset.json').read_text());protocol=json.loads((ROOT/'protocol.json').read_text());assert info['complete']
    assert sha(root/'inputs.npy')==info['input_sha256'] and sha(root/'targets.npy')==info['target_sha256']
    x=np.load(root/'inputs.npy',mmap_mode='r');y=np.load(root/'targets.npy',mmap_mode='r');assert x.shape==(1088,4,128,128) and y.shape==(1088,4,256,256)
    prior=json.loads((REPO/'docs/stock-sr-mission-source-receipts/scene-groups.json').read_text());by={s['stem']:s for s in prior['sources']};seen=set();patches=0;rows=[]
    for index,s in enumerate(info['sources']):
        raw=Path(by[s['stem']]['raw_path']);assert sha(raw)==s['archived_raw_sha256'];assert s['archived_raw_sha256'] not in seen;seen.add(s['archived_raw_sha256'])
        if s['split']=='test':assert s['patch_start'] is None and s['patch_count']==0;continue
        dng=Path(s['path']);assert sha(dng)==s['sha256'];meta=raw_media.extract(dng,14);assert meta['cfa']=='RGGB'
        high=np.memmap(raw,dtype='<u2',mode='r',shape=(6144,8192));lowpath=root/f'source-{index:03d}/decoded.raw';assert sha(lowpath)==s['low_decoded_raw_sha256'];low=np.memmap(lowpath,dtype='<u2',mode='r',shape=(3072,4096))
        for offset,(py,px) in enumerate(s['low_plane_yx']):
            i=s['patch_start']+offset
            for c in range(4):
                sy,sx=c//2,c%2
                assert np.array_equal(x[i,c],low[2*py+sy:2*py+sy+256:2,2*px+sx:2*px+sx+256:2])
                assert np.array_equal(y[i,c],high[4*py+sy:4*py+sy+512:2,4*px+sx:4*px+sx+512:2])
            patches+=1
        rows.append(dict(stem=s['stem'],split=s['split'],patches=s['patch_count'],all_input_and_target_coordinates_exact=True))
    assert patches==1088 and len(rows)==34 and len(seen)==42
    result=dict(schema='gpr.stock_sr_mission_calibrated_pair_audit.v1',complete=True,script_sha256=sha(Path(__file__)),dataset_sha256=sha(root/'dataset.json'),input_sha256=sha(root/'inputs.npy'),target_sha256=sha(root/'targets.npy'),patches_verified=patches,non_test_sources=34,unique_archived_references=42,test_patch_count=0,rows=rows,
        limitations=['Archived SDK parameter JSON has printed numeric precision, not original binary opcode/float identity.','42 count/metadata associations are archived stem/time/ISO records;10 separate source-GPR parameter records corroborate core calibration.','No freshly recovered original GPRs, lossless sensor truth or blind data.'])
    (ROOT/'pair-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(complete=True,patches_verified=patches,non_test_sources=34,test_patches=0)))
if __name__=='__main__':main()
