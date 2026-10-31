"""Bind archived Mission 1 count references; do not imply unavailable source redecoding."""
from pathlib import Path
import sys,json,hashlib,collections,datetime
import numpy as np
REPO=Path('/Users/dcliftreaves/Documents/slop/gpr_check/worktrees/stock-raw-media-runtime');sys.path.insert(0,str(REPO/'tools'))
import raw_media
ROOT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_mission_sources_20261030');ROOT.mkdir(exist_ok=False)
PARENT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/mission1p_source_scan_20260616')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
manifest=json.loads((PARENT/'raw50_decode_manifest.json').read_text());media=json.loads((PARENT/'media_summary.json').read_text());by={x['stem']:x for x in media['stems']}
p=dict(schema='gpr.stock_sr_mission_sources_protocol.v1',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),driver_sha256=sha(Path(__file__)),decode_manifest_sha256=sha(PARENT/'raw50_decode_manifest.json'),media_summary_sha256=sha(PARENT/'media_summary.json'),expected_width=8192,expected_height=6144,expected_samples=8192*6144,sample_bits=14,scope='availability/count-domain/provenance audit, not new source decode or scene split',quality_approval=False)
(ROOT/'protocol.json').write_text(json.dumps(p,indent=2)+'\n');rows=[]
for row in manifest['results']:
 assert row['status']=='ok' and row['returncode']==0
 raw=Path(row['raw']);src=Path(row['source']);entry=by[row['stem']];assert raw.exists() and raw.stat().st_size==p['expected_samples']*2
 x=np.memmap(raw,dtype='<u2',mode='r');lo=int(x.min());hi=int(x.max());assert hi<16384
 rows.append(dict(stem=row['stem'],raw_path=str(raw),raw_sha256=sha(raw),raw_bytes=raw.stat().st_size,min_count=lo,max_count=hi,original_source_path=str(src),original_source_available=src.exists(),recorded_datetime=entry.get('datetime',{}).get('GPR'),recorded_iso=entry.get('iso',{}).get('GPR'),recorded_model=entry.get('model',{}).get('GPR'),recorded_dimensions=entry.get('dims',{}).get('GPR')))
 print(row['stem'],flush=True)
supplied=[]
for name in ['GP011728.GPR','GPAB1094.GPR','GP011689.GPR']:
 src=Path('/Users/dcliftreaves/Downloads')/name;meta=raw_media.extract(src,14);tags={t['code']:t for t in meta['image']}
 supplied.append(dict(name=name,source_sha256=sha(src),width=meta['width'],height=meta['height'],cfa=meta['cfa'],black_level=raw_media.values(tags[50714]),white_level=raw_media.values(tags[50717])))
dates=collections.Counter((r['recorded_datetime'] or 'unknown')[:10] for r in rows)
report=dict(schema='gpr.stock_sr_mission_sources_audit.v1',complete=True,protocol_sha256=sha(ROOT/'protocol.json'),archived_references=rows,source_count=len(rows),original_sources_available=sum(r['original_source_available'] for r in rows),capture_date_counts=dict(sorted(dates.items())),supplied_sources=supplied,quality_approval=False,limitations=['raw hashes newly bind cached SDK count arrays; unavailable original GPRs are not independently redecoded','recorded timestamps/ISO/model are archived metadata, not fresh source extraction','capture dates are not a validated scene or near-duplicate split','GoPro sources are compressed references, not lossless sensor truth','calibration for the supplied GPRs does not establish per-frame calibration for all cached arrays'])
(ROOT/'audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(complete=True,count=len(rows),original_sources_available=report['original_sources_available'],dates=report['capture_date_counts'])),flush=True)
