"""Calibration and phase checks for an aligned top-left Bayer capture view."""
import copy
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import raw_media as media
import stock_crop


def fixture(width=56,height=54,cfa='RGGB'):
    def ints(code,values):return media.record(code,4,len(values),struct.pack('<'+'I'*len(values),*values))
    return dict(schema=media.SCHEMA,width=width,height=height,sample_bits=16,cfa=cfa,
                image=[media.record(271,2,5,b'Test\0'),media.record(272,2,5,b'Test\0'),
                       media.record(50708,2,5,b'Test\0'),media.record(50706,1,4,b'\1\4\0\0'),
                       media.record(33421,3,2,struct.pack('<2H',2,2)),
                       media.record(33422,1,4,bytes('RGB'.index(v) for v in cfa)),
                       media.record(50713,3,2,struct.pack('<2H',1,1)),ints(50714,[4096]),ints(50717,[65535]),
                       media.record(50721,10,9,struct.pack('<18i',1,1,0,1,0,1,0,1,1,1,0,1,0,1,0,1,1,1)),
                       media.record(50728,5,3,struct.pack('<6I',1,1,1,1,1,1)),
                       media.record(50778,3,1,struct.pack('<H',21)),
                       ints(50829,[0,0,height,width]),ints(50719,[4,4]),ints(50720,[width-8,height-8]),
                       media.record(700,1,4,b'XMP!')],
                exif=[ints(40962,[width]),ints(40963,[height])],gps=[])


class Crop(unittest.TestCase):
    def test_clips_default_crop_and_preserves_phase_and_calibration(self):
        for cfa in ('RGGB','GBRG','GRBG','BGGR'):
            source=fixture(cfa=cfa);original=copy.deepcopy(source)
            cropped,receipt=stock_crop.aligned(source)
            self.assertEqual(source,original)
            self.assertEqual((cropped['width'],cropped['height'],cropped['cfa']),(56,48,cfa))
            tags={t['code']:t for t in cropped['image']}
            self.assertEqual(media.values(tags[50829]),(0,0,48,56))
            self.assertEqual(media.values(tags[50719]),(4,4))
            self.assertEqual(media.values(tags[50720]),(48,44))
            self.assertEqual(receipt['removed_bottom_rows'],6)
            self.assertEqual(receipt['omitted'][0]['code'],700)
            for tag in original['image']:
                if tag['code'] not in (700,50829,50719,50720):self.assertEqual(tag,tags[tag['code']])
            exif={t['code']:t for t in cropped['exif']}
            self.assertEqual(media.values(exif[40963]),(48,))

    def test_x2d_geometry(self):
        cropped,receipt=stock_crop.aligned(fixture(11664,8750))
        self.assertEqual((cropped['width'],cropped['height']),(11664,8744))
        tags={t['code']:t for t in cropped['image']}
        self.assertEqual(media.values(tags[50720]),(11656,8740))
        self.assertEqual(receipt['removed_right_columns'],0)

    def test_identity_and_right_crop(self):
        source=fixture(56,48);cropped,receipt=stock_crop.aligned(source)
        self.assertEqual(source,cropped);self.assertEqual(receipt['omitted'],[])
        cropped,_=stock_crop.aligned(fixture(54,54))
        self.assertEqual((cropped['width'],cropped['height']),(48,48))

    def test_rejects_untransformed_spatial_calibration(self):
        for code in (50715,50716,50830,51125,51008,51009,51022):
            source=fixture();source['image'].append(media.record(code,7,4,b'bad!'))
            with self.subTest(code=code),self.assertRaises(ValueError):stock_crop.aligned(source)
        for multiple in (True,0,3,258):
            with self.subTest(multiple=multiple),self.assertRaises(ValueError):stock_crop.aligned(fixture(),multiple)


if __name__=='__main__':unittest.main()
