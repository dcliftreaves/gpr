#!/usr/bin/env python3
"""Render calibrated stock GVID/private MOV to ProRes on macOS.

Requires the optional gpr_render/gpr_prores tools, stock_video decoder and
ffprobe. Torch and caller-selected weights are needed only for reconstruction.
This offline workflow stages deep TIFFs; scratch storage grows with the clip.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time
from fractions import Fraction

import raw_media
import stock_still
import stock_video


def run(command):
    result = subprocess.run(list(map(str, command)), capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f'{Path(command[0]).name} failed: {result.stderr[-8000:]}')
    return result


def clock(timestamps, fps_num, fps_den):
    if not timestamps or len(timestamps) > 100000:
        raise ValueError('rendering requires 1..100000 frames')
    relative = [t-timestamps[0] for t in timestamps]
    period = max(1, (1_000_000_000*fps_den+fps_num//2)//fps_num)
    end = relative[-1]+period
    if end > (1 << 63)-1:
        raise ValueError('rendered timeline exceeds signed nanosecond range')
    unit = 1
    while max([b-a for a, b in zip(relative, relative[1:])]+[period])//unit+1 > 0xffffffff:
        unit *= 10
    if unit > 1_000_000_000:
        raise ValueError('frame gaps exceed supported MOV clock')
    pts = [(t+unit//2)//unit for t in relative]
    finish = (end+unit//2)//unit
    if any(b <= a for a, b in zip(pts, pts[1:])) or finish <= pts[-1]:
        raise ValueError('MOV clock cannot represent distinct frame timestamps')
    return dict(timescale=1_000_000_000//unit, unit_ns=unit, pts=pts, end_pts=finish,
                maximum_timestamp_error_ns=max(abs(p*unit-t) for p, t in zip(pts, relative)),
                final_nominal_duration_ns=period)


def verify(movie, probe, timing, width, height, profile):
    result = json.loads(run([probe, '-v', 'error', '-select_streams', 'v',
        '-show_entries', 'stream=codec_name,profile,width,height,pix_fmt,time_base,duration_ts,color_range,color_space,color_transfer,color_primaries:packet=pts,dts,duration,flags',
        '-of', 'json', movie]).stdout)
    streams = result.get('streams', [])
    if len(streams) != 1:
        raise ValueError('expected one rendered video track')
    stream = streams[0]
    if (stream.get('codec_name'), stream.get('profile'), stream.get('width'), stream.get('height')) != (
            'prores', 'HQ' if profile == 'hq' else '4444', width, height):
        raise ValueError('rendered codec/profile/dimensions disagree')
    if stream.get('pix_fmt') not in (('yuv422p10le',) if profile == 'hq' else ('yuv444p12le', 'yuva444p12le')):
        raise ValueError('unexpected ProRes component depth')
    if any(stream.get(k) != 'bt709' for k in ('color_space', 'color_transfer', 'color_primaries')) or stream.get('color_range') != 'tv':
        raise ValueError('rendered Rec.709 tags disagree')
    base = Fraction(stream['time_base'])
    if base != Fraction(1, timing['timescale']) or int(stream['duration_ts']) != timing['end_pts']:
        raise ValueError('rendered timeline duration differs')
    packets = result.get('packets', [])
    ends = timing['pts'][1:]+[timing['end_pts']]
    if len(packets) != len(timing['pts']):
        raise ValueError('rendered packet count differs')
    for packet, pts, end in zip(packets, timing['pts'], ends):
        if (int(packet['pts']), int(packet['dts']), int(packet['duration'])) != (pts, pts, end-pts) or 'K' not in packet.get('flags', ''):
            raise ValueError('rendered frame timing/sync flag differs')
    return result


def convert(source, output, decoder, renderer, encoder, probe, receipt=None,
            metadata=None, profile='hq', checkpoint=None, cnn_root=None,
            device='cpu', scale=1, tile=256, halo=64, mov_bridge=None):
    started = time.perf_counter()
    source = Path(source).resolve()
    binaries = {k: Path(v).resolve() for k, v in dict(decoder=decoder, renderer=renderer, encoder=encoder, ffprobe=probe).items()}
    if not source.is_file() or any(not path.is_file() for path in binaries.values()):
        raise ValueError('requires regular source and executable files')
    if profile not in ('hq', '4444') or scale not in (1, 2) or (scale != 1 and not checkpoint):
        raise ValueError('invalid ProRes profile or reconstruction scale')
    if tile < 8 or tile % 8 or halo < 0 or halo % 8:
        raise ValueError('tile/halo must be multiples of eight; tile must be positive')
    if (cnn_root and not checkpoint) or (metadata is not None and not isinstance(metadata, dict)):
        raise ValueError('invalid reconstruction/default calibration')
    output, receipt, _ = stock_still.outputs(output, receipt, None)
    with tempfile.TemporaryDirectory(prefix='.stock-prores-', dir=output.parent) as temporary:
        root = Path(temporary)
        gvid = source
        with source.open('rb') as file:
            is_gvid = file.read(4) == b'GVID'
        if not is_gvid:
            if mov_bridge is None or not Path(mov_bridge).is_file():
                raise ValueError('private MOV input requires --mov-bridge')
            gvid = root/'source.gvid'
            run([Path(mov_bridge).resolve(), 'demux', source, gvid])
            binaries['mov_bridge'] = Path(mov_bridge).resolve()
        rows = []
        with gvid.open('rb') as file:
            header = stock_video.read_header(file)
            if (header['bayer'], header['sample_bits']) != ('RGGB', 14):
                raise ValueError('stock video decoder currently requires RGGB14')
            for record in stock_video.records(file, header):
                calibration = record['metadata'].get('raw_metadata', header.get('metadata', {}).get('raw_metadata', metadata))
                raw_media.validate(calibration, header)
                rows.append(dict(index=record['index'], pts_ns=record['pts_ns'],
                    payload_sha256=hashlib.sha256(record['payload']).hexdigest(),
                    calibration_sha256=hashlib.sha256(stock_still.canonical(calibration)).hexdigest()))
                if len(rows) > 100000:
                    raise ValueError('rendering frame limit exceeded')
        # Validate the complete container/calibration before model loading or rendering.
        timing = clock([row['pts_ns'] for row in rows], header['fps_num'], header['fps_den'])
        source_sha = stock_still.digest(source)
        gvid_sha = stock_still.digest(gvid)
        model = model_info = None
        if checkpoint:
            import torch
            device = torch.device(device)
            model, model_info = stock_video.load_cnn(cnn_root, checkpoint, device)
            if model_info.get('output_scale', 1) != scale:
                raise ValueError('checkpoint output scale differs from requested scale')
        manifest = dict(schema='gpr.prores_frames.v1', profile=profile, timescale=timing['timescale'],
                        end_pts=timing['end_pts'], frames=[])
        dimensions = None
        with gvid.open('rb') as file:
            current = stock_video.read_header(file)
            for record, row, pts in zip(stock_video.records(file, current), rows, timing['pts']):
                calibration = record['metadata'].get('raw_metadata', current.get('metadata', {}).get('raw_metadata', metadata))
                raw_media.validate(calibration, current)
                if (record['index'] != row['index'] or record['pts_ns'] != row['pts_ns'] or
                    hashlib.sha256(record['payload']).hexdigest() != row['payload_sha256'] or
                    hashlib.sha256(stock_still.canonical(calibration)).hexdigest() != row['calibration_sha256']):
                    raise ValueError('recording changed during rendering')
                vc5, raw, dng = (root/name for name in ('frame.vc5', 'frame.raw', 'frame.dng'))
                vc5.write_bytes(record['payload'])
                run([binaries['decoder'], '--decode', vc5, '--output', raw, '--width', header['width'], '--height', header['height']])
                payload = raw.read_bytes()
                if len(payload) != header['width']*header['height']*2:
                    raise ValueError('decoded RAW extent differs')
                row['raw_sha256'] = hashlib.sha256(payload).hexdigest()
                if model is not None:
                    from stock_cnn_metadata import scaled
                    restored, elapsed = stock_video.restore(raw, header['width'], header['height'], model, device, tile, halo, scale)
                    calibration, geometry = scaled(calibration, scale)
                    payload = restored.astype('<u2').tobytes()
                    row.update(cnn_s=elapsed, geometry=geometry)
                row['rendered_raw_sha256'] = hashlib.sha256(payload).hexdigest()
                row['render_calibration_sha256'] = hashlib.sha256(stock_still.canonical(calibration)).hexdigest()
                raw_media.write(dng, calibration, payload)
                row['dng_sha256'] = stock_still.digest(dng)
                tiff = root/f'{row["index"]:06}.tiff'
                rendered = json.loads(run([binaries['renderer'], dng, tiff]).stdout)
                if rendered.get('schema') != 'gpr.raw_render.v1' or rendered.get('bits_per_component') != 16 or rendered.get('color_space') != 'ITU-R BT.709':
                    raise ValueError('unexpected renderer output contract')
                size = (rendered['width'], rendered['height'])
                if dimensions is not None and size != dimensions:
                    raise ValueError('rendered crop/orientation changes output dimensions; split the clip')
                dimensions = size
                row.update(render=rendered, tiff_sha256=stock_still.digest(tiff), mov_pts=pts)
                manifest['frames'].append(dict(path=str(tiff), pts=pts))
                for path in (vc5, raw, dng):
                    path.unlink()
        if stock_still.digest(source) != source_sha or stock_still.digest(gvid) != gvid_sha:
            raise ValueError('source changed during rendering')
        control = root/'frames.json'
        control.write_text(json.dumps(manifest))
        movie = root/'output.mov'
        native = json.loads(run([binaries['encoder'], control, movie]).stdout)
        verified = verify(movie, binaries['ffprobe'], timing, *dimensions, profile)
        result = dict(schema='gpr.stock_prores.v1', source_sha256=source_sha, gvid_sha256=gvid_sha,
            output_sha256=stock_still.digest(movie), output_bytes=movie.stat().st_size,
            reencoded=True, profile=profile, color_space='ITU-R BT.709', sdr=True,
            intermediate_bits=16, frames=rows, frame_count=len(rows), cnn=model_info,
            cnn_settings=dict(tile=tile, halo=halo, device=str(device), scale=scale) if model is not None else None,
            reconstruction_scale=scale, timing=timing, verification=verified, native=native,
            complete=header['_complete'], end_marker_verified=header['_end_marker_verified'],
            binary_sha256={k: stock_still.digest(v) for k, v in binaries.items()},
            ffprobe_version=run([binaries['ffprobe'], '-version']).stdout.splitlines()[0],
            elapsed_before_publication_s=time.perf_counter()-started)
        log = root/'receipt.json'
        log.write_text(json.dumps(result, indent=2)+'\n')
        stock_still.publish([(movie, output), (log, receipt)])
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    for flag in ('output', 'decoder', 'renderer', 'encoder', 'ffprobe'):
        parser.add_argument('--'+flag, type=Path, required=True)
    for flag in ('receipt', 'metadata-file', 'checkpoint', 'cnn-root', 'mov-bridge'):
        parser.add_argument('--'+flag, type=Path)
    parser.add_argument('--profile', choices=('hq', '4444'), default='hq')
    parser.add_argument('--device', choices=('cpu', 'mps', 'cuda'), default='cpu')
    parser.add_argument('--scale', type=int, choices=(1, 2), default=1)
    parser.add_argument('--tile', type=int, default=256)
    parser.add_argument('--halo', type=int, default=64)
    args = parser.parse_args()
    options = vars(args).copy()
    source = options.pop('input')
    options['probe'] = options.pop('ffprobe')
    path = options.pop('metadata_file')
    options['metadata'] = stock_video.decode_metadata(path.read_bytes()) if path else None
    print(json.dumps(convert(source, **options), indent=2))


if __name__ == '__main__':
    main()
