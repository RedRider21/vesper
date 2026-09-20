# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Configurazione condivisa del pannello di Vesper.

Usato sia da `panel.py` (legge posizione/altezza/dimensione icone all'avvio)
sia dal Centro di Controllo (le cambia). Tutto persistito in
~/.config/vesper/panel.conf. La posizione e l'altezza sono riflesse nei
<margins> di rc.xml cosi' le finestre massimizzate non coprono il pannello.
Il numero di desktop virtuali (workspaces) e' gestito in rc.xml <desktops>.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from vesper import paths

HOME = paths.HOME
CONF = paths.config("panel.conf")
# Il rc.xml di Vesper, MAI quello dell'utente in ~/.config/openbox: quella è
# la configurazione della sua sessione Openbox e non ci si scrive.
RC_XML = Path(os.environ.get("VESPER_RC_XML", str(paths.config("openbox-rc.xml"))))

# default e limiti
PANEL_HEIGHT = 34          # compatibilita': altezza di default
DEF_HEIGHT = 34
MIN_HEIGHT, MAX_HEIGHT = 24, 64
DEF_ICON_PX = 22
MIN_ICON_PX, MAX_ICON_PX = 16, 40
MIN_DESKTOPS, MAX_DESKTOPS = 1, 12


def _read_conf() -> dict:
    cfg = {}
    try:
        for line in CONF.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
    except OSError:
        pass
    return cfg


def _write_conf(cfg: dict) -> None:
    CONF.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Configurazione pannello Vesper"]
    for k in ("position", "height", "icon_px"):
        if k in cfg:
            lines.append("%s = %s" % (k, cfg[k]))
    CONF.write_text("\n".join(lines) + "\n")


def _clamp(v, lo, hi, default):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def get_position() -> str:
    val = _read_conf().get("position", "bottom").lower()
    return val if val in ("top", "bottom") else "bottom"


def get_height() -> int:
    return _clamp(_read_conf().get("height"), MIN_HEIGHT, MAX_HEIGHT, DEF_HEIGHT)


def get_icon_px() -> int:
    return _clamp(_read_conf().get("icon_px"), MIN_ICON_PX, MAX_ICON_PX,
                  DEF_ICON_PX)


def set_config(position=None, height=None, icon_px=None) -> None:
    """Aggiorna solo le chiavi indicate, preservando le altre."""
    cfg = _read_conf()
    if "position" not in cfg:
        cfg["position"] = get_position()
    if "height" not in cfg:
        cfg["height"] = str(get_height())
    if "icon_px" not in cfg:
        cfg["icon_px"] = str(get_icon_px())
    if position in ("top", "bottom"):
        cfg["position"] = position
    if height is not None:
        cfg["height"] = str(_clamp(height, MIN_HEIGHT, MAX_HEIGHT, DEF_HEIGHT))
    if icon_px is not None:
        cfg["icon_px"] = str(_clamp(icon_px, MIN_ICON_PX, MAX_ICON_PX,
                                    DEF_ICON_PX))
    _write_conf(cfg)


def set_position(pos: str) -> None:
    set_config(position=pos)


def clear_openbox_margins() -> bool:
    """Azzera i <margins> in rc.xml. Ritorna True se ha dovuto cambiarli.

    Lo spazio per la barra NON si riserva più con i margini di Openbox ma con
    gli strut EWMH dichiarati dal pannello (vedi panel._set_struts): funzionano
    con qualunque gestore finestre e seguono la geometria vera della barra.
    Se restassero anche i margini, lo spazio verrebbe riservato DUE volte e le
    finestre massimizzate resterebbero corte del doppio."""
    try:
        txt = RC_XML.read_text()
    except OSError:
        return False
    nuovo = txt
    for lato in ("top", "bottom", "left", "right"):
        nuovo = re.sub(r"<%s>\d+</%s>" % (lato, lato),
                       "<%s>0</%s>" % (lato, lato), nuovo, count=1)
    if nuovo == txt:
        return False
    try:
        RC_XML.write_text(nuovo)
    except OSError:
        return False
    return True


def apply_openbox_margin(pos: str, height: int | None = None) -> None:
    """Compatibilità: i margini non servono più (li sostituiscono gli strut),
    quindi qui si azzerano e basta."""
    _ = pos, height
    clear_openbox_margins()


# ---- Desktop virtuali (workspaces) --------------------------------------
def get_desktops() -> int:
    try:
        txt = RC_XML.read_text()
    except OSError:
        return 1
    m = re.search(r"<desktops>.*?<number>\s*(\d+)\s*</number>", txt, re.S)
    if m:
        return _clamp(m.group(1), MIN_DESKTOPS, MAX_DESKTOPS, 1)
    return 1


def set_desktops(n: int) -> None:
    n = _clamp(n, MIN_DESKTOPS, MAX_DESKTOPS, 1)
    try:
        txt = RC_XML.read_text()
    except OSError:
        return
    # sostituisce il primo <number> dentro <desktops>...</desktops>
    def repl(m):
        return re.sub(r"(<number>\s*)\d+(\s*</number>)",
                      r"\g<1>%d\g<2>" % n, m.group(0), count=1)
    new = re.sub(r"<desktops>.*?</desktops>", repl, txt, count=1, flags=re.S)
    if new != txt:
        RC_XML.write_text(new)
    # rc.xml <number> e' letto SOLO all'avvio di Openbox (reconfigure NON cambia
    # il numero di desktop a runtime): applichiamo SUBITO via EWMH con wmctrl -n
    # (cosi' il pager si aggiorna), e teniamo rc.xml per i riavvii successivi.
    try:
        subprocess.Popen(["wmctrl", "-n", str(n)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        pass
    openbox_reconfigure()


def openbox_reconfigure() -> None:
    try:
        subprocess.Popen(["openbox", "--reconfigure"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        pass


def restart_panel() -> None:
    # Riavvio ROBUSTO del pannello, valido SIA se chiamato dal pannello stesso
    # SIA da un processo separato (Centro di Controllo).
    # NB: non si puo' uccidere os.getpid() (= il PID di CHI chiama): se e' la
    # finestra delle impostazioni, il pannello VECCHIO resta vivo e se ne
    # vedono DUE. Si uccide il PROCESSO DEL PANNELLO per pattern
    # ('python -m vesper.panel'), e il trucco 'vesper[.]panel' fa si' che il
    # killer NON uccida se stesso: la sua cmdline contiene le parentesi
    # quadre, che il regex '.' non matcha (gotcha storico: non re-derivarlo).
    subprocess.Popen(
        ["sh", "-c",
         "sleep 0.3; pkill -f 'vesper[.]panel' 2>/dev/null; "
         "sleep 0.4; exec vesper-panel"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True)


def move_panel(pos: str) -> None:
    """Cambia posizione: persiste, aggiorna i margini, ricarica, riavvia."""
    set_position(pos)
    apply_openbox_margin(pos)
    openbox_reconfigure()
    restart_panel()


def apply_layout(position=None, height=None, icon_px=None) -> None:
    """Salva altezza/icone/posizione, aggiorna i margini Openbox e riavvia."""
    set_config(position=position, height=height, icon_px=icon_px)
    pos = get_position()
    apply_openbox_margin(pos, get_height())
    openbox_reconfigure()
    restart_panel()
