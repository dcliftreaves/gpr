#!/usr/bin/env python3
"""Calibrated stock payload wrapping, independent TIFF reading and SDK decode."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import raw_media as media
import stock_video
import numpy as np
import tifffile


def run(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f'{command}: exit {result.returncode}\n{result.stderr}')
    return result


def metadata(width=128, height=96, bits=14, cfa='RGGB'):
    def tag(code, dtype, fmt, data):
        data = tuple(data)
        return media.record(code, dtype, len(data)//2 if dtype in (5, 10) else len(data), struct.pack('<'+fmt*len(data), *data))
    return dict(schema=media.SCHEMA, width=width, height=height, sample_bits=bits, cfa=cfa,
                image=[media.record(271, 2, 5, b'Test\0'), media.record(272, 2, 7, b'Camera\0'),
                       media.record(50708, 2, 12, b'Test Camera\0'), media.record(50706, 1, 4, b'\1\4\0\0'),
                       tag(33421, 3, 'H', (2, 2)), media.record(33422, 1, 4, bytes('RGB'.index(x) for x in cfa)),
                       tag(50713, 3, 'H', (2, 2)), tag(50714, 5, 'I', (16, 1, 17, 1, 18, 1, 19, 1)),
                       tag(50717, 4, 'I', ((1 << bits)-1,)), tag(50728, 5, 'I', (1, 2, 1, 1, 2, 3)),
                       tag(50721, 10, 'i', (1, 1, 0, 1, 0, 1, 0, 1, 1, 1, 0, 1, 0, 1, 0, 1, 1, 1)),
                       tag(50778, 3, 'H', (21,)), media.record(51009, 7, 4, bytes(4))],
                exif=[tag(33434, 5, 'I', (1, 120)), tag(34855, 3, 'H', (800,)), tag(37384, 3, 'H', (14,))],
                gps=[media.record(0, 1, 4, b'\2\3\0\0')])


class Media(unittest.TestCase):
    def test_big_endian_subifd_and_global_calibration(self):
        m = metadata()
        def extra(tag):
            raw, dtype = media.unpack_record(tag), tag['type']
            if dtype in (1, 7): data = raw
            elif dtype == 2: data = raw.rstrip(b'\0').decode('ascii')
            else:
                fmt = {3: 'H', 4: 'I', 5: 'I', 10: 'i'}[dtype]
                data = struct.unpack('<'+fmt*(tag['count']*(2 if dtype in (5, 10) else 1)), raw)
            return (tag['code'], dtype, tag['count'], data, False)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'subifd.dng'
            with tifffile.TiffWriter(path, byteorder='>') as f:
                f.write(np.zeros((4, 4, 3), dtype=np.uint8), photometric='rgb', subifds=1,
                        metadata=None, extratags=[extra(t) for t in m['image'] if t['code'] in media.GLOBAL_TAGS])
                f.write(np.zeros((96, 128), dtype=np.uint16), photometric=32803, metadata=None,
                        extratags=[extra(t) for t in m['image'] if t['code'] not in media.GLOBAL_TAGS])
            result = media.extract(path, 14)
            self.assertEqual((result['width'], result['height'], result['cfa']), (128, 96, 'RGGB'))
            self.assertEqual({t['code']: media.unpack_record(t) for t in result['image']},
                             {t['code']: media.unpack_record(t) for t in m['image']})

    def test_all_bayer_phases_and_bit_domains(self):
        for bits in (12, 14, 16):
            for phase in ('RGGB', 'GBRG', 'GRBG', 'BGGR'):
                with self.subTest(bits=bits, phase=phase), tempfile.TemporaryDirectory() as temp:
                    path = Path(temp) / 'editable.dng'; meta = metadata(bits=bits, cfa=phase)
                    raw = ((np.arange(128*96, dtype=np.uint32).reshape(96, 128)*13) % (1 << bits)).astype('<u2')
                    media.write(path, meta, raw.tobytes())
                    with tifffile.TiffFile(path) as f:
                        page = f.pages[0]
                        self.assertTrue(np.array_equal(page.asarray(), raw))
                        self.assertEqual(page.tags[33422].value, bytes('RGB'.index(x) for x in phase))
                        self.assertEqual(page.tags[50714].value, (16, 1, 17, 1, 18, 1, 19, 1))
                        self.assertEqual(page.tags[34665].value['ExposureTime'], (1, 120))
                    recovered = media.extract(path, bits)
                    for group in ('image', 'exif', 'gps'):
                        self.assertEqual({t['code']: media.unpack_record(t) for t in recovered[group]},
                                         {t['code']: media.unpack_record(t) for t in meta[group]})
                    with self.assertRaises(FileExistsError): media.write(path, meta, raw.tobytes())

    def test_invalid_calibration(self):
        variants = []
        m = metadata(); m['image'] += [m['image'][0]]; variants.append(m)
        m = metadata(); m['image'][6]['data'] += 'AAAA'; variants.append(m)
        m = metadata(); m['cfa'] = 'BGGR'; variants.append(m)
        m = metadata(); m['image'][9] = media.record(50728, 5, 3, struct.pack('<6I', 1, 0, 1, 1, 1, 1)); variants.append(m)
        m = metadata(); m['image'][10] = media.record(50721, 10, 9, struct.pack('<18i', *(0, 1)*9)); variants.append(m)
        m = metadata(); m['image'].append(media.record(50829, 4, 4, struct.pack('<4I', 0, 0, 100, 128))); variants.append(m)
        m = metadata(); m['image'].append(media.record(273, 4, 1, bytes(4))); variants.append(m)
        m = metadata(); m['exif'].append(media.record(37500, 7, 4, bytes(4))); variants.append(m)
        for m in variants:
            with self.subTest(m=m), self.assertRaises((ValueError, TypeError)): media.validate(m)
        with self.assertRaises(ValueError): media.validate(metadata(), dict(width=72, height=96, sample_bits=14, bayer='RGGB'))
        with tempfile.TemporaryDirectory() as temp, self.assertRaises(ValueError):
            media.write(Path(temp)/'bad.dng', metadata(bits=12), np.full((96, 128), 4096, dtype='<u2').tobytes())

    def test_independent_stock_payload_sdk_and_dng(self):
        for width in (128, 72):
            with self.subTest(width=width), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); meta = metadata(width=width)
                source = Path(__file__).parent / f'fixtures/stock_preview/{width}x96-q3.vc5'
                gpr, raw, ref, dng = (root / name for name in ('editable.gpr', 'decoded.raw', 'reference.raw', 'editable.dng'))
                media.write(gpr, meta, source.read_bytes(), 'gpr')
                dumped = run([str(args.sdk), '-i', str(gpr), '-d', '1']).stdout
                params = json.loads(dumped[dumped.index('{'):dumped.rindex('}')+1])
                self.assertEqual(params['exif_info']['light_source'], 14)
                self.assertEqual(params['exif_info']['flash'], 0xFFFFFFFF)
                with tifffile.TiffFile(gpr) as f:
                    page = f.pages[0]; self.assertEqual(page.compression, 9)
                    offset, length = page.dataoffsets[0], page.databytecounts[0]
                    self.assertEqual(gpr.read_bytes()[offset:offset+length], source.read_bytes())
                run([str(args.sdk), '-i', str(gpr), '-o', str(raw)])
                run([str(args.decoder), '--decode', str(source), '--output', str(ref),
                     '--width', str(width), '--height', '96'])
                self.assertEqual(raw.read_bytes(), ref.read_bytes())
                media.write(dng, meta, raw.read_bytes())
                with tifffile.TiffFile(dng) as f:
                    self.assertEqual(f.asarray().astype('<u2').tobytes(), ref.read_bytes())
                roundtrip = root / 'sdk-dng.raw'
                run([str(args.sdk), '-i', str(dng), '-o', str(roundtrip)])
                self.assertEqual(roundtrip.read_bytes(), ref.read_bytes())
                failed = subprocess.run([str(args.sdk), '-i', str(gpr), '-o', str(root/'missing'/'out.raw')], capture_output=True, text=True)
                self.assertNotEqual(failed.returncode, 0)
                self.assertNotIn('Sanitizer', failed.stderr)
                wrong = metadata(width=width+8)
                with self.assertRaises(ValueError): media.write(root/'bad.gpr', wrong, source.read_bytes(), 'gpr')

    def test_capture_metadata_and_editable_sequence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); clip = root/'capture.gvid'
            metas = [metadata(), metadata()]
            metas[1]['image'][9] = media.record(50728, 5, 3, struct.pack('<6I', 3, 4, 1, 1, 1, 2))
            command = [str(args.capture), '--output', str(clip), '--width', '128', '--height', '96',
                       '--quality', '3', '--frames', '4', '--workspace-mib', '16', '--leased', '--submit-timeout-ms', '10000']
            for i, m in enumerate(metas):
                raw, calibration = root/f'{i}.raw', root/f'{i}.json'
                (np.arange(128*96, dtype=np.uint16)+i).astype('<u2').tofile(raw)
                calibration.write_text(json.dumps(m))
                command += ['--input', str(raw), '--source-metadata', str(calibration)]
            subprocess.run(command, check=True, capture_output=True)
            with clip.open('rb') as f:
                h = stock_video.read_header(f); rows = list(stock_video.records(f, h))
            self.assertTrue(h['_end_marker_verified']); self.assertEqual(len(rows), 4)
            for i, row in enumerate(rows): self.assertEqual(row['metadata']['raw_metadata'], metas[i % 2])
            out = root/'editable'
            tool = Path(__file__).resolve().parents[1]/'tools/stock_video.py'
            base = [sys.executable, str(tool), 'extract', str(clip), '--decoder', str(args.decoder), '--editable', 'both']
            exported = subprocess.run(base+['--out-dir', str(out)], capture_output=True, text=True)
            self.assertEqual(exported.returncode, 0, exported.stderr)
            receipt = json.loads((out/'receipt.json').read_text())
            self.assertTrue(receipt['complete']); self.assertTrue(receipt['end_marker_verified'])
            for i, row in enumerate(rows):
                gpr, dng = out/f'{i:06d}.gpr', out/f'{i:06d}.dng'
                with tifffile.TiffFile(gpr) as f:
                    page = f.pages[0]; start, count = page.dataoffsets[0], page.databytecounts[0]
                    self.assertEqual(gpr.read_bytes()[start:start+count], row['payload'])
                    self.assertEqual(page.tags[50728].value, struct.unpack('<6I', media.unpack_record(metas[i % 2]['image'][9])))
                with tifffile.TiffFile(dng) as f:
                    self.assertEqual(f.asarray().astype('<u2').tobytes(), (out/f'{i:06d}.raw').read_bytes())
            bad = subprocess.run(command[:-2]+['--source-metadata', str(root/'0.json'), '--source-metadata', str(root/'1.json')], capture_output=True)
            self.assertNotEqual(bad.returncode, 0)
            metas[1]['width'] += 8
            (root/'1.json').write_text(json.dumps(metas[1]))
            bad_clip = root/'bad-calibration.gvid'
            bad_command = [str(bad_clip) if arg == str(clip) else arg for arg in command]
            run(bad_command)
            failed = subprocess.run([sys.executable, str(tool), 'extract', str(bad_clip), '--limit', '1',
                                     '--out-dir', str(root/'partial'), '--editable', 'gpr'], capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn('recording domains disagree', failed.stderr)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--sdk', type=Path, required=True); p.add_argument('--decoder', type=Path, required=True)
    p.add_argument('--capture', type=Path, required=True)
    args = p.parse_args(); args.sdk = args.sdk.resolve(); args.decoder = args.decoder.resolve(); args.capture = args.capture.resolve()
    unittest.main(argv=[sys.argv[0]])
