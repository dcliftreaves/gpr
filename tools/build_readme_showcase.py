#!/usr/bin/env python3
"""Build the top-level README showcase image from committed preview assets."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
IMG = ROOT / "docs/img"
W, H = 1600, 1100


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Helvetica.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        p = Path(candidate)
        if p.exists():
            return ImageFont.truetype(str(p), size=size)
    return ImageFont.load_default()


def cover(path: Path, size: tuple[int, int], *, blur: float = 0.0) -> Image.Image:
    im = Image.open(path).convert("RGB")
    im.thumbnail((size[0] * 2, size[1] * 2), Image.Resampling.LANCZOS)
    scale = max(size[0] / im.width, size[1] / im.height)
    resized = im.resize((int(im.width * scale), int(im.height * scale)), Image.Resampling.LANCZOS)
    left = max(0, (resized.width - size[0]) // 2)
    top = max(0, (resized.height - size[1]) // 2)
    out = resized.crop((left, top, left + size[0], top + size[1]))
    return out.filter(ImageFilter.GaussianBlur(blur)) if blur > 0.0 else out


def rounded_rect(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: tuple[int, int, int, int], outline: tuple[int, int, int, int] | None = None, radius: int = 18) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2 if outline else 1)


def paste_panel(canvas: Image.Image, path: Path, box: tuple[int, int, int, int], title: str, subtitle: str) -> None:
    x0, y0, x1, y1 = box
    panel = cover(path, (x1 - x0, y1 - y0))
    mask = Image.new("L", panel.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, panel.width - 1, panel.height - 1), radius=18, fill=255)
    canvas.paste(panel, (x0, y0), mask)
    overlay = Image.new("RGBA", panel.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle((0, panel.height - 108, panel.width, panel.height), fill=(0, 0, 0, 168))
    canvas.alpha_composite(overlay, (x0, y0))
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((x0, y0, x1, y1), radius=18, outline=(235, 242, 248, 225), width=2)
    d.text((x0 + 22, y1 - 92), title, fill=(255, 255, 255), font=font(30, True))
    d.text((x0 + 22, y1 - 52), subtitle, fill=(224, 232, 238), font=font(24))


def metric_card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], title: str, value: str, detail: str, accent: tuple[int, int, int]) -> None:
    rounded_rect(draw, box, fill=(241, 247, 250, 224), outline=(255, 255, 255, 185), radius=12)
    x0, y0, _, _ = box
    draw.text((x0 + 24, y0 + 22), title, fill=(18, 30, 38), font=font(28, True))
    draw.text((x0 + 24, y0 + 78), value, fill=accent, font=font(38, True))
    draw.text((x0 + 24, y0 + 138), detail, fill=(54, 69, 78), font=font(22))


def build(out: Path, quality: int) -> None:
    bg = cover(IMG / "readme_z8_timelapse_1024.webp", (W, H), blur=9.0).convert("RGBA")
    shade = Image.new("RGBA", (W, H), (2, 12, 19, 122))
    bg.alpha_composite(shade)
    d = ImageDraw.Draw(bg)

    d.text((70, 58), "GPR", fill=(255, 255, 255), font=font(76, True))
    d.text((70, 140), "8-bit JPEG size. 16-bit RAW quality.", fill=(255, 255, 255), font=font(38, True))
    d.text((70, 194), "Editable Bayer stills, raw video, camera preview, and offline 8K reconstruction.", fill=(225, 235, 242), font=font(27))

    paste_panel(bg, IMG / "still_three_tiers.png", (70, 270, 650, 600), "RAW stills", "50 MP tiers + normal Bayer coverage")
    paste_panel(bg, IMG / "readme_mission1_native12_100pct.png", (690, 270, 1120, 600), "4K Bayer .gvid", "20+ fps Pi 5 stand-in encode")
    paste_panel(bg, IMG / "readme_mission1_2x_sr_contact.png", (1160, 270, 1530, 600), "8K SR review", "offline .gvid + ProRes receipts")

    metric_card(d, (70, 660, 430, 1006), "RAW stills", "9.80 MB", "smallest 50 MP tier", (0, 111, 88))
    metric_card(d, (455, 660, 815, 1006), "RAW video", "20.50 fps", "4K Bayer .gvid wall", (22, 97, 168))
    metric_card(d, (840, 660, 1200, 1006), "Preview", "1024 x 768", "same raw stream", (0, 126, 148))
    metric_card(d, (1225, 660, 1530, 1006), "Offline SR", "8K", "approved post path", (111, 66, 193))

    d.text((70, 1040), "Premium still/SR remains gated: no-REF 50 MP / 100 MP candidate must beat the current 5% / 5% floor.", fill=(231, 238, 243), font=font(22))
    out.parent.mkdir(parents=True, exist_ok=True)
    bg.convert("RGB").save(out, "WEBP", quality=quality, method=6)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=IMG / "readme_showcase.webp")
    ap.add_argument("--quality", type=int, default=78)
    args = ap.parse_args()
    build(args.out, args.quality)
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
