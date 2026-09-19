#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
#
# Genera i temi Openbox COORDINATI COL PRESET.
#
# Da un template mono-colore (placeholder @ACCENT@) produce, per OGNI preset di
# aspetto, un tema Openbox statico tinto col suo colore. Così, scegliendo una
# FAMIGLIA (Retro / Cards) e cambiando preset, la decorazione delle finestre
# segue il colore, restando però un file STATICO e curato: niente generazione
# a runtime, che si è rivelata fragile.
#
# Famiglie:
#   - Retro  : flat chiaro, nel solco del tema "1977" di Thayer Williams.
#   - Cards  : stile macOS/iOS, con i tre pulsanti a sfera a sinistra.
#
# Uso:  python3 tools/make-openbox-themes.py
# Output: data/themes/Vesper-<Famiglia>-<preset>/openbox-3/
#
# I template stanno in tools/openbox-templates/<famiglia>/openbox-3/
# (themerc.in + le .xbm dei glifi). Rigenerare dopo aver toccato un template o
# i colori in data/presets.json.
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def gen_button_masks(dest_dir):
    """Genera le maschere .xbm dei pulsanti "a sfera" stile macOS/iOS.

    CONVENZIONE OPENBOX: un bit ACCESO (1) e' disegnato in image.color (il
    colore semaforo del pulsante); un bit SPENTO (0) e' trasparente e mostra lo
    sfondo (parentrelative = barra graphite). Quindi la maschera corretta e':
      - DISCO PIENO di bit accesi  -> la sfera colorata;
      - SIMBOLO scavato a bit spenti dentro il disco -> il glifo appare nel
        colore della barra (come inciso).
    In PIL mode "1": bianco(1) -> bit 1 (sfera), nero(0) -> bit 0 (trasparente).
    Le vecchie maschere erano INVERTITE (quadrato pieno con foro tondo): la
    sfera si vedeva come "cerchietto scuro" dentro un quadrato colorato.
    Se PIL non c'e', si tengono le .xbm gia' presenti nel template.
    """
    try:
        from PIL import Image, ImageDraw
    except Exception:
        print("  [i] PIL assente: uso le .xbm gia' presenti nel template")
        return
    # DIMENSIONE = 16px: Openbox NON scala le maschere dei pulsanti, le disegna
    # 1:1 e le RITAGLIA se piu' grandi del pulsante -> una maschera troppo grande
    # (es. 22px) si vede come una "fetta". 16px entra nel pulsante. Per un cerchio
    # 1-bit il piu' tondo possibile: disegno il DISCO in grigio ad alta risoluzione
    # (bordo-a-bordo), lo riduco con LANCZOS (antialias) e soglio -> scelta ottimale
    # dei pixel di contorno. Il GLIFO invece lo incido NITIDO alla dimensione
    # finale (linee crisp), cosi' - e + sono puliti e la X ben leggibile.
    # DIMENSIONE 14px: e' la dimensione STANDARD dei pulsanti Openbox. A 16px la
    # maschera eccedeva il pulsante e Openbox la RITAGLIAVA -> il disco (che tocca
    # i bordi) perdeva le calotte e sembrava "squadrato". A 14px combacia col
    # pulsante e resta TONDO. Geometria/dimensione allineate al tema Arc-Round
    # (the-zero885, GPL-3), la cui close.xbm e' un disco 14px con glifo scavato.
    S = 14
    q = 8
    SS = S * q
    C = (S - 1) / 2.0        # centro esatto (6.5): glifi SIMMETRICI
    ARM = 3.6                # semi-lunghezza dei tratti del glifo
    TH = 0.9                # semi-spessore dei tratti (~2px)

    def _disc():
        big = Image.new("L", (SS, SS), 0)
        ImageDraw.Draw(big).ellipse([0, 0, SS - 1, SS - 1], fill=255)
        return (big.resize((S, S), Image.LANCZOS)
                   .point(lambda p: 255 if p >= 128 else 0).convert("1"))

    def _hole(glyph, dx, dy):
        # dx,dy = distanza dal centro. Glifo = "foro" (bit 0) nel disco.
        if glyph == "close":                    # X: le due diagonali
            return (min(abs(dx - dy), abs(dx + dy)) <= TH
                    and max(abs(dx), abs(dy)) <= ARM)
        if glyph == "iconify":                  # - : barra orizzontale
            return abs(dy) <= TH and abs(dx) <= ARM
        # max / max_toggled -> + : barra orizzontale + verticale
        return ((abs(dx) <= TH and abs(dy) <= ARM)
                or (abs(dy) <= TH and abs(dx) <= ARM))

    def render(glyph):
        d = _disc()
        px = d.load()
        for y in range(S):
            for x in range(S):
                if px[x, y] and _hole(glyph, x - C, y - C):
                    px[x, y] = 0
        return d

    masks = {"close.xbm": "close", "iconify.xbm": "iconify",
             "max.xbm": "max", "max_toggled.xbm": "max"}
    for fname, glyph in masks.items():
        render(glyph).save(os.path.join(dest_dir, fname))
    print("  + maschere pulsanti a sfera rigenerate (%dpx, disco antialias + glifo simmetrico)" % S)


PRESETS_JSON = os.path.join(ROOT, "data/presets.json")
TEMPLATES = os.path.join(ROOT, "tools/openbox-templates")
THEMES_OUT = os.path.join(ROOT, "data/themes")

# famiglia -> suffisso del nome tema "Vesper-<Suffix>-<preset>"
FAMILIES = {"core": "Core", "retro": "Retro", "cards": "Cards"}


def load_light():
    """Quali preset vogliono l'interfaccia chiara."""
    with open(PRESETS_JSON, encoding="utf-8") as f:
        data = json.load(f)
    presets = data.get("presets", data)
    return {k: bool((v or {}).get("light")) for k, v in presets.items()}


def load_accents():
    """Colore d'accento di ogni preset, dal catalogo."""
    with open(PRESETS_JSON, encoding="utf-8") as f:
        data = json.load(f)
    presets = data.get("presets", data)
    out = {}
    for key, val in presets.items():
        acc = (val or {}).get("accent")
        if acc:
            out[key] = acc
    return out


def darken(hex_color, factor=0.72):
    """Restituisce una variante piu' scura di #rrggbb (per hover/pressed)."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    r, g, b = (max(0, min(255, int(c * factor))) for c in (r, g, b))
    return "#%02x%02x%02x" % (r, g, b)


def render(template_text, accent, light=False):
    """Sostituisce i colori del preset. Se il preset è CHIARO, la famiglia
    Core viene tradotta nella variante chiara con la stessa mappa usata per
    l'interfaccia (src/vesper/palette.py): un colore solo, in un posto solo.
    Retro è già chiaro di suo e Cards ha la barra graphite per scelta, quindi
    non si toccano."""
    out = (template_text
           .replace("@ACCENT_DK@", darken(accent))
           .replace("@ACCENT@", accent))
    if light:
        try:
            sys.path.insert(0, os.path.join(ROOT, "src"))
            from vesper.palette import to_light
            out = to_light(out)
        except Exception:
            pass
    return out


def gen_family(fam_dir, suffix, accents, light_map=None):
    src_ob = os.path.join(TEMPLATES, fam_dir, "openbox-3")
    themerc_in = os.path.join(src_ob, "themerc.in")
    if not os.path.isfile(themerc_in):
        print("  [!] template mancante: %s (salto)" % themerc_in)
        return 0
    with open(themerc_in, encoding="utf-8") as f:
        tpl = f.read()
    # La famiglia Cards usa maschere .xbm "a sfera": le (ri)generiamo nel
    # template stesso cosi' restano l'unica fonte di verita' (color-agnostiche).
    # Le maschere dei pulsanti le genera tools/make-button-masks.py e stanno
    # già nel template: qui si copiano soltanto.
    # glifi .xbm da copiare (color-agnostici); niente = pulsanti default Openbox
    xbms = [n for n in os.listdir(src_ob) if n.endswith(".xbm")]
    made = 0
    for key, accent in accents.items():
        name = "Vesper-%s-%s" % (suffix, key)
        dest_ob = os.path.join(THEMES_OUT, name, "openbox-3")
        os.makedirs(dest_ob, exist_ok=True)
        light = bool((light_map or {}).get(key)) and fam_dir == "core"
        with open(os.path.join(dest_ob, "themerc"), "w", encoding="utf-8") as f:
            f.write(render(tpl, accent, light=light))
        for x in xbms:
            shutil.copyfile(os.path.join(src_ob, x),
                            os.path.join(dest_ob, x))
        made += 1
        print("  + %s  (%s)" % (name, accent))
    return made


def gen_fallback(accents):
    """Scrive anche il tema SENZA suffisso (Vesper-Core): è il ripiego usato
    quando il tema del preset non c'è, quindi deve avere lo stesso aspetto.
    Prende il colore del preset predefinito del catalogo."""
    with open(PRESETS_JSON, encoding="utf-8") as f:
        default = json.load(f).get("default", "cyan")
    accent = accents.get(default) or "#00e5ff"
    src_ob = os.path.join(TEMPLATES, "core", "openbox-3")
    with open(os.path.join(src_ob, "themerc.in"), encoding="utf-8") as f:
        tpl = f.read()
    dest_ob = os.path.join(THEMES_OUT, "Vesper-Core", "openbox-3")
    os.makedirs(dest_ob, exist_ok=True)
    with open(os.path.join(dest_ob, "themerc"), "w", encoding="utf-8") as f:
        f.write(render(tpl, accent))
    for x in [n for n in os.listdir(src_ob) if n.endswith(".xbm")]:
        shutil.copyfile(os.path.join(src_ob, x), os.path.join(dest_ob, x))
    print("  + Vesper-Core  (ripiego, %s)" % accent)


def main():
    accents = load_accents()
    light_map = load_light()
    if not accents:
        print("Nessun accent trovato in data/presets.json", file=sys.stderr)
        return 1
    print("Preset: " + ", ".join("%s=%s" % kv for kv in accents.items()))
    total = 0
    for fam_dir, suffix in FAMILIES.items():
        print("Famiglia %s -> Vesper-%s-*" % (fam_dir, suffix))
        total += gen_family(fam_dir, suffix, accents, light_map)
    gen_fallback(accents)
    print("Fatto: %d temi generati in %s" % (total + 1, THEMES_OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
