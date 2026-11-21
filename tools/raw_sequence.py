#!/usr/bin/env python3
"""Turn ordered Bayer DNG/GPR stills into a calibrated non-CNN GVID movie.

This is offline encoding. Playback timestamps are synthesized from --fps-num/
--fps-den, not measured camera capture times. Source files are never modified.
"""
import argparse
import json
from pathlib import Path

import raw_media
import stock_sequence
import stock_still
import stock_video


def convert(inputs, output, sdk, bits=14, quality=3, fps_num=24, fps_den=1):
    inputs=[Path(p).resolve() for p in inputs]
    if not inputs:raise ValueError('at least one input is required')
    if any(p.suffix.lower() not in ('.dng','.gpr') for p in inputs):
        raise ValueError('convert camera-native containers to Bayer DNG first')
    # Reject incompatible sequences before writing any outputs.
    geometry=None
    for source in inputs:
        meta=raw_media.extract(source,bits)
        this=tuple(meta[k] for k in ('width','height','sample_bits','cfa'))
        if geometry is not None and this!=geometry:raise ValueError('sequence geometry/domain differs')
        geometry=this
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    frames=output/'frames';frames.mkdir();encoded=[]
    for i,source in enumerate(inputs):
        path=frames/f'{i:06d}.gpr'
        stock_still.encode(source,raw_media.extract(source,bits),quality,sdk,path,source_type='dng')
        encoded.append(path)
        print(json.dumps(dict(event='encoded',index=i,source=source.name)),flush=True)
    clip=output/'sequence.gvid'
    result=stock_sequence.pack(encoded,clip,quality,bits,fps_num,fps_den)
    with clip.open('rb') as f:
        header=stock_video.read_header(f);count=sum(1 for _ in stock_video.records(f,header))
        if count!=len(inputs) or not header['_end_marker_verified']:raise ValueError('sequence verification failed')
    result.update(verified_frames=count,cnn=False,timestamp_source='synthetic_playback_rate')
    (output/'workflow.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('inputs',type=Path,nargs='+',help='explicit playback order (shell globs sort by filename)')
    p.add_argument('--output',type=Path,required=True,help='new directory')
    p.add_argument('--sdk',type=Path,required=True,help='gpr_tools executable')
    p.add_argument('--sample-bits',type=int,choices=(12,14,16),default=14)
    p.add_argument('--quality',type=int,choices=range(6),default=3)
    p.add_argument('--fps-num',type=int,default=24);p.add_argument('--fps-den',type=int,default=1)
    a=p.parse_args()
    if not 0<a.fps_num<=240000 or not 0<a.fps_den<=10000:p.error('invalid playback rate')
    result=convert(a.inputs,a.output,a.sdk,a.sample_bits,a.quality,a.fps_num,a.fps_den)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
