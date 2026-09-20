# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Skin colore del pannello (barra + menu + popup).

INDIPENDENTI dai preset di aspetto: una skin definisce una palette FISSA per la
barra e i suoi menu; la skin speciale "profile" NON impone colori e lascia
decidere all'accent del preset attivo (comportamento predefinito).

Le skin sono file CSS:
  <dati installati>/panel-themes/*.css   (di serie, generate da
                                          tools/make-panel-themes.py)
  ~/.config/vesper/panel-themes/*.css    (aggiunte dall'utente: basta lasciarci
                                          un .css e compare nell'elenco)
La scelta e' in ~/.config/vesper/panel-theme (una riga: l'id della skin).

Modulo SENZA dipendenze GTK: importabile da CLI e dal pannello. Il caricamento
del CSS a runtime lo fa vesper.common (apply_panel_theme_live).
"""
from __future__ import annotations

import re
from pathlib import Path

from vesper import paths

try:
    from vesper.i18n import t as _t
except Exception:                       # noqa: BLE001
    def _t(chiave, **kw):               # ripiego: mostra la chiave
        return chiave

CONF = paths.PANEL_THEME_CONF
USER_DIR = paths.config("panel-themes")
DEFAULT = "profile"


def _sys_dirs() -> list[Path]:
    """Cartelle delle skin di serie (dati installati o repo dei sorgenti)."""
    return paths.data_dirs("panel-themes")


def _meta_name(path: Path) -> str:
    """Nome leggibile da un commento '/* name: ... */' in testa al file."""
    try:
        for line in path.read_text().splitlines()[:6]:
            m = re.search(r"name:\s*(.+?)\s*(?:\*/|$)", line)
            if m:
                return m.group(1).strip()
    except OSError:
        pass
    return path.stem


def list_themes():
    """Ritorna [(id, nome, sorgente)]; 'profile' e' sempre la prima voce.
    Un file utente con lo STESSO id di una skin di sistema la sostituisce."""
    out = [("profile", _t("v.skin.follow_preset"), "builtin")]
    seen = {"profile"}
    # utente prima cosi' un id ripetuto mostra la variante utente
    for d, src in [(USER_DIR, "utente")] + [(d, "sistema") for d in _sys_dirs()]:
        try:
            files = sorted(d.glob("*.css"))
        except OSError:
            files = []
        for f in files:
            tid = f.stem
            if tid in seen:
                continue
            seen.add(tid)
            out.append((tid, _meta_name(f), src))
    return out


def css_path(tid: str):
    """Percorso del CSS per l'id (utente prevale), o None per 'profile'/assente."""
    if not tid or tid == "profile":
        return None
    for d in [USER_DIR] + _sys_dirs():
        p = d / (tid + ".css")
        if p.exists():
            return p
    return None


def get_theme() -> str:
    try:
        v = CONF.read_text().strip().splitlines()[0].strip()
        return v or DEFAULT
    except (OSError, IndexError):
        return DEFAULT


def set_theme(tid: str) -> None:
    CONF.parent.mkdir(parents=True, exist_ok=True)
    CONF.write_text((tid or DEFAULT) + "\n")


def valid_ids():
    return [t[0] for t in list_themes()]
