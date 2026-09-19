# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""`vesper-files --desktop`: sfondo e icone del desktop.

Sostituisce `pcmanfm --desktop` (e `pcmanfm --set-wallpaper`): Vesper non ha
dipendenze esterne per il desktop.

Architettura (decisa dopo prove fallite con Overlay+Fixed e Gtk.Layout, che
soffrono l'occlusione tra GdkWindow -> sfondo nero e draw inaffidabile): un
UNICO canvas Cairo (`Gtk.DrawingArea`) che disegna wallpaper + icone. Le icone
sono DATI (`IconItem`), con hit-test, selezione e trascinamento gestiti a mano,
e `queue_draw()` per il repaint: niente icone "invisibili finché non clicchi"
(il difetto di libfm) e posizionamento LIBERO, senza riallineamenti forzati.

Cosa fa da componente del DE (oltre al prototipo):
  * sfondo letto dalla configurazione (preset attivo o scelta manuale), con
    ricarica A CALDO quando cambia: `vesper-wallpaper`/Centro di Controllo
    scrivono il file e qui si ridisegna da solo;
  * modalità di adattamento: stretch / fit / center / tile;
  * multi-monitor: una sola finestra copre tutti gli schermi e lo sfondo viene
    disegnato per ciascuno, con ricostruzione al cambio configurazione;
  * icone: selezione multipla (ctrl-clic e rettangolo), trascinamento del
    gruppo, cestino freedesktop, rinomina, apri-con, proprietà;
  * ricarica automatica quando la cartella del desktop cambia (Gio monitor).
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, Gio, GLib, Pango, PangoCairo  # noqa: E402

from vesper import paths

try:
    from vesper.profiles import model as presets_model
except Exception:                     # noqa: BLE001
    presets_model = None

try:
    from vesper.common import apply_css, install_icon_paths
except Exception:                     # noqa: BLE001
    def apply_css():
        pass

    def install_icon_paths():
        pass

try:
    from vesper.i18n import t as _t
except Exception:                     # noqa: BLE001
    def _t(key, **kw):
        return key

ICON_PX = 48                 # dimensione pittogramma
CELL_W, CELL_H = 92, 90      # cella (icona + etichetta): passo della griglia
LABEL_H = 30                 # spazio testo sotto l'icona
MARGIN = 18                  # margine dai bordi schermo
TEXT = (0xc8 / 255, 0xf5 / 255, 0xff / 255)          # #c8f5ff
ACCENT = (0x00 / 255, 0xe5 / 255, 0xff / 255)        # #00e5ff (selezione)
FILLBG = (0x05 / 255, 0x0a / 255, 0x14 / 255)        # #050a14 (senza sfondo)
CONF = paths.DESKTOP_ITEMS


def label(key: str, fallback: str) -> str:
    """Traduzione con ripiego sul testo italiano (chiave mancante = fallback)."""
    s = _t(key)
    return fallback if s == key else s


class DesktopState:
    """Posizioni delle icone + preferenze, su file JSON (persistenti)."""

    def __init__(self):
        self.positions: dict[str, list[int]] = {}
        self.auto_arrange = False          # False = posizioni libere (default)
        self.load()

    def load(self):
        try:
            d = json.loads(CONF.read_text())
            self.positions = d.get("positions", {})
            self.auto_arrange = bool(d.get("auto_arrange", False))
        except (OSError, ValueError):
            pass

    def save(self):
        try:
            CONF.parent.mkdir(parents=True, exist_ok=True)
            CONF.write_text(json.dumps(
                {"positions": self.positions, "auto_arrange": self.auto_arrange},
                indent=1))
        except OSError:
            pass


def wallpaper_file() -> Path | None:
    """Sfondo da usare: la scelta manuale, altrimenti quello del preset."""
    if presets_model is None:
        return None
    try:
        return presets_model.wallpaper_path()
    except Exception:                      # noqa: BLE001
        return None


def wallpaper_mode() -> str:
    if presets_model is None:
        return "stretch"
    try:
        return presets_model.wallpaper_mode()
    except Exception:                      # noqa: BLE001
        return "stretch"


def theme_icon(name: str, size: int):
    theme = Gtk.IconTheme.get_default()
    for n in (name, "application-x-executable", "text-x-generic", "folder"):
        if n and theme.has_icon(n):
            try:
                return theme.load_icon(n, size, Gtk.IconLookupFlags.FORCE_SIZE)
            except Exception:              # noqa: BLE001
                continue
    return None


class IconItem:
    """Una icona del desktop = solo DATI (disegnata su Cairo, non un widget)."""

    __slots__ = ("key", "name", "path", "appinfo", "pixbuf", "x", "y", "sel")

    def __init__(self, key, name, path, appinfo, pixbuf, x=0, y=0):
        self.key, self.name, self.path = key, name, path
        self.appinfo, self.pixbuf = appinfo, pixbuf
        self.x, self.y = x, y
        self.sel = False

    def rect(self):
        return (self.x, self.y, CELL_W, ICON_PX + LABEL_H)

    def hit(self, px, py):
        x, y, w, h = self.rect()
        return x <= px <= x + w and y <= py <= y + h

    def intersects(self, rx, ry, rw, rh):
        x, y, w, h = self.rect()
        return not (x > rx + rw or x + w < rx or y > ry + rh or y + h < ry)


class Desktop(Gtk.Window):
    def __init__(self, wallpaper=None, desktop_dir=None):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        apply_css()
        install_icon_paths()
        self.state = DesktopState()
        self.wallpaper_override = wallpaper
        self.desktop_dir = Path(desktop_dir or self._default_desktop_dir())
        self.wp_cache: list[tuple[Gdk.Rectangle, GdkPixbuf.Pixbuf]] = []
        self.items: list[IconItem] = []
        self._drag = None            # (dx, dy, mosso) per il gruppo selezionato
        self._band = None            # rettangolo di selezione (x0, y0, x, y)
        self._dir_monitor = None
        self._wp_monitor = None

        self.set_title("desktop")
        self.set_type_hint(Gdk.WindowTypeHint.DESKTOP)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_below(True)
        self.stick()
        self.set_app_paintable(True)

        self.canvas = Gtk.DrawingArea()
        self.canvas.add_events(Gdk.EventMask.BUTTON_PRESS_MASK
                               | Gdk.EventMask.BUTTON_RELEASE_MASK
                               | Gdk.EventMask.POINTER_MOTION_MASK
                               | Gdk.EventMask.KEY_PRESS_MASK)
        self.canvas.set_can_focus(True)
        self.canvas.connect("draw", self.on_draw)
        self.canvas.connect("button-press-event", self.on_press)
        self.canvas.connect("motion-notify-event", self.on_motion)
        self.canvas.connect("button-release-event", self.on_release)
        self.connect("key-press-event", self.on_key)
        self.add(self.canvas)

        self._place()
        self.reload_wallpaper()
        self.load_icons()
        self._watch_dir()
        self._watch_wallpaper()

        # Cambio schermi: la finestra deve ricoprire la nuova area e lo sfondo
        # va ridisegnato per ogni monitor.
        scr = self.get_screen()
        if scr is not None:
            scr.connect("monitors-changed", lambda *_: GLib.idle_add(self._on_screens))
            scr.connect("size-changed", lambda *_: GLib.idle_add(self._on_screens))
        try:
            from vesper.common import install_screens_refresh_monitor
            install_screens_refresh_monitor(self._on_screens)
        except Exception:                  # noqa: BLE001
            pass
        # Il tema icone può cambiare col preset: ricarichiamo i pittogrammi.
        try:
            Gtk.IconTheme.get_default().connect(
                "changed", lambda *_: GLib.idle_add(self.load_icons))
        except Exception:                  # noqa: BLE001
            pass

        self.connect("destroy", Gtk.main_quit)

    # -- geometria / percorsi ---------------------------------------------
    def _monitors(self) -> list[Gdk.Rectangle]:
        """Geometria di ogni monitor (per disegnare lo sfondo su ciascuno)."""
        out = []
        disp = Gdk.Display.get_default()
        try:
            for i in range(disp.get_n_monitors()):
                out.append(disp.get_monitor(i).get_geometry())
        except Exception:                  # noqa: BLE001
            pass
        if not out:
            scr = Gdk.Screen.get_default()
            g = Gdk.Rectangle()
            g.x = g.y = 0
            g.width = scr.get_width() if scr else 1920
            g.height = scr.get_height() if scr else 1080
            out.append(g)
        return out

    def _place(self):
        """Una sola finestra che copre TUTTI i monitor: le icone vivono in
        coordinate di schermo e non si perdono passando da uno all'altro."""
        mons = self._monitors()
        x0 = min(m.x for m in mons)
        y0 = min(m.y for m in mons)
        x1 = max(m.x + m.width for m in mons)
        y1 = max(m.y + m.height for m in mons)
        self._ox, self._oy = x0, y0
        self._w, self._h = x1 - x0, y1 - y0
        self.move(x0, y0)
        self.resize(self._w, self._h)
        self.canvas.set_size_request(self._w, self._h)

    def _on_screens(self, *_a):
        self._place()
        self.reload_wallpaper()
        self.canvas.queue_draw()
        return False

    def _default_desktop_dir(self):
        """Cartella del desktop. XDG la dichiara in ~/.config/user-dirs.dirs,
        ma quel file può mancare (home nuova, o creata da un altro sistema): in
        quel caso GLib risponde comunque "$HOME/Desktop", che potrebbe NON
        esistere mentre esiste la cartella nella lingua dell'utente. Quindi:
        prima la scelta XDG SE esiste davvero, poi i nomi tradotti più comuni,
        infine si crea quella XDG (un desktop senza cartella non serve)."""
        xdg = None
        try:
            p = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DESKTOP)
            if p:
                xdg = Path(p)
                if xdg.is_dir():
                    return xdg
        except Exception:                  # noqa: BLE001
            pass
        for name in ("Scrivania", "Desktop", "Bureau", "Escritorio",
                     "Schreibtisch", "Área de Trabalho"):
            p = paths.HOME / name
            if p.is_dir():
                return p
        target = xdg or (paths.HOME / "Desktop")
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return target

    # -- sfondo ------------------------------------------------------------
    def reload_wallpaper(self):
        """(Ri)calcola il pixbuf dello sfondo per ogni monitor."""
        self.wp_cache = []
        f = self.wallpaper_override or wallpaper_file()
        if not f or not os.path.exists(str(f)):
            return
        mode = wallpaper_mode()
        for m in self._monitors():
            pb = self._fit(str(f), m.width, m.height, mode)
            if pb is not None:
                self.wp_cache.append((m, pb))

    @staticmethod
    def _fit(path: str, w: int, h: int, mode: str):
        """Immagine adattata al monitor secondo la modalità scelta."""
        try:
            src = GdkPixbuf.Pixbuf.new_from_file(path)
        except Exception:                  # noqa: BLE001
            return None
        sw, sh = src.get_width(), src.get_height()
        if mode == "stretch":
            return src.scale_simple(w, h, GdkPixbuf.InterpType.BILINEAR)
        if mode == "tile":
            out = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, w, h)
            for y in range(0, h, sh):
                for x in range(0, w, sw):
                    src.copy_area(0, 0, min(sw, w - x), min(sh, h - y), out, x, y)
            return out
        if mode == "center":
            out = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, w, h)
            out.fill(0x050a14ff)
            ox, oy = max(0, (w - sw) // 2), max(0, (h - sh) // 2)
            src.copy_area(max(0, (sw - w) // 2), max(0, (sh - h) // 2),
                          min(sw, w), min(sh, h), out, ox, oy)
            return out
        # fit: riempie senza deformare, ritagliando l'eccesso
        scale = max(w / sw, h / sh)
        tmp = src.scale_simple(max(1, int(sw * scale)), max(1, int(sh * scale)),
                               GdkPixbuf.InterpType.BILINEAR)
        ox = max(0, (tmp.get_width() - w) // 2)
        oy = max(0, (tmp.get_height() - h) // 2)
        return tmp.new_subpixbuf(ox, oy, min(w, tmp.get_width()),
                                 min(h, tmp.get_height()))

    def _watch_wallpaper(self):
        """Sorveglia la scelta dello sfondo: cambiandola da `vesper-wallpaper`
        o dal Centro di Controllo, il desktop si ridisegna da solo."""
        for target in (presets_model.WALLPAPER_CONF if presets_model else None,
                       presets_model.WALLPAPER_MODE_CONF if presets_model else None,
                       paths.PROFILE_CONF):
            if target is None:
                continue
            try:
                mon = Gio.File.new_for_path(str(target)).monitor_file(
                    Gio.FileMonitorFlags.NONE, None)
            except Exception:              # noqa: BLE001
                continue
            if mon is None:
                continue
            mon.connect("changed", self._on_wp_changed)
            # va tenuto un riferimento, altrimenti il monitor viene raccolto
            if self._wp_monitor is None:
                self._wp_monitor = []
            self._wp_monitor.append(mon)

    def _on_wp_changed(self, _m, _f, _o, etype):
        if etype in (Gio.FileMonitorEvent.CHANGED,
                     Gio.FileMonitorEvent.CHANGES_DONE_HINT,
                     Gio.FileMonitorEvent.CREATED,
                     Gio.FileMonitorEvent.MOVED,
                     Gio.FileMonitorEvent.DELETED):
            def redraw():
                self.reload_wallpaper()
                self.canvas.queue_draw()
                return False
            GLib.timeout_add(150, redraw)

    # -- modello icone -----------------------------------------------------
    def _scan_entries(self):
        entries = []
        if not self.desktop_dir.is_dir():
            return entries
        for p in sorted(self.desktop_dir.iterdir(),
                        key=lambda q: (not q.is_dir(), q.name.lower())):
            if p.name.startswith("."):
                continue
            if p.suffix == ".desktop":
                try:
                    ai = Gio.DesktopAppInfo.new_from_filename(str(p))
                except Exception:          # noqa: BLE001
                    ai = None
                if ai is not None:
                    gi_icon = ai.get_icon()
                    icon = gi_icon.to_string() if gi_icon is not None else ""
                    entries.append((p.name, ai.get_display_name(), str(p), ai, icon))
                    continue
                # GLib scarta il file se il programma di Exec non esiste: un
                # lanciatore rotto NON deve sembrare un file di testo. Lo
                # leggiamo col nostro parser, così mostra nome e icona giusti;
                # l'errore si vede al clic (vedi launch()).
                e = self._read_entry(p)
                if e:
                    entries.append((p.name, e[0], str(p), None, e[1]))
                    continue
            icon = "folder" if p.is_dir() else self._mime_icon(p)
            entries.append((p.name, p.name, str(p), None, icon))
        return entries

    @staticmethod
    def _read_entry(p: Path):
        """(nome, icona) da un .desktop letto a mano, o None se non è una voce
        di applicazione. Serve per i lanciatori che GLib rifiuta."""
        try:
            from vesper.desktopentry import _read_desktop, LANG
        except Exception:                  # noqa: BLE001
            return None
        e = _read_desktop(str(p))
        if not e or e.get("Type") != "Application":
            return None
        name = e.get("Name[%s]" % LANG) or e.get("Name") or p.stem
        return name, e.get("Icon", "application-x-executable")

    @staticmethod
    def _mime_icon(p: Path) -> str:
        """Icona dal tipo MIME del file (immagini, testo, audio, ...)."""
        try:
            ctype, _ = Gio.content_type_guess(p.name, None)
            icon = Gio.content_type_get_icon(ctype)
            names = icon.get_names() if hasattr(icon, "get_names") else []
            theme = Gtk.IconTheme.get_default()
            for n in names:
                if theme.has_icon(n):
                    return n
        except Exception:                  # noqa: BLE001
            pass
        return "text-x-generic"

    def _grid_slot(self, index):
        rows = max(1, (self._h - 2 * MARGIN) // CELL_H)
        col, row = divmod(index, rows)
        return MARGIN + col * CELL_W, MARGIN + row * CELL_H

    def load_icons(self):
        sel = {it.key for it in self.items if it.sel}
        self.items = []
        for idx, (key, name, path, ai, icon) in enumerate(self._scan_entries()):
            pb = theme_icon(icon, ICON_PX)
            pos = None if self.state.auto_arrange else self.state.positions.get(key)
            if pos is None:
                pos = self._grid_slot(idx)
                if self.state.auto_arrange:
                    self.state.positions[key] = list(pos)
            it = IconItem(key, name, path, ai, pb, pos[0], pos[1])
            it.sel = key in sel
            self.items.append(it)
        self.state.save()
        self.canvas.queue_draw()
        return False

    def _watch_dir(self):
        """Ricarica le icone quando la cartella del desktop cambia (file nuovi,
        rinominati, cancellati): come ogni desktop, senza premere Aggiorna."""
        try:
            mon = Gio.File.new_for_path(str(self.desktop_dir)).monitor_directory(
                Gio.FileMonitorFlags.NONE, None)
        except Exception:                  # noqa: BLE001
            return
        if mon is None:
            return

        def changed(*_a):
            # piccolo ritardo: le copie fanno più eventi ravvicinati
            GLib.timeout_add(250, self.load_icons)
        mon.connect("changed", changed)
        self._dir_monitor = mon

    # -- disegno -----------------------------------------------------------
    def on_draw(self, _w, cr):
        cr.set_source_rgb(*FILLBG)
        cr.paint()
        for m, pb in self.wp_cache:
            Gdk.cairo_set_source_pixbuf(cr, pb, m.x - self._ox, m.y - self._oy)
            cr.paint()
        for it in self.items:
            self._draw_item(cr, it)
        if self._band:
            x0, y0, x1, y1 = self._band
            x, y = min(x0, x1), min(y0, y1)
            w, h = abs(x1 - x0), abs(y1 - y0)
            cr.set_source_rgba(*ACCENT, 0.15)
            cr.rectangle(x, y, w, h)
            cr.fill()
            cr.set_source_rgba(*ACCENT, 0.7)
            cr.set_line_width(1)
            cr.rectangle(x + 0.5, y + 0.5, w, h)
            cr.stroke()
        return False

    def _draw_item(self, cr, it):
        if it.sel:                                   # evidenziazione selezione
            x, y, w, h = it.rect()
            cr.set_source_rgba(*ACCENT, 0.18)
            self._round_rect(cr, x - 2, y - 2, w + 4, h + 4, 8)
            cr.fill()
        if it.pixbuf is not None:
            ix = it.x + (CELL_W - it.pixbuf.get_width()) // 2
            Gdk.cairo_set_source_pixbuf(cr, it.pixbuf, ix, it.y)
            cr.paint()
        layout = PangoCairo.create_layout(cr)
        layout.set_text(it.name, -1)
        layout.set_width(CELL_W * Pango.SCALE)
        layout.set_alignment(Pango.Alignment.CENTER)
        layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        layout.set_font_description(Pango.FontDescription("Sans 9"))
        tx, ty = it.x, it.y + ICON_PX + 4
        cr.move_to(tx + 1, ty + 1)
        cr.set_source_rgba(0, 0, 0, 0.85)            # ombra: leggibile su ogni sfondo
        PangoCairo.show_layout(cr, layout)
        cr.move_to(tx, ty)
        cr.set_source_rgb(*TEXT)
        PangoCairo.show_layout(cr, layout)

    @staticmethod
    def _round_rect(cr, x, y, w, h, r):
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
        cr.close_path()

    # -- selezione / interazione ------------------------------------------
    def _item_at(self, px, py):
        for it in reversed(self.items):              # gli ultimi disegnati sopra
            if it.hit(px, py):
                return it
        return None

    def selection(self):
        return [it for it in self.items if it.sel]

    def _select_only(self, it):
        for o in self.items:
            o.sel = (o is it)

    def on_press(self, _w, ev):
        self.canvas.grab_focus()
        it = self._item_at(ev.x, ev.y)
        ctrl = bool(ev.state & Gdk.ModifierType.CONTROL_MASK)
        if ev.button == 1:
            if it is None:
                if not ctrl:
                    for o in self.items:
                        o.sel = False
                self._band = (ev.x, ev.y, ev.x, ev.y)
                self.canvas.queue_draw()
                return True
            if ev.type == Gdk.EventType._2BUTTON_PRESS:
                self.launch(it)
                return True
            if ctrl:
                it.sel = not it.sel
            elif not it.sel:
                self._select_only(it)
            # trascinamento dell'INTERA selezione
            self._drag = (ev.x, ev.y, False)
            self.canvas.queue_draw()
            return True
        if ev.button == 3:
            if it is not None and not it.sel:
                self._select_only(it)
            elif it is None:
                for o in self.items:
                    o.sel = False
            self.canvas.queue_draw()
            (self.icon_menu if it else self.desktop_menu)(ev, it)
            return True
        return False

    def on_motion(self, _w, ev):
        if self._band:
            x0, y0, _, _ = self._band
            self._band = (x0, y0, ev.x, ev.y)
            rx, ry = min(x0, ev.x), min(y0, ev.y)
            rw, rh = abs(ev.x - x0), abs(ev.y - y0)
            for it in self.items:
                it.sel = it.intersects(rx, ry, rw, rh)
            self.canvas.queue_draw()
            return True
        if self._drag:
            px, py, _ = self._drag
            dx, dy = int(ev.x - px), int(ev.y - py)
            if dx or dy:
                for it in self.selection():
                    it.x = max(0, it.x + dx)
                    it.y = max(0, it.y + dy)
                self._drag = (ev.x, ev.y, True)
                self.canvas.queue_draw()   # RIDISEGNO immediato e corretto
            return True
        return False

    def on_release(self, _w, ev):
        if self._band:
            self._band = None
            self.canvas.queue_draw()
            return True
        if self._drag and ev.button == 1:
            _px, _py, moved = self._drag
            if moved:
                for it in self.selection():
                    self.state.positions[it.key] = [it.x, it.y]
                self.state.save()          # le altre icone NON si spostano
            self._drag = None
            return True
        return False

    def on_key(self, _w, ev):
        k = ev.keyval
        if k == Gdk.KEY_F5:
            self.load_icons()
            return True
        if k == Gdk.KEY_F2:
            sel = self.selection()
            if len(sel) == 1:
                self.rename(sel[0])
            return True
        if k == Gdk.KEY_Delete:
            self.trash(self.selection())
            return True
        if k == Gdk.KEY_Return:
            for it in self.selection():
                self.launch(it)
            return True
        if k == Gdk.KEY_a and (ev.state & Gdk.ModifierType.CONTROL_MASK):
            for it in self.items:
                it.sel = True
            self.canvas.queue_draw()
            return True
        return False

    # -- azioni ------------------------------------------------------------
    def launch(self, it):
        try:
            if it.appinfo is not None:
                # I .desktop sul desktop si avviano SENZA chiedere conferma
                # (con pcmanfm serviva quick_exec=1 in libfm.conf: qui è il
                # comportamento nostro, nessuna configurazione da ricordare).
                it.appinfo.launch(None, None)
            elif it.path.endswith(".desktop"):
                # lanciatore che GLib ha rifiutato: quasi sempre il programma
                # indicato in Exec non è installato. Lo diciamo chiaramente.
                e = self._read_entry(Path(it.path))
                cmd = ""
                try:
                    from vesper.desktopentry import _read_desktop
                    cmd = (_read_desktop(it.path) or {}).get("Exec", "")
                except Exception:          # noqa: BLE001
                    pass
                self._error(
                    label("fm.launcher_broken", "Lanciatore non utilizzabile"),
                    label("fm.launcher_missing",
                          "Il programma indicato non è installato:") + " " + cmd)
            else:
                Gio.AppInfo.launch_default_for_uri(
                    Gio.File.new_for_path(it.path).get_uri(), None)
        except Exception as e:             # noqa: BLE001
            self._error(label("fm.open_failed", "Impossibile aprire"), str(e))

    def open_with(self, it):
        f = Gio.File.new_for_path(it.path)
        try:
            info = f.query_info("standard::content-type", 0, None)
            ctype = info.get_content_type()
        except Exception:                  # noqa: BLE001
            ctype = "application/octet-stream"
        d = Gtk.AppChooserDialog.new_for_content_type(
            self, Gtk.DialogFlags.MODAL, ctype)
        if d.run() == Gtk.ResponseType.OK:
            ai = d.get_app_info()
            if ai is not None:
                try:
                    ai.launch([f], None)
                except Exception as e:     # noqa: BLE001
                    self._error(label("fm.open_failed", "Impossibile aprire"), str(e))
        d.destroy()

    def rename(self, it):
        new = self._ask(label("fm.rename", "Rinomina"), it.name)
        if not new or new == it.name:
            return
        src = Path(it.path)
        dst = src.with_name(new)
        try:
            src.rename(dst)
        except OSError as e:
            self._error(label("fm.rename_failed", "Rinomina non riuscita"), str(e))
            return
        # la posizione segue il nuovo nome
        if it.key in self.state.positions:
            self.state.positions[new] = self.state.positions.pop(it.key)
            self.state.save()
        self.load_icons()

    def trash(self, items):
        if not items:
            return
        names = ", ".join(i.name for i in items[:4])
        if len(items) > 4:
            names += "…"
        if not self._confirm(label("fm.trash_ask", "Spostare nel cestino?"), names):
            return
        for it in items:
            try:
                Gio.File.new_for_path(it.path).trash(None)
                self.state.positions.pop(it.key, None)
            except Exception as e:         # noqa: BLE001
                self._error(label("fm.trash_failed", "Spostamento nel cestino non riuscito"),
                            "%s: %s" % (it.name, e))
        self.state.save()
        self.load_icons()

    def properties(self, it):
        p = Path(it.path)
        try:
            st = p.stat()
            size = st.st_size
            mtime = GLib.DateTime.new_from_unix_local(int(st.st_mtime))
            when = mtime.format("%d/%m/%Y %H:%M") if mtime else ""
            perm = oct(st.st_mode & 0o777)[2:]
        except OSError as e:
            self._error(label("fm.props", "Proprietà"), str(e))
            return
        body = "%s\n\n%s: %s\n%s: %s\n%s: %s\n%s: %s" % (
            it.path,
            label("fm.kind", "Tipo"),
            label("fm.folder", "Cartella") if p.is_dir() else self._mime_icon(p),
            label("fm.size", "Dimensione"), self._human(size),
            label("fm.modified", "Modificato"), when,
            label("fm.perms", "Permessi"), perm)
        self._info(it.name, body)

    @staticmethod
    def _human(n: int) -> str:
        for unit in ("B", "KiB", "MiB", "GiB"):
            if n < 1024 or unit == "GiB":
                return "%.0f %s" % (n, unit) if unit == "B" else "%.1f %s" % (n, unit)
            n /= 1024.0
        return str(n)

    def new_folder(self):
        name = self._ask(label("fm.new_folder", "Nuova cartella"),
                         label("fm.new_folder_default", "Nuova cartella"))
        if not name:
            return
        try:
            (self.desktop_dir / name).mkdir()
        except OSError as e:
            self._error(label("fm.new_folder", "Nuova cartella"), str(e))
            return
        self.load_icons()

    def open_terminal(self):
        self._spawn(["vesper-terminal"], cwd=str(self.desktop_dir))

    def _spawn(self, argv, cwd=None):
        try:
            subprocess.Popen(argv, cwd=cwd, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError as e:
            self._error(argv[0], str(e))

    # -- dialoghi ----------------------------------------------------------
    def _ask(self, title, preset=""):
        d = Gtk.Dialog(title=title, transient_for=self, modal=True)
        d.add_button(label("v.cancel", "Annulla"), Gtk.ResponseType.CANCEL)
        d.add_button("OK", Gtk.ResponseType.OK)
        e = Gtk.Entry()
        e.set_text(preset)
        e.set_activates_default(True)
        d.set_default_response(Gtk.ResponseType.OK)
        area = d.get_content_area()
        area.set_spacing(8)
        area.set_border_width(12)
        area.pack_start(e, False, False, 0)
        d.show_all()
        resp = d.run()
        val = e.get_text().strip()
        d.destroy()
        return val if resp == Gtk.ResponseType.OK else None

    def _confirm(self, title, body=""):
        d = Gtk.MessageDialog(transient_for=self, modal=True,
                              message_type=Gtk.MessageType.QUESTION,
                              buttons=Gtk.ButtonsType.YES_NO, text=title)
        if body:
            d.format_secondary_text(body)
        resp = d.run()
        d.destroy()
        return resp == Gtk.ResponseType.YES

    def _info(self, title, body=""):
        d = Gtk.MessageDialog(transient_for=self, modal=True,
                              message_type=Gtk.MessageType.INFO,
                              buttons=Gtk.ButtonsType.OK, text=title)
        if body:
            d.format_secondary_text(body)
        d.run()
        d.destroy()

    def _error(self, title, body=""):
        d = Gtk.MessageDialog(transient_for=self, modal=True,
                              message_type=Gtk.MessageType.ERROR,
                              buttons=Gtk.ButtonsType.OK, text=title)
        if body:
            d.format_secondary_text(body)
        d.run()
        d.destroy()

    # -- menu --------------------------------------------------------------
    def _mi(self, menu, text, cb):
        mi = Gtk.MenuItem(label=text)
        mi.connect("activate", lambda *_: cb())
        menu.append(mi)
        return mi

    def icon_menu(self, ev, it):
        sel = self.selection() or [it]
        m = Gtk.Menu()
        self._mi(m, label("fm.open", "Apri"), lambda: [self.launch(i) for i in sel])
        if len(sel) == 1:
            self._mi(m, label("fm.open_with", "Apri con…"), lambda: self.open_with(it))
            self._mi(m, label("fm.rename", "Rinomina") + "  (F2)",
                     lambda: self.rename(it))
        m.append(Gtk.SeparatorMenuItem())
        self._mi(m, label("fm.trash", "Sposta nel cestino") + "  (Del)",
                 lambda: self.trash(sel))
        if len(sel) == 1:
            m.append(Gtk.SeparatorMenuItem())
            self._mi(m, label("fm.props", "Proprietà"), lambda: self.properties(it))
        m.show_all()
        m.popup_at_pointer(ev)

    def desktop_menu(self, ev, _it):
        m = Gtk.Menu()
        self._mi(m, label("fm.open_files", "Apri il file manager"),
                 lambda: self._spawn(["vesper-files", str(self.desktop_dir)]))
        self._mi(m, label("fm.open_terminal", "Apri un terminale qui"),
                 self.open_terminal)
        self._mi(m, label("fm.new_folder", "Nuova cartella"), self.new_folder)
        m.append(Gtk.SeparatorMenuItem())
        chk = Gtk.CheckMenuItem(label=label("fm.auto_arrange",
                                            "Allinea automaticamente le icone"))
        chk.set_active(self.state.auto_arrange)
        chk.connect("toggled", self.on_toggle_arrange)
        m.append(chk)
        self._mi(m, label("fm.refresh", "Aggiorna") + "  (F5)", self.load_icons)
        m.append(Gtk.SeparatorMenuItem())
        self._mi(m, label("fm.wallpaper", "Cambia sfondo…"),
                 lambda: self._spawn(["vesper-control-center", "sfondo"]))
        self._mi(m, label("fm.appearance", "Aspetto del desktop…"),
                 lambda: self._spawn(["vesper-profile"]))
        m.show_all()
        m.popup_at_pointer(ev)

    def on_toggle_arrange(self, item):
        self.state.auto_arrange = item.get_active()
        if self.state.auto_arrange:
            self.state.positions = {}
            for i, it in enumerate(self.items):
                it.x, it.y = self._grid_slot(i)
                self.state.positions[it.key] = [it.x, it.y]
        self.state.save()
        self.canvas.queue_draw()


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    wallpaper = desktop_dir = None
    it = iter(argv)
    for a in it:
        if a == "--wallpaper":
            wallpaper = next(it, None)
        elif a == "--desktop-dir":
            desktop_dir = next(it, None)
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        print("vesper-files --desktop: serve una sessione grafica (DISPLAY)",
              file=sys.stderr)
        return 1
    win = Desktop(wallpaper=wallpaper, desktop_dir=desktop_dir)
    win.show_all()
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
