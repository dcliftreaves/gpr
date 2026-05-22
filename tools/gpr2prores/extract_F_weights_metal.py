"""extract_F_weights_metal.py — weight extractor for the hybrid Metal backend.

This is a thin wrapper around extract_F_weights.py because the on-disk fp16
binary layout that extract_F_weights.py produces is ALREADY the row-major
[Cout, Cin] / [2C, 9] layout the validated NAFBlock Metal kernels expect.

The MPSGraph-only loader (loadConv4D) re-transposes those buffers to HWIO at
load time. The hybrid loader (loadConv4DBoth / loadDWBoth) keeps BOTH a raw
copy (for the Metal kernels) and an HWIO copy (for MPSGraph segments).

Run identically to extract_F_weights.py:

    python3 extract_F_weights_metal.py --ckpt /path/to/F_aa_off.pt --out /tmp/F_weights_metal
"""
import runpy
import os
import sys

if __name__ == "__main__":
    # Defer to extract_F_weights.py main(). We don't override its default --out
    # so the user gets the same behaviour either way.
    here = os.path.dirname(os.path.abspath(__file__))
    sys.argv[0] = os.path.join(here, "extract_F_weights.py")
    runpy.run_path(sys.argv[0], run_name="__main__")
