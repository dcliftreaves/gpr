"""Diagnostic full-frame validation; does not alter or select the rejected model."""
import contextlib,datetime,hashlib,json,sys
from pathlib import Path
repo=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime');sys.path.insert(0,str(repo/'tools'))
import benchmark_stock_sr
root=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_region_relative_20261030')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=json.loads((root/'protocol.json').read_text());info=json.loads((Path(p['dataset'])/'dataset.json').read_text())
selected=root/'selected.pt';f=json.loads((root/'frozen.json').read_text());assert sha(selected)==f['checkpoint_sha256']
sources=[s for s in info['sources'] if s['split']=='validation'];assert len(sources)==4
protocol=dict(schema='gpr.stock_sr_full_validation_protocol.v1',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),checkpoint_sha256=sha(selected),dataset_sha256=sha(Path(p['dataset'])/'dataset.json'),sources=[{k:s[k] for k in ['path','sha256','group','split']} for s in sources],purpose='diagnose sparse-patch vs full-frame validation; candidate already failed final guard; no reselection or weight change',final_sources_evaluated=False,regions=['active','shadow_bottom_decile','highlight_top_decile','detail_top_decile'],driver_sha256=sha(Path(__file__)),evaluator_sha256=sha(repo/'tools/benchmark_stock_sr.py'))
(root/'full-validation-protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
result=dict(schema='gpr.stock_sr_full_validation.v1',complete=False,quality_approval=False,protocol_sha256=sha(root/'full-validation-protocol.json'),checkpoint_sha256=sha(selected),rows=[])
for i,s in enumerate(sources):
 source=Path(s['path']);assert sha(source)==s['sha256']
 with (root/f'validation-{i}.stdout').open('w') as out,contextlib.redirect_stdout(out):
  r=benchmark_stock_sr.evaluate(source,repo/'build-runtime/source/app/gpr_tools/gpr_tools',[selected],root/f'validation-{i}',device='mps',tile=256,halo=64)
 model=r['rows'][0]['metrics'];base=r['bicubic_metrics'];regressions=[k for k in protocol['regions'] if model[k]['rmse_counts']>base[k]['rmse_counts']]
 row=dict(source=source.name,group=s['group'],receipt_sha256=sha(root/f'validation-{i}/benchmark.json'),region_delta_db={k:model[k]['psnr_db']-base[k]['psnr_db'] for k in protocol['regions']},regressions=regressions,passed_numeric_guard=not regressions)
 result['rows'].append(row);(root/'full-validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(row),flush=True)
result.update(complete=True,all_full_validation_guards_pass=all(x['passed_numeric_guard'] for x in result['rows']))
(root/'full-validation.json').write_text(json.dumps(result,indent=2)+'\n')
