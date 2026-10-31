"""Display-only thumbnails and conservative similarity hints; no scene split inferred."""
from pathlib import Path
import json,hashlib
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path('/Volumes/OWC_8TB/gpr_work/artifacts/stock_sr_mission_sources_20261030')
audit=json.loads((ROOT/'audit.json').read_text());rows=audit['archived_references'];thumbs=[];hashes=[]
for r in rows:
 x=np.memmap(r['raw_path'],dtype='<u2',mode='r',shape=(6144,8192))
 gray=(x[0::32,0::32].astype(np.float32)+x[1::32,0::32]+x[0::32,1::32]+x[1::32,1::32])*.25
 low=16.;high=max(low+1.,float(np.percentile(gray,99)));gray=np.sqrt(np.clip((gray-low)/(high-low),0,1));im=Image.fromarray(np.asarray(gray*255,dtype=np.uint8))
 thumb=im.resize((256,192));thumbs.append(thumb)
 small=np.asarray(im.resize((9,8),Image.Resampling.BILINEAR));bits=small[:,1:]>small[:,:-1];h=sum(int(v)<<i for i,v in enumerate(bits.flat));hashes.append(h)
canvas=Image.new('RGB',(7*272,6*232),'white');draw=ImageDraw.Draw(canvas)
for i,(r,im) in enumerate(zip(rows,thumbs)):
 x=(i%7)*272;y=(i//7)*232;canvas.paste(im,(x+8,y+4));draw.text((x+8,y+198),r['stem']+' '+str(r['recorded_datetime']),fill='black')
canvas.save(ROOT/'scene-contact.png')
pairs=[]
for i in range(len(rows)):
 for j in range(i):
  distance=bin(hashes[i]^hashes[j]).count('1')
  if distance<=10:pairs.append(dict(a=rows[j]['stem'],b=rows[i]['stem'],hamming=distance))
report=dict(schema='gpr.stock_sr_mission_similarity_hints.v1',complete=True,driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),audit_sha256=hashlib.sha256((ROOT/'audit.json').read_bytes()).hexdigest(),hashes=[dict(stem=r['stem'],dhash=f'{h:016x}') for r,h in zip(rows,hashes)],pairs=pairs,threshold=10,scene_split_validated=False,limitations=['display uses sampled four-site mean and per-image contrast; no calibrated color claim','dHash similarity hints are not a near-duplicate exclusion proof','manual content grouping and capture metadata needed before splitting'])
(ROOT/'similarity-hints.json').write_text(json.dumps(report,indent=2)+'\n');print('Hints',len(pairs),'pairs; contact sheet created.')
