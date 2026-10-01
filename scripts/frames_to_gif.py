"""Assemble PNG frames into a small GIF (Pillow).

    uv run --with pillow python scripts/frames_to_gif.py <dir> <out.gif> [fps_in] [keep_every] [width]

Keeps every `keep_every`-th frame, resizes to `width`, 64 colors, and merges identical neighbours.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageChops

src, out = Path(sys.argv[1]), Path(sys.argv[2])
fps = float(sys.argv[3]) if len(sys.argv) > 3 else 4
keep = int(sys.argv[4]) if len(sys.argv) > 4 else 2
width = int(sys.argv[5]) if len(sys.argv) > 5 else 640
paths = sorted(src.glob("f_*.png"))[::keep]
frames, durations = [], []
step_ms = int(1000 * keep / fps)
for p in paths:
    im = Image.open(p).convert("RGB")
    im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    if frames and ImageChops.difference(frames[-1], im).getbbox() is None:
        durations[-1] += step_ms
        continue
    frames.append(im)
    durations.append(step_ms)
pal = [f.quantize(colors=48, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
pal[0].save(out, save_all=True, append_images=pal[1:], duration=durations, loop=0, optimize=True)
print(f"{len(frames)} frames -> {out} ({out.stat().st_size // 1024} KB)")
