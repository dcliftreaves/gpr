"""Benchmark Restormer on M5: batch sizes 1/2/4 and 256/512 tile sizes, on MPS + CPU."""
import os, sys, time, importlib.util
import torch

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
RR = os.path.expanduser("~/external/Restormer")
spec = importlib.util.spec_from_file_location(
    "restormer_arch", os.path.join(RR, "basicsr/models/archs/restormer_arch.py"))
_m = importlib.util.module_from_spec(spec); spec.loader.exec_module(_m); Restormer = _m.Restormer
CKPT = os.path.expanduser("~/external/Restormer/Denoising/pretrained_models/pretrained_models/real_denoising.pth")

def load_model(device):
    m = Restormer(LayerNorm_type="BiasFree")
    sd = torch.load(CKPT, map_location="cpu")
    m.load_state_dict(sd.get("params", sd))
    m.eval()
    return m.to(device)

for dev_name in ["mps", "cpu"]:
    if dev_name == "mps" and not torch.backends.mps.is_available(): continue
    dev = torch.device(dev_name)
    print(f"\n=== {dev_name} ===")
    m = load_model(dev)
    for size in [256, 512]:
        for bs in [1, 2, 4]:
            try:
                x = torch.rand(bs, 3, size, size, device=dev)
                # Warmup
                with torch.no_grad():
                    _ = m(x)
                if dev_name == "mps": torch.mps.synchronize()
                t0 = time.time()
                with torch.no_grad():
                    y = m(x)
                if dev_name == "mps": torch.mps.synchronize()
                dt = time.time() - t0
                per_tile = dt / bs
                print(f"  size={size} bs={bs}: {dt:.2f}s total → {per_tile:.3f}s/tile")
            except Exception as e:
                print(f"  size={size} bs={bs}: FAILED {type(e).__name__}: {e}")
                break
    del m
