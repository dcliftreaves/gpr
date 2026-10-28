#!/usr/bin/env python3
"""Lossless stock GVID/MOV interchange with private GVS2/GVS3 sample profiles.

Each MOV sample contains one original framed record, including its calibration
and absolute nanosecond timestamp. This is distinct from CFHD and fused GPRr/
GPR1. The optional native FFmpeg bridge does not encode or decode image data.
"""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import time

import raw_media
import stock_still
import stock_video


def recording(path):
    count=0;calibrated=0;first=last=None
    with Path(path).open('rb') as file:
        header=stock_video.read_header(file)
        clip=header.get('metadata',{})
        if 'raw_metadata' in clip:raw_media.validate(clip['raw_metadata'],header)
        for row in stock_video.records(file,header):
            meta=row['metadata']
            if 'raw_metadata' in meta:raw_media.validate(meta['raw_metadata'],header)
            if 'raw_metadata' in meta or 'raw_metadata' in clip:calibrated+=1
            if first is None:first=row['pts_ns']
            last=row['pts_ns'];count+=1
        if not count:raise ValueError('MOV interchange requires at least one frame')
    return dict(video={k:header[k] for k in ('width','height','fps_num','fps_den','quality','bayer','sample_bits','version')},
                frames=count,calibrated_frames=calibrated,first_timestamp_ns=first,last_timestamp_ns=last,
                complete=header['_complete'],end_marker_verified=header['_end_marker_verified'])


def run(bridge,action,source,output):
    result=subprocess.run([str(Path(bridge).resolve()),action,str(source),str(output)],capture_output=True,text=True)
    if result.returncode:raise RuntimeError(f'gpr_mov {action} failed: {result.stderr[-8000:]}')
    return json.loads(result.stdout)


def convert(action,source,bridge,output,receipt=None):
    if action not in ('wrap','unwrap'):raise ValueError('action must be wrap or unwrap')
    start=time.perf_counter();source=Path(source).resolve();bridge=Path(bridge).resolve()
    output,receipt,_=stock_still.outputs(output,receipt,None)
    source_sha=stock_still.digest(source)
    source_info=recording(source) if action=='wrap' else None
    with tempfile.TemporaryDirectory(prefix='.stock-mov-',dir=output.parent) as temp:
        root=Path(temp);staged=root/('output.mov' if action=='wrap' else 'output.gvid')
        native=run(bridge,'mux' if action=='wrap' else 'demux',source,staged)
        if action=='wrap':
            # Validate the MOV actually written by this installed FFmpeg, not
            # merely the source stream or the muxer's return status.
            verified=root/'verified.gvid';inverse=run(bridge,'demux',staged,verified)
            if stock_still.digest(verified)!=source_sha or inverse['gvid_sha256']!=source_sha or native['gvid_sha256']!=source_sha:
                raise ValueError('MOV round trip changed original GVID bytes')
            info=source_info;gvid_sha=source_sha;movie_sha=stock_still.digest(staged)
        else:
            info=recording(staged);gvid_sha=stock_still.digest(staged);movie_sha=source_sha
            if gvid_sha!=native['gvid_sha256']:raise ValueError('recovered GVID identity differs')
        if native['frames']!=info['frames']:raise ValueError('MOV frame count differs from verified GVID')
        result=dict(schema='gpr.stock_mov.v1',action=action,profile=native['profile'],reencoded=False,
                    source_sha256=source_sha,output_sha256=stock_still.digest(staged),output_bytes=staged.stat().st_size,
                    gvid_sha256=gvid_sha,movie_sha256=movie_sha,native_binary_sha256=stock_still.digest(bridge),
                    native_libavformat_version=native['libavformat_version'],
                    mov_tick_ns=native['unit_ns'],original_timestamps_preserved_exactly=True,
                    **info,elapsed_before_publication_s=time.perf_counter()-start)
        log=root/'receipt.json';log.write_text(json.dumps(result,indent=2)+'\n')
        stock_still.publish([(staged,output),(log,receipt)])
        return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('wrap','unwrap','inspect'));parser.add_argument('input',type=Path)
    parser.add_argument('--bridge',type=Path,required=True,help='optional native gpr_mov executable')
    parser.add_argument('--output',type=Path);parser.add_argument('--receipt',type=Path)
    args=parser.parse_args()
    if args.action=='inspect':
        if args.output or args.receipt:parser.error('inspect prints its report; no output/receipt paths')
        with tempfile.TemporaryDirectory(prefix='stock-mov-inspect-') as temp:
            data=Path(temp)/'recording.gvid';native=run(args.bridge,'demux',args.input.resolve(),data)
            result=dict(schema='gpr.stock_mov.inspect.v1',native=native,**recording(data),gvid_sha256=stock_still.digest(data))
    else:
        if not args.output:parser.error('--output is required')
        result=convert(args.action,args.input,args.bridge,args.output,args.receipt)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
