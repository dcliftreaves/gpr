"""Audit archived isolated/workflow events without Pi access or third-party dependencies."""
from pathlib import Path
import hashlib,json,math,statistics,sys
root=Path(sys.argv[1])
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def audit_modes(path):
    events=[json.loads(line) for line in path.read_text().splitlines()]
    order=['none','retain','reconstruct','reconstruct','retain','none','retain','none','reconstruct','none','reconstruct','retain']
    assert len(events)==192
    for i,r in enumerate(events):
        assert r['block']==i//16 and r['mode']==order[i//16] and r['iteration']==i%16 and r['warmup']==(i%16==0)
        assert r['all_payloads_exact_independent_stock'] and math.isfinite(r['wall_s']) and r['wall_s']>0
        if r['mode']=='reconstruct':assert r['planes_exact_independent_decode']
    return {mode:statistics.median(r['wall_s']*1000 for r in events if r['mode']==mode and not r['warmup']) for mode in ('none','retain','reconstruct')}
isolated={};mode_encodes=plane_checks=0
for name,directory in [('baseline',root/'baseline'),('spacing',root/'spacing'),('rows-v1',root/'rows-v1/isolated'),('rows-v2',root/'rows-v2/isolated')]:
    receipt=read(directory/'receipt.json');assert receipt['complete']
    assert sha(directory/'protocol.json')==receipt['protocol_sha256']
    isolated[name]=[]
    for row in receipt['rows']:
        values=audit_modes(directory/f"{row['source']}.jsonl")
        for mode,value in values.items():assert abs(value-row['modes'][mode]['median_ms'])<1e-8
        isolated[name].append(dict(source=row['source'],modes=values))
        mode_encodes+=192;plane_checks+=64*3
legacy={};native={};accepted=previews=attempts=0
for name in ('rows-v1','rows-v2'):
    directory=root/name/'legacy-abba';receipt=read(directory/'receipt.json');assert receipt['complete']
    assert sha(directory/'protocol.json')==receipt['protocol_sha256']
    legacy[name]=[]
    assert len(receipt['rows'])==8
    for row in receipt['rows']:
        values=audit_modes(directory/f"{row['source']}-{row['run']}.jsonl")
        for mode,value in values.items():assert abs(value-row['modes'][mode]['median_ms'])<1e-8
        legacy[name].append(dict(source=row['source'],run=row['run'],mode=row['mode'],modes=values))
        mode_encodes+=192;plane_checks+=64*3
    directory=root/name/'native-abba';receipt=read(directory/'receipt.json');assert receipt['complete']
    assert sha(directory/'protocol.json')==receipt['protocol_sha256']
    assert [r['mode'] for r in receipt['rows']]==['baseline','candidate','candidate','baseline']
    native[name]=[]
    for row in receipt['rows']:
        v=row['verified'];events=[json.loads(s) for s in (directory/f"{row['index']}.jsonl").read_text().splitlines()]
        f=[r for r in events if r['event']=='frame'];p=[r for r in events if r['event']=='preview']
        assert len(f)==v['frames_verified']==v['previews_verified']==len(p)
        assert v['all_payloads_exact_independent_stock'] and v['all_source_calibration_exact'] and v['all_delivered_preview_pixels_exact_offline'] and v['end_marker_verified']
        assert v['capture']==next(r for r in events if r['event']=='summary')
        assert sum(r['deadline_missed'] for r in f)==v['capture']['deadline_misses']
        assert sum(r['capture_to_sink_ms']>50 for r in p)==v['floor']['preview_late_deliveries']
        assert not v['floor']['recording'] and not v['floor']['preview']
        native[name].append(dict(index=row['index'],mode=row['mode'],accepted=len(f),attempts=v['capture']['attempts'],durable_fps=v['capture']['durable_fps'],encode_median_ms=v['capture']['encode_median_ms'],render_median_ms=v['preview']['render_median_ms'],late_writes=v['capture']['deadline_misses'],late_previews=v['floor']['preview_late_deliveries']))
        accepted+=len(f);previews+=len(p);attempts+=v['capture']['attempts']
stages=read(root/'stages/receipt.json');assert stages['complete'] and stages['diagnostic_only'] and not stages['acceptance_timing']
stage_frames=sum(row['verified']['frames_verified'] for row in stages['rows'])
restored=read(root/'restoration/restoration.json');assert restored['restored'] and restored['main_capture_sha256']=='c576f5662ac605cc5719ae536308e9ff71cdcec4f4e714343a5a919a5711687c'
assert '100% tests passed, 0 tests failed out of 27' in (root/'restoration/restored-mac-release.stdout').read_text()
assert '100% tests passed, 0 tests failed out of 24' in (root/'restoration/restored-pi-release.stdout').read_text()
assert 'ModuleNotFoundError: No module named \'numpy\'' in (root/'validation/initial-missing-numpy/pi-release.stdout').read_text()
assert '100% tests passed, 0 tests failed out of 3' in (root/'validation/pi-python-corrected.stdout').read_text()
summary=dict(schema='gpr.stock_preview_retention_audit.v1',complete=True,decision='discard_all_three_runtime_proposals',runtime_source_changed=False,
    driver_sha256=sha(Path(__file__)),isolated=isolated,legacy=legacy,native=native,
    isolated_payloads_verified=mode_encodes,isolated_plane_comparisons_verified=plane_checks,
    combined_attempts=attempts,combined_payloads_verified=accepted,combined_previews_verified=previews,combined_overruns=attempts-accepted,
    diagnostic_payloads_previews_verified=stage_frames,restored_capture_sha256=restored['main_capture_sha256'],
    interpretation='Retaining alone has a substantial measured cost. Spacing does not recover it. Scratch rows improve some isolated/native results, but ordinary-path concern and inconsistent revised combined comparisons prevent adoption. Slow-regime diagnostic medians do not establish the cause of production fast/slow variability.')
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k not in ('isolated','legacy','native')},indent=2))

