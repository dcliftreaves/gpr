import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import tifffile

repo=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime')
sys.path.insert(0,str(repo/'tools'))
import stock_still
import raw_media

root=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_cleanup_strength_20261030')
pi=root/'pi-evidence';receipt=json.loads((pi/'receipt.json').read_text());rows=[]
for name in ['GP011728','GPAB1094']:
    output=pi/f'{name}.mps.dng'
    if output.exists():
        report=json.loads(output.with_suffix('.dng.json').read_text())
        assert stock_still.digest(output)==report['output_sha256']
        assert stock_still.digest(pi/f'{name}.gpr')==report['source_sha256']
        assert stock_still.digest(root/'selected.pt')==report['model']['checkpoint_sha256']
    else:
        report=stock_still.decode(pi/f'{name}.gpr',14,repo/'build-runtime/source/app/gpr_tools/gpr_tools',output,
            reconstruction=dict(checkpoint=root/'selected.pt',device='mps',tile=256,halo=64,scale=1))
    with tifffile.TiffFile(output) as file:mps=file.asarray()
    with tifffile.TiffFile(pi/f'{name}.restored.dng') as file:cpu=file.asarray()
    frame=next(row for row in receipt['frames'] if row['source']==name)
    assert hashlib.sha256(cpu.astype('<u2').tobytes()).hexdigest()==frame['restored_raw_sha256']
    assert report['raw_sha256']==frame['raw_sha256']
    assert stock_still.canonical(raw_media.extract(output,14))==stock_still.canonical(raw_media.extract(pi/f'{name}.restored.dng',14))
    difference=np.abs(cpu.astype(np.int32)-mps.astype(np.int32))
    row=dict(source=name,checkpoint_sha256=report['model']['checkpoint_sha256'],
        samples=int(difference.size),different_samples=int(np.count_nonzero(difference)),
        max_abs_count_difference=int(difference.max()),mean_abs_count_difference=float(difference.mean()),
        cpu_raw_sha256=frame['restored_raw_sha256'],mps_raw_sha256=report['restored_raw_sha256'],
        decoded_input_exact=True,calibration_exact=True,mps_inference_s=report['cnn_s'])
    rows.append(row);print(json.dumps(row),flush=True)
result=dict(schema='gpr.stock_cleanup_strength_cross_host.v1',complete=True,rows=rows,
    all_within_one_count=all(row['max_abs_count_difference']<=1 for row in rows),
    scope='Two supplied 12 MP still-derived sources; Torch CPU on Pi versus Torch MPS on Mac; not cross-camera quality approval')
(root/'cross-host.json').write_text(json.dumps(result,indent=2)+'\n')
