# /// script
# requires-python = ">=3.13"
# dependencies = ["pillow"]
# ///
"""The images printed by the Python and PHP capture jobs.

    uv run spikes/printer-capture/job_images.py /tmp/phpjobs

writes checkerboard.png and arabic-line.png into the directory.
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ARABIC_FONT = "/System/Library/Fonts/GeezaPro.ttc"  # macOS; any Arabic TrueType font works


def checkerboard() -> Image.Image:
    image = Image.new("1", (160, 64), 1)
    draw = ImageDraw.Draw(image)
    for y in range(0, 64, 16):
        for x in range(0, 160, 16):
            if (x + y) // 16 % 2 == 0:
                draw.rectangle((x, y, x + 15, y + 15), fill=0)
    draw.ellipse((56, 8, 104, 56), outline=0, width=4)
    return image


def arabic_line() -> Image.Image:
    font = ImageFont.truetype(ARABIC_FONT, 36)
    text = "المجموع: ١٢٫٥٠ د.ل"  # noqa: RUF001 (Arabic digits are intended)
    image = Image.new("L", (576, 56), 255)
    draw = ImageDraw.Draw(image)
    draw.text((560, 4), text, font=font, fill=0, anchor="ra", direction="rtl", language="ar")
    return image.point(lambda v: 0 if v < 128 else 255).convert("1")


if __name__ == "__main__":
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    checkerboard().save(output / "checkerboard.png")
    arabic_line().save(output / "arabic-line.png")
    print(f"wrote {output}/checkerboard.png and {output}/arabic-line.png")
