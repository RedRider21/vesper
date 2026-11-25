#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Modelli delle icone del menu del tasto destro (Openbox), da NexusSec OS.

Openbox 3.6 mostra un'icona per voce (attributo icon="PERCORSO" nel menu; su
Debian/Mint/Alpine libobrender usa librsvg, quindi vanno bene gli SVG) ma NON
ricolora le icone simboliche: quelle di Adwaita sono grigio scuro e sul fondo
scuro del menu sparirebbero. Qui se ne fa una copia con il segnaposto
@COLORE@ al posto del colore; a runtime vesper.profiles.model
(write_menu_icons) le tinge col colore del preset in ~/.cache/vesper/menu-icons.

Sorgente: le icone simboliche di adwaita-icon-theme (CC-BY-SA 3.0 / LGPL-3,
vedi THIRD-PARTY.md) installate sul sistema, più la stella di Vesper.
Uso:   python3 tools/make-menu-icons.py [/usr/share/icons/Adwaita]
Output: data/menu-icons/<nome>.svg (committate).
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "menu-icons")
SEGNO = "@COLORE@"

# nome del file prodotto -> icona simbolica Adwaita ("vesper" = la nostra stella)
ICONE = {
    "terminal": "utilities-terminal",
    "files": "system-file-manager",
    "tools": "applications-utilities",
    "clipboard": "edit-paste",
    "nightlight": "night-light",
    "keyboard": "input-keyboard",
    "control-center": "preferences-system",
    "screen": "video-display",
    "lock": "system-lock-screen",
    "screenshot": "camera-photo",
    "look": "vesper",
    "preset": "vesper",
    "wallpaper": "preferences-desktop-wallpaper",
    "panel": "view-app-grid",
    "reload": "view-refresh",
    "shutdown": "system-shutdown",
}

_FILL = re.compile(r'(fill|stroke)="(?!none)[^"]*"')
_FILL_CSS = re.compile(r'(fill|stroke):(?!none)[^;"]+')
_COLOR = re.compile(r'\bcolor="[^"]*"')
_CURRENT = re.compile(r"currentColor")
_SVG_TAG = re.compile(r"<svg\b[^>]*>", re.S)

# Margine interno (px su 16): Openbox disegna l'icona ALTA QUANTO LA VOCE
# (menuframe.c: lato = ITEM_HEIGHT - 2*PADDING, non configurabile). Con le voci
# più alte dei nostri temi (ombra invisibile che aggiunge spazio) il disegno
# pieno risulterebbe troppo grande: il margine lo riporta alla misura giusta.
MARGINE = 3


def inquadra(svg: str) -> str:
    """Colore anche sulla radice (i tracciati senza fill ereditano: altrimenti
    restano NERI) e margine interno nel viewBox (icone su base 16)."""
    m = _SVG_TAG.search(svg)
    if not m:
        return svg
    tag = m.group(0)
    nuovo = re.sub(r'\s(width|height|viewBox|fill)="[^"]*"', "", tag)
    lato = 16 + 2 * MARGINE
    nuovo = nuovo[:-1].rstrip("/") + (
        ' width="16" height="16" viewBox="-%d -%d %d %d" fill="%s">'
        % (MARGINE, MARGINE, lato, lato, SEGNO))
    return svg.replace(tag, nuovo, 1)


def tingi(svg: str) -> str:
    svg = _FILL.sub(lambda m: '%s="%s"' % (m.group(1), SEGNO), svg)
    svg = _FILL_CSS.sub(lambda m: "%s:%s" % (m.group(1), SEGNO), svg)
    svg = _CURRENT.sub(SEGNO, svg)
    return inquadra(_COLOR.sub('color="%s"' % SEGNO, svg))


def trova(src: str, nome: str):
    if nome == "vesper":
        return os.path.join(ROOT, "data", "icons", "hicolor", "scalable",
                            "apps", "vesper-logo-symbolic.svg")
    fn = nome + "-symbolic.svg"
    for base, _dirs, files in os.walk(src):
        if fn in files:
            return os.path.join(base, fn)
    return None


def main(argv):
    src = argv[0] if argv else "/usr/share/icons/Adwaita"
    if not os.path.isdir(src):
        print(__doc__, file=sys.stderr)
        return 2
    os.makedirs(OUT, exist_ok=True)
    mancanti = []
    for out_name, nome in sorted(ICONE.items()):
        p = trova(src, nome)
        if not p or not os.path.isfile(p):
            mancanti.append(nome)
            continue
        with open(p, encoding="utf-8") as f:
            svg = tingi(f.read())
        with open(os.path.join(OUT, out_name + ".svg"), "w", encoding="utf-8") as f:
            f.write(svg)
    if mancanti:
        print("icone non trovate:", mancanti, file=sys.stderr)
        return 1
    print("%d modelli in %s" % (len(ICONE), OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
