#!/usr/bin/env python3
"""Offline RGGB14 signal-compression experiment with self-contained GPR metadata.

No private image paths, original pixels or noise residuals are required by
`decode`. Neural reconstruction additionally requires the hash-bound checkpoint.
"""

import argparse
import base64
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time

import numpy as np
import raw_media as media
import stock_cnn_metadata as geometry
import signal_only_raw_sr_pipeline as signal
from optical_psf_deconvolution import estimate_empirical_sensor_noise_profile

PEAK = 16383
TAG = 65000
MAGIC = b"gpr.signal_raw.v1\0"
HERE = Path(__file__).resolve().parent
DEFAULT_CHECKPOINT = HERE.parent / "models/mission1-large-area-wavelet-sr/selected.pt"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    with Path(path).open("x") as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write("\n")


def pack(raw):
    return np.stack([raw[y::2, x::2] for y, x in ((0, 0), (0, 1), (1, 0), (1, 1))])


def unpack(planes):
    out = np.empty((planes.shape[1] * 2, planes.shape[2] * 2), dtype=planes.dtype)
    for c, (y, x) in enumerate(((0, 0), (0, 1), (1, 0), (1, 1))):
        out[y::2, x::2] = planes[c]
    return out


def environment(quality=3):
    # Experimental flags must never leak from the invoking shell into controls.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GPR_")}
    env.update(
        GPR_BENCH_RUNS="1",
        GPR_BENCH_QUALITY=str(quality),
        GPR_STREAM_UNPACK="1",
        GPR_BAND_STREAM="1",
        GPR_COMPACT_BANDS="1",
        GPR_DIRECT_BANDS="1",
    )
    return env


def native(command, log, quality=3):
    start = time.perf_counter()
    with Path(log).open("w") as f:
        result = subprocess.run(
            list(map(str, command)),
            stdout=f,
            stderr=subprocess.STDOUT,
            env=environment(quality),
        )
    if result.returncode:
        raise RuntimeError(
            f"native codec failed ({result.returncode}): "
            + Path(log).read_text()[-4000:]
        )
    return time.perf_counter() - start


def check_meta(meta):
    media.validate(meta)
    if (
        meta["sample_bits"] != 14
        or meta["cfa"] != "RGGB"
        or meta["width"] % 8
        or meta["height"] % 8
    ):
        raise ValueError(
            "this checkpoint experiment requires aligned RGGB14; other sensor domains are unsupported"
        )


def read_source(path, decoder, temp):
    path = Path(path)
    meta = media.extract(path, 14)
    check_meta(meta)
    # GPR payload extraction is independent of a filename extension.
    try:
        _, payload = media.extract(path, 14, with_payload=True)
    except ValueError:
        import tifffile

        with tifffile.TiffFile(path) as f:

            def pages(page):
                yield page
                if page.pages:
                    for child in page.pages:
                        yield from pages(child)

            candidates = [
                p
                for top in f.pages
                for p in pages(top)
                if int(p.photometric) == 32803
                and p.shape == (meta["height"], meta["width"])
            ]
            if len(candidates) != 1:
                raise ValueError(
                    "requires one uncompressed calibrated Bayer DNG or stock GPR"
                )
            raw = candidates[0].asarray().astype("<u2")
        kind = "source_dng_samples_provenance_not_verified"
    else:
        vc5, decoded = temp / "input.vc5", temp / "input.raw"
        vc5.write_bytes(payload)
        native(
            [decoder, "-i", vc5, "-o", decoded, "-x", "rggb14"],
            temp / "source-decode.log",
        )
        if decoded.stat().st_size != meta["width"] * meta["height"] * 2:
            raise ValueError("source decode size differs")
        raw = np.fromfile(decoded, dtype="<u2").reshape(meta["height"], meta["width"])
        kind = "decoded_source_gpr_not_clean_ground_truth"
    if raw.shape != (meta["height"], meta["width"]) or np.any(raw > PEAK):
        raise ValueError("source count domain/geometry differs")
    return meta, raw, kind


def freeze_profile(profile):
    x = np.asarray(profile["lut_intensity_counts"], dtype=np.float64)
    y = np.asarray(profile["lut_sigma_counts"], dtype=np.float64)
    if (
        not len(x)
        or x.shape != y.shape
        or not np.isfinite(x).all()
        or not np.isfinite(y).all()
        or np.any(y < 0)
        or np.any(np.diff(x) <= 0)
    ):
        raise ValueError("invalid estimated LUT")
    sigma = np.interp(np.linspace(0, PEAK, 32), x, y).astype("<f2")
    if not np.isfinite(sigma).all():
        raise ValueError("noise sigma exceeds float16 range")
    return dict(
        encoding="32_float16_le_sigma_ADC_counts_uniform_0_16383",
        sigma_b64=base64.b64encode(sigma.tobytes()).decode(),
        sigma_bytes=64,
        estimate_kind=profile["estimate_kind"],
        flat_bin_fallback=profile["flat_bin_fallback"],
        grain_model="independent_site_gaussian_v1",
    )


def thaw_profile(profile):
    if (
        profile.get("encoding") != "32_float16_le_sigma_ADC_counts_uniform_0_16383"
        or profile.get("grain_model") != "independent_site_gaussian_v1"
    ):
        raise ValueError("unsupported noise model")
    payload = base64.b64decode(profile["sigma_b64"], validate=True)
    if len(payload) != 64:
        raise ValueError("noise LUT length differs")
    sigma = np.frombuffer(payload, dtype="<f2").astype(np.float32)
    if not np.isfinite(sigma).all() or np.any(sigma < 0):
        raise ValueError("invalid noise sigma")
    return dict(
        lut_intensity_counts=np.linspace(0, PEAK, 32).tolist(),
        lut_sigma_counts=sigma.tolist(),
    )


def attach(meta, contract):
    if any(t["code"] == TAG for t in meta["image"]):
        raise ValueError("input already contains the experimental signal tag")
    data = (
        MAGIC
        + json.dumps(
            contract, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    )
    result = copy.deepcopy(meta)
    result["image"].append(media.record(TAG, 7, len(data), data))
    media.validate(result)
    return result, len(data)


def contract_from(meta):
    tags = [t for t in meta["image"] if t["code"] == TAG]
    if len(tags) != 1 or tags[0]["type"] != 7:
        raise ValueError("missing experimental signal contract")
    data = media.unpack_record(tags[0])
    if not data.startswith(MAGIC):
        raise ValueError("unrecognized private tag owner")
    c = json.loads(data[len(MAGIC) :])
    if (
        c.get("schema") != "gpr.signal_raw.v1"
        or c.get("sample_peak") != PEAK
        or c.get("mode") not in ("stock", "denoised", "simulated_sr")
    ):
        raise ValueError("unsupported signal contract")
    thaw_profile(c["noise"])
    return c


def denoise(planes, profile, strength):
    if not math.isfinite(strength) or not 0 <= strength <= 4:
        raise ValueError("strength must be finite in 0..4")
    if strength == 0:
        return planes.copy()
    source = planes.astype(np.float32)
    out = np.empty_like(planes)
    for c in range(4):
        ch = source[c]
        sigma = np.interp(
            ch, profile["lut_intensity_counts"], profile["lut_sigma_counts"]
        ).astype(np.float32)
        threshold = np.maximum(2 * strength * sigma, 1e-6)
        padded = np.pad(ch, 1, mode="reflect")
        total = ch.copy()
        weight = np.ones_like(ch)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == dx == 0:
                    continue
                neighbor = padded[
                    1 + dy : 1 + dy + ch.shape[0], 1 + dx : 1 + dx + ch.shape[1]
                ]
                w = np.exp(-0.5 * ((neighbor - ch) / threshold) ** 2)
                total += w * neighbor
                weight += w
        out[c] = np.clip(np.rint(total / weight), 0, PEAK).astype(np.uint16)
    return out


def encode(source, output, encoder, decoder, mode, quality, strength, checkpoint, seed):
    if output.exists():
        raise FileExistsError(output)
    if (
        mode not in ("stock", "denoised", "simulated_sr")
        or quality not in range(6)
        or not math.isfinite(strength)
        or not 0 <= strength <= 4
        or not 0 <= seed < 2**64
    ):
        raise ValueError("invalid encoding mode/quality/strength/seed")
    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        meta, raw, kind = read_source(source, decoder, temp)
        if any(t["code"] == TAG for t in meta["image"]):
            raise ValueError(
                "encode requires a camera/reference input, not a prior experiment"
            )
        started = time.perf_counter()
        black = next(t for t in meta["image"] if t["code"] == 50714)
        estimate = estimate_empirical_sensor_noise_profile(
            raw, black_level=float(np.mean(media.values(black)))
        )
        frozen = freeze_profile(estimate)
        profile = thaw_profile(frozen)
        full = copy.deepcopy(meta)
        omitted = []
        planes = pack(raw)
        denoise_noise = None
        if mode == "simulated_sr":
            meta, omitted = geometry.simulated_half(meta)
            if meta["width"] % 8 or meta["height"] % 8:
                raise ValueError(
                    "SR simulation requires full dimensions divisible by 16"
                )
            planes = np.rint(
                signal.box_2x2_downsample_4ch(planes.astype(np.float32))
            ).astype(np.uint16)
            # Estimate in the actual pre-encode domain. Reusing the full-frame
            # sigma would over-filter an averaged input and assumes unknown covariance.
            denoise_noise = freeze_profile(
                estimate_empirical_sensor_noise_profile(
                    unpack(planes), black_level=float(np.mean(media.values(black)))
                )
            )
            profile = thaw_profile(denoise_noise)
        if mode != "stock":
            planes = denoise(planes, profile, strength)
        working = unpack(planes)
        preparation = time.perf_counter() - started
        model = None
        if mode == "simulated_sr":
            model = dict(
                architecture="Mission1LargeAreaWaveletSR_80x4_bounded_v1",
                checkpoint_sha256=digest(checkpoint),
                quality_status="unvalidated_exploratory_frozen_weights",
            )
        contract = dict(
            schema="gpr.signal_raw.v1",
            mode=mode,
            sample_peak=PEAK,
            noise=frozen,
            denoise_noise=denoise_noise,
            grain_seed=seed,
            model=model,
            source_kind=kind,
            source_sha256=digest(source),
            degradation="synthetic_linear_same_color_box2_before_VC5"
            if mode == "simulated_sr"
            else "none",
            does_not_claim_physical_binning_or_VC5_LL1_equivalence=True,
            full_metadata=full if mode == "simulated_sr" else None,
            denoise_strength=strength if mode != "stock" else 0,
            metadata_omissions=omitted,
            original_noise_recoverable=False,
        )
        input_raw, vc5 = temp / "encode.raw", temp / "encode.vc5"
        working.astype("<u2").tofile(input_raw)
        wall = native(
            [
                encoder,
                "-i",
                input_raw,
                "-w",
                meta["width"],
                "-h",
                meta["height"],
                "-p",
                meta["width"] * 2,
                "-x",
                "rggb14",
                "-o",
                vc5,
            ],
            temp / "encode.log",
            quality,
        )
        contract["encoded_payload_sha256"] = digest(vc5)
        meta, contract_bytes = attach(meta, contract)
        # Stage in destination filesystem and publish exclusively.
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output.parent) as stage:
            staged = Path(stage) / "image.gpr"
            media.write(staged, meta, vc5.read_bytes(), "gpr")
            check_meta(media.extract(staged, 14))
            contract_from(media.extract(staged, 14))
            os.link(staged, output)
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        child_rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        return dict(
            peak_process_rss_bytes=rss if sys.platform == "darwin" else rss * 1024,
            peak_native_child_rss_bytes=child_rss
            if sys.platform == "darwin"
            else child_rss * 1024,
            mode=mode,
            quality=quality,
            gpr_bytes=output.stat().st_size,
            vc5_bytes=vc5.stat().st_size,
            private_contract_bytes=contract_bytes,
            noise_sigma_bytes=64 + (64 if denoise_noise is not None else 0),
            preparation_seconds=preparation,
            encode_process_seconds=wall,
            gpr_sha256=digest(output),
            source_kind=kind,
            complete=True,
        )


def decode(
    source,
    output,
    decoder,
    checkpoint,
    device,
    tile,
    halo,
    grain_strength,
    frame_index,
    analytical=True,
):
    if output.exists():
        raise FileExistsError(output)
    if (
        not math.isfinite(grain_strength)
        or not 0 <= grain_strength <= 4
        or not 0 <= frame_index < 2**64
    ):
        raise ValueError("invalid grain strength/frame index")
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as td:
        source_meta, payload = media.extract(source, 14, with_payload=True)
        c = contract_from(source_meta)
        if hashlib.sha256(payload).hexdigest() != c.get("encoded_payload_sha256"):
            raise ValueError("encoded payload digest differs")
        if c["mode"] == "simulated_sr":
            full = c["full_metadata"]
            check_meta(full)
            if (full["width"], full["height"]) != (
                source_meta["width"] * 2,
                source_meta["height"] * 2,
            ):
                raise ValueError("SR output geometry differs from encoded contract")
        del payload
        meta, raw, kind = read_source(source, decoder, Path(td))
        planes = pack(raw)
        if c.get("materialized_output"):
            raise ValueError(
                "decode expects an encoded GPR, not a materialized restoration"
            )
        conserved = None
        model_seconds = 0.0
        checkpoint_sha = None
        telemetry = {}
        if c["mode"] == "simulated_sr":
            t = time.perf_counter()
            if analytical:
                import torch
                import torch.nn.functional as F

                low = torch.from_numpy(planes.astype(np.float32) / PEAK)[None]
                high = F.interpolate(
                    low, scale_factor=2, mode="bicubic", align_corners=False
                )[0].numpy()
                restored = signal.quantize_cell_consistent_4ch(high, planes)
            else:
                import torch

                expected = c["model"]
                if (
                    expected["architecture"]
                    != "Mission1LargeAreaWaveletSR_80x4_bounded_v1"
                    or digest(checkpoint) != expected["checkpoint_sha256"]
                ):
                    raise ValueError("checkpoint binding differs")
                torch.set_num_threads(4)
                cp = torch.load(checkpoint, map_location="cpu", weights_only=True)
                if (cp.get("width"), cp.get("depth")) != (80, 4):
                    raise ValueError("unsupported model dimensions")
                model = signal.build_large_area_wavelet_sr_model()
                model.load_state_dict(cp["model_state"], strict=True)
                restored = signal.restore_tiled(
                    planes,
                    model,
                    tile=tile,
                    halo=halo,
                    device=device,
                    telemetry=telemetry,
                )
                checkpoint_sha = expected["checkpoint_sha256"]
            model_seconds = time.perf_counter() - t
            sums = sum(
                restored[:, y::2, x::2].astype(np.int32)
                for y in range(2)
                for x in range(2)
            )
            conserved = int(np.max(np.abs(sums - 4 * planes.astype(np.int32))))
            if conserved:
                raise ValueError("integer cell sums differ")
            planes = restored
            meta = c["full_metadata"]
            check_meta(meta)
        if grain_strength:
            result, _ = signal.synthesize_empirical_sensor_grain_4ch(
                planes.astype(np.float32) / PEAK,
                thaw_profile(c["noise"]),
                grain_strength,
                c["grain_seed"],
                frame_index,
            )
            planes = np.clip(np.rint(result * PEAK), 0, PEAK).astype(np.uint16)
        raw = unpack(planes)
        if c["mode"] != "simulated_sr":
            meta = copy.deepcopy(meta)
            meta["image"] = [t for t in meta["image"] if t["code"] != TAG]
        view = dict(
            c,
            materialized_output=True,
            grain_strength=grain_strength,
            grain_frame_index=frame_index,
            reconstruction="native_codec"
            if c["mode"] != "simulated_sr"
            else "analytical_bounded"
            if analytical
            else "frozen_neural",
        )
        meta, _ = attach(meta, view)
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output.parent) as stage:
            staged = Path(stage) / "output.dng"
            media.write(staged, meta, raw.astype("<u2").tobytes(), "dng")
            os.link(staged, output)
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return dict(
            complete=True,
            output_sha256=digest(output),
            width=meta["width"],
            height=meta["height"],
            mode=c["mode"],
            grain_strength=grain_strength,
            input_sha256=digest(source),
            max_integer_cell_sum_error_before_grain=conserved,
            checkpoint_sha256=checkpoint_sha,
            model_seconds=model_seconds,
            memory_sampling=telemetry,
            total_decode_seconds=time.perf_counter() - started,
            peak_process_rss_bytes=rss if sys.platform == "darwin" else rss * 1024,
            temporal_grain_frame=frame_index,
            original_noise_recoverable=False,
            reconstruction=view["reconstruction"],
        )


def quality(pred, ref):
    diff = pred.astype(np.float64) - ref.astype(np.float64)
    mse = float(np.mean(diff**2))
    shadow = ref <= np.percentile(ref, 10)
    high = ref >= np.percentile(ref, 90)
    ref_planes = pack(ref).astype(np.float32)
    green = 0.5 * (ref_planes[1] + ref_planes[2])
    energy = (
        np.abs(np.diff(green, axis=0))[:, :-1] + np.abs(np.diff(green, axis=1))[:-1, :]
    )
    green_error = (
        0.5 * (pack(pred).astype(np.float64)[1] + pack(pred).astype(np.float64)[2])
        - green
    )
    interior = green_error[:-1, :-1]
    detail = energy >= np.percentile(energy, 90)
    faint = (energy >= np.percentile(energy, 40)) & (
        energy <= np.percentile(energy, 70)
    )
    flat = energy <= np.percentile(energy, 20)
    tone = np.sqrt(np.clip(pred.astype(np.float64) / PEAK, 0, 1)) - np.sqrt(
        np.clip(ref.astype(np.float64) / PEAK, 0, 1)
    )
    return dict(
        detail_green_rmse_counts=float(np.sqrt(np.mean(interior[detail] ** 2))),
        faint_green_rmse_counts=float(np.sqrt(np.mean(interior[faint] ** 2))),
        flat_green_error_std_counts=float(np.std(interior[flat])),
        tone_proxy_rmse=float(np.sqrt(np.mean(tone**2))),
        raw_psnr_db=None if mse == 0 else 10 * math.log10(PEAK**2 / mse),
        rmse_counts=math.sqrt(mse),
        bias_counts=float(np.mean(diff)),
        max_error_counts=float(np.max(np.abs(diff))),
        shadow_rmse_counts=float(np.sqrt(np.mean(diff[shadow] ** 2))),
        highlight_rmse_counts=float(np.sqrt(np.mean(diff[high] ** 2))),
    )


def preview(raw, output, black, white):
    """Fixed grayscale RAW diagnostic; no demosaicing or color-accuracy claim."""
    from PIL import Image

    green = 0.5 * (raw[0::2, 1::2].astype(np.float32) + raw[1::2, 0::2])
    scaled = np.sqrt(np.clip((green - black) / max(white - black, 1), 0, 1))
    image = Image.fromarray(np.rint(scaled * 255).astype(np.uint8))
    image.thumbnail((1024, 768), Image.Resampling.LANCZOS)
    image.save(output)


def compare(a):
    import tifffile

    root = a.output
    root.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory() as td:
        reference_meta, reference, kind = read_source(a.source, a.decoder, Path(td))
    tags = {t["code"]: t for t in reference_meta["image"]}
    black = float(np.mean(media.values(tags[50714])))
    white = float(media.values(tags[50717])[0])
    preview(reference, root / "reference.png", black, white)
    clean_reference = None
    if a.clean_reference:
        with tempfile.TemporaryDirectory() as td:
            _, clean_reference, _ = read_source(a.clean_reference, a.decoder, Path(td))
        if clean_reference.shape != reference.shape:
            raise ValueError("clean reference geometry differs")
    report = dict(
        schema="gpr.signal_comparison.v1",
        complete=False,
        source_kind=kind,
        source_sha256=digest(a.source),
        checkpoint_sha256=digest(a.checkpoint),
        quality_approval=False,
        clean_ground_truth_available=clean_reference is not None,
        clean_reference_sha256=digest(a.clean_reference) if a.clean_reference else None,
        training_data_provenance="unavailable_for_shipped_checkpoint",
        held_out_scene_status="unverified",
        reference_note="Error to input sensor samples/decoded GPR; does not prove denoising accuracy or a held-out clean target",
        cases=[],
    )

    def receipt():
        (root / "comparison.json").write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n"
        )

    receipt()
    for q in a.qualities:
        for mode in ("stock", "denoised", "simulated_sr"):
            folder = root / f"{mode}-q{q}"
            folder.mkdir()
            gpr = folder / "image.gpr"
            enc_path = folder / "encode.json"
            subprocess.run(
                [
                    sys.executable,
                    __file__,
                    "encode",
                    str(a.source),
                    "--output",
                    str(gpr),
                    "--encoder",
                    str(a.encoder),
                    "--decoder",
                    str(a.decoder),
                    "--mode",
                    mode,
                    "--quality",
                    str(q),
                    "--strength",
                    str(a.strength),
                    "--checkpoint",
                    str(a.checkpoint),
                    "--seed",
                    str(a.seed),
                    "--receipt",
                    str(enc_path),
                ],
                check=True,
            )
            enc = json.loads(enc_path.read_text())
            views = (
                [("decoded", 0.0, False)]
                if mode != "simulated_sr"
                else [
                    ("analytical", 0.0, True),
                    ("neural", 0.0, False),
                    ("grain", a.grain_strength, False),
                ]
            )
            for name, grain, analytical in views:
                out = folder / (name + ".dng")
                log = folder / (name + ".json")
                cmd = [
                    sys.executable,
                    __file__,
                    "decode",
                    str(gpr),
                    "--output",
                    str(out),
                    "--decoder",
                    str(a.decoder),
                    "--checkpoint",
                    str(a.checkpoint),
                    "--device",
                    a.device,
                    "--tile",
                    str(a.tile),
                    "--halo",
                    str(a.halo),
                    "--grain-strength",
                    str(grain),
                    "--receipt",
                    str(log),
                ]
                if analytical:
                    cmd += ["--analytical"]
                elif mode == "simulated_sr":
                    cmd += ["--neural"]
                subprocess.run(cmd, check=True)
                restored = tifffile.imread(out)
                if restored.shape != reference.shape:
                    raise ValueError("comparison geometry differs")
                preview(restored, folder / (name + ".png"), black, white)
                metrics = quality(restored, reference)
                report["cases"].append(
                    dict(
                        case=f"{mode}-q{q}-{name}",
                        encode=enc,
                        decode=json.loads(log.read_text()),
                        quality=metrics,
                        quality_to_clean_reference=quality(restored, clean_reference)
                        if clean_reference is not None
                        else None,
                        view=str(out.relative_to(root)),
                    )
                )
                receipt()
                print(
                    "PASS",
                    mode,
                    q,
                    name,
                    enc["gpr_bytes"],
                    metrics["raw_psnr_db"],
                    flush=True,
                )
    report["complete"] = True
    receipt()
    import csv

    with (root / "measurements.csv").open("x", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "case",
                "gpr_bytes",
                "encode_process_seconds",
                "preparation_seconds",
                "decode_seconds",
                "peak_decode_rss_bytes",
                "raw_psnr_vs_input_db",
                "raw_psnr_vs_clean_db",
                "cell_sum_error",
            ],
        )
        writer.writeheader()
        for c in report["cases"]:
            writer.writerow(
                dict(
                    case=c["case"],
                    gpr_bytes=c["encode"]["gpr_bytes"],
                    encode_process_seconds=c["encode"]["encode_process_seconds"],
                    preparation_seconds=c["encode"]["preparation_seconds"],
                    decode_seconds=c["decode"]["total_decode_seconds"],
                    peak_decode_rss_bytes=c["decode"]["peak_process_rss_bytes"],
                    raw_psnr_vs_input_db=c["quality"]["raw_psnr_db"],
                    raw_psnr_vs_clean_db=c["quality_to_clean_reference"]["raw_psnr_db"]
                    if c["quality_to_clean_reference"]
                    else None,
                    cell_sum_error=c["decode"][
                        "max_integer_cell_sum_error_before_grain"
                    ],
                )
            )
    import html

    rows = []
    for c in report["cases"]:
        metric = c["quality"]
        psnr = metric["raw_psnr_db"]
        rows.append(
            f'<tr><td>{html.escape(c["case"])}</td><td>{c["encode"]["gpr_bytes"]}</td><td>{psnr if psnr is not None else "exact"}</td><td>{c["encode"]["encode_process_seconds"]:.4f}</td><td>{c["decode"]["total_decode_seconds"]:.4f}</td><td>{c["decode"]["peak_process_rss_bytes"] / 1048576:.1f}</td><td><a href="{html.escape(c["view"])}">DNG</a> / <a href="{html.escape(str(Path(c["view"]).with_suffix(".png")))}">Preview</a></td></tr>'
        )
    (root / "report.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Signal RAW comparison</title><style>body{font:16px system-ui;margin:2rem}td,th{padding:.6rem;text-align:left;border-bottom:1px solid #ddd}</style><h1>Signal RAW comparison</h1><p>Desktop experiment; no camera performance or independent clean-reference quality approval. File bytes include metadata. Timings include subprocess startup / I/O; memory is the entire decoder process, including Torch. Synthetic linear box reduction is not VC-5 LL1 or physical sensor binning. Grain is generated texture, not recovered original noise. Integer cell sums are checked before grain.</p><p><a href="reference.png">Input grayscale RAW preview</a> / <a href="measurements.csv">Measurements CSV</a>. All previews use the same display curve.</p><table><tr><th>Case</th><th>GPR bytes</th><th>RAW PSNR vs input</th><th>Encode seconds</th><th>Decode seconds</th><th>Peak MiB</th><th>Output</th></tr>'
        + "".join(rows)
        + "</table>"
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("encode", "decode", "compare"):
        q = sub.add_parser(name)
        q.add_argument("source", type=Path)
        q.add_argument("--output", required=True, type=Path)
        q.add_argument("--decoder", required=True, type=Path)
        q.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
        if name != "decode":
            q.add_argument("--encoder", required=True, type=Path)
            q.add_argument("--strength", type=float, default=1.0)
            q.add_argument("--seed", type=int, default=42)
        if name == "encode":
            q.add_argument(
                "--mode",
                choices=("stock", "denoised", "simulated_sr"),
                default="denoised",
            )
            q.add_argument("--quality", type=int, choices=range(6), default=3)
        else:
            q.add_argument("--device", choices=("cpu", "mps"), default="cpu")
            q.add_argument("--tile", type=int, default=128)
            q.add_argument("--halo", type=int, default=64)
            q.add_argument(
                "--grain-strength",
                type=float,
                default=1.0 if name == "compare" else 0.0,
            )
        if name == "decode":
            q.add_argument("--frame-index", type=int, default=0)
            reconstruction = q.add_mutually_exclusive_group()
            reconstruction.add_argument(
                "--analytical",
                action="store_true",
                help="Bounded analytical reconstruction (default)",
            )
            reconstruction.add_argument(
                "--neural",
                action="store_true",
                help="Explicitly opt into the unvalidated frozen neural checkpoint",
            )
        if name == "compare":
            q.add_argument(
                "--qualities", type=int, nargs="+", choices=range(6), default=[0, 3, 5]
            )
            q.add_argument(
                "--clean-reference",
                type=Path,
                help="Optional independently obtained aligned clean target; provenance remains operator supplied",
            )
        else:
            q.add_argument("--receipt", type=Path)
    a = p.parse_args()
    if getattr(a, "receipt", None) and a.receipt.exists():
        raise FileExistsError(a.receipt)
    if a.command == "encode":
        result = encode(
            a.source,
            a.output,
            a.encoder,
            a.decoder,
            a.mode,
            a.quality,
            a.strength,
            a.checkpoint,
            a.seed,
        )
    elif a.command == "decode":
        result = decode(
            a.source,
            a.output,
            a.decoder,
            a.checkpoint,
            a.device,
            a.tile,
            a.halo,
            a.grain_strength,
            a.frame_index,
            a.analytical or not a.neural,
        )
    else:
        compare(a)
        return
    if a.receipt:
        save(a.receipt, result)
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
