"""One fixed old production checkpoint on current stock low input; no retuning."""
from pathlib import Path
import subprocess,sys,json,hashlib,datetime
import numpy as np,torch,tifffile
REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime');sys.path.insert(0,str(REPO/'tools'))
import raw_media,stock_still
from benchmark_stills import quality
ROOT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_old_selected_transfer_20261030');ROOT.mkdir(exist_ok=False)
DATA=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_cnn_supplied_gopro_shared_20261030');CASE=DATA/'GP011689';REV='8be29eee57b4637865b572f18ab9e3f4edaa2236';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
CP=Path('/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_cnn_hardtile_gate_aligned_20260624/interp_step1_to_balanced_step200/q4t2_coord_detail_balanced_step001_to_step200_alpha0p5.pt')
assert sha(CP)=='791628778f74b13542677edeb5de7934b88d274531a8ec1755d8cf3d6388fb07'
for name in ['mission1_sr_models.py','mission1_sr_runtime.py']:(ROOT/name).write_bytes(subprocess.check_output(['git','show',REV+':tools/cnn/'+name],cwd=REPO))
current=json.loads((DATA/'summary.json').read_text());row=next(r for r in current['cases'] if r['source']=='GP011689.GPR');assert sha(CASE/'decoded.raw')==row['decoded_low_raw_sha256']
protocol=dict(schema='gpr.stock_old_selected_transfer_protocol.v1',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),driver_sha256=sha(Path(__file__)),old_runtime_revision=REV,runtime_source_sha256={n:sha(ROOT/n) for n in ['mission1_sr_models.py','mission1_sr_runtime.py']},checkpoint_sha256=sha(CP),source_sha256=row['source_sha256'],decoded_low_raw_sha256=row['decoded_low_raw_sha256'],tile=512,overlap=32,coordinates=True,device='mps',retuning_or_selection=False,quality_approval=False,limitations=['old model trained against fused q4/t2 detail-sidecar inputs; this input is stockQ3','old training used Gaussian-area degradation; current frozen comparison uses same-site area averaging','same household venue appears in old training; not an unseen-scene claim','camera GPR decoded count reference, not lossless sensor truth'])
(ROOT/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
sys.path.insert(0,str(ROOT));import mission1_sr_models as models;import mission1_sr_runtime as runtime
checkpoint=torch.load(CP,map_location='cpu',weights_only=True);config=checkpoint['config'];model=models.make_model_from_config(config).to('mps');model.load_state_dict(checkpoint['model'],strict=True);model.eval();torch.set_num_threads(4)
low=np.fromfile(CASE/'decoded.raw',dtype='<u2').reshape(3072,4096);out,stats=runtime.run_tiles(model,runtime.deinterleave(low),torch.device('mps'),512,32,True,8192,6144,True)
assert out is not None and out.shape==(4,3072,4096) and out.max()<=16383
runtime.reinterleave_to_path(ROOT/'restored.raw',out)
with tifffile.TiffFile(CASE/'source.dng') as f:reference=f.asarray()
restored=np.fromfile(ROOT/'restored.raw',dtype='<u2').reshape(6144,8192);metrics=quality(reference,restored,raw_media.extract(CASE/'source.dng',14));base=row['baseline_metrics'];regions=['active','shadow_bottom_decile','highlight_top_decile','detail_top_decile'];failed=[r for r in regions if metrics[r]['rmse_counts']>base[r]['rmse_counts']]
meta=raw_media.extract(CASE/'restored.dng',14);raw_media.write(ROOT/'restored.dng',meta,restored.tobytes());assert stock_still.canonical(raw_media.extract(ROOT/'restored.dng',14))==stock_still.canonical(meta)
report=dict(schema='gpr.stock_old_selected_transfer.v1',complete=True,quality_approval=False,protocol_sha256=sha(ROOT/'protocol.json'),config=config,metrics=metrics,current_stock_bicubic_metrics=base,current_stock_bibo_metrics=row['restored_metrics'],active_gain_vs_stock_bicubic_db=metrics['active']['psnr_db']-base['active']['psnr_db'],active_gain_vs_current_stock_bibo_db=metrics['active']['psnr_db']-row['restored_metrics']['active']['psnr_db'],regional_regressions=failed,runtime_stats=stats,output_raw_sha256=sha(ROOT/'restored.raw'),editable_supported_calibration_verified=True)
(ROOT/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(complete=True,gain_vs_bicubic_db=report['active_gain_vs_stock_bicubic_db'],gain_vs_current_bibo_db=report['active_gain_vs_current_stock_bibo_db'],regressions=failed)),flush=True)
