# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Preset di aspetto di Vesper: accent, sfondo, icone, stile finestre.

Un **preset** è un look completo del desktop: colore d'accento, sfondo,
tema icone, stile delle finestre. Cambiarlo ricolora al volo barra, menu,
Centro di Controllo e finestre già aperte (i CSS generati qui sono sorvegliati
da `vesper.common`, che li ricarica a caldo).

- catalogo preset: <dati installati>/presets.json
- preset attivo:   ~/.config/vesper/profile
- sfondo scelto a mano (vince sul preset): ~/.config/vesper/wallpaper
- stile finestre:  ~/.config/vesper/window-style
- famiglia tema finestre: ~/.config/vesper/theme

Nessuna dipendenza GTK: importabile dalla CLI (`vesper-profile`) e dal
pannello. I percorsi arrivano da `vesper.paths` (ridefinibili via
VESPER_CONFIG_HOME / VESPER_DATA_DIRS per provare su una copia isolata).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from vesper import paths

HOME = paths.HOME
CONF_DIR = paths.CONFIG_HOME

# ---- file di stato/configurazione ----
USER_PROFILE_FILE = paths.PROFILE_CONF          # preset attivo
ACCENT_CSS = paths.ACCENT_CSS                   # CSS accent generato
WALLPAPER_CONF = CONF_DIR / "wallpaper"         # sfondo scelto a mano
WALLPAPER_MODE_CONF = CONF_DIR / "wallpaper-mode"
WALLPAPER_MODES = ("stretch", "fit", "center", "tile")
DEFAULT_WALLPAPER_MODE = "stretch"

# rc.xml di Openbox: contiene <theme><name>...</name></theme>. Cambiare tema
# finestre = riscrivere quel nome e fare "openbox --reconfigure".
RC_XML = Path(os.environ.get(
    "VESPER_RC_XML", str(HOME / ".config" / "openbox" / "rc.xml")))
# Famiglia del tema finestre COORDINATA col preset (~/.config/vesper/theme):
#   core  -> Vesper-Core (scuro fisso, NON segue il preset) [default]
#   retro -> Vesper-Retro-<preset> (flat chiaro)
#   cards -> Vesper-Cards-<preset> (stile "scheda", header colorato)
#   raw:<nome> -> un qualsiasi tema Openbox installato, fisso (non coordinato)
THEME_FAMILY_FILE = CONF_DIR / "theme"
THEME_FAMILIES = ("core", "retro", "cards")
THEME_PREFIX = "Vesper"
FALLBACK_OB_THEME = "Vesper-Core"
# titleLayout di Openbox: default = pulsanti a DESTRA (N=icona, L=titolo, I/M/C);
# Cards (stile macOS) = pulsanti a SINISTRA (C=chiudi, I=minimizza, M=massimizza).
OB_TITLELAYOUT_DEFAULT = "NLIMC"
OB_TITLELAYOUT_LEFT = "CIML"
# Compositor per angoli arrotondati/vetro reale: attivo con Cards o stile aero.
PICOM_CONF = HOME / ".config" / "picom.conf"

DEFAULT_ACCENT = "#00e5ff"

_JSON_CACHE: dict = {}   # path -> (mtime, dati)


def _load_json(path: Path) -> dict:
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {}
    cached = _JSON_CACHE.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    _JSON_CACHE[path] = (mtime, data)
    return data


# ---------------------------------------------------------------- catalogo
# Preset di serie in caso di catalogo assente (Vesper avviato dai sorgenti o
# installazione senza presets.json): il DE deve partire comunque.
_BUILTIN = {
    "default": "vesper",
    "presets": {
        "vesper": {"name": "Vesper", "desc": "Blu notte con accento cyan.",
                   "accent": "#00e5ff", "icon": "weather-clear-night-symbolic"},
    },
}


def _catalog() -> dict:
    p = paths.find_data("presets.json")
    data = _load_json(p) if p else {}
    return data if data.get("presets") else _BUILTIN


def presets() -> dict:
    """Catalogo dei preset: chiave -> {name, desc, accent, wallpaper, icon}."""
    return _catalog().get("presets", {})


def default_preset() -> str:
    return _catalog().get("default", "vesper")


def preset_data(key: str | None = None) -> dict:
    if key is None:
        key = current_preset()
    return presets().get(key, {})


def accent(key: str | None = None) -> str:
    return preset_data(key).get("accent", DEFAULT_ACCENT)


# ---------------------------------------------------------------- stato
def current_preset() -> str:
    """Chiave del preset attivo (~/.config/vesper/profile)."""
    try:
        txt = USER_PROFILE_FILE.read_text().strip()
    except OSError:
        return default_preset()
    key = ""
    if txt.startswith("{"):
        try:
            key = json.loads(txt).get("active_profile", "")
        except ValueError:
            key = ""
    else:
        key = txt.splitlines()[0].strip() if txt else ""
    return key if key in presets() else default_preset()


def set_current(key: str) -> None:
    """Salva il preset attivo nella configurazione utente."""
    paths.ensure_config()
    USER_PROFILE_FILE.write_text(json.dumps({"active_profile": key}) + "\n")


# ---------------------------------------------------------------- sfondo
# Lo sfondo scelto a mano (voce separata, indipendente dal preset) vince su
# quello del preset e sopravvive al cambio preset. Vuoto/assente = si torna
# allo sfondo del preset. Gestito da `vesper-wallpaper`.

def wallpaper_dirs() -> list[Path]:
    """Cartelle degli sfondi di serie (dati installati o repo dei sorgenti)."""
    return paths.data_dirs("backgrounds")


def wallpaper_path(key: str | None = None) -> Path | None:
    """Sfondo da usare: prima la scelta manuale, poi quello del preset.
    None se nessuno dei due esiste (il desktop disegna la tinta piatta)."""
    try:
        ov = WALLPAPER_CONF.read_text().strip()
        if ov:
            p = Path(ov).expanduser()
            if p.is_file():
                return p
    except OSError:
        pass
    name = preset_data(key).get("wallpaper")
    if not name:
        return None
    for d in wallpaper_dirs():
        p = d / name
        if p.is_file():
            return p
    return None


def wallpaper_mode() -> str:
    try:
        m = WALLPAPER_MODE_CONF.read_text().strip().lower()
        if m in WALLPAPER_MODES:
            return m
    except OSError:
        pass
    return DEFAULT_WALLPAPER_MODE


def set_wallpaper_mode(mode: str) -> None:
    if mode not in WALLPAPER_MODES:
        mode = DEFAULT_WALLPAPER_MODE
    paths.ensure_config()
    WALLPAPER_MODE_CONF.write_text(mode + "\n")


def set_wallpaper(path: Path | None, remember: bool = True) -> bool:
    """Imposta lo sfondo.

    In Vesper lo sfondo lo disegna il NOSTRO desktop (`vesper-files
    --desktop`), che sorveglia questo file di configurazione e si ridisegna da
    solo: qui basta scriverlo (niente pcmanfm, niente feh in condizioni
    normali). Il fallback esterno serve solo quando il pannello di Vesper gira
    sotto un altro desktop, dove nessuno disegnerebbe lo sfondo.
    """
    if path is not None and not Path(path).is_file():
        return False
    if remember:
        paths.ensure_config()
        WALLPAPER_CONF.write_text((str(path) if path else "") + "\n")
    if _vesper_desktop_running():
        return True                       # se ne occupa il desktop di Vesper
    return _set_wallpaper_external(path)


def _vesper_desktop_running() -> bool:
    try:
        return subprocess.run(["pgrep", "-f", "vesper-files.*--desktop"],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0
    except (FileNotFoundError, OSError):
        return False


def _set_wallpaper_external(path: Path | None) -> bool:
    """Ripiego per quando il desktop di Vesper non gira (uso sotto altri WM)."""
    if path is None:
        return False
    mode = wallpaper_mode()
    for cmd in (["xwallpaper", {"stretch": "--stretch", "fit": "--zoom",
                                "center": "--center", "tile": "--tile"}[mode],
                 str(path)],
                ["feh", {"stretch": "--bg-scale", "fit": "--bg-fill",
                         "center": "--bg-center", "tile": "--bg-tile"}[mode],
                 str(path)],
                ["hsetroot", "-fill", str(path)]):
        if not shutil.which(cmd[0]):
            continue
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            return True
        except OSError:
            continue
    return False


# ---------------------------------------------------------------- aspetto
def write_accent_css(key: str | None = None) -> None:
    """Genera ~/.config/vesper/accent.css con gli accenti del preset (override
    mirati, caricati da vesper.common.apply_css)."""
    ac = accent(key)
    try:
        h = ac.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        r, g, b = 0, 229, 255
    rgb = f"{r},{g},{b}"
    css = f"""/* accent del preset attivo - generato da vesper.profiles.model
   Colorazione raffinata su barra, menu e finestre (accent usato con
   parsimonia: filetti, tag, aloni morbidi). Caricato con priorita' sopra il
   tema base (vedi vesper.common.apply_css). */

/* --- BARRA: filetto accento + stati con alone morbido --- */
.vesper-panel {{ border-top: 2px solid {ac}; }}
.vesper-panel.vesper-panel-top {{ border-top: none; border-bottom: 2px solid {ac}; }}
.vesper-panel button.vesper-menu, .vesper-panel button.vesper-menu image {{ color: {ac}; }}
.vesper-panel button image {{ color: {ac}; }}
.vesper-panel button:hover {{ background-color: rgba({rgb},0.14); border-color: transparent; }}
.vesper-panel button.vesper-icon:hover image {{ color: {ac}; }}
.vesper-panel button.vesper-task-active {{
  color: {ac}; background-color: rgba({rgb},0.14);
  border-color: transparent; box-shadow: inset 0 -2px {ac}; }}
.vesper-panel button.vesper-pager-active {{
  color: #050a14; background-color: {ac}; border-color: {ac}; }}

/* --- MENU: striscia, categorie a tag, hover e selezione --- */
.vesper-menu-strip {{ background-image: linear-gradient(to top, #03070f, {ac} 60%, {ac}); }}
label.vesper-menu-cat {{ color: {ac}; }}
button.vesper-menu-cat {{ border-left-color: {ac}; }}
button.vesper-menu-cat:hover {{ border-left-color: {ac}; color: {ac};
  background-image: linear-gradient(to right, rgba({rgb},0.16), rgba({rgb},0)); }}
button.vesper-menu-item image {{ color: {ac}; }}
button.vesper-menu-item:hover {{ background-color: rgba({rgb},0.14); border-color: transparent; }}
button.vesper-menu-item:hover label {{ color: {ac}; }}
button.vesper-app-item:hover {{ border-left-color: {ac}; background-color: rgba({rgb},0.12); }}

/* --- FINESTRE (Centro di Controllo, viste, dialoghi): raffinato --- */
.vesper-section {{ color: {ac}; border-bottom-color: {ac}; }}
.vesper-headerbar {{ border-bottom-color: {ac}; box-shadow: inset 0 -2px {ac}; }}
.vesper-headerbar label.title {{ color: {ac}; }}
.vesper-eyebrow {{ color: {ac}; }}
.vesper-key, .vesper-card-title {{ color: {ac}; }}
.vesper-tile-badge {{ background-color: rgba({rgb},0.16); }}
.vesper-tile-badge image {{ color: {ac}; }}
.vesper-tile:hover, .vesper-card:hover {{ border-color: {ac}; box-shadow: inset 0 2px {ac}; }}
button.vesper-primary {{ color: {ac}; border-color: {ac}; background-color: rgba({rgb},0.12); }}
button.vesper-primary:hover {{ background-color: rgba({rgb},0.22); box-shadow: 0 6px 22px rgba({rgb},0.28); }}
button:hover {{ border-color: {ac}; background-color: rgba({rgb},0.12); }}
button:hover image {{ color: {ac}; }}
entry:focus {{ border-color: {ac}; box-shadow: 0 0 0 3px rgba({rgb},0.18); }}
switch:checked {{ background-color: rgba({rgb},0.30); border-color: {ac}; }}
switch:checked slider {{ background-color: {ac}; }}
notebook tab:checked {{ color: {ac}; box-shadow: inset 0 -2px {ac}; }}
progressbar > trough > progress {{ background-color: {ac}; }}
treeview:selected {{ background-color: rgba({rgb},0.20); color: {ac}; }}
list row:selected {{ background-color: rgba({rgb},0.20); box-shadow: inset 3px 0 {ac}; }}
list row:selected label {{ color: {ac}; }}
scale highlight {{ background-color: {ac}; }}
scale slider {{ background-color: {ac}; border-color: {ac}; }}
"""
    paths.ensure_config()
    ACCENT_CSS.write_text(css)
    # rigenera anche lo stile finestre (usa lo stesso accent del preset)
    write_window_style_css(key=key)


# ---- Stile finestre (flat / vetro / telaio / aero) commutabile ------------
WINDOW_STYLE_CONF = CONF_DIR / "window-style"
WINDOW_STYLE_CSS = paths.WINDOW_STYLE_CSS
#   aero = "Vetro reale": finestre semi-trasparenti + sfocatura del compositor
#          (picom, blur dual_kawase) dietro, effetto acrilico/Aero stile Windows.
#          A differenza di 'vetro' (che simula il vetro col solo CSS) questo
#          rende le finestre DAVVERO traslucide, quindi ACCENDE picom anche senza
#          la famiglia Cards (vedi _picom_wanted / set_window_style).
WINDOW_STYLES = ("flat", "vetro", "telaio", "aero")
DEFAULT_WINDOW_STYLE = "vetro"


def get_window_style() -> str:
    """Ritorna lo stile finestre scelto (default 'vetro')."""
    try:
        s = WINDOW_STYLE_CONF.read_text().strip().lower()
        if s in WINDOW_STYLES:
            return s
    except OSError:
        pass
    return DEFAULT_WINDOW_STYLE


def set_window_style(style: str, key: str | None = None) -> None:
    """Persiste lo stile e rigenera il CSS relativo con l'accent corrente."""
    if style not in WINDOW_STYLES:
        style = DEFAULT_WINDOW_STYLE
    paths.ensure_config()
    WINDOW_STYLE_CONF.write_text(style + "\n")
    write_window_style_css(style=style, key=key)
    # 'aero' richiede il compositor per la trasparenza/sfocatura reale; gli altri
    # stili non lo pretendono, ma potrebbe servire ancora alla famiglia Cards.
    _manage_picom(_picom_wanted())


def write_window_style_css(style: str | None = None, key: str | None = None) -> None:
    """Genera ~/.config/vesper/window-style.css per lo stile scelto, tinto con
    l'accent del preset. Caricato SOPRA accent.css (vedi vesper.common)."""
    if style is None:
        style = get_window_style()
    ac = accent(key)
    try:
        h = ac.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        r, g, b = 0, 229, 255
    rgb = f"{r},{g},{b}"
    head = ("/* stile finestre Vesper: %s - generato da vesper.profiles.model.\n"
            "   Caricato sopra accent.css (vesper.common.apply_css). */\n" % style)
    if style == "flat":
        css = head + "/* Flat arrotondato: nessun override, usa il tema base + accent. */\n"
    elif style == "aero":
        # VETRO REALE (Aero/acrilico): lo SFONDO della finestra e' semi-trasparente
        # (alpha < 1) cosi' picom, che sfoca lo sfondo dietro le finestre traslucide
        # (blur dual_kawase in picom.conf), crea il tipico effetto "vetro smerigliato"
        # di Windows. GTK3 usa il visual RGBA quando c'e' un compositor, quindi
        # basta l'alpha nel background per rendere la finestra davvero traslucida.
        # Testi e tessere restano su fondi piu' pieni per la leggibilita'.
        css = head + f"""
/* VETRO REALE (trasparenza + sfocatura del compositor). Serve picom acceso:
   lo accende set_window_style quando questo stile e' attivo. */
window, .background, dialog {{
  background-color: rgba(10,18,32,0.68);
}}
.vesper-headerbar {{
  background-color: rgba({rgb},0.12);
  border-top: 2px solid {ac};
  border-bottom: 1px solid rgba({rgb},0.22);
}}
.vesper-tile, .vesper-card, .vesper-profilo-card {{
  background-color: rgba({rgb},0.10);
  border: 1px solid rgba({rgb},0.20);
  border-radius: 10px;
}}
.vesper-tile:hover, .vesper-card:hover, .vesper-profilo-card:hover {{
  background-color: rgba({rgb},0.18); border-color: {ac};
  box-shadow: inset 0 0 0 1px rgba({rgb},0.30); }}
.vesper-profilo-card.sel {{ border-color: {ac}; background-color: rgba({rgb},0.22);
  box-shadow: inset 0 0 0 1px rgba({rgb},0.40); }}
button {{ background-color: rgba({rgb},0.10); border: 1px solid rgba({rgb},0.28);
  border-radius: 9px; }}
button:hover {{ border-color: {ac}; background-color: rgba({rgb},0.18); }}
button.vesper-primary {{ background-color: {ac}; color: #04121a; border-color: {ac};
  box-shadow: 0 0 18px rgba({rgb},0.55); }}
entry {{ background-color: rgba(5,9,15,0.55); border: 1px solid rgba({rgb},0.24); }}
textview, textview text {{ background-color: rgba(5,9,15,0.45); }}
frame > border {{ border-color: rgba({rgb},0.18); }}
progressbar > trough {{ background-color: rgba(26,45,58,0.6); border-radius: 999px; }}
progressbar > trough > progress {{ border-radius: 999px; background-color: {ac}; }}
"""
    elif style == "telaio":
        # Fedele al mockup "Telaio a contorno": fondo quasi nero (#05090f),
        # header con barretta laterale d'accento, tessere #070d14 col bordo
        # d'accento e un filetto verticale sinistro. Primario pieno.
        css = head + f"""
/* TELAIO A CONTORNO (neon outline): fondo quasi NERO, elementi definiti da un
   bordo d'accento e da una barretta laterale. Estetica terminale/cyber. */
window, .background, dialog {{ background-color: #05090f; }}
.vesper-headerbar {{
  background-color: #070d14;
  border-top: none;
  border-left: 3px solid {ac};
  border-bottom: 1px solid rgba({rgb},0.24);
  box-shadow: none;
}}
.vesper-tile, .vesper-card, .vesper-profilo-card {{
  background-color: #070d14;
  border: 1px solid rgba({rgb},0.20);
  border-left: 3px solid rgba({rgb},0.55);
  border-radius: 6px;
}}
.vesper-tile:hover, .vesper-card:hover, .vesper-profilo-card:hover {{
  background-color: rgba({rgb},0.10);
  border-color: {ac}; border-left-color: {ac}; box-shadow: none; }}
.vesper-profilo-card.sel {{ border-color: {ac}; border-left-color: {ac};
  background-color: rgba({rgb},0.12); }}
.vesper-section {{ border-bottom: 1px solid rgba({rgb},0.24); }}
button {{ border-radius: 5px; background-color: #080f18; border: 1px solid rgba({rgb},0.30); }}
button:hover {{ border-color: {ac}; background-color: rgba({rgb},0.10); }}
button.vesper-primary {{ background-color: {ac}; color: #04121a; border-color: {ac};
  box-shadow: none; }}
entry {{ border-radius: 5px; background-color: #05090f; border: 1px solid rgba({rgb},0.24); }}
frame > border {{ border-color: rgba({rgb},0.24); border-radius: 6px; }}
notebook tab {{ border-radius: 5px 5px 0 0; }}
progressbar > trough {{ background-color: #071019; border-radius: 999px; }}
progressbar > trough > progress {{ border-radius: 999px; background-color: {ac}; }}
switch {{ background-color: #05090f; border-color: rgba({rgb},0.30); }}
"""
    else:  # vetro (default)
        # FEDELE AL MOCKUP "Vetro / HUD". Il tratto distintivo NON e' un fondo
        # piu' chiaro (il mockup resta su #0a1220, vicino al base) ma:
        #  1) la TRAMA A RIGHE verticali nell'header (repeating-linear-gradient);
        #  2) il filetto superiore d'accento 2px + velatura sull'header;
        #  3) le tessere con velatura d'accento e bordo ciano;
        #  4) il primario pieno con glow.
        # NB GTK3: gradienti con sintassi vecchia (to bottom/to right, niente
        # angoli), e repeating-linear-gradient con DUE stop espliciti per colore.
        css = head + f"""
/* VETRO / HUD: velatura d'accento, filo superiore colorato e trama a righe
   nell'header. "Console operativa" ma elegante (identico al mockup). */
window, .background, dialog {{
  background-color: #0a1220;
  background-image: linear-gradient(to bottom, rgba({rgb},0.06), rgba(10,18,32,0.0) 55%);
}}
.vesper-headerbar {{
  background-color: #0a1220;
  border-top: 2px solid {ac};
  border-bottom: 1px solid #122536;
  background-image:
    repeating-linear-gradient(to right,
      rgba({rgb},0.07) 0px, rgba({rgb},0.07) 1px,
      rgba(10,18,32,0.0) 1px, rgba(10,18,32,0.0) 7px),
    linear-gradient(to bottom, rgba({rgb},0.10), rgba(10,18,32,0.0));
}}
.vesper-tile, .vesper-card, .vesper-profilo-card {{
  background-color: rgba({rgb},0.05);
  border: 1px solid rgba({rgb},0.16);
  border-radius: 10px;
}}
.vesper-tile:hover, .vesper-card:hover, .vesper-profilo-card:hover {{
  background-color: rgba({rgb},0.12); border-color: {ac};
  box-shadow: inset 0 0 0 1px rgba({rgb},0.30); }}
.vesper-profilo-card.sel {{ border-color: {ac}; background-color: rgba({rgb},0.16);
  box-shadow: inset 0 0 0 1px rgba({rgb},0.40); }}
button {{ background-color: rgba({rgb},0.05); border: 1px solid #173042; border-radius: 9px; }}
button:hover {{ border-color: {ac}; background-color: rgba({rgb},0.12); }}
button.vesper-primary {{ background-color: {ac}; color: #04121a; border-color: {ac};
  box-shadow: 0 0 18px rgba({rgb},0.55); }}
button.vesper-primary:hover {{ background-color: {ac}; box-shadow: 0 0 24px rgba({rgb},0.80); }}
entry {{ background-color: rgba({rgb},0.04); border: 1px solid #173042; }}
frame > border {{ border-color: rgba({rgb},0.16); }}
progressbar > trough {{ background-color: #1a2d3a; border-radius: 999px; }}
progressbar > trough > progress {{ border-radius: 999px; background-color: {ac}; }}
"""
    paths.ensure_config()
    WINDOW_STYLE_CSS.write_text(css)


def _mix(fg: str, bg: str, frac: float) -> str:
    """Miscela fg su bg (frac = quota di fg, 0..1) -> #rrggbb."""
    def _rgb(h):
        h = h.lstrip("#")
        return [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    try:
        f, b = _rgb(fg), _rgb(bg)
    except (ValueError, IndexError):
        return bg
    return "#%02x%02x%02x" % tuple(
        max(0, min(255, round(frac * f[i] + (1 - frac) * b[i]))) for i in range(3))


def theme_family() -> str:
    """Famiglia tema finestre scelta (~/.config/vesper/theme). Default: 'core'."""
    try:
        v = THEME_FAMILY_FILE.read_text().strip()
        if v:
            return v
    except OSError:
        pass
    return "core"


def set_theme_family(fam: str) -> None:
    """Salva la famiglia tema e la applica al preset corrente."""
    paths.ensure_config()
    try:
        THEME_FAMILY_FILE.write_text(fam.strip() + "\n")
    except OSError:
        return
    set_window_theme()


def _theme_installed(name: str) -> bool:
    for d in [HOME / ".themes", HOME / ".local" / "share" / "themes",
              Path("/usr/share/themes")] + paths.data_dirs("themes"):
        if (d / name / "openbox-3" / "themerc").is_file():
            return True
    return False


def resolve_ob_theme(family: str | None = None, key: str | None = None) -> str:
    """Dal (famiglia, preset) al nome del tema Openbox concreto da applicare.
    Le famiglie coordinate (retro/cards) mappano su Vesper-<Fam>-<preset>; con
    fallback alla variante -base e infine a Vesper-Core se il tema manca."""
    if family is None:
        family = theme_family()
    if key is None:
        key = current_preset()
    if family.startswith("raw:"):
        name = family[4:].strip()
        return name if _theme_installed(name) else FALLBACK_OB_THEME
    if family == "retro":
        cand = f"{THEME_PREFIX}-Retro-{key}"
    elif family == "cards":
        cand = f"{THEME_PREFIX}-Cards-{key}"
    else:
        return FALLBACK_OB_THEME
    if not _theme_installed(cand):
        base = cand.rsplit("-", 1)[0] + "-base"
        cand = base if _theme_installed(base) else FALLBACK_OB_THEME
    return cand


def _apply_rc(name: str, layout: str, reconfigure: bool = True) -> None:
    """Scrive in rc.xml sia <theme><name> sia <titleLayout> (una sola
    read-modify-write) e ricarica Openbox una volta sola."""
    try:
        txt = RC_XML.read_text()
    except OSError:
        return
    new = re.sub(r"(<theme>.*?<name>)[^<]*(</name>)",
                 r"\g<1>" + name + r"\g<2>", txt, count=1, flags=re.DOTALL)
    new = re.sub(r"<titleLayout>[^<]*</titleLayout>",
                 "<titleLayout>" + layout + "</titleLayout>", new, count=1)
    if new != txt:
        try:
            RC_XML.write_text(new)
        except OSError:
            return
    if reconfigure:
        try:
            subprocess.Popen(["openbox", "--reconfigure"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (FileNotFoundError, OSError):
            pass


def _picom_wanted() -> bool:
    """picom serve se: la famiglia tema e' 'cards' (angoli arrotondati) OPPURE
    lo stile finestre e' 'aero' (trasparenza + sfocatura reale). Cosi' la
    scelta del vetro reale e' INDIPENDENTE dal preset e dalla decorazione."""
    try:
        return theme_family() == "cards" or get_window_style() == "aero"
    except Exception:                            # noqa: BLE001
        return False


def _manage_picom(enable: bool) -> None:
    """Compositor per gli angoli arrotondati dello stile Cards. Avvia picom se
    serve (e non gira gia'), lo ferma altrimenti. Best-effort: se picom non c'e'
    o il backend GLX non e' disponibile (certe VM), non blocca nulla."""
    try:
        running = subprocess.run(["pgrep", "-x", "picom"],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL).returncode == 0
    except (FileNotFoundError, OSError):
        running = False
    if enable and not running:
        try:
            cmd = ["picom", "-b"]
            if PICOM_CONF.is_file():
                cmd += ["--config", str(PICOM_CONF)]
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except (FileNotFoundError, OSError):
            pass
    elif not enable and running:
        try:
            subprocess.run(["pkill", "-x", "picom"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (FileNotFoundError, OSError):
            pass


def set_window_theme(key: str | None = None, reconfigure: bool = True) -> None:
    """Applica il tema finestre Openbox COORDINATO col preset.
    La famiglia scelta (~/.config/vesper/theme) decide QUALE tema statico usare:
    'core' = scuro fisso; 'retro'/'cards' = Vesper-<Fam>-<preset>, cosi' la
    decorazione segue il colore del preset restando un file STATICO e curato
    (nessuna generazione a runtime: e' fragile e non deterministica). Per
    'cards' (stile macOS) sposta anche i pulsanti a SINISTRA (titleLayout) e
    accende picom per gli angoli arrotondati; per le altre famiglie ripristina
    i pulsanti a destra e spegne picom."""
    fam = theme_family()
    name = resolve_ob_theme(fam, key)
    layout = OB_TITLELAYOUT_LEFT if fam == "cards" else OB_TITLELAYOUT_DEFAULT
    _apply_rc(name, layout, reconfigure=reconfigure)
    _manage_picom(_picom_wanted())


# ---------------------------------------------------------------- tema icone
def icon_theme_name(key: str | None = None) -> str:
    """Nome del tema icone tinto per il preset (Vesper-<Preset>).
    I temi sono pre-generati (tools/make-icons.py) ed ereditano un tema di
    sistema per la copertura completa."""
    k = key or current_preset()
    return f"{THEME_PREFIX}-" + (k[:1].upper() + k[1:])


def _replace_line(path: Path, prefix: str, newline: str) -> None:
    """Sostituisce (o aggiunge) una riga che inizia con prefix in un file di
    config a righe, senza toccare le altre impostazioni."""
    try:
        lines = path.read_text().splitlines() if path.exists() else []
    except Exception:                     # noqa: BLE001
        lines = []
    out, done = [], False
    for ln in lines:
        if ln.strip().startswith(prefix):
            out.append(newline); done = True
        else:
            out.append(ln)
    if not done:
        out.append(newline)
    path.parent.mkdir(parents=True, exist_ok=True)
    # SCRITTURA ATOMICA (file temporaneo + rename). Con write_text il file
    # viene prima TRONCATO e poi riempito: chi lo sta leggendo in quel preciso
    # istante lo trova vuoto o a meta. GTK sorveglia settings.ini e lo rilegge
    # a ogni modifica, quindi all avvio - dove il pannello parte mentre
    # "vesper-profile apply" riscrive questo stesso file - poteva ricavarne un tema
    # icone vuoto e ripiegare sul default: le icone NOSTRE sparivano dalla
    # barra, mentre quelle del tema di sistema restavano.
    # Era il "alcune si vedono e altre no". Con rename() il file passa da una
    # versione completa all altra senza stati intermedi.
    import os as _os
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(out) + "\n")
    _os.replace(str(tmp), str(path))


def set_icon_theme(key: str | None = None, refresh: bool = False) -> str:
    """Imposta il tema icone GTK2/GTK3 sul preset (icone tinte con l'accent).

    Se il tema del preset non e' installato NON si tocca la scelta dell'utente:
    Vesper e' un DE generico e potrebbe girare senza i temi icone di serie.
    Nessun riavvio di processi: le app GTK (compreso il desktop di Vesper)
    rileggono settings.ini da sole e ricaricano le icone a caldo."""
    theme = icon_theme_name(key)
    if not _icon_theme_installed(theme):
        return current_icon_theme()
    _replace_line(HOME / ".config" / "gtk-3.0" / "settings.ini",
                  "gtk-icon-theme-name", f"gtk-icon-theme-name={theme}")
    _replace_line(HOME / ".gtkrc-2.0",
                  "gtk-icon-theme-name", f'gtk-icon-theme-name="{theme}"')
    return theme




def _icon_theme_installed(name: str) -> bool:
    """Un tema icone c'e' se esiste la sua index.theme in una delle cartelle
    standard (o nei dati di Vesper)."""
    for d in [HOME / ".icons", HOME / ".local" / "share" / "icons",
              Path("/usr/share/icons"), Path("/usr/local/share/icons")] + \
             paths.data_dirs("icons"):
        if (d / name / "index.theme").is_file():
            return True
    return False


def current_icon_theme() -> str:
    """Tema icone attualmente impostato in GTK3 (o 'Adwaita')."""
    try:
        for ln in (HOME / ".config" / "gtk-3.0" / "settings.ini").read_text().splitlines():
            if ln.strip().startswith("gtk-icon-theme-name"):
                return ln.split("=", 1)[1].strip()
    except (OSError, IndexError):
        pass
    return "Adwaita"

# ---------------------------------------------------------------- attivazione
def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def activate_preset(key: str, log=print) -> bool:
    """Attiva un preset: salva lo stato e applica accent, sfondo, icone e tema
    finestre. Tutto a caldo: nessun riavvio della sessione."""
    if key not in presets():
        log(f"[!] preset sconosciuto: {key}")
        return False
    set_current(key)
    set_icon_theme(key)
    set_wallpaper(wallpaper_path(key), remember=False)
    write_accent_css(key)
    set_window_theme(key)
    return True


def apply_current() -> dict:
    """Riapplica l'aspetto del preset già corrente (uso all'avvio sessione)."""
    key = current_preset()
    set_icon_theme(key)
    set_wallpaper(wallpaper_path(key), remember=False)
    write_accent_css(key)
    set_window_theme(key)
    return preset_data(key)


# Compatibilità: il selettore chiama apply_preset.
def apply_preset(key: str) -> dict:
    activate_preset(key)
    return preset_data(key)
