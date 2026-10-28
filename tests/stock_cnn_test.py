#!/usr/bin/env python3
"""Optional Torch contract/integration tests; no trained weights are needed."""
import argparse
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import tifffile
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import raw_media
import stock_still
import stock_video
from raw_media_test import metadata


class Contract(unittest.TestCase):
    def test_context_halos_match_whole_image(self):
        # A known spatial filter tests seams, four distinct planes and the
        # non-multiple-of-eight image edges against one whole-image inference.
        with tempfile.TemporaryDirectory() as temp:
            h,w=98,130
            y,x=np.indices((h,w),dtype=np.uint32)
            image=((y*131+x*67+x*y*31)&16383).astype('<u2')
            raw=Path(temp)/'source.raw'; image.tofile(raw)
            model=torch.nn.Conv2d(4,4,3,padding=1,groups=4,bias=False)
            with torch.no_grad():
                model.weight[:]=torch.tensor([[0,.125,0],[.125,.5,.125],[0,.125,0]])
            tiled,_=stock_video.restore(raw,w,h,model,torch.device('cpu'),16,8)
            planes=np.stack([image[0::2,0::2],image[0::2,1::2],image[1::2,0::2],image[1::2,1::2]])
            tensor=torch.from_numpy(planes.astype(np.float32)/16383)[None]
            tensor=torch.nn.functional.pad(tensor,(0,7,0,7),mode='replicate')
            with torch.inference_mode(): whole=model(tensor)[0,:,:h//2,:w//2].numpy()
            expected=np.clip(whole*16383+.5,0,16383).astype('<u2')
            for site in range(4):
                np.testing.assert_array_equal(tiled[site//2::2,site%2::2],expected[site])

    def test_nonfinite_and_wrong_shape_outputs_rejected(self):
        class Bad(torch.nn.Module):
            def __init__(self,kind): super().__init__(); self.kind=kind
            def forward(self,x):
                if self.kind=='nan': return x*float('nan')
                if self.kind=='rgb': return x[:,:3]
                return x.repeat_interleave(2,-1)
        with tempfile.TemporaryDirectory() as temp:
            raw=Path(temp)/'input.raw'; np.zeros((48,48),dtype='<u2').tofile(raw)
            for kind in ('nan','rgb','2x'):
                with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,'finite same-size'):
                    stock_video.restore(raw,48,48,Bad(kind),torch.device('cpu'),16,8)

    def test_still_restoration_preserves_calibration_and_decoded_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); meta=metadata()
            # Nonstandard white and fractional black exercise the private
            # full-domain decoding carrier; published calibration stays exact.
            import struct
            meta['image']=[t for t in meta['image'] if t['code'] not in (50714,50717)]
            meta['image'] += [raw_media.record(50717,4,1,struct.pack('<I',15000)),
                              raw_media.record(50714,5,4,struct.pack('<8I',33,2,35,2,37,2,39,2))]
            raw=root/'source.raw'
            (np.arange(128*96,dtype=np.uint16)%15000).astype('<u2').tofile(raw)
            gpr=root/'source.gpr'; stock_still.encode(raw,meta,3,args.sdk,gpr)
            plain=root/'plain.dng'; baseline=stock_still.decode(gpr,14,args.sdk,plain)
            settings=dict(root=root,checkpoint=root/'unused.pt',device='cpu',tile=16,halo=8)
            info=dict(checkpoint_sha256='test-identity',quality_status='unvalidated_for_stock_video')
            with patch.object(stock_video,'load_cnn',return_value=(torch.nn.Identity(),info)):
                output=root/'restored.dng'
                receipt=stock_still.decode(gpr,14,args.sdk,output,reconstruction=settings)
                self.assertTrue(receipt['cnn']); self.assertEqual(receipt['action'],'restore')
                self.assertFalse(receipt['quality_approval'])
                self.assertEqual(receipt['raw_sha256'],baseline['raw_sha256'])
                self.assertEqual(receipt['restored_raw_sha256'],baseline['raw_sha256'])
                with tifffile.TiffFile(plain) as a,tifffile.TiffFile(output) as b:
                    np.testing.assert_array_equal(a.asarray(),b.asarray())
                self.assertEqual(stock_still.canonical(raw_media.extract(output,14)),stock_still.canonical(meta))
                before=output.read_bytes()
                with self.assertRaises(FileExistsError): stock_still.decode(gpr,14,args.sdk,output,reconstruction=settings)
                self.assertEqual(output.read_bytes(),before)
                with self.assertRaisesRegex(ValueError,'tile/halo'):
                    stock_still.decode(gpr,14,args.sdk,root/'bad.dng',reconstruction=dict(settings,tile=0))
                self.assertFalse((root/'bad.dng').exists())


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk',type=Path,required=True)
    args=parser.parse_args(); args.sdk=args.sdk.resolve()
    torch.set_num_threads(1)
    unittest.main(argv=[sys.argv[0]])
