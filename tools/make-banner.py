#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Genera il marchio e i banner di Vesper per il README e il sito.

Due banner, non uno: GitHub (e il sito) hanno tema chiaro e tema scuro, e un
banner scuro su pagina scura sparisce. Quindi:

  docs/img/banner.png         fondo teal/blu, per chi guarda in tema CHIARO
  docs/img/banner-chiaro.png  fondo azzurro chiarissimo, per il tema SCURO

Entrambi hanno una cornice sottile nel colore d'accento, così staccano
comunque. Il README li serve con <picture> e prefers-color-scheme.

Uso: python3 tools/make-banner.py
"""
from __future__ import annotations

import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "docs", "img")
ACCENT = (0, 229, 255)
ACCENT_CHIARO = (10, 120, 160)      # accent leggibile su fondo chiaro


def font(size, bold=True):
    per = ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
           "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
           "/usr/share/fonts/TTF/DejaVuSans.ttf")
    for p in per:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def star(d, cx, cy, rv, rh, fill, waist=0.17, steps=40):
    """La stella a quattro punte del marchio (lati concavi)."""
    tips = [(cx, cy - rv), (cx + rh, cy), (cx, cy + rv), (cx - rh, cy)]
    ctrl = [(cx + waist * rh, cy - waist * rv), (cx + waist * rh, cy + waist * rv),
            (cx - waist * rh, cy + waist * rv), (cx - waist * rh, cy - waist * rv)]
    pts = []
    for i in range(4):
        p0, p1, p2 = tips[i], ctrl[i], tips[(i + 1) % 4]
        for s in range(steps):
            t = s / steps
            u = 1 - t
            pts.append((u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
                        u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]))
    d.polygon(pts, fill=fill)


def mark(size=512, accent=ACCENT):
    """Marchio su sfondo trasparente: alone, anello, stella e orizzonte."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    c = size / 2
    ImageDraw.Draw(glow).ellipse(
        [c - size * 0.30, c - size * 0.30, c + size * 0.30, c + size * 0.30],
        fill=accent + (70,))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(size * 0.06)))
    d = ImageDraw.Draw(img)
    d.ellipse([c - size * 0.40, c - size * 0.40, c + size * 0.40, c + size * 0.40],
              outline=accent + (120,), width=max(2, size // 170))
    star(d, c, c, size * 0.36, size * 0.30, accent + (255,))
    star(d, c + size * 0.26, c - size * 0.24, size * 0.085, size * 0.07, accent + (200,))
    d.rounded_rectangle([c - size * 0.33, c + size * 0.44, c + size * 0.33, c + size * 0.47],
                        radius=size * 0.015, fill=accent + (230,))
    return img


def gradiente(w, h, a, b):
    """Sfondo a gradiente diagonale: niente tinta piatta, così il banner
    stacca sia su pagina chiara sia su pagina scura."""
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            t = (x / w) * 0.72 + (y / h) * 0.28
            px[x, y] = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
    return img.convert("RGBA")


def banner(w=1280, h=380, scuro=True):
    accent = ACCENT if scuro else ACCENT_CHIARO
    if scuro:
        # teal profondo -> blu notte: più chiaro del fondo scuro di GitHub
        img = gradiente(w, h, (8, 52, 70), (12, 24, 52))
        testo = (240, 252, 255)
        tenue = (155, 205, 220)
    else:
        # azzurro chiarissimo -> bianco: stacca su pagina scura
        img = gradiente(w, h, (208, 236, 247), (250, 253, 255))
        testo = (10, 26, 40)
        tenue = (60, 90, 110)

    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [w * 0.05, -h * 0.35, w * 0.44, h * 1.3], fill=accent + (60 if scuro else 34,))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(90)))

    if scuro:
        rnd = random.Random(7)
        sd = ImageDraw.Draw(img)
        for _ in range(80):
            x, y = rnd.randint(0, w), rnd.randint(0, h)
            b = rnd.randint(50, 150)
            sd.ellipse([x, y, x + 1, y + 1], fill=(b, b, b, b))

    img.alpha_composite(mark(int(h * 0.72), accent), (int(w * 0.09), int(h * 0.14)))

    d = ImageDraw.Draw(img)
    d.text((int(w * 0.30), int(h * 0.26)), "Vesper", font=font(int(h * 0.30)), fill=testo)
    d.text((int(w * 0.305), int(h * 0.60)),
           "ambiente desktop leggero  ·  Python + GTK3", font=font(int(h * 0.075), False),
           fill=tenue)
    d.rounded_rectangle([int(w * 0.305), int(h * 0.76),
                         int(w * 0.305) + int(h * 0.55), int(h * 0.775)],
                        radius=4, fill=accent + (230,))
    # cornice sottile: il banner non si confonde col fondo della pagina
    d.rectangle([0, 0, w - 1, h - 1], outline=accent + (150,), width=2)
    return img.convert("RGB")


def main() -> int:
    os.makedirs(DEST, exist_ok=True)
    mark(512).save(os.path.join(DEST, "logo.png"))
    mark(128).save(os.path.join(DEST, "logo-128.png"))
    banner(scuro=True).save(os.path.join(DEST, "banner.png"))
    banner(scuro=False).save(os.path.join(DEST, "banner-chiaro.png"))
    print("marchio e banner in", DEST)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
