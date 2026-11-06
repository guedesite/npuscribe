"""Genere assets/app.ico — la meme onde que la pastille, toutes tailles."""
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "app.ico")

BG = (26, 26, 30)
ACCENT = (255, 138, 76)
SIZES = [16, 24, 32, 48, 64, 128, 256]


def draw(size: int) -> Image.Image:
    s = 256
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8, 8, s - 8, s - 8], radius=52, fill=BG)

    bars = [0.34, 0.55, 0.86, 0.62, 1.00, 0.62, 0.86, 0.55, 0.34]
    n = len(bars)
    bw, gap = 14, 10
    total = n * bw + (n - 1) * gap
    x = (s - total) // 2
    cy = s // 2
    maxh = 108
    for h in bars:
        hh = max(10, h * maxh)
        d.rounded_rectangle([x, cy - hh / 2, x + bw, cy + hh / 2],
                            radius=bw // 2, fill=ACCENT)
        x += bw + gap
    return img.resize((size, size), Image.LANCZOS)


def main() -> int:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    imgs = [draw(sz) for sz in SIZES]
    imgs[-1].save(OUT, format="ICO", sizes=[(sz, sz) for sz in SIZES],
                  append_images=imgs[:-1])
    print(f"ecrit {OUT} ({os.path.getsize(OUT)} octets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
