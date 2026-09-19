# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Centro di Controllo di Vesper.

Finestra unica con sezioni e tessere: ogni tessera apre una vera interfaccia
grafica nativa (vedi `views.py`), non un terminale né un dump testuale.
Ogni vista si apre come PROCESSO separato (`vesper-control-center <vista>`):
così la finestra principale resta una sola toplevel — su server X minimali
aprire più toplevel nello stesso processo si è rivelato instabile — e un
errore in una vista non porta giù il Centro di Controllo.
"""
from __future__ import annotations

import subprocess
import sys
import traceback

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from vesper.common import (apply_css, info_dialog,          # noqa: E402
                           install_screens_refresh_monitor,
                           center_toplevel_windows)
from vesper.control_center import views  # noqa: E402

try:
    from vesper.i18n import t as _t       # traduzioni (it/en/fr/es/de)
except Exception:                         # noqa: BLE001
    def _t(key, **kw):                    # fallback: non rompe mai la UI
        return key


def launch(view: str):
    """Apre una vista come processo separato (`vesper-control-center <vista>`)."""
    def handler(_btn=None):
        try:
            subprocess.Popen(["vesper-control-center", view])
        except Exception:                # noqa: BLE001
            traceback.print_exc()
            fn = VIEW_MAP.get(view)      # ripiego in-process se il comando manca
            if fn:
                fn()
    return handler


def launch_app(argv):
    """Handler che avvia un'applicazione esterna (processo separato)."""
    def handler(_btn=None):
        try:
            subprocess.Popen(argv)
        except Exception:                # noqa: BLE001
            traceback.print_exc()
    return handler


def safe(handler):
    """Avvolge l'handler di una tessera: un'eccezione mostra un dialogo e
    finisce nel log invece di chiudere tutto. Logga inizio e fine con flush,
    così anche un crash NATIVO (che salta il try/except) lascia traccia."""
    name = getattr(handler, "__name__", str(handler))

    def wrapper(*args, **kwargs):
        print("[cc] >>> apertura: %s" % name, flush=True)
        try:
            r = handler(*args, **kwargs)
            print("[cc] <<< completato: %s" % name, flush=True)
            return r
        except Exception as e:           # noqa: BLE001
            traceback.print_exc()
            try:
                info_dialog("Errore", "%s: %s" % (type(e).__name__, e),
                            level="error")
            except Exception:            # noqa: BLE001
                pass
        return None
    return wrapper


# NB: NIENTE stringhe tradotte a livello di modulo: le stringhe si risolvono
# con _t() mentre si costruisce la finestra (build_window), così seguono la
# lingua attiva anche se il modulo è stato importato prima del cambio lingua.

# Viste apribili da riga di comando (le usa anche il menu del gestore finestre
# per saltare direttamente al pannello giusto):
#   vesper-control-center schermi
VIEW_MAP = {
    "sysinfo": views.open_sysinfo,
    "monitor": views.open_monitor,
    "rete": views.open_network,
    "network": views.open_network,
    "log": views.open_logs,
    "logs": views.open_logs,
    "hotkey": views.open_hotkeys,
    "barra": views.open_statusbar,
    "pannello": views.open_statusbar,
    "panel": views.open_statusbar,
    "temi-finestre": views.open_openbox_theme,
    "window-theme": views.open_openbox_theme,
    "aspetto": views.open_appearance,
    "appearance": views.open_appearance,
    "menu": views.open_menu_editor,
    "tema-gtk": views.open_gtk_theme,
    "gtk-theme": views.open_gtk_theme,
    "tastiera": views.open_keyboard,
    "keyboard": views.open_keyboard,
    "sfondo": views.open_wallpaper,
    "wallpaper": views.open_wallpaper,
    "salvaschermo": views.open_screensaver,
    "screensaver": views.open_screensaver,
    "autostart": views.open_autostart,
    "bluetooth": views.open_bluetooth,
    "stile-finestre": views.open_window_style,
    "window-style": views.open_window_style,
    "schermi": views.open_screens,
    "screens": views.open_screens,
    "mouse": views.open_mouse,
    "touchpad": views.open_mouse,
    "lingua": views.open_language,
    "language": views.open_language,
    "zram": views.open_zram,
    "memoria": views.open_zram,
}


class Tile(Gtk.Button):
    def __init__(self, icon_name: str, label: str, tooltip: str, handler):
        super().__init__()
        self.set_relief(Gtk.ReliefStyle.NONE)
        self.get_style_context().add_class("vesper-tile")
        self.set_tooltip_text(tooltip)
        # Icona in un badge arrotondato in alto a sinistra, etichetta sotto.
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_halign(Gtk.Align.START)
        box.set_valign(Gtk.Align.START)
        badge = Gtk.Box()
        badge.get_style_context().add_class("vesper-tile-badge")
        badge.set_halign(Gtk.Align.START)
        img = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.LARGE_TOOLBAR)
        img.set_pixel_size(22)
        badge.add(img)
        lbl = Gtk.Label(label=label)
        lbl.set_xalign(0)
        lbl.set_line_wrap(True)
        lbl.set_max_width_chars(16)
        box.pack_start(badge, False, False, 0)
        box.pack_start(lbl, False, False, 0)
        self.add(box)
        self.connect("clicked", safe(handler))


def section(title: str, tiles: list) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    lab = Gtk.Label(label=title)
    lab.set_xalign(0)
    lab.get_style_context().add_class("vesper-section")
    box.pack_start(lab, False, False, 0)
    flow = Gtk.FlowBox()
    flow.set_selection_mode(Gtk.SelectionMode.NONE)
    flow.set_max_children_per_line(8)
    flow.set_min_children_per_line(1)
    flow.set_homogeneous(True)
    flow.set_column_spacing(10)
    flow.set_row_spacing(10)
    for t in tiles:
        flow.add(t)
    box.pack_start(flow, False, False, 0)
    return box


def build_window() -> Gtk.Window:
    apply_css()
    app_title = _t("cc.app_title")
    win = Gtk.Window(title=app_title)
    win.set_default_size(860, 600)
    win.set_position(Gtk.WindowPosition.CENTER)
    win.connect("destroy", Gtk.main_quit)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    win.add(outer)

    header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    header.get_style_context().add_class("vesper-headerbar")
    title = Gtk.Label(label=app_title)
    title.set_xalign(0)
    title.get_style_context().add_class("title")
    sub = Gtk.Label(label=_t("cc.subtitle"))
    sub.set_xalign(0)
    sub.get_style_context().add_class("subtitle")
    header.pack_start(title, False, False, 0)
    header.pack_start(sub, False, False, 0)
    outer.pack_start(header, False, False, 0)

    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    outer.pack_start(sw, True, True, 0)

    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
    body.set_margin_top(12)
    body.set_margin_bottom(12)
    body.set_margin_start(16)
    body.set_margin_end(16)
    sw.add(body)

    body.pack_start(section(_t("cc.sec.appearance"), [
        Tile("vesper-logo", _t("cc.t.preset"), _t("cc.d.preset"),
             launch_app(["vesper-profile"])),
        Tile("preferences-desktop-wallpaper", _t("cc.t.wallpaper"),
             _t("cc.d.wallpaper"), launch("sfondo")),
        Tile("preferences-desktop-theme", _t("cc.t.appearance"),
             _t("cc.d.appearance"), launch("aspetto")),
        Tile("preferences-system-windows", _t("cc.t.windowstyle"),
             _t("cc.d.windowstyle"), launch("stile-finestre")),
        Tile("preferences-desktop-theme", _t("cc.t.gtktheme"),
             _t("cc.d.gtktheme"), launch("tema-gtk")),
        Tile("preferences-desktop-screensaver", _t("cc.t.screensaver"),
             _t("cc.d.screensaver"), launch("salvaschermo")),
        Tile("preferences-desktop-locale", _t("cc.t.language"),
             _t("cc.d.language"), launch("lingua")),
    ]), False, False, 0)

    body.pack_start(section(_t("cc.sec.desktop"), [
        Tile("preferences-desktop-display", _t("cc.t.panel"),
             _t("cc.d.panel"), launch("pannello")),
        Tile("preferences-system-windows", _t("cc.t.obtheme"),
             _t("cc.d.obtheme"), launch("temi-finestre")),
        Tile("input-mouse", _t("cc.t.menu"), _t("cc.d.menu"), launch("menu")),
        Tile("preferences-desktop-keyboard-shortcuts", _t("cc.t.hotkeys"),
             _t("cc.d.hotkeys"), launch("hotkey")),
        Tile("system-run", _t("cc.t.autostart"),
             _t("cc.d.autostart"), launch("autostart")),
    ]), False, False, 0)

    body.pack_start(section(_t("cc.sec.hardware"), [
        Tile("preferences-desktop-display", _t("cc.t.screens"),
             _t("cc.d.screens"), launch("schermi")),
        Tile("input-keyboard", _t("cc.t.keyboard"),
             _t("cc.d.keyboard"), launch("tastiera")),
        Tile("input-mouse", _t("cc.t.mouse"), _t("cc.d.mouse"), launch("mouse")),
        Tile("network-wired", _t("cc.t.network"),
             _t("cc.d.network"), launch("rete")),
        Tile("bluetooth", _t("cc.t.bluetooth"),
             _t("cc.d.bluetooth"), launch("bluetooth")),
    ]), False, False, 0)

    body.pack_start(section(_t("cc.sec.system"), [
        Tile("computer", _t("cc.t.sysinfo"), _t("cc.d.sysinfo"), launch("sysinfo")),
        Tile("utilities-system-monitor", _t("cc.t.monitor"),
             _t("cc.d.monitor"), launch("monitor")),
        Tile("system-file-manager", _t("cc.t.files"), _t("cc.d.files"),
             launch_app(["vesper-files"])),
        Tile("drive-harddisk", _t("cc.t.zram"), _t("cc.d.zram"),
             launch("zram")),
        Tile("utilities-terminal", _t("cc.t.logs"), _t("cc.d.logs"),
             launch("log")),
    ]), False, False, 0)

    footer = Gtk.Label(label=_t("cc.footer"))
    footer.set_xalign(0)
    footer.get_style_context().add_class("vesper-footer")
    outer.pack_start(footer, False, False, 0)

    return win


def run() -> int:
    apply_css()
    args = sys.argv[1:]
    try:
        if args and args[0] in VIEW_MAP:
            # Apre solo la vista richiesta (uso da menu/riga di comando).
            VIEW_MAP[args[0]]()
            for w in Gtk.Window.list_toplevels():
                if w.get_visible():
                    w.connect("destroy", Gtk.main_quit)
        elif args and args[0] in ("-h", "--help", "aiuto"):
            print("uso: vesper-control-center [vista]\nviste: %s"
                  % " ".join(sorted(VIEW_MAP)))
            return 0
        else:
            win = build_window()
            win.show_all()
    except Exception:                    # noqa: BLE001
        traceback.print_exc()
        info_dialog("Errore di avvio",
                    "I dettagli sono nel log del Centro di Controllo "
                    "(~/.cache/vesper/control-center.log).", level="error")
        return 1
    # Dopo un cambio schermi la finestra si ricentra sul monitor attivo da sé.
    install_screens_refresh_monitor(center_toplevel_windows)
    Gtk.main()
    return 0
