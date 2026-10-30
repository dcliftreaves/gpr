"""Recheck published model's full-reference RAW guard on native backends."""
import contextlib,hashlib,json,sys,time
from pathlib import Path
import numpy as np
import tifffile
repo=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime');sys.path.insert(0,str(repo/'tools'))
import raw_media,stock_still
from benchmark_stills import quality
study=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_source_regions_20261030/all-qualified');root=study/'native'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
base_protocol=json.loads((root/'protocol.json').read_text())
protocol=dict(schema='gpr.stock_sr_source_native_quality_protocol.v1',checkpoint_sha256=base_protocol['checkpoint_sha256'],native_check_protocol_sha256=sha(root/'protocol.json'),cases=base_protocol['cases'],references=['0001','0067','5323','6693'],baseline='same frozen Torch MPS bicubic counts/metrics from the published final evaluation, on identical stock-Q3 low input',regions=['active','shadow_bottom_decile','highlight_top_decile','detail_top_decile'],quality_approval=False,selection_used=False,driver_sha256=sha(Path(__file__)),evaluator_sha256=sha(repo/'tools/benchmark_stills.py'))
(root/'quality-protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
result=dict(schema='gpr.stock_sr_source_native_quality.v1',complete=False,quality_approval=False,protocol_sha256=sha(root/'quality-protocol.json'),rows=[])
for case in protocol['cases']:
 for name in protocol['references']:
  frozen_dir=study/f'final-{name}';frozen=json.loads((frozen_dir/'benchmark.json').read_text())
  source=frozen_dir/'simulated-low-q3.gpr';assert sha(source)==frozen['low_gpr_sha256']
  ref_path=frozen_dir/'independent-sdk.raw';assert sha(ref_path)==frozen['reference_raw_sha256']
  reference=np.fromfile(ref_path,dtype='<u2').reshape(frozen['height'],frozen['width'])
  original=Path('/Users/dcliftreaves/gpr_data/gate_dngs')/f'Z8Z_{name}.dng';assert sha(original)==frozen['source_sha256'];meta=raw_media.extract(original,14)
  output=root/f"quality-{case['backend']}-{case['units']}-{name}.dng"
  command=[sys.executable,'-S',str(repo/'tools/stock_still.py'),'restore',str(source),'--sample-bits','14','--sdk',str(repo/'build-runtime/source/app/gpr_tools/gpr_tools'),'--checkpoint',str(repo/'models/stock-q3-rggb14-sr-diagnostic/selected.pt'),'--scale','2','--native-executable',str(repo/'build-runtime/source/app/stock_metal/gpr_reconstruct'),'--native-artifact',case['artifact'],'--native-backend',case['backend'],'--native-units',case['units'],'--native-threads','4','--tile','256','--halo','64','--output',str(output)]
  if case['backend']!='coreml':command+=['--native-kernels',str(repo/'build-runtime/source/app/stock_metal/gpr_stock.metallib')]
  started=time.perf_counter();subprocess_result=__import__('subprocess').run(command,capture_output=True,text=True,check=True,timeout=600);wall=time.perf_counter()-started
  receipt=json.loads(output.with_suffix('.dng.json').read_text());assert receipt['model']['checkpoint_sha256']==protocol['checkpoint_sha256'] and receipt['raw_sha256']==frozen['low_decoded_raw_sha256']
  with tifffile.TiffFile(output) as file:counts=file.asarray()
  assert hashlib.sha256(counts.astype('<u2').tobytes()).hexdigest()==receipt['restored_raw_sha256']
  assert stock_still.canonical(raw_media.extract(output,14))==stock_still.canonical(raw_media.extract(frozen_dir/'candidate-0.dng',14))
  metrics=quality(reference,counts,meta);baseline=frozen['bicubic_metrics'];failed=[key for key in protocol['regions'] if metrics[key]['rmse_counts']>baseline[key]['rmse_counts']]
  with tifffile.TiffFile(frozen_dir/'candidate-0.dng') as file:mps=file.asarray()
  diff=np.abs(counts.astype(np.int32)-mps.astype(np.int32));maximum=int(diff.max());bound=case['bound']
  row=dict(source=name,backend=case['backend'],units=case['units'],command=command,receipt_sha256=sha(output.with_suffix('.dng.json')),reference_raw_sha256=frozen['reference_raw_sha256'],decoded_input_exact=True,calibration_exact=True,independent_pixels_verified=True,metrics=metrics,bicubic_metrics=baseline,region_gain_db={key:metrics[key]['psnr_db']-baseline[key]['psnr_db'] for key in protocol['regions']},regressions=failed,passed_quality_guard=not failed,max_abs_count_difference_from_mps=maximum,bound_counts=bound,passed_numeric_bound=maximum<=bound,native=receipt['native_reconstruction'],process_wall_s=wall)
  result['rows'].append(row);(root/'quality.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:row[k] for k in ['source','backend','units','region_gain_db','regressions','max_abs_count_difference_from_mps','passed_numeric_bound']}),flush=True)
result.update(complete=True,all_quality_guards_passed=all(r['passed_quality_guard'] for r in result['rows']),all_numeric_bounds_passed=all(r['passed_numeric_bound'] for r in result['rows']))
(root/'quality.json').write_text(json.dumps(result,indent=2)+'\n')
