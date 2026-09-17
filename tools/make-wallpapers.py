#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Generatore degli sfondi di Vesper (PIL) - uno per ogni colore d'accento.

Impianto grafico unico per tutti i colori, ripreso dal marchio (la stella
della sera sopra l'orizzonte): cielo a gradiente tinto verso l'accent, campo
stellato che si dirada verso il basso, ORIZZONTE luminoso nel terzo inferiore
con la sua riflessione, e la STELLA a quattro punte dentro anelli tenui.
**Nessuna scritta**: nessun monogramma, nessun wordmark, nessuna etichetta del
colore o del tema - lo sfondo resta pulito e riusabile.

Output: data/backgrounds/<colore>.png (1920x1080) e data/presets.json (il
catalogo dei preset di aspetto: questa tavolozza è la fonte di verità, così
sfondi e preset non possono divergere).

Uso:    python3 tools/make-wallpapers.py [--size 2560x1440] [--only cyan,verde]
        python3 tools/make-wallpapers.py --presets-only
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W, H = 1920, 1080
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "data", "backgrounds")

# Tavolozza: id -> accent, fondo profondo tinto, nome e descrizione. Il fondo
# è quasi nero ma virato verso l'accent, così anche i bordi restano coerenti.
# È anche il catalogo dei preset: da qui nasce data/presets.json.
DEFAULT_PRESET = "cyan"

PALETTE = {
    "cyan":    ("#00e5ff", "#020611", "Cyan", "Blu notte con accento cyan: il colore di Vesper."),
    "acqua":   ("#2ad1c5", "#02100f", "Acquamarina", "Verde-azzurro tenue, riposante."),
    "verde":   ("#23d18b", "#02100a", "Verde", "Verde smeraldo su fondo scuro."),
    "lime":    ("#b8ff3b", "#060c02", "Lime", "Verde acido, molto contrastato."),
    "giallo":  ("#ffe14b", "#0d0c02", "Giallo", "Giallo caldo, alta visibilità."),
    "ambra":   ("#ffb000", "#0f0902", "Ambra", "Ambra da terminale d'altri tempi."),
    "arancio": ("#ff8a3b", "#0f0602", "Arancio", "Arancio tramonto, caldo."),
    "rosso":   ("#ff3b5c", "#0c0205", "Rosso", "Rosso acceso su nero."),
    "rosa":    ("#ff5a8a", "#0f0309", "Rosa", "Rosa intenso, tono serale."),
    "magenta": ("#ff5ad0", "#0f0310", "Magenta", "Magenta vivido, stile neon."),
    "viola":   ("#a06bff", "#070310", "Viola", "Viola crepuscolo."),
    "indaco":  ("#6366f1", "#04030f", "Indaco", "Indaco profondo, sobrio."),
    "blu":     ("#3b82f6", "#02060f", "Blu", "Blu pieno, classico."),
    "argento": ("#b8c6d0", "#05080c", "Argento", "Grigio argento: senza dominante di colore."),
}


def hx(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def luma(c) -> float:
    """Luminosità percepita 0..1 (Rec. 709): serve a calmare gli aloni dei
    colori chiari (lime, giallo, argento), che altrimenti sbiancano lo sfondo
    e rendono illeggibili le etichette delle icone."""
    return (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255.0


def glow_gain(accent) -> float:
    """Fattore 0.45..1 per l'intensità degli aloni, inverso alla luminosità."""
    return 1.0 - 0.55 * luma(accent)


# ----------------------------------------------------------------- background
def background(accent, deep, focal, w, h):
    """Gradiente radiale: tinto verso l'accent nel punto focale, quasi nero ai
    bordi, più vignette."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    fx, fy = focal
    d = np.sqrt(((xx - fx) / w) ** 2 + ((yy - fy) / h) ** 2)
    d = np.clip(d / d.max(), 0, 1)
    glow = (1 - d) ** 2.2                      # più luce al centro focale
    near = np.array(mix(deep, accent, 0.18), np.float32)
    far = np.array(deep, np.float32)
    img = far[None, None, :] + (near - far)[None, None, :] * glow[..., None]
    vig = 1 - 0.55 * (d ** 2)                  # vignette ai bordi
    img *= vig[..., None]
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB").convert("RGBA")


def starfield(seed, w, h, horizon, n=420):
    """Campo stellato che si dirada scendendo: fitto in alto, quasi assente
    sull'orizzonte (dove la luce del tramonto lo cancellerebbe)."""
    rnd = random.Random(seed)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(n):
        x, y = rnd.randint(0, w), rnd.randint(0, int(horizon))
        fade = 1 - (y / horizon) ** 0.8          # 1 in cima, 0 sull'orizzonte
        b = int(rnd.randint(40, 180) * fade)
        if b <= 8:
            continue
        r = rnd.choice([0, 0, 0, 1])
        d.ellipse([x - r, y - r, x + r, y + r], fill=(b, b, b, b))
    return layer


def sparkle_pts(cx, cy, rv, rh, waist=0.17, steps=26):
    """Punti della stella a quattro punte del marchio: quattro archi quadratici
    fra le punte, con i lati CONCAVI (il control point sta vicino al centro).
    Stessa forma dell'SVG del logo, così sfondo e icona sono la stessa cosa."""
    tips = [(cx, cy - rv), (cx + rh, cy), (cx, cy + rv), (cx - rh, cy)]
    ctrl = [(cx + waist * rh, cy - waist * rv), (cx + waist * rh, cy + waist * rv),
            (cx - waist * rh, cy + waist * rv), (cx - waist * rh, cy - waist * rv)]
    pts = []
    for i in range(4):
        p0, p2 = tips[i], tips[(i + 1) % 4]
        p1 = ctrl[i]
        for s in range(steps):
            t = s / steps
            u = 1 - t
            pts.append((u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
                        u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]))
    return pts


def emblem(accent, cx, cy, w, h, scale=1.0):
    """Emblema: la stella della sera dentro due anelli tenui, con la compagna
    piccola in alto a destra. Nessun testo: va bene con qualsiasi colore."""
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    hard = accent + (240,)
    soft = accent + (150,)
    faint = accent + (55,)
    rv, rh = 300 * scale, 250 * scale
    # anelli del "cielo"
    for r, col in ((int(360 * scale), accent + (38,)), (int(430 * scale), accent + (18,))):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col, width=2)
    # stella principale
    d.polygon(sparkle_pts(cx, cy, rv, rh), fill=hard)
    # stella compagna
    d.polygon(sparkle_pts(cx + int(255 * scale), cy - int(230 * scale),
                          70 * scale, 58 * scale), fill=soft)
    return layer


def horizon(accent, w, h, y, cx, scale=1.0):
    """Orizzonte: filetto luminoso + secondo filetto tenue (foschia) + colonna
    di luce riflessa sotto la stella."""
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    m = int(w * 0.14)
    th = max(2, int(3 * scale))
    d.rounded_rectangle([m, y, w - m, y + th], radius=th // 2 + 1,
                        fill=accent + (225,))
    m2 = int(w * 0.30)
    d.rounded_rectangle([m2, y + int(26 * scale), w - m2, y + int(26 * scale) + max(2, th - 1)],
                        radius=th // 2, fill=accent + (90,))
    # riflessione sull'acqua: colonna che si assottiglia e sfuma scendendo
    # (a strisce sovrapposte, poi sfocata: niente bordi netti)
    refl = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    rd = ImageDraw.Draw(refl)
    steps = 40
    band = (h - y) / steps
    gain = glow_gain(accent)
    for i in range(steps):
        t = i / steps
        a = int(52 * gain * (1 - t) ** 2.2)
        if a <= 1:
            break
        cw = int(w * 0.05 * (1 - 0.55 * t))      # si restringe verso il basso
        yy = y + th + t * (h - y)
        rd.rounded_rectangle([cx - cw, yy, cx + cw, yy + band * 1.6],
                             radius=int(band), fill=accent + (a,))
    layer = Image.alpha_composite(layer, refl.filter(ImageFilter.GaussianBlur(26)))
    return layer


def glow_compose(base, layer, radius=9):
    """Sovrappone il layer due volte: sfocato (alone) e nitido."""
    blurred = layer.filter(ImageFilter.GaussianBlur(radius))
    base = Image.alpha_composite(base, blurred)
    return Image.alpha_composite(base, layer)


def make(cid: str, accent_hex: str, deep_hex: str, w: int, h: int) -> str:
    accent = hx(accent_hex)
    deep = hx(deep_hex)
    scale = min(w / W, h / H) * 0.62       # soggetto contenuto: e' uno SFONDO
    hor_y = int(h * 0.72)                  # l'orizzonte nel terzo inferiore
    # stella spostata a destra: in alto a sinistra ci vanno le icone del desktop
    cx, cy = int(w * 0.655), int(h * 0.42)
    focal = (int(w * 0.62), hor_y)         # la luce nasce dall'orizzonte

    img = background(accent, deep, focal, w, h)
    img = Image.alpha_composite(img, starfield(abs(hash(cid)) & 0xffff, w, h, hor_y))

    # bagliore del tramonto sull'orizzonte + alone dietro la stella
    # (attenuati sui colori chiari: vedi glow_gain)
    g = glow_gain(accent)
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([-w * 0.25, hor_y - h * 0.30, w * 1.25, hor_y + h * 0.30],
               fill=accent + (int(52 * g),))
    r = int(330 * scale)
    gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=accent + (int(34 * g),))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(170)))

    img = glow_compose(img, horizon(accent, w, h, hor_y, cx, scale), radius=14)
    img = glow_compose(img, emblem(accent, cx, cy, w, h, scale), radius=12)

    os.makedirs(DEST, exist_ok=True)
    out = os.path.join(DEST, cid + ".png")
    img.convert("RGB").save(out, "PNG", optimize=True)
    return out


def write_presets() -> str:
    """Scrive data/presets.json dalla tavolozza (catalogo dei preset)."""
    cat = {
        "default": DEFAULT_PRESET,
        "presets": {
            cid: {
                "name": name,
                "desc": desc,
                "accent": accent,
                "wallpaper": cid + ".png",
                "icon": "vesper-logo-symbolic",
            }
            for cid, (accent, _deep, name, desc) in PALETTE.items()
        },
    }
    out = os.path.join(ROOT, "data", "presets.json")
    with open(out, "w") as f:
        json.dump(cat, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Genera gli sfondi e i preset di Vesper")
    ap.add_argument("--size", default="1920x1080", help="risoluzione, es. 2560x1440")
    ap.add_argument("--only", default="", help="solo questi colori (separati da virgola)")
    ap.add_argument("--presets-only", action="store_true",
                    help="rigenera solo data/presets.json, senza gli sfondi")
    args = ap.parse_args()
    if args.presets_only:
        print("catalogo preset:", write_presets())
        return 0
    try:
        w, h = (int(v) for v in args.size.lower().split("x"))
    except ValueError:
        print("--size va scritto come LARGHEZZAxALTEZZA (es. 1920x1080)")
        return 2
    wanted = [c.strip() for c in args.only.split(",") if c.strip()] or list(PALETTE)
    for cid in wanted:
        if cid not in PALETTE:
            print("colore sconosciuto:", cid, "- disponibili:", ", ".join(PALETTE))
            return 2
        accent, deep = PALETTE[cid][0], PALETTE[cid][1]
        print("generato", make(cid, accent, deep, w, h))
    print("catalogo preset:", write_presets())
    print(f"[sfondi] {len(wanted)} file in {os.path.normpath(DEST)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
