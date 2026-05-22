"""Generate the 512x512 UA — Umbrel Analyser app icon.

Re-run after tweaking colors/layout:
    python3 scripts/make_icon.py
"""

import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZE = 512
BG          = (15, 17, 21, 255)        # near-black navy
BG_INNER    = (30, 35, 48, 255)        # subtle inner highlight
GLASS       = (255, 255, 255, 255)
ACCENT      = (247, 147, 26, 255)      # bitcoin orange
SHADOW      = (0, 0, 0, 120)

CORNER_RADIUS = 96
LENS_CENTER   = (212, 212)
LENS_RADIUS   = 138
RING_WIDTH    = 30
HANDLE_WIDTH  = 38
HANDLE_LEN    = 170                    # how far the handle extends past the lens
HANDLE_ANGLE  = 45                     # degrees, down-right

FONT_CANDIDATES = [
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/SFNS.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def load_font(size: int) -> ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def draw_icon() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Rounded background with a subtle inner gradient (two stacked rects)
    d.rounded_rectangle((0, 0, SIZE, SIZE), radius=CORNER_RADIUS, fill=BG)
    pad = 6
    d.rounded_rectangle(
        (pad, pad, SIZE - pad, SIZE - pad),
        radius=CORNER_RADIUS - 4,
        outline=BG_INNER, width=2,
    )

    cx, cy = LENS_CENTER
    r = LENS_RADIUS

    # Handle — drawn first so the lens overlaps it (cleaner join)
    rad = math.radians(HANDLE_ANGLE)
    # Start a bit inside the lens edge, so there's no visible seam
    start = (cx + (r - 6) * math.cos(rad), cy + (r - 6) * math.sin(rad))
    end   = (cx + (r + HANDLE_LEN) * math.cos(rad),
             cy + (r + HANDLE_LEN) * math.sin(rad))

    # Soft shadow under the handle (offset slightly)
    d.line(
        (start[0] + 4, start[1] + 6, end[0] + 4, end[1] + 6),
        fill=SHADOW, width=HANDLE_WIDTH + 2,
    )
    d.line((start[0], start[1], end[0], end[1]), fill=GLASS, width=HANDLE_WIDTH)
    # Rounded cap at the far end
    cap_r = HANDLE_WIDTH // 2
    d.ellipse((end[0] - cap_r, end[1] - cap_r, end[0] + cap_r, end[1] + cap_r), fill=GLASS)

    # Lens — outer ring (white) with subtle shadow under it
    d.ellipse(
        (cx - r + 4, cy - r + 8, cx + r + 4, cy + r + 8),
        outline=SHADOW, width=RING_WIDTH + 2,
    )
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=GLASS, width=RING_WIDTH)

    # Inner lens fill — slight tint so "UA" pops
    inner_r = r - RING_WIDTH - 2
    d.ellipse(
        (cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r),
        fill=(20, 23, 31, 255),
    )

    # "UA" centered in the lens, orange
    font = load_font(126)
    text = "UA"
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = cx - tw / 2 - bbox[0]
    ty = cy - th / 2 - bbox[1]
    d.text((tx, ty), text, font=font, fill=ACCENT)

    return img


def main() -> None:
    out = draw_icon()
    root = Path(__file__).resolve().parent.parent
    target = root / "umbrel" / "icon.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    out.save(target, "PNG", optimize=True)
    print(f"wrote {target}  ({target.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
