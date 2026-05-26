"""Generate the Dexter Assistant brand asset pack from dexter_logo.png.

Produces:
  brand/logo.png                 (original, copied)
  brand/logo-256.png             (square, padded)
  brand/logo-512.png             (square, padded)
  brand/icon-192.png             (PWA)
  brand/icon-512.png             (PWA)
  brand/apple-touch-icon.png     (180x180)
  brand/favicon-16.png
  brand/favicon-32.png
  brand/favicon-48.png
  brand/favicon.ico              (multi-resolution)
  brand/og-image.png             (1200x630, navy bg + centered mark + wordmark)

Run:
  python Tools/dexter_ui/generate_brand_assets.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ----- locations -----
ROOT = Path(__file__).resolve().parents[2]
SOURCE_LOGO = ROOT / "Dexter Assistant" / "dexter_logo.png"
OUT_DIR = Path(__file__).resolve().parent / "brand"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ----- brand palette -----
NAVY = (34, 66, 122, 255)
GOLD = (232, 163, 64, 255)
CREAM = (250, 246, 239, 255)
INK = (27, 31, 39, 255)
DARK_BG = (15, 20, 32, 255)


def load_logo() -> Image.Image:
    if not SOURCE_LOGO.exists():
        raise SystemExit(f"Source logo not found: {SOURCE_LOGO}")
    return Image.open(SOURCE_LOGO).convert("RGBA")


def trim_alpha(img: Image.Image, pad: int = 0) -> Image.Image:
    """Crop transparent border off an RGBA image, optionally add a uniform pad."""
    bbox = img.getbbox()
    if not bbox:
        return img
    cropped = img.crop(bbox)
    if pad <= 0:
        return cropped
    w, h = cropped.size
    out = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    out.paste(cropped, (pad, pad), cropped)
    return out


def square_on(canvas_size: int, logo: Image.Image, bg=(0, 0, 0, 0), inset_ratio: float = 0.08) -> Image.Image:
    """Place logo centered on a square canvas of canvas_size, inset by ratio."""
    canvas = Image.new("RGBA", (canvas_size, canvas_size), bg)
    inset = int(canvas_size * inset_ratio)
    box = canvas_size - 2 * inset
    fitted = logo.copy()
    fitted.thumbnail((box, box), Image.LANCZOS)
    x = (canvas_size - fitted.width) // 2
    y = (canvas_size - fitted.height) // 2
    canvas.paste(fitted, (x, y), fitted)
    return canvas


def make_og_image(logo: Image.Image) -> Image.Image:
    W, H = 1200, 630
    canvas = Image.new("RGBA", (W, H), NAVY)

    # Subtle vignette using a radial-ish gradient (approx via concentric rects).
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for i in range(60):
        a = int(110 * (i / 60) ** 2)
        od.rectangle([i * 4, i * 2, W - i * 4, H - i * 2], outline=(0, 0, 0, a))
    canvas = Image.alpha_composite(canvas, overlay)

    # Place logo on left half.
    logo_panel = square_on(420, logo, bg=(0, 0, 0, 0), inset_ratio=0.05)
    canvas.paste(logo_panel, (90, (H - 420) // 2), logo_panel)

    # Title + tagline (try system fonts, fall back to default).
    draw = ImageDraw.Draw(canvas)
    title_font = _pick_font(["arialbd.ttf", "seguibl.ttf", "arial.ttf"], 82)
    tag_font = _pick_font(["arial.ttf", "seguisb.ttf"], 36)

    draw.text((560, 215), "Dexter Assistant", font=title_font, fill=CREAM)
    draw.text((562, 320), "All-in-one restaurant ops", font=tag_font, fill=GOLD)

    return canvas


def _pick_font(candidates, size: int):
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main() -> None:
    raw = load_logo()
    trimmed = trim_alpha(raw)

    # square variants (transparent bg)
    for size in (256, 512):
        square_on(size, trimmed).save(OUT_DIR / f"logo-{size}.png", optimize=True)

    # PWA icons (transparent bg, looks fine on light and dark)
    square_on(192, trimmed).save(OUT_DIR / "icon-192.png", optimize=True)
    square_on(512, trimmed).save(OUT_DIR / "icon-512.png", optimize=True)

    # Apple touch icon — solid cream background for iOS rendering quality
    apple = square_on(180, trimmed, bg=CREAM, inset_ratio=0.10)
    apple.save(OUT_DIR / "apple-touch-icon.png", optimize=True)

    # Favicons
    for size in (16, 32, 48):
        square_on(size, trimmed, inset_ratio=0.05).save(OUT_DIR / f"favicon-{size}.png", optimize=True)
    # Multi-resolution ICO
    ico_sources = [
        square_on(s, trimmed, inset_ratio=0.05) for s in (16, 32, 48, 64)
    ]
    ico_sources[0].save(
        OUT_DIR / "favicon.ico",
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64)],
        append_images=ico_sources[1:],
    )

    # OG image
    make_og_image(trimmed).save(OUT_DIR / "og-image.png", optimize=True)

    # Copy the original PNG into the brand folder for convenience
    raw.save(OUT_DIR / "logo.png", optimize=True)

    print(f"[brand] wrote assets to: {OUT_DIR}")
    for p in sorted(OUT_DIR.glob("*")):
        print(f"  - {p.name}  ({p.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
