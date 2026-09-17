# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Percorsi di Vesper: un unico posto dove sapere dove stanno le cose.

Questo modulo è il livello di disaccoppiamento del DE: tutto il resto del
codice chiede QUI dove leggere/scrivere, senza percorsi assoluti sparsi in
giro. Tre famiglie di percorsi:

- **configurazione utente** (`~/.config/vesper/`): scelte dell'utente (profilo
  attivo, accent, skin del pannello, layout del desktop, ...). Scrivibile.
- **cache utente** (`~/.cache/vesper/`): roba rigenerabile (thumbnail, file di
  refresh degli schermi). Cancellabile senza danni.
- **dati installati** (`/usr/share/vesper/`, `/usr/local/share/vesper/`,
  `~/.local/share/vesper/`): temi, sfondi, icone, preset. Sola lettura.
  Cercati in ordine, così un DE installato e uno avviato dal repo dei
  sorgenti funzionano entrambi.

`VESPER_CONFIG_HOME` e `VESPER_DATA_DIRS` permettono di spostare tutto (utile
per i test: si prova su una copia isolata senza toccare la config vera).
"""
from __future__ import annotations

import os
from pathlib import Path

HOME = Path(os.path.expanduser("~"))

APP = "vesper"

# ---- configurazione utente -------------------------------------------------

def _xdg(var: str, default: Path) -> Path:
    v = os.environ.get(var)
    return Path(v) if v else default


CONFIG_HOME = _xdg("VESPER_CONFIG_HOME",
                   _xdg("XDG_CONFIG_HOME", HOME / ".config") / APP)
CACHE_HOME = _xdg("VESPER_CACHE_HOME",
                  _xdg("XDG_CACHE_HOME", HOME / ".cache") / APP)
STATE_HOME = _xdg("VESPER_STATE_HOME",
                  _xdg("XDG_DATA_HOME", HOME / ".local" / "share") / APP)


def config(*parts: str) -> Path:
    """Percorso dentro la configurazione utente (non crea nulla)."""
    return CONFIG_HOME.joinpath(*parts)


def cache(*parts: str) -> Path:
    """Percorso dentro la cache utente (non crea nulla)."""
    return CACHE_HOME.joinpath(*parts)


def ensure_config() -> Path:
    """Crea (se serve) la cartella di configurazione e la ritorna."""
    try:
        CONFIG_HOME.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return CONFIG_HOME


def ensure_cache() -> Path:
    """Crea (se serve) la cartella di cache e la ritorna."""
    try:
        CACHE_HOME.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return CACHE_HOME


# ---- dati installati (sola lettura) ----------------------------------------

def _data_dirs() -> list[Path]:
    env = os.environ.get("VESPER_DATA_DIRS")
    if env:
        return [Path(p) for p in env.split(os.pathsep) if p]
    dirs = [STATE_HOME]
    # Installazione in un prefisso qualunque: se il pacchetto sta in
    # <prefisso>/lib/vesper/vesper, i dati stanno in <prefisso>/share/vesper.
    here = Path(__file__).resolve()
    prefix_share = here.parent.parent.parent / "share" / APP
    if prefix_share.is_dir():
        dirs.append(prefix_share)
    dirs += [Path("/usr/local/share") / APP, Path("/usr/share") / APP]
    # Avvio dal repo dei sorgenti: src/vesper/paths.py -> <repo>/data
    repo_data = here.parent.parent.parent / "data"
    if repo_data.is_dir():
        dirs.append(repo_data)
    # niente duplicati, ordine preservato
    seen, out = set(), []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


DATA_DIRS = _data_dirs()


def find_data(*parts: str) -> Path | None:
    """Primo percorso esistente fra i dati installati, o None."""
    for base in DATA_DIRS:
        p = base.joinpath(*parts)
        if p.exists():
            return p
    return None


def data_dirs(*parts: str) -> list[Path]:
    """Tutti i percorsi esistenti (per unire più sorgenti, es. temi)."""
    out = []
    for base in DATA_DIRS:
        p = base.joinpath(*parts)
        if p.is_dir() and p not in out:
            out.append(p)
    return out


# ---- file noti -------------------------------------------------------------
# Tenuti qui perché più moduli li condividono (pannello, centro di controllo,
# profili) e devono essere d'accordo sul nome.

ACCENT_CSS = config("accent.css")            # accent del preset attivo
WINDOW_STYLE_CSS = config("window-style.css")  # stile finestre (flat/vetro/telaio)
PANEL_THEME_CONF = config("panel-theme")     # skin del pannello
PANEL_CONF = config("panel.json")            # layout/applet del pannello
PROFILE_CONF = config("profile")             # preset di aspetto attivo
DESKTOP_ITEMS = config("desktop-items.json")  # posizioni icone del desktop
SCREENS_REFRESH = cache("screens-refresh")   # tocco dopo un cambio schermi
