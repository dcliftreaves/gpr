from pathlib import Path
import json,hashlib,sys
import numpy as np
import tifffile
repo=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime');sys.path.insert(0,str(repo/'tools'))
import stock_still,raw_media
root=Path(__file__).resolve().parent;out=root/'portability';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
pi=json.loads((out/'receipt.json').read_text());mps=json.loads((root/'mps-portability.json').read_text());p=json.loads((root/'cross-host-protocol.json').read_text())
assert pi['complete'] and pi['checkpoint_sha256']==p['checkpoint_sha256'];rows=[]
for cpu,gpu in zip(pi['frames'],mps['rows']):
 name=cpu['source'];assert name==gpu['source'] and cpu['raw_sha256']==gpu['raw_sha256']
 with tifffile.TiffFile(out/f'{name}.restored.dng') as f:a=f.asarray()
 with tifffile.TiffFile(out/f'{name}.mps.dng') as f:b=f.asarray()
 assert a.shape==b.shape==(6144,8192)
 assert hashlib.sha256(a.astype('<u2').tobytes()).hexdigest()==cpu['restored_raw_sha256'] and hashlib.sha256(b.astype('<u2').tobytes()).hexdigest()==gpu['restored_raw_sha256']
 diff=np.abs(a.astype(np.int32)-b.astype(np.int32));maximum=int(diff.max());assert maximum<=p['cpu_mps_max_abs_count_difference']
 assert stock_still.canonical(raw_media.extract(out/f'{name}.restored.dng',14))==stock_still.canonical(raw_media.extract(out/f'{name}.mps.dng',14))
 rows.append(dict(source=name,samples=int(a.size),max_abs_count_difference=maximum,different_samples=int(np.count_nonzero(diff)),mean_abs_count_difference=float(diff.mean()),calibration_exact=True,decoded_input_exact=True,pixels_independently_verified=True,pi_cnn_s=cpu['cnn_s'],mps_cnn_s=gpu['cnn_s']))
result=dict(schema='gpr.stock_sr_source_all_cross_host.v1',complete=True,quality_approval=False,protocol_sha256=sha(root/'cross-host-protocol.json'),checkpoint_sha256=pi['checkpoint_sha256'],pi_receipt_sha256=sha(out/'receipt.json'),mps_receipt_sha256=sha(root/'mps-portability.json'),verification_driver_sha256=sha(Path(__file__)),numeric_bound_passed=True,rows=rows,source_kind=p['source_kind'])
(root/'cross-host.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(rows,indent=2))
