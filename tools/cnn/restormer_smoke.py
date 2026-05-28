"""Smoke test: load Restormer real_denoising.pth, run forward on a 512x512 tile.

Targets M5 MPS first; falls back to CPU on unsupported ops. Used to verify
the teacher precompute path before running the full 498-source pass.
"""
import os, sys, time
import numpy as np
import torch

RESTORMER_REPO = os.path.expanduser("~/external/Restormer")
# Load the arch module directly to avoid basicsr's __init__ pulling in lmdb etc.
import importlib.util
_arch_path = os.path.join(RESTORMER_REPO, "basicsr/models/archs/restormer_arch.py")
spec = importlib.util.spec_from_file_location("restormer_arch", _arch_path)
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)
Restormer = _mod.Restormer

CKPT = os.path.expanduser("~/external/Restormer/Denoising/pretrained_models/pretrained_models/real_denoising.pth")

# Pick device: MPS preferred, CPU fallback. For Restormer with transformer
# ops, MPS may hit unsupported kernels; allow fallback automatically.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
if torch.backends.mps.is_available():
    DEVICE = torch.device("mps")
else:
    DEVICE = torch.device("cpu")

print(f"device: {DEVICE}")
print(f"loading Restormer + real_denoising weights...")
t0 = time.time()
model = Restormer(
    inp_channels=3, out_channels=3,
    dim=48, num_blocks=[4, 6, 6, 8], num_refinement_blocks=4,
    heads=[1, 2, 4, 8], ffn_expansion_factor=2.66,
    bias=False, LayerNorm_type="BiasFree",
    dual_pixel_task=False,
)
sd = torch.load(CKPT, map_location="cpu")
# Real-denoising checkpoint key is 'params'
sd_inner = sd.get("params", sd)
model.load_state_dict(sd_inner)
model.eval()
model.to(DEVICE)
print(f"  loaded in {time.time()-t0:.1f}s, {sum(p.numel() for p in model.parameters()):,} params")

# Generate a 512x512 noisy RGB tile and forward
x = torch.rand(1, 3, 512, 512, device=DEVICE)
print(f"running forward on {tuple(x.shape)} on {DEVICE}...")
t0 = time.time()
with torch.no_grad():
    y = model(x)
print(f"  forward in {time.time()-t0:.2f}s  out shape: {tuple(y.shape)}  out range: [{y.min().item():.3f}, {y.max().item():.3f}]")
print("OK")
