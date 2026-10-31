"""Audit emitted numeric events and summarize per-source timing after all captures finish."""
from pathlib import Path
import hashlib,json,sys

root=Path(sys.argv[1])
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def quantile(values,fraction):
    return sorted(values)[int((len(values)-1)*fraction)]
rows=[]
protocol=json.loads((root/'protocol.json').read_text())
payload_sizes=[i['bytes'] for i in protocol['reference_payloads']]
assert len(set(payload_sizes))==2
for mode,directory in (('recording-preview',root),('recording',root/'recording-control')):
    receipt=json.loads((directory/'receipt.json').read_text());assert receipt['complete']
    for entry in receipt['rows']:
        index=entry['index'];verified=entry['verified']
        events=[json.loads(line) for line in (directory/f'{index}.jsonl').read_text().splitlines() if line.startswith('{')]
        frames=[r for r in events if r['event']=='frame'];previews=[r for r in events if r['event']=='preview']
        summary=next(r for r in events if r['event']=='summary')
        assert summary==verified['capture'] and len(frames)==verified['frames_verified']
        assert len(previews)==verified['previews_verified']
        assert sum(r['deadline_missed'] for r in frames)==summary['deadline_misses']
        assert abs(quantile([r['encode_ms'] for r in frames],.5)-summary['encode_median_ms'])<.0002
        assert sum(r['capture_to_sink_ms']>50 for r in previews)==verified['floor']['preview_late_deliveries']
        sources={r['index']:payload_sizes.index(r['bytes']) for r in frames}
        assert all(sources[r['index']]==r['source_index'] for r in previews)
        grouped={}
        for source in range(2):
            f=[r for r in frames if sources[r['index']]==source]
            p=[r for r in previews if r['source_index']==source]
            grouped[str(source)]=dict(frames=len(f),encode_median_ms=quantile([r['encode_ms'] for r in f],.5),
                encode_maximum_ms=max(r['encode_ms'] for r in f),late_writes=sum(r['deadline_missed'] for r in f),
                previews=len(p),late_previews=sum(r['capture_to_sink_ms']>50 for r in p))
            if p:
                grouped[str(source)]['render_median_ms']=quantile([r['render_ms'] for r in p],.5)
                grouped[str(source)]['maximum_capture_to_sink_ms']=max(r['capture_to_sink_ms'] for r in p)
        rows.append(dict(mode=mode,index=index,event_sha256=sha(directory/f'{index}.jsonl'),per_source=grouped))
result=dict(schema='gpr.stock_native12_event_audit.v1',complete=True,driver_sha256=sha(Path(__file__)),
    protocol_sha256=sha(root/'protocol.json'),receipt_sha256=sha(root/'receipt.json'),
    control_protocol_sha256=sha(root/'recording-control/protocol.json'),control_receipt_sha256=sha(root/'recording-control/receipt.json'),
    note='Source inferred from the two distinct, independently verified constant payload lengths. Capture encode interval includes retained-band preview reconstruction when enabled; differences are not isolated kernel costs.',rows=rows)
(root/'event-audit.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
