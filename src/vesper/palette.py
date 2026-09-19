# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Chiaro o scuro: una sola mappa di colori per tutta l'interfaccia.

I CSS di Vesper (il tema base in `common.py` e quelli generati dai preset)
sono scritti nei colori della versione SCURA. Per la versione chiara non si
riscrive nulla: si sostituiscono i colori uno a uno con l'equivalente chiaro,
qui in un posto solo. Così un colore aggiunto al tema scuro continua a
funzionare, e per la versione chiara basta aggiungere la sua corrispondenza.

La modalità sta in `~/.config/vesper/ui-mode`:

    auto    (predefinito) la decide il preset attivo: i preset "chiari"
            accendono l'interfaccia chiara, gli altri quella scura
    chiaro  sempre chiara
    scuro   sempre scura
"""
from __future__ import annotations

import re

from vesper import paths

MODE_CONF = paths.config("ui-mode")
MODES = ("auto", "chiaro", "scuro")

# scuro -> chiaro. L'ordine non conta: la sostituzione è per valore esatto.
# I commenti dicono a cosa serve ogni colore, così la mappa resta leggibile.
LIGHT = {
    "#050a14": "#f4f7fa",   # sfondo finestra
    "#05090f": "#f4f7fa",   # sfondo finestra (stile telaio)
    "#070f1a": "#ffffff",   # sfondo campi di testo
    "#071019": "#e6ecf1",   # trough della barra di avanzamento
    "#0a1220": "#f7f9fb",   # sfondo finestra (stile vetro)
    "#0a1422": "#ffffff",   # tessere e schede
    "#0a141c": "#e9eef3",   # barra del titolo inattiva
    "#0a1a26": "#e9eef3",   # pannello, menu, popup
    "#080f18": "#eef2f6",   # pulsanti (stile telaio)
    "#0d1622": "#eef2f6",   # pulsanti
    "#070d14": "#ffffff",   # tessere (stile telaio)
    "#0d1a24": "#e9eef3",   # barra del titolo attiva
    "#101b28": "#dde5eb",   # hover linguette
    "#12202e": "#d7dfe6",   # bordo tessere
    "#122536": "#d7dfe6",   # bordo header (vetro)
    "#1a2d3a": "#dde5eb",   # trough barra avanzamento
    "#1a3a52": "#ccd6de",   # bordi
    "#163040": "#ccd6de",   # bordo pager
    "#17293a": "#ccd6de",   # bordi pulsanti
    "#173042": "#ccd6de",   # bordi (vetro)
    "#17475f": "#b9c6d0",   # bordo finestra attiva
    "#00334a": "#d6e9f5",   # selezione
    "#00475f": "#c3dff0",   # selezione (hover)
    "#c8f5ff": "#17242e",   # testo principale
    "#eafcff": "#0d1720",   # testo marcato
    "#dff6ff": "#0d1720",   # testo marcato (sottotitolo)
    "#eaf7ff": "#0d1720",   # testo barra del titolo
    "#e2f6ff": "#0d1720",   # wordmark
    "#5a8a9a": "#5d6b76",   # testo tenue
    "#7fb0c2": "#4a5a66",   # categorie del menu
    "#35d0e0": "#0f7f95",   # eyebrow
    "#45606e": "#9aa7b1",   # glifi inattivi
    "#2a4452": "#b9c6d0",   # glifi disabilitati
    "#223440": "#c6d1d9",   # glifi disabilitati (inattiva)
    "#03070f": "#dfe7ee",   # base della banda del menu
    # --- tema finestre "Core": colori Mint-Y scuro -> Mint-Y chiaro ---
    "#2b2b2b": "#e8e8e8",   # barra del titolo
    "#323232": "#f2f2f2",   # voci di menu
    "#e3e3e3": "#202020",   # testo attivo
    "#acacac": "#9d9d9d",   # testo inattivo
    "#d3d3d3": "#404040",   # glifi dei pulsanti
    "#7d7d7d": "#a5a5a5",   # glifi inattivi
    "#3a3a3a": "#d8d8d8",   # sfondo pulsante sotto il mouse
    "#4a4a4a": "#c9c9c9",   # sfondo pulsante premuto
    "#5a5a5a": "#bcbcbc",   # glifi disabilitati
    "#1f1f1f": "#c6c6c6",   # cornice
    "#6f6f6f": "#b0b0b0",   # chiudi inattivo
    "#464646": "#d6d6d6",   # separatore di menu
    "#10161c": "#ffffff",   # testo sulla voce di menu attiva
    "#ffffff": "#101010",   # glifo sotto il mouse
    # --- tema finestre "Core" (vecchi colori, tenuti per compatibilità) ---
    "#16222c": "#ccd6de",   # cornice inattiva
    "#17303f": "#dce6ed",   # sfondo del pulsante sotto il mouse
    "#7a2038": "#ffd9e1",   # sfondo del pulsante Chiudi sotto il mouse
    "#ffe6ec": "#7a2038",   # glifo del pulsante Chiudi sotto il mouse
    "#22040c": "#ffffff",   # glifo del Chiudi premuto
}

_HEX = re.compile(r"#[0-9a-fA-F]{6}")


def to_light(css: str) -> str:
    """Traduce un CSS scuro nella versione chiara (i colori non mappati, come
    l'accent del preset, restano come sono)."""
    def sub(m):
        return LIGHT.get(m.group(0).lower(), m.group(0))
    return _HEX.sub(sub, css)


def get_mode() -> str:
    """Modalità scelta: auto | chiaro | scuro."""
    try:
        v = MODE_CONF.read_text().strip().lower()
        return v if v in MODES else "auto"
    except OSError:
        return "auto"


def set_mode(mode: str) -> str:
    paths.ensure_config()
    mode = mode if mode in MODES else "auto"
    MODE_CONF.write_text(mode + "\n")
    return mode


def is_light(preset_light: bool | None = None) -> bool:
    """Vero se l'interfaccia va disegnata chiara. In "auto" decide il preset:
    chi chiama può passarne il flag per evitare un import circolare."""
    mode = get_mode()
    if mode == "chiaro":
        return True
    if mode == "scuro":
        return False
    if preset_light is not None:
        return bool(preset_light)
    try:                                   # import pigro: model importa noi
        from vesper.profiles import model
        return bool(model.preset_data().get("light"))
    except Exception:                      # noqa: BLE001
        return False
