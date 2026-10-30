"""Check the published 2x diagnostic candidate through standalone native media frontends."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import tifffile

repo=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime')
sys.path.insert(0,str(repo/'tools'))
import raw_media
import stock_still

study=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_source_regions_20261030/all-qualified')
root=study/'native';checkpoint=repo/'models/stock-q3-rggb14-sr-diagnostic/selected.pt'
native=repo/'build-runtime/source/app/stock_metal/gpr_reconstruct'
kernels=repo/'build-runtime/source/app/stock_metal/gpr_stock.metallib'
digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
cases=[dict(backend='coreml',units=units,artifact=str(root/'coreml-f32'),bound=1) for units in ['cpu','gpu','ane','all']]
cases += [dict(backend=backend,units='all',artifact=str(root/'metal-f16'),bound=32) for backend in ['mpsgraph','hybrid']]
protocol=dict(schema='gpr.stock_sr_source_native_protocol.v1',checkpoint_sha256=digest(checkpoint),
    executable_sha256=digest(native),kernels_sha256=digest(kernels),cases=cases,
    source_kind='two frozen supplied 12 MP stock-Q3 GPRs; not lossless sensor references',
    comparison='native final counts against previously recorded Torch MPS counts; existing Core ML float32 <=1 and Metal fp16 <=32 count contracts',
    ml_python_runtime_disabled=True,quality_approval=False)
(root/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
report=dict(schema='gpr.stock_sr_source_native_check.v1',complete=False,quality_approval=False,
    protocol_sha256=digest(root/'protocol.json'),rows=[])
for case in cases:
    for name in ['GP011728','GPAB1094']:
        label=case['backend']+'-'+case['units']+'-'+name
        output=root/(label+'.dng')
        command=[sys.executable,'-S',str(repo/'tools/stock_still.py'),'restore',str(Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_cleanup_strength_20261030/pi-evidence')/(name+'.gpr')),
            '--sample-bits','14','--sdk',str(repo/'build-runtime/source/app/gpr_tools/gpr_tools'),
            '--checkpoint',str(checkpoint),'--scale','2','--native-executable',str(native),
            '--native-artifact',case['artifact'],'--native-backend',case['backend'],
            '--native-units',case['units'],'--native-threads','4','--tile','256','--halo','64','--output',str(output)]
        if case['backend']!='coreml':command += ['--native-kernels',str(kernels)]
        started=time.perf_counter()
        completed=subprocess.run(command,capture_output=True,text=True,check=True,timeout=600)
        wall=time.perf_counter()-started
        result=json.loads(output.with_suffix('.dng.json').read_text())
        with tifffile.TiffFile(output) as file:actual=file.asarray()
        reference_path=study/'portability'/(name+'.mps.dng')
        with tifffile.TiffFile(reference_path) as file:reference=file.asarray()
        reference_receipt=json.loads(reference_path.with_suffix('.dng.json').read_text())
        assert result['raw_sha256']==reference_receipt['raw_sha256']
        assert result['model']['checkpoint_sha256']==protocol['checkpoint_sha256']
        assert digest(output)==result['output_sha256']
        assert hashlib.sha256(actual.astype('<u2').tobytes()).hexdigest()==result['restored_raw_sha256']
        assert stock_still.canonical(raw_media.extract(output,14))==stock_still.canonical(raw_media.extract(reference_path,14))
        difference=np.abs(actual.astype(np.int32)-reference.astype(np.int32));worst=int(difference.max())
        row=dict(source=name,backend=case['backend'],units=case['units'],command=command,
            receipt_sha256=digest(output.with_suffix('.dng.json')),native=result['native_reconstruction'],
            process_wall_s=wall,max_abs_count_difference=worst,mean_abs_count_difference=float(difference.mean()),
            different_samples=int(np.count_nonzero(difference)),samples=int(difference.size),
            decoded_input_exact=True,calibration_exact=True,independent_pixels_verified=True,
            bound_counts=case['bound'],passed_numeric_bound=worst<=case['bound'])
        report['rows'].append(row)
        (root/'native-check.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(dict(source=name,backend=case['backend'],units=case['units'],worst=worst,
            restore_s=result['native_reconstruction']['restore_s'],wall_s=wall,passed=row['passed_numeric_bound'])),flush=True)
report.update(complete=True,all_numeric_bounds_passed=all(row['passed_numeric_bound'] for row in report['rows']))
(root/'native-check.json').write_text(json.dumps(report,indent=2)+'\n')
