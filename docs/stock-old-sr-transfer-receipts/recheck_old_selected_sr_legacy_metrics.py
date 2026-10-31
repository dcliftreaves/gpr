"""Finish legacy-control metrics from the saved prediction; no inference rerun."""
from pathlib import Path
import json,sys,hashlib
import numpy as np
ROOT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_old_selected_transfer_20261030');REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime');sys.path.insert(0,str(REPO/'tools'))
from benchmark_stills import quality
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();p=json.loads((ROOT/'legacy-control-protocol.json').read_text())
low=Path('/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_residual_q4t2_broad_gate_20260619/mission42_q4_t2_all/low/GP017346.raw');high=Path('/Volumes/OWC_8TB/gpr_work/artifacts/mission1p_source_scan_20260616/raw50_decode/GP017346.raw')
prior=Path('/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_cnn_hardtile_gate_aligned_20260624/interp_step1_to_balanced_step200/alpha0p5_mission42_broad_fullframe/summary.json');summary=json.loads(prior.read_text());row=next(r for r in summary['images'] if r['image']=='GP017346');bench=json.loads(Path(row['bench_json']).read_text());compare=json.loads(Path(row['compare_json']).read_text());assert sha(low)==p['low_sha256']==bench['raw_sha256'] and sha(high)==p['high_sha256'] and sha(prior)==p['prior_summary_sha256']
ref=np.fromfile(high,dtype='<u2').reshape(6144,8192);value=np.fromfile(ROOT/'legacy-control.raw',dtype='<u2').reshape(6144,8192)
metrics=quality(ref,value,dict(sample_bits=14,width=8192,height=6144,cfa='RGGB',image=[]));previous=Path(compare['sr_raw']);old_match=None
if previous.exists():
 original=np.memmap(previous,mode='r',dtype='<u2',shape=(6144,8192));maximum=0;changed=0
 for start in range(0,6144,128):
  d=abs(original[start:start+128].astype(np.int32)-value[start:start+128].astype(np.int32));maximum=max(maximum,int(d.max()));changed+=int(np.count_nonzero(d))
 old_match=dict(archived_prediction_sha256=sha(previous),max_count_difference=maximum,differing_samples=changed)
report=dict(schema='gpr.stock_old_sr_legacy_control.v1',complete=True,protocol_sha256=sha(ROOT/'legacy-control-protocol.json'),metrics_driver_sha256=sha(Path(__file__)),metrics=metrics,expected_psnr_db=row['model_psnr14_db'],actual_psnr_db=metrics['active']['psnr_db'],delta_from_recorded_db=metrics['active']['psnr_db']-row['model_psnr14_db'],output_sha256=sha(ROOT/'legacy-control.raw'),archived_prediction_comparison=old_match,initial_metric_error='diagnostic metadata lacked cfa site labels; prediction had completed and is reused',quality_approval=False)
(ROOT/'legacy-control.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(expected=report['expected_psnr_db'],actual=report['actual_psnr_db'],delta=report['delta_from_recorded_db'],prediction_comparison=old_match)),flush=True)
