#!/usr/bin/env python3
"""Build link-preview images (Discord etc.) for guides with a cover.

For each page in content/_guides/ with a `cover:`, writes
assets/img/previews/<file name>.jpg: the cover cropped to fill 1200x630
(keeping its `cover_position` focal point), with the overlay
(_tools/assets/preview-overlay.png, transparent background) in the top-right
corner at 15% of the image height and ~3% padding. _plugins/social.rb uses
these automatically.

Re-run after changing a cover or the overlay:
    python3 _tools/make_previews.py
Needs ImageMagick (`magick`) and `curl` (for covers hosted elsewhere).
"""
import hashlib
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OVERLAY = ROOT / "_tools" / "assets" / "preview-overlay.png"
OUT = ROOT / "assets" / "img" / "previews"
CACHE = ROOT / "_tools" / "preview-cache"   # downloaded remote covers (git-ignored)

W, H = 1200, 630
OVERLAY_H = round(H * 0.15)                  # 15% of the height
PAD = round(H * 0.03)                        # ~3% padding, same gap top and right


def front_matter(path):
    text = path.read_text()
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    fm = {}
    for line in (m.group(1) if m else "").splitlines():
        k, sep, v = line.partition(":")
        if sep and not line.startswith(" "):
            fm[k.strip()] = v.split("#", 1)[0].strip().strip('"') if not v.strip().startswith('"') else v.strip().split('"')[1]
    return fm


def local_cover(cover):
    if cover.startswith("http"):
        CACHE.mkdir(parents=True, exist_ok=True)
        dest = CACHE / (hashlib.sha1(cover.encode()).hexdigest()[:16] + ".img")
        if not dest.exists():
            subprocess.run(["curl", "-sSLf", "-o", str(dest), cover], check=True)
        return dest
    return ROOT / cover.lstrip("/")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    overlay_png = OVERLAY
    for page in sorted((ROOT / "content" / "_guides").glob("*.md")):
        fm = front_matter(page)
        cover = fm.get("cover")
        if not cover:
            continue
        src = local_cover(cover)
        pos = float(fm.get("cover_position", "50%").rstrip("%")) / 100
        out = OUT / f"{page.stem}.jpg"
        # Fill 1200x630, cropping around the focal point (like CSS object-position: center <pos>).
        filled = CACHE / "filled.png"
        subprocess.run(["magick", str(src) + "[0]", "-auto-orient", "-resize", f"{W}x{H}^", str(filled)], check=True)
        fw, fh = map(int, subprocess.run(["magick", "identify", "-format", "%w %h", str(filled)],
                                         check=True, capture_output=True, text=True).stdout.split())
        x, y = (fw - W) // 2, round((fh - H) * pos)
        subprocess.run([
            "magick", str(filled), "-crop", f"{W}x{H}+{x}+{y}", "+repage",
            "(", str(overlay_png), "-resize", f"x{OVERLAY_H}", ")",
            "-gravity", "NorthEast", "-geometry", f"+{PAD}+{PAD}", "-composite",
            "-strip", "-quality", "85", str(out)], check=True)
        print("wrote", out.relative_to(ROOT))


if __name__ == "__main__":
    main()
