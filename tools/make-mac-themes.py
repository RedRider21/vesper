#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Genera i temi Openbox "Vesper-Mac" (chiaro) e "Vesper-Mac-Scuro", piu'
una variante chiara e una scura per OGNI preset (Vesper-Mac-<preset>,
Vesper-Mac-Scuro-<preset>): pulsanti a semaforo in stile macOS a SINISTRA,
titolo centrato. Portato da NexusSec OS.

    python3 tools/make-mac-themes.py      -> data/themes/Vesper-Mac*/

Limite reale (verificato 2026-11-22 con Openbox 3.6.1): i
pulsanti accettano SOLO maschere .xbm a 1 bit (i .png vengono ignorati), e
senza compositor niente angoli arrotondati ne' ombre. Quindi: cerchi disegnati
pixel per pixel, un colore per pulsante (image.color per tipo), grigi a
finestra inattiva, simbolo (x - +) che compare al passaggio del mouse
(maschere *_hover = cerchio col simbolo "scavato").
"""
import os

QUI = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(QUI, "..", "data", "themes")
D = 12          # diametro del semaforo (px)


def cerchio():
    c = (D - 1) / 2.0
    r2 = (D / 2.0 - 0.15) ** 2
    return [[(x - c) ** 2 + (y - c) ** 2 <= r2 for x in range(D)] for y in range(D)]


def scava(g, punti):
    g = [r[:] for r in g]
    for x, y in punti:
        if 0 <= x < D and 0 <= y < D:
            g[y][x] = False
    return g


def simbolo(nome):
    m = D // 2
    if nome == "close":            # x
        return [(m - 3 + i, m - 3 + i) for i in range(6)] + [(m + 2 - i, m - 3 + i) for i in range(6)]
    if nome == "iconify":          # -
        return [(x, m - 1) for x in range(m - 3, m + 3)] + [(x, m) for x in range(m - 3, m + 3)]
    if nome in ("max", "max_toggled"):  # +
        return ([(x, m - 1) for x in range(m - 3, m + 3)] + [(x, m) for x in range(m - 3, m + 3)]
                + [(m - 1, y) for y in range(m - 3, m + 3)] + [(m, y) for y in range(m - 3, m + 3)])
    return []


def xbm(nome, g):
    righe = []
    for row in g:
        b = 0
        for x, on in enumerate(row):
            if on:
                b |= 1 << x
        righe.append(b)
    byte = []
    per = (D + 7) // 8
    for v in righe:
        for k in range(per):
            byte.append((v >> (8 * k)) & 0xFF)
    corpo = ", ".join("0x%02x" % b for b in byte)
    return ("#define %s_width %d\n#define %s_height %d\nstatic unsigned char %s_bits[] = {\n  %s };\n"
            % (nome, D, nome, D, nome, corpo))


VARIANTI = {
    "Vesper-Mac": dict(
        tit_a1="#ececec", tit_a2="#dcdcdc", tit_i="#f6f6f6", testo_a="#4a4a4a", testo_i="#b0b0b0",
        bordo_a="#b4b4b4", bordo_i="#d2d2d2", client="#ececec", inattivo="#cdcdcd",
        simbolo="#ececec"),
    "Vesper-Mac-Scuro": dict(
        tit_a1="#3b3b3d", tit_a2="#323234", tit_i="#2c2c2e", testo_a="#e3e3e3", testo_i="#7d7d80",
        bordo_a="#1f1f21", bordo_i="#262628", client="#323234", inattivo="#55555a",
        simbolo="#3b3b3d"),
}
ROSSO, GIALLO, VERDE = "#ff5f57", "#febc2e", "#28c840"
# colori PIU' SCURI per il cerchio quando ci passa sopra il mouse (come macOS
# il simbolo appare; noi lo "scaviamo" e scuriamo un po' il colore)
ROSSO_H, GIALLO_H, VERDE_H = "#e0443e", "#dea123", "#1aab29"


def themerc(n, v):
    return f"""# {n} - tema finestre in stile macOS per Vesper (generato da
# tools/make-mac-themes.py: modificare quello, non questo file).
# 3 px: bordo afferrabile per il ridimensionamento (Openbox mostra le frecce
# sopra bordi e angoli); colorato come la barra, cosi' resta discreto
border.width: 3
padding.width: 8
padding.height: 5
window.handle.width: 5
window.client.padding.width: 0
window.client.padding.height: 0
menu.overlap: 0

window.active.border.color: {v['tit_a2']}
window.inactive.border.color: {v['tit_i']}
window.active.title.separator.color: {v['bordo_a']}
window.inactive.title.separator.color: {v['bordo_i']}
window.active.client.color: {v['client']}
window.inactive.client.color: {v['client']}

window.active.title.bg: flat gradient vertical
window.active.title.bg.color: {v['tit_a1']}
window.active.title.bg.colorTo: {v['tit_a2']}
window.inactive.title.bg: flat solid
window.inactive.title.bg.color: {v['tit_i']}

window.active.label.bg: parentrelative
window.inactive.label.bg: parentrelative
window.active.label.text.color: {v['testo_a']}
window.inactive.label.text.color: {v['testo_i']}
window.label.text.justify: center

window.active.handle.bg: flat solid
window.active.handle.bg.color: {v['tit_a2']}
window.inactive.handle.bg: flat solid
window.inactive.handle.bg.color: {v['tit_i']}
window.active.grip.bg: flat solid
window.active.grip.bg.color: {v['tit_a2']}
window.inactive.grip.bg: flat solid
window.inactive.grip.bg.color: {v['tit_i']}

window.active.button.unpressed.bg: parentrelative
window.active.button.pressed.bg: parentrelative
window.active.button.hover.bg: parentrelative
window.active.button.disabled.bg: parentrelative
window.active.button.toggled.unpressed.bg: parentrelative
window.active.button.toggled.pressed.bg: parentrelative
window.active.button.toggled.hover.bg: parentrelative
window.inactive.button.unpressed.bg: parentrelative
window.inactive.button.pressed.bg: parentrelative
window.inactive.button.hover.bg: parentrelative
window.inactive.button.disabled.bg: parentrelative
window.inactive.button.toggled.unpressed.bg: parentrelative
window.inactive.button.toggled.pressed.bg: parentrelative
window.inactive.button.toggled.hover.bg: parentrelative

window.active.button.close.unpressed.image.color: {ROSSO}
window.active.button.close.hover.image.color: {ROSSO_H}
window.active.button.close.pressed.image.color: {ROSSO_H}
window.active.button.iconify.unpressed.image.color: {GIALLO}
window.active.button.iconify.hover.image.color: {GIALLO_H}
window.active.button.iconify.pressed.image.color: {GIALLO_H}
window.active.button.max.unpressed.image.color: {VERDE}
window.active.button.max.hover.image.color: {VERDE_H}
window.active.button.max.pressed.image.color: {VERDE_H}
window.active.button.max.toggled.unpressed.image.color: {VERDE}
window.active.button.max.toggled.hover.image.color: {VERDE_H}
window.active.button.max.toggled.pressed.image.color: {VERDE_H}
window.active.button.toggled.unpressed.image.color: {VERDE}
window.active.button.toggled.hover.image.color: {VERDE_H}
window.active.button.toggled.pressed.image.color: {VERDE_H}
window.active.button.desk.unpressed.image.color: {v['inattivo']}
window.active.button.shade.unpressed.image.color: {v['inattivo']}

window.inactive.button.unpressed.image.color: {v['inattivo']}
window.inactive.button.hover.image.color: {v['inattivo']}
window.inactive.button.pressed.image.color: {v['inattivo']}
window.inactive.button.toggled.unpressed.image.color: {v['inattivo']}
window.inactive.button.toggled.hover.image.color: {v['inattivo']}
window.inactive.button.close.hover.image.color: {ROSSO}
window.inactive.button.iconify.hover.image.color: {GIALLO}
window.inactive.button.max.hover.image.color: {VERDE}

menu.border.width: 1
menu.border.color: {v['bordo_a']}
menu.title.bg: flat solid
menu.title.bg.color: {v['tit_a2']}
menu.title.text.color: {v['testo_a']}
menu.title.text.justify: center
menu.items.bg: flat solid
menu.items.bg.color: {v['client']}
menu.items.text.color: {v['testo_a']}
menu.items.disabled.text.color: {v['testo_i']}
menu.items.active.bg: flat solid
menu.items.active.bg.color: {v.get('menu_hl', '#2f7cf6')}
menu.items.active.text.color: #ffffff
menu.separator.color: {v['bordo_i']}

osd.border.width: 1
osd.border.color: {v['bordo_a']}
osd.bg: flat solid
osd.bg.color: {v['client']}
osd.label.text.color: {v['testo_a']}
osd.hilight.bg: flat solid
osd.hilight.bg.color: {v.get('menu_hl', '#2f7cf6')}
osd.unhilight.bg: flat solid
osd.unhilight.bg.color: {v['bordo_i']}
"""


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    """Colore a mescolato con b: t=0 -> b, t=1 -> a."""
    ra, rb = _rgb(a), _rgb(b)
    return "#%02x%02x%02x" % tuple(round(x * t + y * (1 - t)) for x, y in zip(ra, rb))


def varianti_profilo():
    """Una variante chiara e una scura per OGNI preset (colori da
    data/presets.json): tinta leggera della barra, bordo, titolo e voce
    evidenziata dei menu nel colore del preset. I semafori restano
    rosso/giallo/verde."""
    import json
    pj = os.path.join(QUI, "..", "data", "presets.json")
    d = json.load(open(pj))
    prof = {k: v["accent"] for k, v in (d.get("presets", d)).items()
            if isinstance(v, dict) and v.get("accent")}
    out = {}
    for k, acc in prof.items():
        s = dict(VARIANTI["Vesper-Mac-Scuro"])
        s.update(tit_a1=mix(acc, "#3b3b3d", 0.16), tit_a2=mix(acc, "#323234", 0.08),
                 bordo_a=mix(acc, "#1f1f21", 0.55), testo_a=mix(acc, "#ffffff", 0.45),
                 menu_hl=mix(acc, "#1f1f21", 0.75))
        out["Vesper-Mac-Scuro-" + k] = s
        c = dict(VARIANTI["Vesper-Mac"])
        c.update(tit_a1=mix(acc, "#ececec", 0.10), tit_a2=mix(acc, "#dcdcdc", 0.05),
                 bordo_a=mix(acc, "#b4b4b4", 0.45), testo_a=mix(acc, "#3a3a3a", 0.40),
                 menu_hl=mix(acc, "#ffffff", 0.85))
        out["Vesper-Mac-" + k] = c
    return out


def main():
    base = cerchio()
    tutte = dict(VARIANTI)
    tutte.update(varianti_profilo())
    for n, v in tutte.items():
        d = os.path.join(DEST, n, "openbox-3")
        os.makedirs(d, exist_ok=True)
        for b in ("close", "iconify", "max", "max_toggled"):
            open(os.path.join(d, b + ".xbm"), "w").write(xbm(b, base))
            open(os.path.join(d, b + "_hover.xbm"), "w").write(xbm(b + "_hover", scava(base, simbolo(b))))
            open(os.path.join(d, b + "_pressed.xbm"), "w").write(xbm(b + "_pressed", scava(base, simbolo(b))))
        # pulsanti non usati nel layout mac: cerchio neutro
        for b in ("desk", "desk_toggled", "shade", "shade_toggled"):
            open(os.path.join(d, b + ".xbm"), "w").write(xbm(b, base))
        open(os.path.join(d, "themerc"), "w").write(themerc(n, v))
        print("tema:", n)


if __name__ == "__main__":
    main()
