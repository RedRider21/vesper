# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""`vesper-files [CARTELLA]`: il file manager in modalità finestra.

Clone funzionale di pcmanfm, in GTK3, con la stessa base di codice della
modalità desktop (vedi `desktop.py`). Cosa c'è:

  * navigazione con cronologia (indietro/avanti/su), barra del percorso
    modificabile e **schede**;
  * viste ICONE (`Gtk.IconView`) e ELENCO (`Gtk.TreeView`) sullo stesso
    modello, commutabili;
  * barra dei luoghi: home, desktop, cartelle XDG, cestino, segnalibri letti
    da `~/.config/gtk-3.0/bookmarks` (gli stessi degli altri file manager);
  * operazioni su file ASINCRONE via `Gio` (copia, spostamento, eliminazione)
    con finestra di avanzamento e annullamento;
  * cestino freedesktop (`Gio.File.trash`), svuotamento cestino;
  * apri-con (MIME/`.desktop`), rinomina, nuova cartella, nuovo file,
    proprietà, permessi;
  * miniature delle immagini, file nascosti commutabili, monitoraggio della
    cartella (l'elenco si aggiorna da sé).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, Gio, GLib  # noqa: E402

from vesper import paths

try:
    from vesper.common import apply_css, install_icon_paths
except Exception:                      # noqa: BLE001
    def apply_css():
        pass

    def install_icon_paths():
        pass

try:
    from vesper.i18n import t as _t
except Exception:                      # noqa: BLE001
    def _t(key, **kw):
        return key

ICON_PX = 48                 # miniatura in vista icone
LIST_PX = 22                 # icona in vista elenco
THUMB_MAX = 8 * 1024 * 1024  # oltre questa dimensione niente miniatura


def label(key: str, fallback: str) -> str:
    """Traduzione con ripiego (chiave mancante = testo italiano)."""
    s = _t(key)
    return fallback if s == key else s


def human(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or unit == "TiB":
            return "%d %s" % (n, unit) if unit == "B" else "%.1f %s" % (n, unit)
        n /= 1024.0
    return str(n)


def bookmarks() -> list[tuple[str, Path]]:
    """Segnalibri GTK: gli stessi che usano gli altri file manager."""
    out = []
    f = paths.HOME / ".config" / "gtk-3.0" / "bookmarks"
    try:
        lines = f.read_text().splitlines()
    except OSError:
        return out
    for ln in lines:
        ln = ln.strip()
        if not ln or not ln.startswith("file://"):
            continue
        uri, _, name = ln.partition(" ")
        p = Path(GLib.filename_from_uri(uri)[0])
        out.append((name or p.name, p))
    return out


def xdg_places() -> list[tuple[str, str, Path]]:
    """Luoghi di serie: (etichetta, icona, percorso)."""
    d = GLib.UserDirectory
    wanted = [
        (d.DIRECTORY_DESKTOP, "user-desktop", label("fm.place_desktop", "Scrivania")),
        (d.DIRECTORY_DOCUMENTS, "folder-documents", label("fm.place_docs", "Documenti")),
        (d.DIRECTORY_DOWNLOAD, "folder-download", label("fm.place_dl", "Scaricati")),
        (d.DIRECTORY_MUSIC, "folder-music", label("fm.place_music", "Musica")),
        (d.DIRECTORY_PICTURES, "folder-pictures", label("fm.place_pics", "Immagini")),
        (d.DIRECTORY_VIDEOS, "folder-videos", label("fm.place_video", "Video")),
    ]
    out = [(label("fm.place_home", "Home"), "user-home", paths.HOME)]
    for key, icon, name in wanted:
        try:
            p = GLib.get_user_special_dir(key)
        except Exception:              # noqa: BLE001
            p = None
        if p and Path(p) != paths.HOME and Path(p).is_dir():
            out.append((name, icon, Path(p)))
    return out


class Progress(Gtk.Window):
    """Finestra di avanzamento di un'operazione su file, con annullamento."""

    def __init__(self, parent, title):
        super().__init__(title=title, transient_for=parent, modal=False)
        self.set_default_size(420, 110)
        self.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        self.cancellable = Gio.Cancellable()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(14)
        self.add(box)
        self.lab = Gtk.Label(label=title)
        self.lab.set_xalign(0)
        self.lab.set_ellipsize(3)
        box.pack_start(self.lab, False, False, 0)
        self.bar = Gtk.ProgressBar()
        box.pack_start(self.bar, False, False, 0)
        b = Gtk.Button(label=label("v.cancel", "Annulla"))
        b.connect("clicked", lambda *_: self.cancellable.cancel())
        box.pack_end(b, False, False, 0)
        self.show_all()

    def step(self, text, frac=None):
        self.lab.set_text(text)
        if frac is None:
            self.bar.pulse()
        else:
            self.bar.set_fraction(max(0.0, min(1.0, frac)))


class FileList(Gtk.Box):
    """Contenuto di una scheda: modello, viste icone/elenco, navigazione."""

    COL_ICON, COL_NAME, COL_SIZE, COL_KIND, COL_MTIME, COL_PATH, COL_ISDIR = range(7)

    def __init__(self, win, path: Path):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.win = win
        self.path = Path(path)
        self.history: list[Path] = []
        self.future: list[Path] = []
        self.monitor = None
        self._thumbs: dict[str, GdkPixbuf.Pixbuf] = {}

        # icona, nome, dimensione, tipo, modificato, percorso, è-cartella
        self.store = Gtk.ListStore(GdkPixbuf.Pixbuf, str, str, str, str, str, bool)
        self.store.set_sort_func(0, self._sort_rows, None)
        self.store.set_sort_column_id(0, Gtk.SortType.ASCENDING)

        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.pack_start(self.scroller, True, True, 0)

        self.iconview = Gtk.IconView.new_with_model(self.store)
        self.iconview.set_pixbuf_column(self.COL_ICON)
        self.iconview.set_text_column(self.COL_NAME)
        self.iconview.set_item_width(96)
        self.iconview.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
        self.iconview.connect("item-activated",
                              lambda _v, tp: self.activate_path(self._path_at(tp)))
        self.iconview.connect("button-press-event", self._on_button)

        self.treeview = Gtk.TreeView.new_with_model(self.store)
        self.treeview.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        for i, (title, col) in enumerate((
                (label("fm.col_name", "Nome"), self.COL_NAME),
                (label("fm.col_size", "Dimensione"), self.COL_SIZE),
                (label("fm.col_kind", "Tipo"), self.COL_KIND),
                (label("fm.col_mtime", "Modificato"), self.COL_MTIME))):
            if i == 0:
                c = Gtk.TreeViewColumn(title)
                c.pack_start(Gtk.CellRendererPixbuf(), False)
                c.add_attribute(c.get_cells()[0], "pixbuf", self.COL_ICON)
                txt = Gtk.CellRendererText()
                c.pack_start(txt, True)
                c.add_attribute(txt, "text", self.COL_NAME)
                c.set_expand(True)
            else:
                c = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=col)
            c.set_resizable(True)
            self.treeview.append_column(c)
        self.treeview.connect("row-activated",
                              lambda _v, tp, _c: self.activate_path(self._path_at(tp)))
        self.treeview.connect("button-press-event", self._on_button)

        self.view = None
        self.set_mode(win.view_mode)
        self.load()

    # -- modello -----------------------------------------------------------
    def _sort_rows(self, model, a, b, _data):
        """Cartelle prima, poi per nome (senza distinzione di maiuscole)."""
        da, db = model[a][self.COL_ISDIR], model[b][self.COL_ISDIR]
        if da != db:
            return -1 if da else 1
        na = (model[a][self.COL_NAME] or "").lower()
        nb = (model[b][self.COL_NAME] or "").lower()
        return (na > nb) - (na < nb)

    def _icon_for(self, p: Path, isdir: bool, px: int):
        """Icona: miniatura per le immagini, altrimenti icona del tipo MIME."""
        theme = Gtk.IconTheme.get_default()
        if not isdir and px >= ICON_PX and self.win.thumbnails:
            key = "%s:%d" % (p, px)
            if key in self._thumbs:
                return self._thumbs[key]
            try:
                ctype, _ = Gio.content_type_guess(p.name, None)
                if ctype and ctype.startswith("image/") and p.stat().st_size <= THUMB_MAX:
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_size(str(p), px, px)
                    self._thumbs[key] = pb
                    return pb
            except Exception:          # noqa: BLE001
                pass
        names = ["folder"] if isdir else []
        if not isdir:
            try:
                ctype, _ = Gio.content_type_guess(p.name, None)
                icon = Gio.content_type_get_icon(ctype)
                names = list(icon.get_names()) if icon else []
            except Exception:          # noqa: BLE001
                names = []
            names.append("text-x-generic")
        for n in names:
            if theme.has_icon(n):
                try:
                    return theme.load_icon(n, px, Gtk.IconLookupFlags.FORCE_SIZE)
                except Exception:      # noqa: BLE001
                    continue
        return None

    def load(self):
        """Rilegge la cartella corrente nel modello."""
        self.store.clear()
        px = ICON_PX if self.win.view_mode == "icons" else LIST_PX
        try:
            entries = list(self.path.iterdir())
        except OSError as e:
            self.win.error(label("fm.read_failed", "Cartella non leggibile"), str(e))
            entries = []
        for p in entries:
            if p.name.startswith(".") and not self.win.show_hidden:
                continue
            try:
                isdir = p.is_dir()
                st = p.stat()
                size = "" if isdir else human(st.st_size)
                dt = GLib.DateTime.new_from_unix_local(int(st.st_mtime))
                mtime = dt.format("%d/%m/%Y %H:%M") if dt else ""
            except OSError:
                isdir, size, mtime = False, "", ""
            kind = label("fm.folder", "Cartella") if isdir else self._kind(p)
            self.store.append([self._icon_for(p, isdir, px), p.name, size, kind,
                               mtime, str(p), isdir])
        self.win.update_state()
        self._watch()

    @staticmethod
    def _kind(p: Path) -> str:
        try:
            ctype, _ = Gio.content_type_guess(p.name, None)
            return Gio.content_type_get_description(ctype) or ""
        except Exception:              # noqa: BLE001
            return ""

    def _watch(self):
        """Monitor della cartella: l'elenco si aggiorna da sé."""
        if self.monitor is not None:
            try:
                self.monitor.cancel()
            except Exception:          # noqa: BLE001
                pass
            self.monitor = None
        try:
            mon = Gio.File.new_for_path(str(self.path)).monitor_directory(
                Gio.FileMonitorFlags.NONE, None)
        except Exception:              # noqa: BLE001
            return
        if mon is None:
            return
        self._reload_pending = 0

        def changed(*_a):
            if self._reload_pending:
                return
            self._reload_pending = GLib.timeout_add(300, self._reload_now)
        mon.connect("changed", changed)
        self.monitor = mon

    def _reload_now(self):
        self._reload_pending = 0
        self.load()
        return False

    # -- viste -------------------------------------------------------------
    def set_mode(self, mode):
        child = self.scroller.get_child()
        if child is not None:
            self.scroller.remove(child)
        self.view = self.iconview if mode == "icons" else self.treeview
        self.scroller.add(self.view)
        self.scroller.show_all()

    def _path_at(self, treepath):
        it = self.store.get_iter(treepath)
        return Path(self.store[it][self.COL_PATH])

    def selection(self) -> list[Path]:
        if self.view is self.iconview:
            return [self._path_at(tp) for tp in self.iconview.get_selected_items()]
        model, rows = self.treeview.get_selection().get_selected_rows()
        return [Path(model[r][self.COL_PATH]) for r in rows]

    def select_all(self):
        if self.view is self.iconview:
            self.iconview.select_all()
        else:
            self.treeview.get_selection().select_all()

    # -- navigazione -------------------------------------------------------
    def go(self, path: Path, remember=True):
        path = Path(path)
        if not path.is_dir():
            return
        if remember and path != self.path:
            self.history.append(self.path)
            self.future.clear()
        self.path = path
        self._thumbs.clear()
        self.load()
        self.win.tab_renamed(self)

    def back(self):
        if self.history:
            self.future.append(self.path)
            self.go(self.history.pop(), remember=False)

    def forward(self):
        if self.future:
            self.history.append(self.path)
            self.go(self.future.pop(), remember=False)

    def up(self):
        if self.path.parent != self.path:
            self.go(self.path.parent)

    def activate_path(self, p: Path):
        if p.is_dir():
            self.go(p)
        else:
            self.win.open_file(p)

    # -- menu contestuale --------------------------------------------------
    def _on_button(self, widget, ev):
        if ev.button != 3:
            return False
        # clic destro su una voce non selezionata: selezionala
        if widget is self.iconview:
            tp = self.iconview.get_path_at_pos(int(ev.x), int(ev.y))
            if tp is not None and not self.iconview.path_is_selected(tp):
                self.iconview.unselect_all()
                self.iconview.select_path(tp)
            hit = tp is not None
        else:
            res = self.treeview.get_path_at_pos(int(ev.x), int(ev.y))
            sel = self.treeview.get_selection()
            if res is not None and not sel.path_is_selected(res[0]):
                sel.unselect_all()
                sel.select_path(res[0])
            hit = res is not None
        self.win.context_menu(ev, self, hit)
        return True


class FileWindow(Gtk.Window):
    def __init__(self, start: Path):
        super().__init__(title=label("fm.title", "File"))
        apply_css()
        install_icon_paths()
        self.set_default_size(960, 620)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.view_mode = "icons"
        self.show_hidden = False
        self.thumbnails = True
        self.clip: tuple[str, list[Path]] | None = None   # ("copy"|"cut", file)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(outer)

        # --- barra strumenti ---
        tb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        tb.get_style_context().add_class("vesper-headerbar")
        outer.pack_start(tb, False, False, 0)

        def tool(icon, tip, cb):
            b = Gtk.Button()
            b.set_relief(Gtk.ReliefStyle.NONE)
            b.set_tooltip_text(tip)
            b.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON))
            b.connect("clicked", lambda *_: cb())
            tb.pack_start(b, False, False, 0)
            return b

        self.b_back = tool("go-previous-symbolic", label("fm.back", "Indietro"),
                           lambda: self.tab().back())
        self.b_fwd = tool("go-next-symbolic", label("fm.forward", "Avanti"),
                          lambda: self.tab().forward())
        self.b_up = tool("go-up-symbolic", label("fm.up", "Cartella superiore"),
                         lambda: self.tab().up())
        tool("go-home-symbolic", label("fm.place_home", "Home"),
             lambda: self.tab().go(paths.HOME))

        self.entry = Gtk.Entry()
        self.entry.set_tooltip_text(label("fm.path", "Percorso"))
        self.entry.connect("activate", self._on_path_entry)
        tb.pack_start(self.entry, True, True, 4)

        tool("view-grid-symbolic", label("fm.view_icons", "Vista a icone"),
             lambda: self.set_view("icons"))
        tool("view-list-symbolic", label("fm.view_list", "Vista a elenco"),
             lambda: self.set_view("list"))
        tool("tab-new-symbolic", label("fm.new_tab", "Nuova scheda"),
             lambda: self.add_tab(self.tab().path))
        tool("open-menu-symbolic", label("fm.menu", "Menu"), self.main_menu)

        # --- corpo: luoghi + schede ---
        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        outer.pack_start(body, True, True, 0)

        self.places = Gtk.ListBox()
        self.places.get_style_context().add_class("vesper-places")
        self.places.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.places.connect("row-activated", self._on_place)
        pl_scroll = Gtk.ScrolledWindow()
        pl_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        pl_scroll.set_size_request(190, -1)
        pl_scroll.add(self.places)
        body.pack_start(pl_scroll, False, False, 0)
        body.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL),
                        False, False, 0)

        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        self.notebook.connect("switch-page", lambda *_: GLib.idle_add(self.update_state))
        body.pack_start(self.notebook, True, True, 0)

        # --- barra di stato ---
        self.status = Gtk.Label(label="")
        self.status.set_xalign(0)
        self.status.get_style_context().add_class("vesper-footer")
        outer.pack_end(self.status, False, False, 0)

        self.fill_places()
        self.add_tab(start)
        self.connect("key-press-event", self.on_key)
        self.connect("destroy", Gtk.main_quit)

    # -- luoghi ------------------------------------------------------------
    def fill_places(self):
        for ch in self.places.get_children():
            self.places.remove(ch)

        def row(text, icon, target):
            r = Gtk.ListBoxRow()
            r.target = target
            b = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            b.set_margin_top(6)
            b.set_margin_bottom(6)
            b.set_margin_start(10)
            b.set_margin_end(10)
            b.pack_start(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU),
                         False, False, 0)
            lab = Gtk.Label(label=text)
            lab.set_xalign(0)
            lab.set_ellipsize(3)
            b.pack_start(lab, True, True, 0)
            r.add(b)
            self.places.add(r)

        def header(text):
            r = Gtk.ListBoxRow()
            r.target = None
            r.set_selectable(False)
            lab = Gtk.Label(label=text)
            lab.set_xalign(0)
            lab.get_style_context().add_class("vesper-section")
            lab.set_margin_start(10)
            r.add(lab)
            self.places.add(r)

        header(label("fm.places", "Luoghi"))
        for name, icon, p in xdg_places():
            row(name, icon, p)
        row(label("fm.trash", "Cestino"), "user-trash", "trash:///")
        row(label("fm.filesystem", "File system"), "drive-harddisk", Path("/"))
        bm = bookmarks()
        if bm:
            header(label("fm.bookmarks", "Segnalibri"))
            for name, p in bm:
                row(name, "folder", p)
        self.places.show_all()

    def _on_place(self, _lb, row):
        t = getattr(row, "target", None)
        if t is None:
            return
        if isinstance(t, str) and t.startswith("trash:"):
            self.open_trash()
            return
        self.tab().go(Path(t))

    def open_trash(self):
        """Il cestino: cartella freedesktop dei file eliminati."""
        p = Path(GLib.get_user_data_dir()) / "Trash" / "files"
        if p.is_dir():
            self.tab().go(p)
        else:
            self.info(label("fm.trash", "Cestino"),
                      label("fm.trash_empty", "Il cestino è vuoto."))

    # -- schede ------------------------------------------------------------
    def add_tab(self, path: Path):
        fl = FileList(self, Path(path))
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lab = Gtk.Label(label=Path(path).name or "/")
        lab.set_ellipsize(3)
        lab.set_max_width_chars(18)
        box.pack_start(lab, True, True, 0)
        close = Gtk.Button()
        close.set_relief(Gtk.ReliefStyle.NONE)
        close.set_image(Gtk.Image.new_from_icon_name("window-close-symbolic",
                                                     Gtk.IconSize.MENU))
        close.connect("clicked", lambda *_: self.close_tab(fl))
        box.pack_start(close, False, False, 0)
        box.show_all()
        fl._tab_label = lab
        self.notebook.append_page(fl, box)
        self.notebook.show_all()
        self.notebook.set_current_page(self.notebook.page_num(fl))
        self.notebook.set_show_tabs(self.notebook.get_n_pages() > 1)
        self.update_state()
        return fl

    def close_tab(self, fl):
        if self.notebook.get_n_pages() <= 1:
            self.destroy()
            return
        self.notebook.remove_page(self.notebook.page_num(fl))
        self.notebook.set_show_tabs(self.notebook.get_n_pages() > 1)

    def tab(self) -> FileList:
        return self.notebook.get_nth_page(self.notebook.get_current_page())

    def tab_renamed(self, fl):
        if hasattr(fl, "_tab_label"):
            fl._tab_label.set_text(fl.path.name or "/")

    def update_state(self):
        fl = self.tab()
        if fl is None:
            return False
        self.entry.set_text(str(fl.path))
        self.b_back.set_sensitive(bool(fl.history))
        self.b_fwd.set_sensitive(bool(fl.future))
        self.b_up.set_sensitive(fl.path.parent != fl.path)
        n = len(fl.store)
        sel = len(fl.selection())
        txt = label("fm.count", "%d elementi") % n
        if sel:
            txt += "  ·  " + label("fm.selected", "%d selezionati") % sel
        self.status.set_text(txt)
        self.set_title("%s - %s" % (fl.path.name or "/", label("fm.title", "File")))
        return False

    def set_view(self, mode):
        self.view_mode = mode
        for i in range(self.notebook.get_n_pages()):
            fl = self.notebook.get_nth_page(i)
            fl.set_mode(mode)
            fl.load()

    def _on_path_entry(self, entry):
        p = Path(os.path.expanduser(entry.get_text().strip()))
        if p.is_dir():
            self.tab().go(p)
        elif p.is_file():
            self.open_file(p)
        else:
            self.error(label("fm.no_path", "Percorso inesistente"), str(p))

    # -- azioni su file ----------------------------------------------------
    def open_file(self, p: Path):
        try:
            Gio.AppInfo.launch_default_for_uri(
                Gio.File.new_for_path(str(p)).get_uri(), None)
        except Exception as e:         # noqa: BLE001
            self.error(label("fm.open_failed", "Impossibile aprire"), str(e))

    def open_with(self, p: Path):
        f = Gio.File.new_for_path(str(p))
        try:
            ctype = f.query_info("standard::content-type", 0, None).get_content_type()
        except Exception:              # noqa: BLE001
            ctype = "application/octet-stream"
        d = Gtk.AppChooserDialog.new_for_content_type(self, Gtk.DialogFlags.MODAL, ctype)
        if d.run() == Gtk.ResponseType.OK:
            ai = d.get_app_info()
            if ai is not None:
                try:
                    ai.launch([f], None)
                except Exception as e:  # noqa: BLE001
                    self.error(label("fm.open_failed", "Impossibile aprire"), str(e))
        d.destroy()

    def copy_selection(self, cut=False):
        sel = self.tab().selection()
        if sel:
            self.clip = ("cut" if cut else "copy", sel)

    def paste(self):
        if not self.clip:
            return
        action, files = self.clip
        dest_dir = self.tab().path
        prog = Progress(self, label("fm.copying", "Copia in corso…") if action == "copy"
                        else label("fm.moving", "Spostamento in corso…"))
        queue = list(files)

        def next_one():
            if not queue or prog.cancellable.is_cancelled():
                prog.destroy()
                if action == "cut":
                    self.clip = None
                self.tab().load()
                return False
            src = queue.pop(0)
            dst = dest_dir / src.name
            if dst.exists():
                dst = self._unique(dst)
            prog.step(src.name, 1 - len(queue) / max(1, len(files)))
            gsrc = Gio.File.new_for_path(str(src))
            gdst = Gio.File.new_for_path(str(dst))
            try:
                flags = Gio.FileCopyFlags.NONE
                if src.is_dir():
                    # Gio non copia ricorsivamente: per le cartelle si delega a
                    # una copia ricorsiva nostra (semplice e prevedibile).
                    self._copy_tree(src, dst)
                    if action == "cut":
                        self._rm_tree(src)
                elif action == "copy":
                    gsrc.copy(gdst, flags, prog.cancellable, None, None)
                else:
                    gsrc.move(gdst, flags, prog.cancellable, None, None)
            except Exception as e:     # noqa: BLE001
                prog.destroy()
                self.error(label("fm.op_failed", "Operazione non riuscita"),
                           "%s: %s" % (src.name, e))
                return False
            return True                 # continua col prossimo a idle
        GLib.idle_add(next_one)

    @staticmethod
    def _unique(p: Path) -> Path:
        """Nome libero: 'file (2).txt', come fanno gli altri file manager."""
        stem, suf, i = p.stem, p.suffix, 2
        while True:
            cand = p.with_name("%s (%d)%s" % (stem, i, suf))
            if not cand.exists():
                return cand
            i += 1

    def _copy_tree(self, src: Path, dst: Path):
        dst.mkdir(parents=True, exist_ok=True)
        for child in src.iterdir():
            target = dst / child.name
            if child.is_dir():
                self._copy_tree(child, target)
            else:
                Gio.File.new_for_path(str(child)).copy(
                    Gio.File.new_for_path(str(target)),
                    Gio.FileCopyFlags.NONE, None, None, None)

    def _rm_tree(self, p: Path):
        for child in p.iterdir():
            if child.is_dir():
                self._rm_tree(child)
            else:
                child.unlink()
        p.rmdir()

    def trash_selection(self):
        sel = self.tab().selection()
        if not sel:
            return
        names = ", ".join(p.name for p in sel[:4]) + ("…" if len(sel) > 4 else "")
        if not self.confirm(label("fm.trash_ask", "Spostare nel cestino?"), names):
            return
        for p in sel:
            try:
                Gio.File.new_for_path(str(p)).trash(None)
            except Exception as e:     # noqa: BLE001
                self.error(label("fm.trash_failed", "Spostamento nel cestino non riuscito"),
                           "%s: %s" % (p.name, e))
        self.tab().load()

    def delete_selection(self):
        """Eliminazione DEFINITIVA (Maiusc+Canc), con conferma esplicita."""
        sel = self.tab().selection()
        if not sel:
            return
        names = ", ".join(p.name for p in sel[:4]) + ("…" if len(sel) > 4 else "")
        if not self.confirm(label("fm.delete_ask",
                                  "Eliminare DEFINITIVAMENTE? Non si potrà recuperare."),
                            names):
            return
        for p in sel:
            try:
                if p.is_dir():
                    self._rm_tree(p)
                else:
                    p.unlink()
            except OSError as e:
                self.error(label("fm.op_failed", "Operazione non riuscita"),
                           "%s: %s" % (p.name, e))
        self.tab().load()

    def rename_selection(self):
        sel = self.tab().selection()
        if len(sel) != 1:
            return
        p = sel[0]
        new = self.ask(label("fm.rename", "Rinomina"), p.name)
        if not new or new == p.name:
            return
        try:
            p.rename(p.with_name(new))
        except OSError as e:
            self.error(label("fm.rename_failed", "Rinomina non riuscita"), str(e))
        self.tab().load()

    def new_folder(self):
        name = self.ask(label("fm.new_folder", "Nuova cartella"),
                        label("fm.new_folder_default", "Nuova cartella"))
        if not name:
            return
        try:
            (self.tab().path / name).mkdir()
        except OSError as e:
            self.error(label("fm.new_folder", "Nuova cartella"), str(e))
        self.tab().load()

    def new_file(self):
        name = self.ask(label("fm.new_file", "Nuovo file"), "nuovo.txt")
        if not name:
            return
        try:
            (self.tab().path / name).touch(exist_ok=False)
        except OSError as e:
            self.error(label("fm.new_file", "Nuovo file"), str(e))
        self.tab().load()

    def properties(self):
        sel = self.tab().selection()
        if not sel:
            return
        p = sel[0]
        try:
            st = p.stat()
            dt = GLib.DateTime.new_from_unix_local(int(st.st_mtime))
            when = dt.format("%d/%m/%Y %H:%M") if dt else ""
            size = human(st.st_size) if not p.is_dir() else self._dir_size(p)
            perm = oct(st.st_mode & 0o777)[2:]
        except OSError as e:
            self.error(label("fm.props", "Proprietà"), str(e))
            return
        body = "%s\n\n%s: %s\n%s: %s\n%s: %s\n%s: %s" % (
            p, label("fm.kind", "Tipo"),
            label("fm.folder", "Cartella") if p.is_dir() else FileList._kind(p),
            label("fm.size", "Dimensione"), size,
            label("fm.modified", "Modificato"), when,
            label("fm.perms", "Permessi"), perm)
        self.info(p.name, body)

    @staticmethod
    def _dir_size(p: Path) -> str:
        """Dimensione di una cartella: somma dei file contenuti (un livello per
        volta, senza bloccare l'interfaccia su alberi enormi)."""
        total, count = 0, 0
        for root, _dirs, files in os.walk(p):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
                count += 1
                if count > 20000:        # limite di cortesia
                    return "> " + human(total)
        return human(total)

    def open_terminal(self):
        self.spawn(["vesper-terminal"], cwd=str(self.tab().path))

    def spawn(self, argv, cwd=None):
        try:
            subprocess.Popen(argv, cwd=cwd, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError as e:
            self.error(argv[0], str(e))

    # -- menu --------------------------------------------------------------
    def _mi(self, menu, text, cb, enabled=True):
        mi = Gtk.MenuItem(label=text)
        mi.set_sensitive(enabled)
        mi.connect("activate", lambda *_: cb())
        menu.append(mi)
        return mi

    def context_menu(self, ev, fl, on_item):
        sel = fl.selection()
        m = Gtk.Menu()
        if on_item and sel:
            self._mi(m, label("fm.open", "Apri"),
                     lambda: [fl.activate_path(p) for p in sel])
            if len(sel) == 1:
                self._mi(m, label("fm.open_with", "Apri con…"),
                         lambda: self.open_with(sel[0]))
                if sel[0].is_dir():
                    self._mi(m, label("fm.open_tab", "Apri in una nuova scheda"),
                             lambda: self.add_tab(sel[0]))
            m.append(Gtk.SeparatorMenuItem())
            self._mi(m, label("fm.copy", "Copia") + "  (Ctrl+C)",
                     lambda: self.copy_selection(False))
            self._mi(m, label("fm.cut", "Taglia") + "  (Ctrl+X)",
                     lambda: self.copy_selection(True))
            if len(sel) == 1:
                self._mi(m, label("fm.rename", "Rinomina") + "  (F2)",
                         self.rename_selection)
            self._mi(m, label("fm.trash", "Sposta nel cestino") + "  (Del)",
                     self.trash_selection)
            self._mi(m, label("fm.delete", "Elimina definitivamente"),
                     self.delete_selection)
            m.append(Gtk.SeparatorMenuItem())
            self._mi(m, label("fm.props", "Proprietà"), self.properties)
        else:
            self._mi(m, label("fm.new_folder", "Nuova cartella"), self.new_folder)
            self._mi(m, label("fm.new_file", "Nuovo file"), self.new_file)
            m.append(Gtk.SeparatorMenuItem())
            self._mi(m, label("fm.paste", "Incolla") + "  (Ctrl+V)", self.paste,
                     enabled=bool(self.clip))
            self._mi(m, label("fm.select_all", "Seleziona tutto") + "  (Ctrl+A)",
                     fl.select_all)
            m.append(Gtk.SeparatorMenuItem())
            self._mi(m, label("fm.open_terminal", "Apri un terminale qui"),
                     self.open_terminal)
            self._mi(m, label("fm.refresh", "Aggiorna") + "  (F5)", fl.load)
        m.show_all()
        m.popup_at_pointer(ev)

    def main_menu(self):
        m = Gtk.Menu()
        h = Gtk.CheckMenuItem(label=label("fm.show_hidden", "Mostra i file nascosti")
                              + "  (Ctrl+H)")
        h.set_active(self.show_hidden)
        h.connect("toggled", lambda w: self._toggle_hidden(w.get_active()))
        m.append(h)
        t = Gtk.CheckMenuItem(label=label("fm.show_thumbs", "Miniature delle immagini"))
        t.set_active(self.thumbnails)
        t.connect("toggled", lambda w: self._toggle_thumbs(w.get_active()))
        m.append(t)
        m.append(Gtk.SeparatorMenuItem())
        self._mi(m, label("fm.new_tab", "Nuova scheda") + "  (Ctrl+T)",
                 lambda: self.add_tab(self.tab().path))
        self._mi(m, label("fm.open_terminal", "Apri un terminale qui"),
                 self.open_terminal)
        m.append(Gtk.SeparatorMenuItem())
        self._mi(m, label("fm.trash", "Cestino"), self.open_trash)
        m.show_all()
        m.popup_at_pointer(Gdk.Event.new(Gdk.EventType.BUTTON_PRESS))

    def _toggle_hidden(self, val):
        self.show_hidden = val
        self.tab().load()

    def _toggle_thumbs(self, val):
        self.thumbnails = val
        self.tab().load()

    # -- tastiera ----------------------------------------------------------
    def on_key(self, _w, ev):
        ctrl = bool(ev.state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(ev.state & Gdk.ModifierType.SHIFT_MASK)
        k = ev.keyval
        if ctrl and k in (Gdk.KEY_c, Gdk.KEY_C):
            self.copy_selection(False)
            return True
        if ctrl and k in (Gdk.KEY_x, Gdk.KEY_X):
            self.copy_selection(True)
            return True
        if ctrl and k in (Gdk.KEY_v, Gdk.KEY_V):
            self.paste()
            return True
        if ctrl and k in (Gdk.KEY_h, Gdk.KEY_H):
            self._toggle_hidden(not self.show_hidden)
            return True
        if ctrl and k in (Gdk.KEY_t, Gdk.KEY_T):
            self.add_tab(self.tab().path)
            return True
        if ctrl and k in (Gdk.KEY_w, Gdk.KEY_W):
            self.close_tab(self.tab())
            return True
        if ctrl and k in (Gdk.KEY_l, Gdk.KEY_L):
            self.entry.grab_focus()
            return True
        if k == Gdk.KEY_F5:
            self.tab().load()
            return True
        if k == Gdk.KEY_F2:
            self.rename_selection()
            return True
        if k == Gdk.KEY_Delete:
            self.delete_selection() if shift else self.trash_selection()
            return True
        if k == Gdk.KEY_BackSpace:
            self.tab().up()
            return True
        if k == Gdk.KEY_Escape:
            self.entry.set_text(str(self.tab().path))
            return True
        return False

    # -- dialoghi ----------------------------------------------------------
    def ask(self, title, preset=""):
        d = Gtk.Dialog(title=title, transient_for=self, modal=True)
        d.add_button(label("v.cancel", "Annulla"), Gtk.ResponseType.CANCEL)
        d.add_button("OK", Gtk.ResponseType.OK)
        d.set_default_response(Gtk.ResponseType.OK)
        e = Gtk.Entry()
        e.set_text(preset)
        e.set_activates_default(True)
        area = d.get_content_area()
        area.set_spacing(8)
        area.set_border_width(12)
        area.pack_start(e, False, False, 0)
        d.show_all()
        resp = d.run()
        val = e.get_text().strip()
        d.destroy()
        return val if resp == Gtk.ResponseType.OK else None

    def confirm(self, title, body=""):
        d = Gtk.MessageDialog(transient_for=self, modal=True,
                              message_type=Gtk.MessageType.QUESTION,
                              buttons=Gtk.ButtonsType.YES_NO, text=title)
        if body:
            d.format_secondary_text(body)
        resp = d.run()
        d.destroy()
        return resp == Gtk.ResponseType.YES

    def info(self, title, body=""):
        d = Gtk.MessageDialog(transient_for=self, modal=True,
                              message_type=Gtk.MessageType.INFO,
                              buttons=Gtk.ButtonsType.OK, text=title)
        if body:
            d.format_secondary_text(body)
        d.run()
        d.destroy()

    def error(self, title, body=""):
        d = Gtk.MessageDialog(transient_for=self, modal=True,
                              message_type=Gtk.MessageType.ERROR,
                              buttons=Gtk.ButtonsType.OK, text=title)
        if body:
            d.format_secondary_text(body)
        d.run()
        d.destroy()


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    start = Path(argv[0]).expanduser() if argv else paths.HOME
    if not start.is_dir():
        start = start.parent if start.parent.is_dir() else paths.HOME
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        print("vesper-files: serve una sessione grafica (DISPLAY)", file=sys.stderr)
        return 1
    w = FileWindow(start)
    w.show_all()
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
