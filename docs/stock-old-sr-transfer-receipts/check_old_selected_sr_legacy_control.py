"""Check the transferred checkpoint/runtime against one archived matched-input result."""
from pathlib import Path
import sys,json,hashlib
import numpy as np,torch
ROOT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_old_selected_transfer_20261030');REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime');sys.path.insert(0,str(ROOT));sys.path.insert(0,str(REPO/'tools'))
import mission1_sr_models as models,mission1_sr_runtime as runtime
from benchmark_stills import quality
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
cp=Path('/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_cnn_hardtile_gate_aligned_20260624/interp_step1_to_balanced_step200/q4t2_coord_detail_balanced_step001_to_step200_alpha0p5.pt')
low=Path('/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_residual_q4t2_broad_gate_20260619/mission42_q4_t2_all/low/GP017346.raw');high=Path('/Volumes/OWC_8TB/gpr_work/artifacts/mission1p_source_scan_20260616/raw50_decode/GP017346.raw')
prior=Path('/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_cnn_hardtile_gate_aligned_20260624/interp_step1_to_balanced_step200/alpha0p5_mission42_broad_fullframe/summary.json');old=json.loads(prior.read_text());expected=next(r for r in old['images'] if r['image']=='GP017346')
p=dict(schema='gpr.stock_old_sr_legacy_control_protocol.v1',checkpoint_sha256=sha(cp),low_sha256=sha(low),high_sha256=sha(high),prior_summary_sha256=sha(prior),driver_sha256=sha(Path(__file__)),expected_psnr_db=expected['model_psnr14_db'],source='archived matched old q4/t2 sidecar counts; original GPR not redecoded',retuning=False)
(ROOT/'legacy-control-protocol.json').write_text(json.dumps(p,indent=2)+'\n');d=torch.load(cp,map_location='cpu',weights_only=True);model=models.make_model_from_config(d['config']).to('mps');model.load_state_dict(d['model']);model.eval();torch.set_num_threads(4)
planes=runtime.deinterleave(np.fromfile(low,dtype='<u2').reshape(3072,4096));out,stats=runtime.run_tiles(model,planes,torch.device('mps'),512,32,True,8192,6144,True);runtime.reinterleave_to_path(ROOT/'legacy-control.raw',out)
ref=np.fromfile(high,dtype='<u2').reshape(6144,8192);value=np.fromfile(ROOT/'legacy-control.raw',dtype='<u2').reshape(6144,8192)
metrics=quality(ref,value,dict(sample_bits=14,width=8192,height=6144,image=[]));report=dict(schema='gpr.stock_old_sr_legacy_control.v1',complete=True,protocol_sha256=sha(ROOT/'legacy-control-protocol.json'),metrics=metrics,expected_psnr_db=expected['model_psnr14_db'],actual_psnr_db=metrics['active']['psnr_db'],delta_from_recorded_db=metrics['active']['psnr_db']-expected['model_psnr14_db'],prior_compare_json=expected['compare_json'],runtime_stats=stats,output_sha256=sha(ROOT/'legacy-control.raw'),quality_approval=False)
(ROOT/'legacy-control.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(expected=report['expected_psnr_db'],actual=report['actual_psnr_db'],delta=report['delta_from_recorded_db'])),flush=True)
