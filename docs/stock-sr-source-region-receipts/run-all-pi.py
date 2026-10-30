import hashlib
import json
import platform
from pathlib import Path
import resource
import sys
import time

repo=Path('/mnt/ssd/gpr_work/stock-raw-media-runtime')
sys.path.insert(0,str(repo/'tools'))
import numpy as np
import tifffile
import torch
import raw_media
import stock_still
import stock_cnn_metadata

root=Path('/mnt/ssd/gpr_work/stock-sr-source-regions-all-20261030')
checkpoint=root/'selected.pt'
assert stock_still.digest(checkpoint)=='f7bda0449b94be4ebd3617297b9dee04506b00e38788dba2d0b04eb71fdaa2f4'
torch.set_num_threads(4)
seed=Path('/mnt/ssd/gpr_work/pi-mission1-writeback8-20261030')
sources=['GP011728','GPAB1094']
receipt=dict(schema='gpr.stock_sr_source_all_pi.v1',complete=False,quality_approval=False,
    checkpoint_sha256=stock_still.digest(checkpoint),torch=torch.__version__,threads=4,
    host=platform.platform(),source_kind='two frozen still-derived stock-Q3 payloads; not lossless sensor references',
    tile=256,halo=64,frames=[])
for i,name in enumerate(sources):
    metadata=json.loads((repo/'mission1-inputs'/(name+'.json')).read_text())
    payload=(seed/f'reference-{i}.vc5').read_bytes()
    source=root/f'{name}.gpr';raw_media.write(source,metadata,payload,'gpr')
    started=time.perf_counter()
    output=root/f'{name}.restored.dng'
    row=stock_still.decode(source,14,repo/'build-runtime/source/app/gpr_tools/gpr_tools',output,
        reconstruction=dict(checkpoint=checkpoint,device='cpu',tile=256,halo=64,scale=2))
    wall=time.perf_counter()-started
    with tifffile.TiffFile(output) as file:counts=file.asarray()
    assert hashlib.sha256(counts.astype('<u2').tobytes()).hexdigest()==row['restored_raw_sha256']
    assert counts.shape==(6144,8192) and counts.dtype==np.dtype('<u2')
    assert int(counts.max())<=16383
    assert stock_still.canonical(raw_media.extract(output,14))==stock_still.canonical(stock_cnn_metadata.scaled(metadata,2)[0])
    row.update(source=name,payload_sha256=hashlib.sha256(payload).hexdigest(),workflow_wall_s=wall,
        pixels_independently_read_back=True,calibration_exact=True)
    receipt['frames'].append(row)
    (root/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(dict(source=name,cnn_s=row['cnn_s'],workflow_wall_s=wall,restored_raw_sha256=row['restored_raw_sha256'])),flush=True)
receipt.update(complete=True,process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
(root/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
