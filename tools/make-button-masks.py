#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Genera le maschere .xbm dei pulsanti della barra del titolo (Openbox).

CONVENZIONE OPENBOX: un bit ACCESO (1) viene disegnato nel colore
`window.*.button.*.image.color`; un bit SPENTO (0) resta trasparente e lascia
vedere lo sfondo del pulsante. Quindi per i glifi "simbolici" (stile Mint) il
TRATTO è fatto di bit accesi e il resto è spento.

Due stili:

- `simbolico`: minimizza «—», massimizza «□», ripristina «❐», chiudi «✕»,
  tratti pieni e completi. È lo stile del tema predefinito di Vesper.
- `sfera`: il disco pieno dei pulsanti stile macOS, col simbolo SCAVATO
  dentro (bit spenti). Usato dalla famiglia Cards.

ATTENZIONE alla DIMENSIONE: Openbox NON scala le maschere, le disegna 1:1 e le
RITAGLIA se sono più grandi del pulsante. Una maschera troppo grande si vede
come uno "spicchio" di cerchio: è il motivo per cui qui si sta bassi (12px) e
il tema riserva abbastanza altezza alla barra del titolo.

MISURA VERIFICATA: 12px. A 14px, con la barra del titolo di Vesper, Openbox
ritagliava le maschere e di square e X si vedevano solo gli angoli: è proprio
il difetto "pulsanti tagliati" da evitare.

Uso:  python3 tools/make-button-masks.py [--size 12] [--dest CARTELLA]
      (senza argomenti aggiorna i template in tools/openbox-templates/)
"""
from __future__ import annotations

import argparse
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))


def _img(size):
    return Image.new("1", (size, size), 0)        # tutto spento = trasparente


def simbolico(glyph: str, size: int = 12) -> Image.Image:
    """Glifo a tratto pieno, centrato e simmetrico."""
    img = _img(size)
    d = ImageDraw.Draw(img)
    th = 2 if size >= 12 else 1                   # spessore del tratto
    m = 1                                         # margine dal bordo
    a, b = m, size - 1 - m                        # estremi del glifo
    if glyph == "iconify":                        # —
        y = size - 1 - m - (th - 1)
        d.rectangle([a, y, b, y + th - 1], fill=1)
    elif glyph == "max":                          # □
        d.rectangle([a, a, b, b], outline=1, width=th)
    elif glyph == "max_toggled":                  # ❐ (ripristina)
        off = 3 if size >= 12 else 2
        d.rectangle([a, a + off, b - off, b], outline=1, width=th)
        d.rectangle([a + off, a, b, b - off], outline=1, width=th)
    elif glyph == "close":                        # ✕
        # due diagonali di spessore th, disegnate come linee spesse: restano
        # simmetriche e non "impastano" gli angoli
        d.line([a, a, b, b], fill=1, width=th)
        d.line([a, b, b, a], fill=1, width=th)
    elif glyph == "shade":                        # ▲ (arrotola)
        d.polygon([(size // 2, a), (b, b - 2), (a, b - 2)], outline=1)
    elif glyph == "desk":                         # ▣ (su tutti i desktop)
        d.rectangle([a, a, b, b], outline=1, width=1)
        d.rectangle([a + 3, a + 3, b - 3, b - 3], fill=1)
    return img


def sfera(glyph: str, size: int = 12) -> Image.Image:
    """Disco pieno con il simbolo scavato dentro (stile macOS/iOS).
    Il disco si disegna in grande e si riduce con antialias, poi si soglia:
    così il cerchio resta tondo anche a 12px."""
    q = 8
    big = Image.new("L", (size * q, size * q), 0)
    ImageDraw.Draw(big).ellipse([0, 0, size * q - 1, size * q - 1], fill=255)
    disc = (big.resize((size, size), Image.LANCZOS)
               .point(lambda p: 255 if p >= 128 else 0).convert("1"))
    px = disc.load()
    c = (size - 1) / 2.0
    arm = size * 0.26                              # semi-lunghezza del simbolo
    th = 0.9                                       # semi-spessore
    for y in range(size):
        for x in range(size):
            if not px[x, y]:
                continue
            dx, dy = x - c, y - c
            if glyph == "close":
                hole = (min(abs(dx - dy), abs(dx + dy)) <= th
                        and max(abs(dx), abs(dy)) <= arm)
            elif glyph == "iconify":
                hole = abs(dy) <= th and abs(dx) <= arm
            else:                                  # max / ripristina: +
                hole = ((abs(dx) <= th and abs(dy) <= arm)
                        or (abs(dy) <= th and abs(dx) <= arm))
            if hole:
                px[x, y] = 0
    return disc


GLIFI = ("iconify", "max", "max_toggled", "close", "shade", "desk")


def scrivi(dest: str, stile: str, size: int) -> int:
    os.makedirs(dest, exist_ok=True)
    fn = simbolico if stile == "simbolico" else sfera
    n = 0
    for g in GLIFI:
        if stile == "sfera" and g in ("shade", "desk"):
            continue                               # Cards non li usa
        img = fn(g, size)
        img.save(os.path.join(dest, g + ".xbm"))
        n += 1
    # Openbox cerca anche max_disabled/desk_toggled: li facciamo uguali
    if stile == "simbolico":
        simbolico("max", size).save(os.path.join(dest, "max_disabled.xbm"))
        simbolico("desk", size).save(os.path.join(dest, "desk_toggled.xbm"))
        n += 2
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="Maschere dei pulsanti Openbox")
    ap.add_argument("--size", type=int, default=12, help="lato in pixel (default 12)")
    ap.add_argument("--dest", default="", help="cartella di destinazione")
    ap.add_argument("--stile", choices=("simbolico", "sfera"), default="simbolico")
    args = ap.parse_args()
    if args.dest:
        n = scrivi(args.dest, args.stile, args.size)
        print("%d maschere %s in %s" % (n, args.stile, args.dest))
        return 0
    # senza argomenti: aggiorna i template (Core simbolico, Cards a sfera)
    core = os.path.join(HERE, "openbox-templates", "core", "openbox-3")
    cards = os.path.join(HERE, "openbox-templates", "cards", "openbox-3")
    retro = os.path.join(HERE, "openbox-templates", "retro", "openbox-3")
    print("%d maschere simboliche in %s" % (scrivi(core, "simbolico", args.size), core))
    print("%d maschere a sfera in %s" % (scrivi(cards, "sfera", args.size), cards))
    print("%d maschere simboliche in %s" % (scrivi(retro, "simbolico", args.size), retro))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
