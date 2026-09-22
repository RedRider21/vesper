#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Icone PNG del marchio, in tutte le dimensioni che servono ai programmi.

Perché non basta l'SVG. Il file `vesper-logo.svg` è scritto in
`currentColor`, così nel pannello prende il colore del testo: comodo lì,
disastroso altrove. Il greeter del display manager (slick-greeter, lightdm-gtk)
disegna l'icona della sessione fuori da qualunque contesto GTK, e
`currentColor` senza un `color` definito vale **nero**: su uno sfondo scuro il
logo semplicemente spariva. In più diversi greeter cercano PNG a misura fissa
e `/usr/share/pixmaps`, non lo scalable.

Quindi: PNG a colori veri, in ogni misura, più una variante **semplificata**
per le misure piccole — sotto i 32px l'anello sottile e l'orizzonte diventano
sporcizia, e resta leggibile solo la stella.

    tools/make-icons.py            rigenera data/icons/hicolor/*/apps/*.png
    tools/make-icons.py --mostra   apre un provino con tutte le misure
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

RADICE = Path(__file__).resolve().parent.parent
DEST = RADICE / "data" / "icons" / "hicolor"
ACCENT = (0, 229, 255)              # il ciano di Vesper
MISURE = (16, 22, 24, 32, 48, 64, 128, 256, 512)
SEMPLICE_SOTTO = 48                 # sotto questa misura: solo la stella


def stella(d, cx, cy, rv, rh, fill, vita=0.17, passi=48):
    """Stella a quattro punte coi lati concavi: la stessa curva del marchio."""
    punte = [(cx, cy - rv), (cx + rh, cy), (cx, cy + rv), (cx - rh, cy)]
    ctrl = [(cx + vita * rh, cy - vita * rv), (cx + vita * rh, cy + vita * rv),
            (cx - vita * rh, cy + vita * rv), (cx - vita * rh, cy - vita * rv)]
    punti = []
    for i in range(4):
        p0, p1, p2 = punte[i], ctrl[i], punte[(i + 1) % 4]
        for s in range(passi):
            t = s / passi
            u = 1 - t
            punti.append((u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
                          u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]))
    d.polygon(punti, fill=fill)


def icona(lato: int, accent=ACCENT) -> Image.Image:
    """Il marchio alla misura richiesta, su sfondo trasparente.

    Si disegna a 8x e si riduce con LANCZOS: i bordi curvi della stella
    restano puliti anche a 16px, che disegnati direttamente sarebbero scalini.
    """
    scala = 8
    s = lato * scala
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    c = s / 2
    semplice = lato < SEMPLICE_SOTTO

    if not semplice:
        # alone morbido, appena accennato: dà corpo su sfondi chiari
        alone = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        ImageDraw.Draw(alone).ellipse(
            [c - s * 0.30, c - s * 0.30, c + s * 0.30, c + s * 0.30],
            fill=accent + (70,))
        img = Image.alpha_composite(
            img, alone.filter(ImageFilter.GaussianBlur(s * 0.06)))

    d = ImageDraw.Draw(img)
    if not semplice:
        d.ellipse([c - s * 0.40, c - s * 0.40, c + s * 0.40, c + s * 0.40],
                  outline=accent + (120,), width=max(scala, int(s / 170)))
        stella(d, c, c, s * 0.36, s * 0.30, accent + (255,))
        stella(d, c + s * 0.26, c - s * 0.24, s * 0.085, s * 0.07, accent + (200,))
        d.rounded_rectangle([c - s * 0.33, c + s * 0.44, c + s * 0.33, c + s * 0.47],
                            radius=s * 0.015, fill=accent + (230,))
    else:
        # piccola: la stella riempie il riquadro e l'orizzonte si ispessisce,
        # altrimenti a 16px sparisce del tutto. Le coordinate sono in frazioni
        # del LATO, non a partire dal centro: con c + s*0.60 l'orizzonte
        # finiva fuori dal riquadro e non si vedeva affatto.
        stella(d, c, s * 0.42, s * 0.38, s * 0.33, accent + (255,))
        d.rounded_rectangle([s * 0.16, s * 0.82, s * 0.84, s * 0.90],
                            radius=s * 0.04, fill=accent + (255,))
    return img.resize((lato, lato), Image.LANCZOS)


def scrivi() -> int:
    quante = 0
    for lato in MISURE:
        cartella = DEST / ("%dx%d" % (lato, lato)) / "apps"
        cartella.mkdir(parents=True, exist_ok=True)
        icona(lato).save(cartella / "vesper-logo.png")
        quante += 1
    # copia unica per /usr/share/pixmaps: alcuni greeter guardano solo lì
    pixmaps = RADICE / "data" / "pixmaps"
    pixmaps.mkdir(parents=True, exist_ok=True)
    icona(256).save(pixmaps / "vesper.png")
    icona(256).save(pixmaps / "vesper-logo.png")
    print("scritte %d icone in %s + 2 in %s" % (quante, DEST, pixmaps))
    return 0


def provino() -> int:
    """Tutte le misure affiancate su fondo scuro e su fondo chiaro: è così che
    si vede se a 16px resta qualcosa di riconoscibile."""
    larghezza = sum(m + 12 for m in MISURE) + 12
    prova = Image.new("RGBA", (larghezza, 2 * 280), (10, 18, 32, 255))
    ImageDraw.Draw(prova).rectangle([0, 280, larghezza, 560], fill=(245, 245, 245, 255))
    x = 12
    for m in MISURE:
        ic = icona(m)
        prova.alpha_composite(ic, (x, 140 - m // 2))
        prova.alpha_composite(ic, (x, 420 - m // 2))
        x += m + 12
    fuori = Path("/tmp/vesper-icone-provino.png")
    prova.save(fuori)
    print("provino in", fuori)
    return 0


if __name__ == "__main__":
    sys.exit(provino() if "--mostra" in sys.argv else scrivi())
