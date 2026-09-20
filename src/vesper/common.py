# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Helper condivisi e tema di Vesper (pannello, Centro di Controllo, viste)."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gtk, Gdk, GLib, Gio  # noqa: E402

from vesper import paths  # noqa: E402

try:
    from vesper.i18n import t as _t
except Exception:                       # noqa: BLE001
    def _t(chiave, **kw):               # ripiego: mostra la chiave
        return chiave

HOME = paths.HOME

# Palette Vesper (default; l'accent è sovrascrivibile dal preset attivo)
COL_BG = "#050a14"
COL_PANEL = "#0a1a26"
COL_ACCENT = "#00e5ff"
COL_TEXT = "#c8f5ff"
COL_DIM = "#5a8a9a"
COL_BORDER = "#1a3a52"
COL_ALERT = "#ff5a8a"

CSS = b"""
window, .background, dialog { background-color: #050a14; color: #c8f5ff; }
/* Viewport (dentro gli ScrolledWindow) trasparente: senza, userebbe il colore
   "base" del tema (bianco) e le viste scrollabili apparirebbero bianche. */
viewport { background-color: transparent; }
/* Font dell'interfaccia: titoli ed etichette in Chakra Petch (look "tech"),
   meta in IBM Plex Mono. Se non sono installati (pacchetto font opzionale di
   Vesper, o /usr/share/fonts/vesper) valgono i fallback dichiarati dopo. */
.vesper-headerbar label.title, .vesper-section, .vesper-key, .vesper-card-title,
.vesper-tile label, frame > label, .vesper-primary, .vesper-primary label {
  font-family: "Chakra Petch", "DejaVu Sans", sans-serif;
}
.vesper-headerbar label.subtitle, .vesper-footer {
  font-family: "IBM Plex Mono", monospace;
}
.vesper-section {
  color: #00e5ff; font-weight: bold; font-size: 11pt;
  padding: 10px 4px 6px 4px; border-bottom: 1px solid #1a3a52; margin-bottom: 8px;
}
.vesper-tile {
  background-color: #0a1422; color: #c8f5ff;
  border: 1px solid #12202e; border-radius: 12px;
  padding: 14px; min-width: 110px; min-height: 96px;
  transition: background-color 120ms ease, border-color 120ms ease;
}
.vesper-tile:hover { background-color: rgba(0,229,255,0.10); border-color: #00e5ff; }
.vesper-tile:active, .vesper-tile:focus { background-color: rgba(0,229,255,0.18); border-color: #00e5ff; }
.vesper-tile label { color: #c8f5ff; font-size: 9pt; }
.vesper-tile-badge { background-color: rgba(0,229,255,0.14); border-radius: 9px;
  padding: 7px; min-width: 20px; min-height: 20px; }
.vesper-tile-badge image { color: #00e5ff; }
.vesper-headerbar {
  background-color: #0a1a26; color: #c8f5ff;
  border-bottom: 1px solid #00e5ff; padding: 8px 14px;
}
.vesper-headerbar label.title { color: #00e5ff; font-weight: bold; font-size: 12pt; }
.vesper-headerbar label.subtitle { color: #5a8a9a; font-size: 9pt; }
/* Eyebrow: marchietto discreto in cima all'header (mono, accent). */
.vesper-eyebrow { color: #35d0e0; font-family: "IBM Plex Mono", monospace;
  font-size: 8pt; margin-bottom: 2px; }
.vesper-footer {
  background-color: #050a14; color: #5a8a9a;
  border-top: 1px solid #1a3a52; padding: 6px 12px; font-size: 8pt;
}
.vesper-key { color: #00e5ff; font-weight: bold; font-size: 11pt; }
.vesper-val { color: #c8f5ff; font-size: 11pt; }
.vesper-card {
  background-color: #0a1422; border: 1px solid #12202e;
  border-radius: 12px; padding: 14px; margin: 4px;
}
.vesper-card-title { color: #00e5ff; font-weight: bold; }
textview, textview text {
  background-color: #050a14; color: #c8f5ff;
  font-family: monospace; caret-color: #00e5ff;
}
textview text selection { background-color: #00e5ff; color: #050a14; }
button {
  background-image: none; background-color: #0d1622; color: #c8f5ff;
  border: 1px solid #17293a; border-radius: 9px; padding: 7px 16px;
  transition: background-color 120ms ease, border-color 120ms ease;
}
button:hover { border-color: #00e5ff; background-color: #12202e; }
button:active, button:checked { background-color: #00e5ff; color: #050a14; }
button.vesper-primary { background-color: #00334a; border-color: #00e5ff; color: #00e5ff; }
button.vesper-primary:hover { background-color: #00475f; }
entry {
  background-color: #070f1a; color: #c8f5ff;
  border: 1px solid #17293a; border-radius: 9px; caret-color: #00e5ff; padding: 6px 12px;
}
entry:focus { border-color: #00e5ff; }
treeview {
  background-color: #050a14; color: #c8f5ff;
}
treeview:selected { background-color: #00334a; color: #00e5ff; }
treeview header button {
  background-color: #0a1a26; color: #00e5ff; border: none;
  border-bottom: 1px solid #1a3a52; border-radius: 0; font-weight: bold;
}
progressbar > trough { background-color: #0a1422; border: 1px solid #17293a;
  min-height: 12px; border-radius: 7px; }
progressbar > trough > progress { background-color: #00e5ff; border-radius: 7px; }
progressbar.vesper-warn > trough > progress { background-color: #ffaa00; }
progressbar.vesper-alert > trough > progress { background-color: #ff5a8a; }
levelbar block.filled { background-color: #00e5ff; }
notebook header { background-color: #0a1a26; }
notebook tab { background-color: transparent; color: #5a8a9a; padding: 6px 12px;
  margin: 2px 1px 0 1px; border-radius: 8px 8px 0 0; }
notebook tab:hover { background-color: #101b28; color: #c8f5ff; }
notebook tab:checked { color: #00e5ff; background-color: #0d1622;
  box-shadow: inset 0 -2px #00e5ff; }
switch { background-color: #0a1422; border: 1px solid #17293a; border-radius: 13px; }
switch:checked { background-color: #00334a; border-color: #00e5ff; }
switch slider { background-color: #5a8a9a; border-radius: 50%; }
switch:checked slider { background-color: #00e5ff; }
radiobutton, checkbutton { color: #c8f5ff; }
combobox { color: #c8f5ff; }
frame { border-radius: 12px; }
frame > border { border: 1px solid #17293a; border-radius: 12px; }
frame > label { color: #00e5ff; font-weight: bold; }
spinner { color: #00e5ff; }

/* ---- Pannello inferiore stile MATE (vesper-panel) ---- */
.vesper-panel {
  background-color: #0a1a26;
  border-top: 1px solid #1a3a52;
}
.vesper-panel.vesper-panel-top { border-top: none; border-bottom: 1px solid #1a3a52; }
.vesper-panel button {
  background-color: transparent; background-image: none;
  border: 1px solid transparent; border-radius: 3px;
  color: #c8f5ff; padding: 2px 10px; margin: 3px 1px;
}
.vesper-panel button:hover { background-color: rgba(0,229,255,0.10); border-color: #1a3a52; }
.vesper-panel button:active { background-color: rgba(0,229,255,0.20); }
/* Icone simboliche monocrome nel colore accent */
.vesper-panel button image { color: #00e5ff; -gtk-icon-style: symbolic; }
.vesper-panel button.vesper-icon { padding: 3px 5px; margin: 2px 0px; }
.vesper-panel button.vesper-icon:hover image { color: #c8f5ff; }
.vesper-panel button.vesper-menu { color: #00e5ff; font-weight: bold; padding: 2px 12px; }
.vesper-panel button.vesper-menu image { color: #00e5ff; }
.vesper-panel button.vesper-launcher { padding: 2px 8px; }
.vesper-panel button.vesper-task {
  color: #5a8a9a; padding: 2px 12px; margin: 3px 1px;
}
.vesper-panel button.vesper-task:hover { color: #c8f5ff; }
.vesper-panel button.vesper-task-active {
  color: #00e5ff; background-color: rgba(0,229,255,0.12);
  border-color: #1a3a52;
}
/* Pager desktop virtuali (workspaces) */
.vesper-panel button.vesper-pager-btn {
  color: #5a8a9a; padding: 1px 8px; margin: 4px 1px; font-size: 9pt;
  min-width: 20px; border: 1px solid #163040; border-radius: 6px;
}
.vesper-panel button.vesper-pager-btn:hover { color: #c8f5ff; }
.vesper-panel button.vesper-pager-active {
  color: #050a14; background-color: #00e5ff; border-color: #00e5ff;
  font-weight: bold;
}
.vesper-panel label.vesper-clock { color: #c8f5ff; font-size: 10pt; padding: 0 6px; }
.vesper-panel label.vesper-clock-date { color: #5a8a9a; font-size: 7.5pt; padding: 0 6px; }
.vesper-panel separator { background-color: #1a3a52; margin: 5px 4px; }
/* Menu a comparsa (tasto destro sul desktop, menu del pannello) */
menu, .menu, menu.background {
  background-color: #0a1a26; color: #c8f5ff;
  border: 1px solid #1a3a52; border-radius: 10px; padding: 6px 0;
}
menu menuitem {
  padding: 7px 14px; margin: 1px 6px; border-radius: 6px;
  min-height: 20px;
}
menu menuitem:hover { background-color: rgba(0,229,255,0.14); color: #00e5ff; }
menu menuitem:disabled { color: #45606e; }
menu menuitem image { color: #00e5ff; -gtk-icon-style: symbolic; }
menu menuitem:hover image { color: #00e5ff; }
/* intestazione di sezione dentro il menu del desktop */
menu label.vesper-menu-head {
  color: #5a8a9a; font-size: 8pt; font-weight: bold;
  padding: 2px 2px 4px 2px;
}
menu separator { background-color: #1a3a52; margin: 4px 10px; }

/* Popup del pannello come finestre toplevel (menu start, calendario) */
.vesper-popup, .vesper-popup.background {
  background-color: #0a1a26; border: 1px solid #1a3a52;
}

/* Menu applicazioni con banda verticale laterale */
popover.vesper-startmenu, popover.vesper-startmenu.background {
  background-color: #0a1a26; border: 1px solid #1a3a52; padding: 0;
}
popover.vesper-startmenu > arrow {
  background-color: #00334a; border: 1px solid #1a3a52;
}
.vesper-menu-strip {
  background-image: linear-gradient(to top, #03070f, #00334a 45%, #00e5ff);
  border-right: 1px solid #1a3a52;
  padding: 10px 6px;
}
.vesper-menu-strip label.brand {
  color: #eafcff; font-weight: bold; font-size: 14pt;
  text-shadow: 0 1px 2px rgba(0,0,0,0.6);
}
.vesper-menu-strip label.brand-sub {
  color: #dff6ff; font-weight: bold; font-size: 9pt;
  text-shadow: 0 1px 2px rgba(0,0,0,0.7);
}
.vesper-startmenu-list { padding: 6px; }
button.vesper-menu-item {
  background-color: transparent; background-image: none;
  border: 1px solid transparent; border-radius: 3px;
  color: #c8f5ff; padding: 7px 16px 7px 10px; margin: 1px 2px;
}
button.vesper-menu-item label { color: #c8f5ff; }
button.vesper-menu-item image { color: #00e5ff; }
button.vesper-menu-item:hover {
  background-color: rgba(0,229,255,0.14); border-color: #1a3a52;
}
button.vesper-menu-item:hover label { color: #00e5ff; }
.vesper-startmenu-list separator { background-color: #1a3a52; margin: 4px 6px; }

/* Ricerca applicazioni in cima al menu */
entry.vesper-menu-search {
  background-color: #050a14; color: #c8f5ff;
  border: 1px solid #1a3a52; border-radius: 3px;
  margin: 6px 8px 2px 8px; padding: 4px 6px;
}
entry.vesper-menu-search:focus { border-color: #00e5ff; }
entry.vesper-menu-search image { color: #5a8a9a; }

/* Intestazione di categoria nella lista app: banda di sezione con marcatore
   accent a sinistra e lieve gradiente (NB: niente text-transform/letter-spacing
   = proprieta' GTK4, in GTK3 fanno fallire il parser CSS). */
label.vesper-menu-cat {
  color: #5a8a9a; font-size: 10px; font-weight: bold;
  padding: 8px 10px 2px 12px;
}
button.vesper-menu-cat {
  background-image: linear-gradient(to right, rgba(0,229,255,0.06), rgba(0,229,255,0));
  border: none; border-left: 2px solid #1a3a52; box-shadow: none;
  padding: 7px 10px 7px 12px; margin: 3px 4px 1px 4px;
  color: #7fb0c2; font-size: 10px; font-weight: bold;
}
button.vesper-menu-cat:hover {
  background-image: linear-gradient(to right, rgba(0,229,255,0.16), rgba(0,229,255,0));
  border-left-color: #00e5ff; color: #00e5ff;
}
/* Righe-applicazione: rientrate sotto la categoria, con barra accent
   all'hover e sfondo tenue, per una lista piu' leggibile e curata. */
button.vesper-app-item {
  padding-left: 26px; margin: 1px 4px 1px 8px;
  border-left: 2px solid transparent; border-radius: 0 3px 3px 0;
}
button.vesper-app-item:hover {
  border-left-color: #00e5ff; background-color: rgba(0,229,255,0.12);
}
button.vesper-app-item label { font-size: 10.5px; }
/* Lo scroller del menu non deve disegnare un fondo opaco sopra il popup */
.vesper-startmenu-scroll, .vesper-startmenu-scroll viewport {
  background-color: transparent; border: none;
}

/* Pulsante orologio + calendario a comparsa (stile MATE) */
/* Ora + data: due righe dentro una barra alta 34px. Il padding e il
   margine verticali rubavano 6px e i discendenti della data (la g di
   'giu') finivano tagliati sul bordo inferiore. */
.vesper-panel button.vesper-clock-btn { padding: 0 8px; margin: 1px; }
.vesper-calbox { padding: 6px; }
calendar.vesper-calendar {
  background-color: #0a1a26; color: #c8f5ff;
  border: 1px solid #1a3a52; padding: 4px;
}
calendar.vesper-calendar:selected {
  background-color: #00e5ff; color: #050a14; border-radius: 3px;
}
calendar.vesper-calendar.header { color: #00e5ff; font-weight: bold; }
calendar.vesper-calendar.button { color: #00e5ff; }
calendar.vesper-calendar.highlight { color: #00e5ff; }
calendar.vesper-calendar:indeterminate { color: #5a8a9a; }

/* Righe regolazione ora/data/fuso nel popup dell'orologio */
.vesper-dt-row { padding: 2px 2px; }
.vesper-dt-row label { color: #5a8a9a; font-size: 9pt; padding: 0 2px; }
.vesper-dt-row spinbutton, .vesper-dt-row combobox {
  background-color: #0a1a26; color: #c8f5ff;
  border: 1px solid #1a3a52; min-height: 20px;
}
.vesper-dt-row spinbutton entry { background-color: #0a1a26; color: #c8f5ff; }
.vesper-dt-row button.vesper-menu-item { padding: 1px 8px; }

/* Applet monitor risorse (mini-grafici CPU/RAM/Rete) */
.vesper-loadmon { padding: 0 2px; margin: 2px 1px; }

/* Etichette di stato nei popup (es. rete connessa, servizio attivo) */
label.vesper-ok { color: #4be38a; font-size: 9pt; }
label.vesper-attn { color: #e5b34b; font-size: 9pt; }

/* ---- Viste a elenco/icone (file manager, liste del Centro di Controllo) ----
   Senza queste regole GTK usa il colore "base" del tema (BIANCO) e le viste
   appaiono candide dentro una finestra scura: e' lo stesso motivo per cui
   sopra si azzera lo sfondo dei viewport. */
iconview, .view, treeview.view, list, list row {
  background-color: #050a14; color: #c8f5ff;
}
iconview:selected, iconview .cell:selected, .view:selected,
treeview.view:selected, list row:selected {
  background-color: #00334a; color: #00e5ff;
}
/* NIENTE padding sulle celle della vista a icone: GTK3 non lo conta nel
   calcolo dell'altezza della voce e le etichette finiscono TAGLIATE a meta'.
   La spaziatura si mette sul widget (set_item_padding), non qui.
   NB: questo e' dentro una stringa BYTES, quindi niente lettere accentate. */
scrolledwindow, scrolledwindow > viewport { background-color: #050a14; }
/* Barra dei luoghi: leggermente staccata dal contenuto */
list.vesper-places, list.vesper-places row { background-color: #070f1a; }
"""

_css_done = False
_icon_paths_done = False
_base_prov = [None]          # provider del tema base, per scambiarlo a caldo
_uimode_mon = None


# Accent del preset attivo: CSS opzionale generato da vesper.profiles
# (model.write_accent_css).
ACCENT_CSS_FILE = paths.ACCENT_CSS
# Stile finestre (flat/vetro/telaio): CSS generato da vesper.profiles, sopra
# l'accent.
WINDOW_STYLE_CSS_FILE = paths.WINDOW_STYLE_CSS

# Provider accent tracciato per il reload a caldo (vedi apply_accent_live).
_accent_prov = None
_accent_mon = None
_accent_reloading = False

# Skin colore del pannello (barra + menu + popup), indipendente dal profilo.
# Vedi vesper.paneltheme. Il file di scelta e' sorvegliato per il reload a caldo.
PANEL_THEME_CONF = paths.PANEL_THEME_CONF
_paneltheme_prov = None
_paneltheme_mon = None
_paneltheme_reloading = False


def install_icon_paths() -> None:
    """Rende trovabili le icone di Vesper (il marchio, i temi icone dei
    preset) anche quando il DE gira dai sorgenti o è installato in un prefisso
    non standard: aggiunge le nostre cartelle al percorso di ricerca di GTK.
    Inerte se già fatto o se non c'è uno schermo."""
    global _icon_paths_done
    if _icon_paths_done:
        return
    try:
        theme = Gtk.IconTheme.get_default()
    except Exception:                    # noqa: BLE001
        return
    if theme is None:
        return
    for d in paths.icon_dirs():
        try:
            theme.append_search_path(str(d))
        except Exception:                # noqa: BLE001
            pass
    _icon_paths_done = True


def base_css() -> bytes:
    """Il tema base nella variante giusta: scura (com'è scritto) o chiara
    (tradotta da vesper.palette). La scelta la fa il preset attivo, o la
    forza l'utente da ~/.config/vesper/ui-mode."""
    try:
        from vesper import palette
        if palette.is_light():
            return palette.to_light(CSS.decode()).encode()
    except Exception:                    # noqa: BLE001
        pass
    return CSS


def apply_css() -> None:
    global _css_done
    if _css_done:
        return
    install_icon_paths()
    _install_uimode_monitor()
    prov = Gtk.CssProvider()
    # Difensivo: un errore nel CSS NON deve mai far crashare il pannello/le app
    # (in GTK3 load_from_data SOLLEVA su CSS non valido). Se fallisce, l'app
    # resta funzionante col tema GTK di default.
    try:
        prov.load_from_data(base_css())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), prov,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        _base_prov[0] = prov
    except Exception:                    # noqa: BLE001
        import sys
        print("[vesper] CSS non applicato (parse error):", sys.exc_info()[1],
              file=sys.stderr)
    # Override accent del profilo attivo (priorita' piu' alta del tema base).
    # Ricaricato A CALDO se il file cambia: cosi' le finestre gia' aperte
    # (es. il Centro di Controllo) cambiano colore al cambio profilo senza
    # chiudere/riaprire.
    apply_accent_live()
    _install_accent_monitor()
    # Stile finestre (flat/vetro/telaio): caricato come UNICO provider tracciato
    # (sopra l'accent), cosi' un cambio stile lo rimuove e rimpiazza in modo
    # pulito (prima il provider d'avvio restava e i cambi non si vedevano).
    apply_window_style_live()
    # Skin del pannello: caricata SOPRA l'accent (APPLICATION+2), cosi' una skin
    # a palette fissa vince sull'accent del profilo (barra indipendente). La
    # skin "profile" non e' un file: niente provider -> resta base+accent.
    apply_panel_theme_live()
    _install_paneltheme_monitor()
    _css_done = True


def apply_base_css_live() -> None:
    """Riscambia il tema base chiaro/scuro senza riavviare nulla: serve quando
    si passa a un preset chiaro (o si forza la modalità) mentre le finestre
    sono già aperte."""
    scr = Gdk.Screen.get_default()
    if scr is None:
        return
    prov = Gtk.CssProvider()
    try:
        prov.load_from_data(base_css())
    except Exception:                    # noqa: BLE001
        return
    if _base_prov[0] is not None:
        try:
            Gtk.StyleContext.remove_provider_for_screen(scr, _base_prov[0])
        except Exception:                # noqa: BLE001
            pass
    Gtk.StyleContext.add_provider_for_screen(
        scr, prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    _base_prov[0] = prov
    _reset_widgets_kick()
    try:
        GLib.idle_add(_reset_widgets_kick)
    except Exception:                    # noqa: BLE001
        pass


def _install_uimode_monitor() -> None:
    """Sorveglia la scelta chiaro/scuro e il preset attivo: cambiandoli, ogni
    processo GTK di Vesper si ridisegna da solo."""
    global _uimode_mon
    if _uimode_mon is not None:
        return
    _uimode_mon = []
    for target in (paths.config("ui-mode"), paths.PROFILE_CONF):
        try:
            mon = Gio.File.new_for_path(str(target)).monitor_file(
                Gio.FileMonitorFlags.NONE, None)
        except Exception:                # noqa: BLE001
            continue
        if mon is None:
            continue

        def changed(_m, _f, _o, etype):
            if etype in (Gio.FileMonitorEvent.CHANGED,
                         Gio.FileMonitorEvent.CHANGES_DONE_HINT,
                         Gio.FileMonitorEvent.CREATED,
                         Gio.FileMonitorEvent.MOVED):
                try:
                    GLib.idle_add(apply_base_css_live)
                except Exception:        # noqa: BLE001
                    pass
        mon.connect("changed", changed)
        _uimode_mon.append(mon)


def apply_panel_theme_live() -> None:
    """Applica/ricarica a caldo la skin del pannello scelta in ~/.config/vesper/
    panel-theme. Sostituisce il provider precedente, cosi' un cambio skin si
    vede subito su barra e menu gia' aperti."""
    global _paneltheme_prov, _paneltheme_reloading
    if _paneltheme_reloading:
        return
    _paneltheme_reloading = True
    try:
        from vesper import paneltheme
        scr = Gdk.Screen.get_default()
        if scr is None:
            return
        if _paneltheme_prov is not None:
            try:
                Gtk.StyleContext.remove_provider_for_screen(scr, _paneltheme_prov)
            except Exception:            # noqa: BLE001
                pass
            _paneltheme_prov = None
        p = paneltheme.css_path(paneltheme.get_theme())
        if p is not None:
            try:
                pv = Gtk.CssProvider()
                pv.load_from_path(str(p))
                # Priorita' +4: DEVE stare SOPRA lo stile finestre (window-style
                # a +3). window-style imposta `window { background }` generico, che
                # colpisce anche la FINESTRA del menu (una Gtk.Window .vesper-popup):
                # a +2 lo sfondo scuro dello stile vinceva sullo sfondo della skin
                # -> nella skin "Chiaro" il menu restava scuro col testo scuro
                # (illeggibile). A +4 la skin del pannello/menu prevale come deve.
                Gtk.StyleContext.add_provider_for_screen(
                    scr, pv, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 4)
                _paneltheme_prov = pv
            except Exception:            # noqa: BLE001
                import sys
                print("[vesper] skin pannello non applicata:", sys.exc_info()[1],
                      file=sys.stderr)
        _reset_widgets_kick()
        try:
            GLib.idle_add(_reset_widgets_kick)
        except Exception:                # noqa: BLE001
            pass
    finally:
        _paneltheme_reloading = False


def _on_paneltheme_changed(mon, _file, _other, etype) -> None:
    if etype in (Gio.FileMonitorEvent.CHANGED,
                 Gio.FileMonitorEvent.CHANGES_DONE_HINT,
                 Gio.FileMonitorEvent.CREATED,
                 Gio.FileMonitorEvent.MOVED):
        try:
            GLib.idle_add(apply_panel_theme_live)
        except Exception:                # noqa: BLE001
            pass


def _install_paneltheme_monitor() -> None:
    """Sorveglia il file di scelta skin: ogni processo GTK di Vesper che ha
    chiamato apply_css cambia skin da solo quando la scelta cambia."""
    global _paneltheme_mon
    if _paneltheme_mon is not None:
        return
    try:
        f = Gio.File.new_for_path(str(PANEL_THEME_CONF))
        mon = f.monitor_file(Gio.FileMonitorFlags.NONE, None)
        if mon is None:
            return
        mon.connect("changed", _on_paneltheme_changed)
        _paneltheme_mon = mon
    except Exception:                    # noqa: BLE001
        _paneltheme_mon = None


def apply_accent_live() -> None:
    """Ricarica accent.css a caldo (dopo un cambio di profilo), sostituendo il
    provider accent precedente. Senza questo la finestra del Centro di Controllo
    gia' aperta resterebbe col colore vecchio finche' non si chiude e riapre."""
    global _accent_prov, _accent_reloading
    if _accent_reloading:
        return
    _accent_reloading = True
    try:
        scr = Gdk.Screen.get_default()
        if scr is None:
            return
        if _accent_prov is not None:
            try:
                Gtk.StyleContext.remove_provider_for_screen(scr, _accent_prov)
            except Exception:            # noqa: BLE001
                pass
            _accent_prov = None
        if ACCENT_CSS_FILE.exists():
            try:
                ap = Gtk.CssProvider()
                ap.load_from_path(str(ACCENT_CSS_FILE))
                Gtk.StyleContext.add_provider_for_screen(
                    scr, ap, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
                _accent_prov = ap
            except Exception:            # noqa: BLE001
                pass
        # Ristila SUBITO i widget gia' realizzati (vedi _reset_widgets_kick):
        # una volta a giro corrente e una a idle.
        _reset_widgets_kick()
        try:
            GLib.idle_add(_reset_widgets_kick)
        except Exception:                # noqa: BLE001
            pass
    finally:
        _accent_reloading = False


def _on_accent_file_changed(mon, _file, _other, etype) -> None:
    """Il file accent.css e' cambiato (profilo appena applicato): riaggiorna i
    colori delle finestre gia' aperte. Il guard in apply_accent_live evita
    doppioni quando arrivano piu' eventi insieme."""
    if etype in (Gio.FileMonitorEvent.CHANGED,
                 Gio.FileMonitorEvent.CHANGES_DONE_HINT,
                 Gio.FileMonitorEvent.CREATED,
                 Gio.FileMonitorEvent.MOVED):
        try:
            GLib.idle_add(apply_accent_live)
        except Exception:                # noqa: BLE001
            pass


def _install_accent_monitor() -> None:
    """Sorveglia accent.css: se il profilo cambia mentre le app sono aperte,
    ogni processo GTK di Vesper che ha chiamato apply_css si ricolora da solo."""
    global _accent_mon
    if _accent_mon is not None:
        return
    try:
        f = Gio.File.new_for_path(str(ACCENT_CSS_FILE))
        mon = f.monitor_file(Gio.FileMonitorFlags.NONE, None)
        if mon is None:
            return
        mon.connect("changed", _on_accent_file_changed)
        _accent_mon = mon
    except Exception:                    # noqa: BLE001
        _accent_mon = None


# ---- Reload schermi al volo (cambio monitor/risoluzione) ----
# vesper-screens tocca questo file dopo ogni modifica (mirror/extend/only/mode/
# primary). Pannello e Centro di Controllo lo ascoltano per riposizionare
# barre e finestre sul monitor attivo: xrandr --off/--primary spesso NON
# scatena "monitors-changed" di GTK, quindi senza questo le barre restano
# sul monitor spento e le finestre non si ricentrano.
SCREENS_REFRESH_FILE = paths.SCREENS_REFRESH

_refresh_mon = None


def install_screens_refresh_monitor(cb) -> None:
    """Installa UNA volta per processo un monitor sul file di refresh scritto da
    vesper-screens. Quando scatta chiama cb (via idle, dopo che il file e'
    completamente scritto)."""
    global _refresh_mon
    if _refresh_mon is not None:
        return
    try:
        f = Gio.File.new_for_path(str(SCREENS_REFRESH_FILE))
        mon = f.monitor_file(Gio.FileMonitorFlags.NONE, None)
        if mon is None:
            return
        def _on_refresh(mon, _file, _other, etype):
            if etype in (Gio.FileMonitorEvent.CHANGED,
                         Gio.FileMonitorEvent.CHANGES_DONE_HINT,
                         Gio.FileMonitorEvent.CREATED,
                         Gio.FileMonitorEvent.MOVED):
                try:
                    GLib.idle_add(cb)
                except Exception:            # noqa: BLE001
                    pass
        mon.connect("changed", _on_refresh)
        _refresh_mon = mon
    except Exception:                        # noqa: BLE001
        _refresh_mon = None


def center_win_on_screen(win) -> None:
    """Centra una finestra sul monitor dove sta (o su quello primario se e'
    rimasta su un monitor appena spento). Serve dopo un cambio schermi, quando
    la finestra del Centro di Controllo era su un output ora spento."""
    scr = Gdk.Screen.get_default()
    if scr is None:
        return
    try:
        gw = win.get_window()
        if gw is not None:
            mon = scr.get_monitor_at_window(gw)
        else:
            mon = scr.get_primary_monitor()
        if mon < 0 or mon >= scr.get_n_monitors():
            mon = scr.get_primary_monitor()
        g = scr.get_monitor_geometry(mon)
        w, h = win.get_size()
        win.move(g.x + max(0, (g.width - w) // 2), g.y + max(0, (g.height - h) // 2))
    except Exception:                        # noqa: BLE001
        pass


def center_toplevel_windows() -> bool:
    """Centra tutte le finestre visibili di QUESTO processo (le viste del
    Centro di Controllo). Ritorna False per GLib.idle_add."""
    try:
        for w in Gtk.Window.list_toplevels():
            if w.get_visible() and not w.get_decorated():
                continue                     # popup del pannello: niente da centrare
            if w.get_visible():
                center_win_on_screen(w)
    except Exception:                        # noqa: BLE001
        pass
    return False


_live_style_prov = None


def _ensure_window_style_css() -> None:
    """Se window-style.css non esiste ancora su disco (es. profilo mai
    applicato, oppure primo avvio prima che `vesper-profile apply` scriva i CSS), lo
    generiamo al volo con lo stile scelto (default 'vetro'). Senza questo file
    lo stile finestre semplicemente NON si vedrebbe: e' la causa n.1 del
    sintomo "la grafica sulle finestre non si vede per nulla"."""
    if WINDOW_STYLE_CSS_FILE.exists():
        return
    try:
        from vesper.profiles import model            # import morbido
        model.write_window_style_css()
    except Exception:                              # noqa: BLE001
        pass


def _reset_widgets_kick() -> bool:
    """Forza GTK a ri-applicare lo stile a TUTTI i widget gia' realizzati.
    Necessario perche' il provider viene aggiunto quando la finestra e' gia'
    disegnata: GTK non ristila i widget realizzati finche' non cambia stato
    (es. perdita del focus -> :backdrop). Senza questo, lo stile appare solo
    dopo aver aperto una seconda finestra (sintomo riportato dall'utente).
    Ritorna False per non ripetersi (uso con GLib.idle_add)."""
    scr = Gdk.Screen.get_default()
    if scr is not None:
        try:
            Gtk.StyleContext.reset_widgets(scr)
        except Exception:                # noqa: BLE001
            pass
    return False


def apply_window_style_live() -> None:
    """Ricarica window-style.css a caldo (dopo un cambio di stile), sostituendo
    l'eventuale provider live precedente cosi' la finestra corrente si aggiorna
    subito senza riavvio."""
    global _live_style_prov
    scr = Gdk.Screen.get_default()
    if scr is None:
        return
    if _live_style_prov is not None:
        try:
            Gtk.StyleContext.remove_provider_for_screen(scr, _live_style_prov)
        except Exception:                # noqa: BLE001
            pass
        _live_style_prov = None
    _ensure_window_style_css()
    if not WINDOW_STYLE_CSS_FILE.exists():
        return
    try:
        p = Gtk.CssProvider()
        p.load_from_path(str(WINDOW_STYLE_CSS_FILE))
        Gtk.StyleContext.add_provider_for_screen(
            scr, p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 3)
        _live_style_prov = p
    except Exception:                    # noqa: BLE001
        return
    # Ristila SUBITO i widget gia' realizzati (vedi _reset_widgets_kick): una
    # volta a giro corrente e una a idle (dopo che la finestra e' mostrata).
    _reset_widgets_kick()
    try:
        GLib.idle_add(_reset_widgets_kick)
    except Exception:                    # noqa: BLE001
        pass


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def run_bg(cmd: list[str]) -> None:
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError as e:
        info_dialog(_t("v.cmd_notfound"), str(e), level="warn")


def run_capture(cmd: list[str], timeout: int = 6) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = res.stdout or ""
        if res.returncode != 0 and res.stderr:
            out += ("\n" if out else "") + res.stderr.strip()
        return out.strip()
    except FileNotFoundError:
        return ""
    except subprocess.TimeoutExpired:
        return "(timeout)"


def info_dialog(title: str, body: str = "", level: str = "info", parent=None) -> None:
    typ = {"info": Gtk.MessageType.INFO, "warn": Gtk.MessageType.WARNING,
           "error": Gtk.MessageType.ERROR}.get(level, Gtk.MessageType.INFO)
    d = Gtk.MessageDialog(transient_for=parent, modal=True, message_type=typ,
                          buttons=Gtk.ButtonsType.OK, text=title)
    if body:
        d.format_secondary_text(body)
    d.run()
    d.destroy()


def panel_window(title: str, width: int = 640, height: int = 460):
    """Crea una finestra stilizzata con header. Ritorna (win, body_box)."""
    apply_css()
    win = Gtk.Window(title=title)
    win.set_default_size(width, height)
    win.set_position(Gtk.WindowPosition.CENTER)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    win.add(outer)

    header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    header.get_style_context().add_class("vesper-headerbar")
    lab = Gtk.Label(label=title)
    lab.set_xalign(0)
    lab.get_style_context().add_class("title")
    header.pack_start(lab, True, True, 0)
    outer.pack_start(header, False, False, 0)

    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    body.set_margin_top(12)
    body.set_margin_bottom(12)
    body.set_margin_start(14)
    body.set_margin_end(14)
    # SCORRIMENTO VERTICALE: se il contenuto e' piu' alto della finestra (schermi
    # piccoli/bassa risoluzione) comparirebbe tagliato. Avvolgiamo il corpo in
    # uno ScrolledWindow (mai orizzontale, verticale automatico) cosi' TUTTE le
    # finestre del Centro di Controllo scorrono senza dover cambiare risoluzione.
    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroller.add(body)                     # GTK3 crea da solo il viewport per un Box
    outer.pack_start(scroller, True, True, 0)

    # Dopo un cambio schermi la vista si ricentra sul monitor attivo da sola.
    install_screens_refresh_monitor(center_toplevel_windows)

    return win, body


def icon_button(label: str, icon_name: str, primary: bool = False):
    """Pulsante con icona + testo, coerente col tema di Vesper.

    icon_name e' un nome di icona del tema (es. 'window-close',
    'preferences-desktop-keyboard'); se assente nel tema GTK ripiega
    sull'icona 'image-missing' senza rompere il layout.
    """
    btn = Gtk.Button()
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    img = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON)
    box.pack_start(img, False, False, 0)
    box.pack_start(Gtk.Label(label=label), False, False, 0)
    btn.add(box)
    if primary:
        btn.get_style_context().add_class("vesper-primary")
    return btn


def read_file(path) -> str:
    p = Path(path)
    try:
        return p.read_text() if p.exists() else _t("v.file_missing") % p
    except OSError as e:
        return _t("v.read_error") % e
