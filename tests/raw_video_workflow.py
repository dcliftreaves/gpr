#!/usr/bin/env python3
"""Stdlib-only release workflow: calibrated RAW -> GVID -> GPR/DNG; failure/recovery."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import raw_media
import stock_video


def calibration(bits, cfa, width=128, height=96):
    def tag(code, dtype, fmt, values):
        return raw_media.record(code, dtype, len(values)//2 if dtype in (5,10) else len(values),
                                struct.pack('<'+fmt*len(values), *values))
    return dict(schema=raw_media.SCHEMA, width=width, height=height, sample_bits=bits, cfa=cfa,
                image=[raw_media.record(271,2,5,b'Test\0'),
                       raw_media.record(272,2,7,b'Camera\0'),
                       raw_media.record(50708,2,12,b'Test Camera\0'),
                       raw_media.record(50706,1,4,b'\1\4\0\0'),
                       tag(33421,3,'H',(2,2)),
                       raw_media.record(33422,1,4,bytes('RGB'.index(c) for c in cfa)),
                       tag(50713,3,'H',(2,2)), tag(50714,5,'I',(16,1,17,1,18,1,19,1)),
                       tag(50717,4,'I',((1 << bits)-1,)),
                       tag(50728,5,'I',(1,2,1,1,2,3)),
                       tag(50721,10,'i',(1,1,0,1,0,1,0,1,1,1,0,1,0,1,0,1,1,1)),
                       tag(50778,3,'H',(21,))],
                exif=[tag(33434,5,'I',(1,120)),tag(34855,3,'H',(800,))], gps=[])


def run(cmd, okay=True, **kw):
    r = subprocess.run([str(x) for x in cmd], capture_output=True, text=True, timeout=60, **kw)
    if (r.returncode == 0) != okay:
        raise RuntimeError(f'{cmd}: exit {r.returncode}\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}')
    return r


def parse(path, recover=False):
    with path.open('rb') as f:
        h=stock_video.read_header(f); rows=list(stock_video.records(f,h,recover))
    return h,rows


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture',type=Path,required=True)
    p.add_argument('--decoder',type=Path,required=True)
    a=p.parse_args(); a.capture=a.capture.resolve(); a.decoder=a.decoder.resolve()
    env={k:v for k,v in os.environ.items() if not k.startswith('GPR_')}
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp); cases=0
        formats=[(bits,cfa,96) for bits in (12,14,16) for cfa in ('RGGB','GBRG','GRBG','BGGR')]
        formats.append((14,'RGGB',98))
        for bits,cfa,height in formats:
            case=root/f'{cfa}{bits}-{height}';case.mkdir()
            meta=calibration(bits,cfa,height=height); source=case/'source.raw'; sidecar=case/'metadata.json'
            source.write_bytes(struct.pack('<'+'H'*(128*height),
                *((i*79+(i//128)*211)&((1<<bits)-1) for i in range(128*height))))
            sidecar.write_text(json.dumps(meta)); clip=case/'clip.gvid'
            cmd=[a.capture,'--input',source,'--source-metadata',sidecar,'--output',clip,
                 '--width',128,'--height',height,'--sample-bits',bits,'--cfa',cfa,
                 '--frames',3,'--quality',4,'--workspace-mib',4,'--queue',2,
                 '--submit-timeout-ms',4294967295,'--leased']
            r=run(cmd,env=env); summary=json.loads(r.stdout.splitlines()[-1])
            assert summary['complete'] and summary['written']==3 and summary['overruns']==0
            h,rows=parse(clip);assert len(rows)==3 and h['_end_marker_verified']
            out=case/'export'
            export=[sys.executable,ROOT/'tools/stock_video.py','extract',clip,'--out-dir',out,
                    '--decoder',a.decoder,'--editable','both']
            run(export,env=env)
            for i,row in enumerate(rows):
                stem=out/f'{i:06d}'
                for extension in ('.dng','.gpr'):
                    restored=raw_media.extract(stem.with_suffix(extension),bits)
                    for key in ('width','height','sample_bits','cfa'):
                        assert restored[key]==meta[key], (key,restored,meta)
                    for group in ('image','exif','gps'):
                        assert sorted(restored[group],key=lambda t:t['code'])==sorted(meta[group],key=lambda t:t['code']), (group,restored,meta)
                assert stem.with_suffix('.raw').stat().st_size==128*height*2
                assert stem.with_suffix('.vc5').read_bytes()==row['payload']
            before=hashlib.sha256((out/'000000.raw').read_bytes()).hexdigest()
            run(export,okay=False,env=env) # Existing output directory must never be overwritten.
            assert hashlib.sha256((out/'000000.raw').read_bytes()).hexdigest()==before
            run(cmd,okay=False,env=env) # Existing recordings are exclusive, too.
            if cases==0:
                truncated=case/'interrupted.gvid';truncated.write_bytes(clip.read_bytes()[:-48])
                try: parse(truncated)
                except ValueError: pass
                else: raise AssertionError('strict reader accepted interrupted recording')
                rh,rr=parse(truncated,True)
                assert len(rr)==3 and not rh['_end_marker_verified']
                damaged=bytearray(clip.read_bytes());damaged[-49]^=1
                bad=case/'damaged.gvid';bad.write_bytes(damaged)
                rh,rr=parse(bad,True)
                assert len(rr)==2 and not rh['_end_marker_verified']
                if os.name=='posix':
                    import resource,signal
                    def limit_output():
                        signal.signal(signal.SIGXFSZ,signal.SIG_IGN)
                        resource.setrlimit(resource.RLIMIT_FSIZE,(1024,1024))
                    failed=case/'write-failed.gvid';failure_cmd=cmd.copy()
                    failure_cmd[failure_cmd.index(clip)]=failed
                    run(failure_cmd,okay=False,env=env,preexec_fn=limit_output)
                    try: parse(failed)
                    except ValueError: pass
                    else: raise AssertionError('write failure produced complete recording')
            cases+=1
        print(json.dumps(dict(cases=cases, calibrated_exports=True, strict_recovery=True,
                              write_failure=True, exclusive_outputs=True, cnn=False)))

if __name__=='__main__':main()
