# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Pannello di Vesper: la barra del desktop.

Barra nativa GTK3 con icone simboliche, agganciabile in basso o in alto
(configurabile da ~/.config/vesper/panel.conf, vedi panelcfg.py):

  [menu] [term][file][centro] | lista finestre... | applet | [orologio]

In multi-monitor si crea UNA barra per schermo, così barra e menu compaiono
anche sullo schermo esterno. La lista finestre viene da `wmctrl -l` (poll
~1s); il clic attiva la finestra o la minimizza se già attiva. Niente conky,
niente tint2: solo GTK3 + wmctrl. Le icone seguono il tema icone scelto e il
colore lo impone il CSS (.vesper-panel button image), quindi seguono l'accent
del preset attivo.
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import threading
import time

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf, Pango  # noqa: E402

from vesper.common import (apply_css, have, run_bg,      # noqa: E402
                           install_screens_refresh_monitor)
from vesper import panelcfg  # noqa: E402
from vesper.desktopentry import scan_desktop_apps, launch as launch_app  # noqa: E402

# i18n condiviso (it/en/fr/es/de). Soft-import: se assente, _t restituisce la
# chiave (l'interfaccia non va mai in crash per una traduzione mancante).
try:
    from vesper.i18n import t as _t, current_lang as _current_lang  # noqa: E402
    _LANG = _current_lang()
except Exception:                 # noqa: BLE001
    def _t(key, **kw):
        return key
    _LANG = "it"

# Preset di aspetto (nessuna dipendenza GTK). Se assente, il pannello resta
# pienamente funzionante senza la voce dell'aspetto.
try:
    from vesper.profiles import model as presets_model  # noqa: E402
except Exception:                                       # noqa: BLE001
    presets_model = None

# Categorie del menu applicazioni: quelle STANDARD freedesktop (le stesse che
# usano gli altri DE), ognuna con la sua icona simbolica e l'elenco dei valori
# `Categories=` dei file .desktop che le finiscono dentro. L'ordine è quello di
# visualizzazione; "other" raccoglie tutto il resto.
APP_CATEGORIES = [
    ("favorites",   ("Preferite",        "starred-symbolic", ())),
    ("accessories", ("Accessori",        "applications-utilities-symbolic",
                     ("Utility", "Accessories", "Core"))),
    ("development", ("Sviluppo",         "applications-engineering-symbolic",
                     ("Development", "Building", "Debugger", "IDE"))),
    ("education",   ("Istruzione",       "applications-science-symbolic",
                     ("Education", "Science", "Math"))),
    ("games",       ("Giochi",           "applications-games-symbolic",
                     ("Game",))),
    ("graphics",    ("Grafica",          "applications-graphics-symbolic",
                     ("Graphics", "Photography", "Viewer"))),
    ("internet",    ("Internet",         "applications-internet-symbolic",
                     ("Network", "WebBrowser", "Email", "Chat", "P2P"))),
    ("multimedia",  ("Audio e video",    "applications-multimedia-symbolic",
                     ("AudioVideo", "Audio", "Video", "Player", "Recorder"))),
    ("office",      ("Ufficio",          "x-office-document-symbolic",
                     ("Office", "WordProcessor", "Spreadsheet", "Presentation"))),
    ("settings",    ("Impostazioni",     "preferences-system-symbolic",
                     ("Settings", "DesktopSettings", "HardwareSettings"))),
    ("system",      ("Sistema",          "applications-system-symbolic",
                     ("System", "Monitor", "FileTools", "TerminalEmulator",
                      "Security", "Filesystem"))),
    ("other",       ("Altre",            "application-x-executable-symbolic",
                     ())),
]
APP_CAT_LABEL = {k: v[0] for k, v in APP_CATEGORIES}     # etichette IT (fallback)
APP_CAT_ICON = {k: v[1] for k, v in APP_CATEGORIES}
APP_CAT_ORDER = [k for k, _ in APP_CATEGORIES]
# valore .desktop -> id categoria nostra (il primo che combacia vince)
_XDG_TO_CAT = {}
for _cid, (_lbl, _ico, _vals) in APP_CATEGORIES:
    for _v in _vals:
        _XDG_TO_CAT.setdefault(_v, _cid)


def cat_label(cat):
    """Nome tradotto della categoria (risolto a runtime: segue la lingua).
    Se la traduzione manca si usa l'etichetta italiana di APP_CATEGORIES."""
    s = _t("appcat." + cat)
    return APP_CAT_LABEL.get(cat, cat) if s == "appcat." + cat else s


def app_category(entry) -> str:
    """Categoria nostra per una voce .desktop, dal suo campo Categories."""
    for v in (entry.get("categories") or "").split(";"):
        v = v.strip()
        if v in _XDG_TO_CAT:
            return _XDG_TO_CAT[v]
    return "other"

PANEL_HEIGHT = panelcfg.get_height()
ICON_PX = panelcfg.get_icon_px()
POLL_MS = 1000

# Fusi orari offerti nel popup dell'orologio (cambio al volo senza aprire il
# Centro di Controllo). Il fuso corrente, se non in lista, viene aggiunto in cima.
COMMON_TZ = [
    "Europe/Rome", "Europe/London", "Europe/Paris", "Europe/Berlin",
    "Europe/Madrid", "Europe/Athens", "Europe/Moscow", "UTC",
    "America/New_York", "America/Chicago", "America/Denver",
    "America/Los_Angeles", "America/Sao_Paulo", "Asia/Dubai",
    "Asia/Kolkata", "Asia/Shanghai", "Asia/Tokyo", "Australia/Sydney",
]

# --- monitor di sistema (mini-grafici stile multiload) -----------------------
MON_HIST = 30          # campioni tenuti in ogni grafico
MON_MS = 1500          # intervallo di aggiornamento (ms)
# Dischi FISICI interi (no partizioni/loop/ram) per l'I/O da /proc/diskstats.
_DISK_RE = re.compile(r'^(sd[a-z]+|vd[a-z]+|hd[a-z]+|xvd[a-z]+|'
                      r'nvme\d+n\d+|mmcblk\d+)$')


# Finestre da NON mostrare nella tasklist: la finestra "desktop" del nostro
# file manager (vesper-files --desktop) e i popup del pannello. Il file manager
# in modalita' finestra ha come titolo il nome della cartella, quindi resta.
_SKIP_TITLES = {"desktop", "vesper-desktop", "", "vesper-popup"}


def _set_x_cardinals(gdk_window, nome: str, valori) -> None:
    """Scrive una proprietà X di tipo CARDINAL (32 bit) sulla finestra.

    Serve per _NET_WM_STRUT / _NET_WM_STRUT_PARTIAL, con cui il pannello
    dichiara al gestore finestre lo spazio da NON coprire. PyGObject non
    espone più `Gdk.property_change`, quindi si chiama Xlib direttamente con
    ctypes: libX11 è presente ovunque giri X, nessuna dipendenza nuova.
    """
    import ctypes

    from gi.repository import GdkX11                       # noqa: PLC0415

    xid = GdkX11.X11Window.get_xid(gdk_window)
    xlib = ctypes.CDLL("libX11.so.6")
    xlib.XOpenDisplay.restype = ctypes.c_void_p
    xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    xlib.XInternAtom.restype = ctypes.c_ulong
    xlib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    xlib.XChangeProperty.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong,
        ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int]
    xlib.XFlush.argtypes = [ctypes.c_void_p]
    xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]

    dpy = xlib.XOpenDisplay(None)
    if not dpy:
        raise RuntimeError("nessun display X")
    try:
        prop = xlib.XInternAtom(dpy, nome.encode(), False)
        cardinal = xlib.XInternAtom(dpy, b"CARDINAL", False)
        # formato 32 = array di `long` per Xlib (non di uint32)
        dati = (ctypes.c_long * len(valori))(*valori)
        xlib.XChangeProperty(dpy, xid, prop, cardinal, 32, 0,  # 0 = Replace
                             ctypes.cast(dati, ctypes.POINTER(ctypes.c_ubyte)),
                             len(valori))
        xlib.XFlush(dpy)
    finally:
        xlib.XCloseDisplay(dpy)


def _xid_int(wid):
    """Converte un id finestra di wmctrl (es. '0x0a000005') in intero."""
    try:
        return int(wid, 16)
    except (TypeError, ValueError):
        return -1


def _wmctrl_list():
    """Ritorna [(id, desktop, titolo)] delle finestre normali."""
    try:
        out = subprocess.run(["wmctrl", "-l"], capture_output=True,
                             text=True, timeout=3).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    wins = []
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        wid, desk, _host, title = parts
        if desk == "-1":          # finestre sticky/desktop escluse
            continue
        if title.strip().lower() in _SKIP_TITLES:   # desktop di pcmanfm
            continue
        wins.append((wid, desk, title))
    return wins


def _wmctrl_desktops():
    """Ritorna (numero_desktop, indice_corrente) via 'wmctrl -d'."""
    try:
        out = subprocess.run(["wmctrl", "-d"], capture_output=True,
                             text=True, timeout=3).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return (0, -1)
    count = 0; cur = -1
    for line in out.splitlines():
        parts = line.split()
        if not parts:
            continue
        try:
            idx = int(parts[0])
        except ValueError:
            continue
        count += 1
        if len(parts) > 1 and parts[1] == "*":
            cur = idx
    return (count, cur)


def _active_window():
    """ID esadecimale della finestra attiva (via Gdk, nessuna dipendenza)."""
    try:
        w = Gdk.Screen.get_default().get_active_window()
        if w is not None:
            return "0x%08x" % w.get_xid()
    except Exception:
        pass
    return None


def _tray_img(icon_name):
    """Immagine per la barra, dimensionata a ICON_PX (configurabile)."""
    img = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.LARGE_TOOLBAR)
    img.set_pixel_size(ICON_PX)
    return img


def _icon_button(icon_name, tooltip, css_class="vesper-icon"):
    b = Gtk.Button()
    b.set_relief(Gtk.ReliefStyle.NONE)
    b.set_tooltip_text(tooltip)
    b.get_style_context().add_class(css_class)
    b.set_image(_tray_img(icon_name))
    b.set_always_show_image(True)
    return b


def _app_image(icon, px=22):
    """Immagine per una voce app, SEMPRE alla dimensione richiesta.

    CAUSA A MONTE dell "icona enorme nel menu": alcune applicazioni spediscono
    la propria icona in UNA SOLA misura, grande. lxterminal, per esempio, ha
    solo /usr/share/icons/hicolor/128x128/apps/lxterminal.png (verificato).
    Gtk.Image.new_from_icon_name NON forza il ridimensionamento: quando il tema
    offre unicamente la variante da 128px, quella finisce nel menu a grandezza
    naturale e sfonda la riga. Gtk.IconTheme.load_icon con FORCE_SIZE garantisce
    invece esattamente la misura chiesta.
    """
    # 1) percorso assoluto nel .desktop: caricalo e scalalo
    try:
        if icon and icon.startswith("/") and os.path.exists(icon):
            pix = GdkPixbuf.Pixbuf.new_from_file_at_size(icon, px, px)
            return Gtk.Image.new_from_pixbuf(pix)
    except Exception:                                # noqa: BLE001
        pass

    nome = icon or "application-x-executable"
    # il campo Icon a volte porta l estensione: per il tema serve il nome nudo
    for ext in (".png", ".svg", ".xpm"):
        if nome.endswith(ext):
            nome = nome[:-len(ext)]
            break

    # 2) nome dal tema, con dimensione FORZATA
    try:
        pix = Gtk.IconTheme.get_default().load_icon(
            nome, px, Gtk.IconLookupFlags.FORCE_SIZE)
        if pix is not None:
            return Gtk.Image.new_from_pixbuf(pix)
    except Exception:                                # noqa: BLE001
        pass

    # 3) ripiego: alcune app mettono il file in pixmaps, fuori da ogni tema
    for base in ("/usr/share/pixmaps/", "/usr/local/share/pixmaps/"):
        for ext in (".png", ".svg", ".xpm"):
            f = base + nome + ext
            try:
                if os.path.exists(f):
                    return Gtk.Image.new_from_pixbuf(
                        GdkPixbuf.Pixbuf.new_from_file_at_size(f, px, px))
            except Exception:                        # noqa: BLE001
                pass

    return Gtk.Image.new_from_icon_name("application-x-executable",
                                        Gtk.IconSize.LARGE_TOOLBAR)


def _human(n):
    """Byte/s -> stringa compatta (es. 1536 -> '2K')."""
    for unit in ("B", "K", "M", "G"):
        if n < 1024 or unit == "G":
            return "%.0f%s" % (n, unit)
        n /= 1024.0


class _Meter(Gtk.DrawingArea):
    """Mini-grafico a barre (storia scorrevole) di una risorsa, valori 0..1."""
    def __init__(self, rgb):
        super().__init__()
        self.rgb = rgb
        self.hist = [0.0] * MON_HIST
        self.set_size_request(30, PANEL_HEIGHT - 12)
        self.connect("draw", self._draw)

    def push(self, v):
        v = 0.0 if v < 0 else (1.0 if v > 1 else v)
        self.hist.append(v)
        del self.hist[0]
        self.queue_draw()

    @staticmethod
    def _chiaro() -> bool:
        """Interfaccia chiara? Il grafico è disegnato in Cairo, quindi il CSS
        non lo tocca: il colore di fondo va scelto qui."""
        try:
            from vesper import palette
            return palette.is_light()
        except Exception:                # noqa: BLE001
            return False

    def _draw(self, _w, cr):
        w = self.get_allocated_width()
        h = self.get_allocated_height()
        if self._chiaro():
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.75)      # fondo chiaro
        else:
            cr.set_source_rgba(0.02, 0.06, 0.10, 0.85)   # fondo scuro
        cr.rectangle(0, 0, w, h)
        cr.fill()
        r, g, b = self.rgb
        n = len(self.hist)
        if n >= 2:
            step = w / (n - 1)

            def yv(v):
                return h - 1 - (0.0 if v < 0 else (1.0 if v > 1 else v)) * (h - 2)
            # area riempita (sparkline stile multiload)
            cr.move_to(0, h)
            for i, v in enumerate(self.hist):
                cr.line_to(i * step, yv(v))
            cr.line_to((n - 1) * step, h)
            cr.close_path()
            cr.set_source_rgba(r, g, b, 0.45 if self._chiaro() else 0.30)
            cr.fill()
            # linea di contorno
            cr.set_source_rgba(r, g, b, 0.95)
            cr.set_line_width(1.2)
            for i, v in enumerate(self.hist):
                (cr.move_to if i == 0 else cr.line_to)(i * step, yv(v))
            cr.stroke()
        if self._chiaro():
            cr.set_source_rgba(0.72, 0.78, 0.83, 0.9)  # bordo tenue (chiaro)
        else:
            cr.set_source_rgba(0.10, 0.23, 0.32, 0.9)  # bordo tenue (scuro)
        cr.set_line_width(1)
        cr.rectangle(0.5, 0.5, w - 1, h - 1)
        cr.stroke()


class LoadMonitor(Gtk.EventBox):
    """Applet risorse: mini-grafici CPU / RAM / Rete letti da /proc (nessuna
    dipendenza esterna). Clic -> Monitor risorse del Centro di Controllo."""
    def __init__(self):
        super().__init__()
        self.get_style_context().add_class("vesper-loadmon")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        box.set_valign(Gtk.Align.CENTER)
        self.load = _Meter((1.00, 0.45, 0.58))   # rosa/rosso: carico medio
        self.cpu = _Meter((0.00, 0.898, 1.00))   # cyan
        self.mem = _Meter((0.40, 0.95, 0.65))    # verde
        self.net = _Meter((1.00, 0.72, 0.25))    # ambra
        self.disk = _Meter((0.66, 0.55, 1.00))   # viola (I/O disco)
        self._ncpu = os.cpu_count() or 1
        for m in (self.load, self.cpu, self.mem, self.net, self.disk):
            box.pack_start(m, False, False, 0)
        self.add(box)
        self.set_tooltip_text(_t("pn.tip.monitor"))
        self.connect("button-press-event", self._on_click)

        self._prev_cpu = self._read_cpu()
        self._prev_net = self._read_net()
        self._prev_disk = self._read_disk()
        self._net_peak = 64 * 1024.0
        self._disk_peak = 128 * 1024.0
        self._alive = True
        self.connect("destroy", lambda *_: setattr(self, "_alive", False))
        GLib.timeout_add(MON_MS, self._tick)

    def _on_click(self, _w, _e):
        run_bg(["vesper-control-center", "monitor"])
        return True

    @staticmethod
    def _read_cpu():
        try:
            with open("/proc/stat") as f:
                parts = f.readline().split()
            vals = [float(x) for x in parts[1:]]
            idle = vals[3] + (vals[4] if len(vals) > 4 else 0.0)  # idle+iowait
            return idle, sum(vals)
        except (OSError, ValueError, IndexError):
            return 0.0, 0.0

    @staticmethod
    def _read_mem():
        try:
            info = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    k, _, rest = line.partition(":")
                    info[k] = float(rest.split()[0])
            total = info.get("MemTotal", 0.0)
            avail = info.get("MemAvailable", info.get("MemFree", 0.0))
            return 0.0 if total <= 0 else 1.0 - avail / total
        except (OSError, ValueError, IndexError):
            return 0.0

    @staticmethod
    def _read_net():
        tot = 0.0
        try:
            with open("/proc/net/dev") as f:
                for line in f.readlines()[2:]:
                    iface, _, data = line.partition(":")
                    if iface.strip() == "lo":
                        continue
                    cols = data.split()
                    tot += float(cols[0]) + float(cols[8])   # rx + tx bytes
        except (OSError, ValueError, IndexError):
            pass
        return tot

    @staticmethod
    def _read_disk():
        """Byte totali letti+scritti dai dischi FISICI (da /proc/diskstats).
        Solo i dischi interi (sd*, vd*, nvme*n*, mmcblk*, hd*, xvd*) per non
        contare due volte disco + partizioni; esclude loop/ram. Settori * 512."""
        sectors = 0.0
        try:
            with open("/proc/diskstats") as f:
                for line in f:
                    p = line.split()
                    if len(p) < 11:
                        continue
                    if not _DISK_RE.match(p[2]):
                        continue
                    sectors += float(p[5]) + float(p[9])     # letti + scritti
        except (OSError, ValueError, IndexError):
            pass
        return sectors * 512.0

    def _tick(self):
        idle, total = self._read_cpu()
        pidle, ptotal = self._prev_cpu
        dt = total - ptotal
        cpu = 0.0 if dt <= 0 else max(0.0, 1.0 - (idle - pidle) / dt)
        self._prev_cpu = (idle, total)
        self.cpu.push(cpu)

        mem = self._read_mem()
        self.mem.push(mem)

        cur = self._read_net()
        rate = max(0.0, cur - self._prev_net) / (MON_MS / 1000.0)
        self._prev_net = cur
        # auto-scala sul picco osservato (decadimento lento), minimo 64K/s
        self._net_peak = max(self._net_peak * 0.98, rate, 64 * 1024.0)
        self.net.push(rate / self._net_peak)

        dcur = self._read_disk()
        drate = max(0.0, dcur - self._prev_disk) / (MON_MS / 1000.0)
        self._prev_disk = dcur
        self._disk_peak = max(self._disk_peak * 0.98, drate, 128 * 1024.0)
        self.disk.push(drate / self._disk_peak)

        # Carico medio (load average) normalizzato sui core: 1.0 = tutti i core pieni.
        try:
            la1, la5, la15 = os.getloadavg()
        except OSError:
            la1 = la5 = la15 = 0.0
        self.load.push(min(1.0, la1 / self._ncpu))

        self.set_tooltip_text(
            "Carico %.2f/%.2f/%.2f (%d core)   CPU %d%%   RAM %d%%   "
            "Rete %s/s   Disco %s/s   (clic: Monitor)"
            % (la1, la5, la15, self._ncpu, round(cpu * 100), round(mem * 100),
               _human(rate), _human(drate)))
        return self._alive


class Panel(Gtk.Window):
    def __init__(self, monitor_index=None):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        apply_css()
        # Su quale monitor si ancora questa barra: indice Gdk (None = primario).
        # In multi-monitor si crea UNA Panel per schermo (vedi run()), cosi' la
        # barra e il menu compaiono anche sul monitor esterno.
        self._monitor_index = monitor_index
        self.position = panelcfg.get_position()
        self.set_type_hint(Gdk.WindowTypeHint.DOCK)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.stick()
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        ctx = self.get_style_context()
        ctx.add_class("vesper-panel")
        if self.position == "top":
            ctx.add_class("vesper-panel-top")

        self._task_btns = {}      # id -> Gtk.Button
        self._last_sig = None
        self._popups = {}         # key -> finestra toplevel aperta
        self._popup_closed = {}   # key -> timestamp ultima chiusura (anti-rimbalzo)
        # Flag di vita: in multi-monitor le barre si ricostruiscono (hotplug),
        # ma i GLib.timeout restano attivi anche dopo destroy -> i callback
        # ritornano self._alive per auto-cancellarsi sulla barra distrutta.
        self._alive = True
        self.connect("destroy", lambda *_: setattr(self, "_alive", False))
        # Riconsidera la propria geometria quando cambiano i monitor o la
        # risoluzione: con un monitor esterno che spegne quello interno (xrandr
        # --off) le barre devono ripiazzarsi sul monitor attivo, NON rimanere
        # su quello spento.
        scr = self.get_screen()
        if scr is not None:
            scr.connect("monitors-changed",
                        lambda *_: GLib.idle_add(self._safe_place))
            scr.connect("size-changed",
                        lambda *_: GLib.idle_add(self._safe_place))

        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.add(root)

        # --- Sinistra: menu + lanciatori (icone) ---
        left = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        root.pack_start(left, False, False, 0)

        # Marchio di Vesper in versione SIMBOLICA (la stella della sera):
        # monocromo, così GTK lo ricolora col colore della skin/preset del
        # pannello come tutte le altre icone. Vedi data/icons/hicolor/scalable/
        # apps/vesper-logo-symbolic.svg.
        menu_btn = _icon_button("vesper-logo-symbolic", _t("menu.title"), "vesper-menu")
        menu_btn.connect("clicked", self._on_menu)
        left.pack_start(menu_btn, False, False, 0)

        left.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL),
                        False, False, 0)

        # Lanciatori di serie: solo componenti DI VESPER (terminale, file
        # manager, Centro di Controllo). Niente app di terze parti fissate
        # nella barra: quelle stanno nel menu Applicazioni, che le trova da
        # sole dai file .desktop.
        for icon, tip, cmd in (
            ("utilities-terminal-symbolic", _t("app.terminal"), ["vesper-terminal"]),
            ("system-file-manager-symbolic", _t("app.files_short"), ["vesper-files"]),
            ("preferences-system-symbolic", _t("app.control_center"),
             ["vesper-control-center"]),
        ):
            b = _icon_button(icon, tip)
            b.connect("clicked", lambda _w, c=cmd: run_bg(c))
            left.pack_start(b, False, False, 0)

        left.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL),
                        False, False, 0)

        # --- Pager desktop virtuali (workspaces): compare solo se > 1 ---
        self.pager = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self.pager.get_style_context().add_class("vesper-pager")
        left.pack_start(self.pager, False, False, 2)
        self.pager_sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        left.pack_start(self.pager_sep, False, False, 0)
        self._pager_btns = {}
        self._n_desktops = 0
        self._cur_desktop = -1

        # --- Centro: lista finestre ---
        self.tasks = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        root.pack_start(self.tasks, True, True, 0)

        # --- Destra (da DESTRA a sinistra): mostra-desktop, orologio+data,
        #     WiFi, Schermi, monitor risorse. In pack_start (sinistra->destra)
        #     l'ordine e' quindi: monitor, Schermi, WiFi, orologio, desktop. ---
        right = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        root.pack_end(right, False, False, 0)

        # Mini-grafici CPU/RAM/Rete/Disco (stile multiload), clic -> Monitor.
        self.loadmon = LoadMonitor()
        right.pack_start(self.loadmon, False, False, 4)

        right.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL),
                         False, False, 0)

        # Applet Schermi (xrandr) e WiFi (scan/connessione): compaiono sempre;
        # se manca l'hardware il popup lo segnala.
        scr_btn = _icon_button("video-display-symbolic", _t("tray.screens"))
        scr_btn.connect("clicked", self._toggle_screens)
        right.pack_start(scr_btn, False, False, 0)

        self.wifi_btn = _icon_button("network-wireless-offline-symbolic", _t("tray.wifi"))
        self.wifi_btn.connect("clicked", self._toggle_wifi)
        right.pack_start(self.wifi_btn, False, False, 0)

        # Audio (volume/uscite via wpctl-PipeWire): clic = popup, rotella = +/-.
        self.vol_btn = _icon_button("audio-volume-medium-symbolic", _t("tray.audio"))
        self.vol_btn.connect("clicked", self._toggle_volume)
        self.vol_btn.add_events(Gdk.EventMask.SCROLL_MASK)
        self.vol_btn.connect("scroll-event", self._vol_scroll)
        right.pack_start(self.vol_btn, False, False, 0)

        # Microfono (source PipeWire): applet a sé nella barra (stile MATE).
        # Compare SOLO se un mic e' presente (visibilita' decisa dal poll):
        # clic = popup (livello/muta/ingresso), rotella = +/- diretto sul volume.
        self.mic_btn = _icon_button("audio-input-microphone-symbolic", _t("pn.tray.mic"))
        self.mic_btn.connect("clicked", self._toggle_mic)
        self.mic_btn.add_events(Gdk.EventMask.SCROLL_MASK)
        self.mic_btn.connect("scroll-event", self._mic_scroll)
        self.mic_btn.set_no_show_all(True)          # la visibilita' la decide il poll
        right.pack_start(self.mic_btn, False, False, 0)

        # Bluetooth (bluetoothctl-BlueZ): clic = popup accensione/scan/connetti.
        self.bt_btn = _icon_button("bluetooth-active-symbolic", _t("tray.bluetooth"))
        self.bt_btn.connect("clicked", self._toggle_bluetooth)
        right.pack_start(self.bt_btn, False, False, 0)

        # Lingua dell'interfaccia: applet nella barra (oltre alla voce di menu).
        # Clic -> stesso popup di scelta (_choose_language), cambio al volo.
        self.lang_btn = _icon_button("preferences-desktop-locale-symbolic",
                                     _t("menu.language"))
        self.lang_btn.connect("clicked", lambda _b: self._choose_language())
        right.pack_start(self.lang_btn, False, False, 0)

        # Batteria / alimentazione (sysfs): l'applet compare solo se presente
        # una batteria o un alimentatore (su desktop fissi resta nascosto).
        self.batt_btn = _icon_button("battery-missing-symbolic", _t("tray.battery"))
        self.batt_btn.connect("clicked", self._toggle_battery)
        self.batt_btn.set_no_show_all(True)      # la visibilita' la decide il poll
        right.pack_start(self.batt_btn, False, False, 0)

        right.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL),
                         False, False, 0)

        clock_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        clock_box.set_valign(Gtk.Align.CENTER)
        self.clock = Gtk.Label()
        self.clock.get_style_context().add_class("vesper-clock")
        self.date = Gtk.Label()
        self.date.get_style_context().add_class("vesper-clock-date")
        clock_box.pack_start(self.clock, False, False, 0)
        clock_box.pack_start(self.date, False, False, 0)

        # Pulsante orologio: apre/chiude il calendario (finestra toplevel).
        self.clock_btn = Gtk.Button()
        self.clock_btn.set_relief(Gtk.ReliefStyle.NONE)
        self.clock_btn.set_tooltip_text(_t("tray.calendar"))
        self.clock_btn.get_style_context().add_class("vesper-clock-btn")
        self.clock_btn.add(clock_box)
        self.clock_btn.connect("clicked", self._toggle_calendar)
        right.pack_start(self.clock_btn, False, False, 0)

        sd = _icon_button("user-desktop-symbolic", _t("tray.show_desktop"))
        sd.connect("clicked", self._on_show_desktop)
        right.pack_start(sd, False, False, 0)

        self._place()
        self.connect("screen-changed", lambda *_: self._place())
        self.connect("realize", self._on_realize)

        self._tick_clock()
        self._refresh_tasks()
        GLib.timeout_add(POLL_MS, self._refresh_tasks)
        GLib.timeout_add(1000, self._tick_clock)
        # icone audio/bluetooth aggiornate periodicamente (non bloccante)
        self._refresh_media()
        GLib.timeout_add(4000, self._refresh_media)

    # --- geometria ---
    def _place(self):
        if not getattr(self, "_alive", False):
            return
        scr = self.get_screen()
        if scr is None:
            return
        n = scr.get_n_monitors() if hasattr(scr, "get_n_monitors") else 1
        mon = self._monitor_index
        # Indice non valido (monitor scollegato) -> ripiega sul primario.
        if mon is None or mon < 0 or mon >= n:
            mon = (scr.get_primary_monitor()
                   if hasattr(scr, "get_primary_monitor") else 0)
        geo = scr.get_monitor_geometry(mon)
        self._geo = geo
        self.set_size_request(geo.width, PANEL_HEIGHT)
        if self.position == "top":
            self.move(geo.x, geo.y)
        else:
            self.move(geo.x, geo.y + geo.height - PANEL_HEIGHT)
        self._set_struts(geo)

    def _set_struts(self, geo=None):
        """Dichiara al gestore finestre lo spazio occupato dalla barra
        (_NET_WM_STRUT e _NET_WM_STRUT_PARTIAL).

        Senza questa dichiarazione le finestre MASSIMIZZATE finiscono SOTTO il
        pannello e il loro bordo inferiore non si vede. Prima ci si affidava ai
        <margins> di rc.xml, che però valgono solo per Openbox: con marco o
        metacity (che Vesper usa per le decorazioni di Mint) non hanno alcun
        effetto. Gli strut invece li capiscono tutti i gestori finestre
        conformi a EWMH, e seguono la geometria REALE della barra."""
        win = self.get_window()
        if win is None:
            return                          # non ancora realizzata: al realize
        if geo is None:
            geo = getattr(self, "_geo", None)
            if geo is None:
                return
        scr = self.get_screen()
        try:
            schermo_h = scr.get_height()
            schermo_w = scr.get_width()
        except Exception:                    # noqa: BLE001
            return
        alto = self.position == "top"
        # Quanto togliere al bordo: l'altezza della barra PIÙ la distanza fra
        # il bordo del monitor e il bordo dello schermo (in multi-monitor la
        # barra non sta sul bordo dello schermo, e lo strut si misura da lì).
        if alto:
            top = geo.y + PANEL_HEIGHT
            bottom = 0
        else:
            top = 0
            bottom = schermo_h - (geo.y + geo.height) + PANEL_HEIGHT
        strut = [0, 0, max(0, top), max(0, bottom)]
        # la parte parziale dice anche DA DOVE A DOVE, così su più monitor lo
        # spazio si riserva solo sulla porzione coperta davvero dalla barra
        x1, x2 = geo.x, min(schermo_w, geo.x + geo.width) - 1
        parziale = strut + [0, 0, 0, 0] + ([x1, x2] if alto else [0, 0]) \
            + ([0, 0] if alto else [x1, x2])
        # PyGObject non espone più Gdk.property_change, quindi la proprietà
        # si scrive con Xlib via ctypes: libX11 c'è sempre dove gira X.
        try:
            _set_x_cardinals(win, "_NET_WM_STRUT", strut)
            _set_x_cardinals(win, "_NET_WM_STRUT_PARTIAL", parziale)
        except Exception as e:               # noqa: BLE001
            print("[vesper] spazio riservato non dichiarato:", e, file=sys.stderr)

    def _center_dialog(self, d):
        """Centra un dialogo sul MONITOR di questo pannello.

        Perche' non basta transient_for: il genitore e' il pannello, una barra
        alta PANEL_HEIGHT incollata a un bordo, e il default GTK
        (CENTER_ON_PARENT) lo piazza percio' a filo del bordo inferiore. E non
        basta nemmeno CENTER_ALWAYS: su X con due monitor "schermo" e' l'area
        virtuale complessiva, quindi il dialogo finirebbe a cavallo dei due.
        Usiamo la geometria del monitor su cui vive questa barra."""
        try:
            geo = getattr(self, "_geo", None)
            if geo is None:
                d.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
                return
            d.set_position(Gtk.WindowPosition.NONE)

            def _place(*_a):
                try:
                    w, h = d.get_size()
                    d.move(geo.x + max(0, (geo.width - w) // 2),
                           geo.y + max(0, (geo.height - h) // 2))
                except Exception:            # noqa: BLE001
                    pass
                return False
            d.connect("show", lambda *_a: GLib.idle_add(_place))
        except Exception:                    # noqa: BLE001
            pass

    def _safe_place(self):
        """Riposiziona questa barra in modo sicuro: no-op se la barra e' stata
        distrutta (hotplug) o lo schermo non e' piu' disponibile."""
        if not getattr(self, "_alive", False):
            return False
        try:
            self._place()
        except Exception:
            pass
        return False

    def _on_realize(self, _w):
        # Lo spazio riservato si dichiara con gli strut EWMH (vedi
        # _set_struts): vale per qualunque gestore finestre, non solo Openbox.
        self._place()
        self._set_struts()

    # --- popup come finestre toplevel keep_above (i Gtk.Popover su Openbox
    #     senza compositor finivano "sotto" lo sfondo) ---
    def _spawn_popup(self, key, content, align, autoclose=True, keep_bottom=False):
        # toggle: se gia' aperto, chiudi
        if key in self._popups:
            self._popups.pop(key).destroy()
            self._popup_closed[key] = time.time()
            return
        # anti-rimbalzo: evita la riapertura immediata dopo il focus-out
        if time.time() - self._popup_closed.get(key, 0) < 0.25:
            return

        w = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        w.set_decorated(False)
        w.set_resizable(False)
        w.set_title("vesper-popup")          # filtrato dalla tasklist (vedi _SKIP_TITLES)
        w.set_skip_taskbar_hint(True)
        w.set_skip_pager_hint(True)
        w.set_keep_above(True)
        w.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        w.set_screen(self.get_screen())
        w.get_style_context().add_class("vesper-popup")
        w.add(content)
        w.show_all()

        _min, nat = w.get_preferred_size()
        pw, ph = nat.width, nat.height
        geo = self._geo
        margin = 6
        # Clamp: il popup non deve mai superare l'area disponibile (altrimenti il
        # bordo alto esce dallo schermo e le prime voci diventano irraggiungibili).
        avail_h = geo.height - PANEL_HEIGHT - margin
        if ph > avail_h:
            ph = avail_h
            w.resize(pw, ph)
        if align == "right":
            x = geo.x + geo.width - pw - margin
        else:
            x = geo.x + margin
        if self.position == "top":
            y = geo.y + PANEL_HEIGHT
        else:
            y = geo.y + geo.height - PANEL_HEIGHT - ph
        w.move(x, y)

        # Ancoraggio al FONDO per il pannello in basso: se il contenuto cambia
        # altezza (es. la ricerca del menu filtra le voci -> il popup si accorcia)
        # GTK ridimensiona la finestra tenendo fisso il bordo ALTO, cosi' il bordo
        # basso risaliva lasciando uno spazio dal pannello. Riposizioniamo a ogni
        # size-allocate mantenendo il bordo basso incollato al pannello.
        if keep_bottom and self.position != "top":
            bottom_y = geo.y + geo.height - PANEL_HEIGHT
            top_min = geo.y + margin
            self._popup_last_y = {} if not hasattr(self, "_popup_last_y") else self._popup_last_y

            def _reanchor(_w, alloc, _key=key, _x=x, _by=bottom_y, _tmin=top_min):
                ny = max(_tmin, _by - alloc.height)
                if self._popup_last_y.get(_key) != ny:
                    self._popup_last_y[_key] = ny
                    _w.move(_x, ny)
                return False
            w.connect("size-allocate", _reanchor)

        def on_focus_out(*_a):
            # Chiusura al clic FUORI, ma DIFFERITA e "intelligente": se il focus
            # e' passato a un combo/menu interno (che tiene un grab GTK) o e'
            # subito rientrato nel popup, NON chiudere -> cosi' i popup con combo
            # (fuso orario, schermi) restano aperti mentre scegli una voce, ma un
            # clic sul desktop o su un'altra finestra li chiude come atteso.
            GLib.timeout_add(150, self._autoclose_check, key)
            return False
        if autoclose:
            w.connect("focus-out-event", on_focus_out)

        def on_key(_w, ev):
            if ev.keyval == Gdk.KEY_Escape:
                self._close_popup(key)
                return True
            return False
        w.connect("key-press-event", on_key)
        self._popups[key] = w
        w.present()

    def _close_popup(self, key):
        if key in self._popups:
            self._popups.pop(key).destroy()
            self._popup_closed[key] = time.time()

    def _autoclose_check(self, key):
        """Decide (dopo il focus-out differito) se chiudere il popup. Chiude solo
        se il focus e' uscito DAVVERO: resta aperto se il popup ha riottenuto il
        focus o se un combo/menu interno tiene un grab GTK (sceglierne una voce
        chiuderebbe tutto). Cosi' il clic-fuori chiude, ma i combo funzionano."""
        w = self._popups.get(key)
        if w is None:
            return False
        try:
            if w.has_toplevel_focus():
                return False
        except Exception:                # noqa: BLE001
            pass
        # combo/menu interno aperto (fa un grab GTK) -> non chiudere ora
        if Gtk.grab_get_current() is not None:
            return False
        self._close_popup(key)
        return False

    def _refresh_media_once(self):
        """Aggiornamento icone audio/BT ONE-SHOT per GLib.timeout_add: come
        _refresh_media ma ritorna False, cosi' NON ri-arma un timer periodico.
        (Bug precedente: ogni scroll/mute/toggle lasciava un poller permanente
        perche' _refresh_media ritorna True -> i timer si accumulavano.)"""
        self._refresh_media()
        return False

    # --- menu applicazioni (con banda verticale laterale) ---
    def _menu_item(self, key, icon, label, cmd=None, move_to=None, confirm=None):
        b = Gtk.Button()
        b.set_relief(Gtk.ReliefStyle.NONE)
        b.get_style_context().add_class("vesper-menu-item")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        img = Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.LARGE_TOOLBAR)
        lab = Gtk.Label(label=label)
        lab.set_xalign(0)
        box.pack_start(img, False, False, 0)
        box.pack_start(lab, True, True, 0)
        b.add(box)

        def on_click(_w):
            self._close_popup(key)
            if move_to is not None:
                panelcfg.move_panel(move_to)
                return
            if cmd is None:
                return
            if confirm:
                d = Gtk.MessageDialog(
                    transient_for=self, modal=True,
                    message_type=Gtk.MessageType.QUESTION,
                    buttons=Gtk.ButtonsType.YES_NO, text=confirm)
                # Senza questo il dialogo esce incollato al bordo inferiore:
                # il genitore e' il pannello (vedi _center_dialog).
                self._center_dialog(d)
                d.set_keep_above(True)
                resp = d.run()
                d.destroy()
                if resp != Gtk.ResponseType.YES:
                    return
            run_bg(cmd)
        b.connect("clicked", on_click)
        return b

    # --- selettore lingua interfaccia (it/en/fr/es/de) ---
    def _choose_language(self):
        try:
            from vesper import i18n
            langs = list(i18n.LANGS)
            names = i18n.LANG_NAMES
            cur = i18n.current_lang()
        except Exception:                # noqa: BLE001
            return
        d = Gtk.Dialog(title=_t("lang.title"), transient_for=self, modal=True)
        d.add_button("OK", Gtk.ResponseType.OK)
        d.add_button("Annulla", Gtk.ResponseType.CANCEL)
        area = d.get_content_area()
        area.set_spacing(8)
        try:
            area.set_border_width(12)
        except Exception:                # noqa: BLE001
            pass
        combo = Gtk.ComboBoxText()
        for c in langs:
            combo.append(c, names.get(c, c))
        combo.set_active_id(cur)
        lab = Gtk.Label(label=_t("lang.title")); lab.set_xalign(0)
        area.pack_start(lab, False, False, 0)
        area.pack_start(combo, False, False, 0)
        hint = Gtk.Label(); hint.set_xalign(0)
        hint.set_markup("<small>%s</small>" % _t("lang.restart_hint"))
        area.pack_start(hint, False, False, 0)
        self._center_dialog(d)
        d.set_keep_above(True)
        d.show_all()
        resp = d.run()
        code = combo.get_active_id()
        d.destroy()
        if resp == Gtk.ResponseType.OK and code and code != cur:
            run_bg(["vesper-lang", "set", code])

    # --- preset di aspetto ---
    def _preset_data(self):
        """Dati del preset di aspetto corrente, o {} se il modulo è assente."""
        if presets_model is None:
            return {}
        try:
            return presets_model.preset_data()
        except Exception:                # noqa: BLE001
            return {}

    def _on_menu(self, _btn):
        """Costruisce e apre il menu: ricerca, voci di Vesper, applicazioni
        raggruppate per categoria (a fisarmonica) e footer di sessione."""
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        hbox.get_style_context().add_class("vesper-startmenu")

        # Banda verticale col nome del DE e, sotto, il preset di aspetto attivo.
        strip = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        strip.get_style_context().add_class("vesper-menu-strip")
        strip.set_valign(Gtk.Align.FILL)
        brand = Gtk.Label(label="Vesper")
        brand.get_style_context().add_class("brand")
        brand.set_angle(90)
        preset = self._preset_data()
        sub = Gtk.Label(label=preset.get("name", ""))
        sub.get_style_context().add_class("brand-sub")
        sub.set_angle(90)
        # Ancorate IN BASSO (pack_end): il nome parte ~14px dal fondo e legge
        # verso l'alto, senza uscire dallo schermo.
        strip.pack_end(brand, False, False, 14)
        strip.pack_end(sub, False, False, 0)
        hbox.pack_start(strip, False, False, 0)

        lst = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        lst.get_style_context().add_class("vesper-startmenu-list")
        # Con molte applicazioni la lista supera l'altezza schermo: la mettiamo
        # in uno ScrolledWindow che cresce fino allo spazio disponibile e poi
        # scorre, così nessuna voce resta tagliata in alto.
        scroller = Gtk.ScrolledWindow()
        scroller.get_style_context().add_class("vesper-startmenu-scroll")
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_propagate_natural_width(True)
        scroller.set_propagate_natural_height(True)
        # Riservo ~220px per ricerca + footer fisso (sessione), così il footer
        # non viene mai schiacciato e le app scorrono nello spazio sopra.
        avail_h = max(160, self._geo.height - PANEL_HEIGHT - 24 - 220)
        scroller.set_max_content_height(avail_h)
        scroller.add(lst)
        # Scorrevole SÌ, ma NON deve auto-scrollare da solo: di default lo
        # ScrolledWindow segue il focus (una voce prende il focus -> il menu si
        # apre già scrollato). Neutralizziamo gli adjustment di focus del
        # viewport: lo scroll lo decide solo l'utente.
        _vp = scroller.get_child()
        if _vp is not None:
            _vp.set_focus_vadjustment(Gtk.Adjustment())
            _vp.set_focus_hadjustment(Gtk.Adjustment())

        # Colonna destra = [ricerca] + [lista scrollabile]. La ricerca resta
        # fissa in alto e filtra dal vivo le applicazioni.
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        search = Gtk.SearchEntry()
        search.get_style_context().add_class("vesper-menu-search")
        search.set_placeholder_text(_t("menu.search_app"))
        col.pack_start(search, False, False, 0)
        col.pack_start(scroller, True, True, 0)
        hbox.pack_start(col, True, True, 0)

        # Registri per il filtro live: ogni riga-app e ogni intestazione di
        # categoria con le sue righe, per nascondere le sezioni vuote.
        app_rows_all = []     # [(widget, testo_ricerca)]
        cat_sections = []     # [(header, [righe], stato)]

        def sep():
            lst.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL),
                           False, False, 0)

        # Rivela una riga collassata: NB con set_no_show_all(True) lo show_all
        # iniziale salta la riga E I SUOI FIGLI (icona+etichetta), quindi un
        # set_visible(True) mostrerebbe solo il bottone vuoto (si vedeva
        # l'hover ma NON il testo). Va tolto il flag e fatto show_all().
        def _reveal_row(r):
            r.set_no_show_all(False)
            r.show_all()

        # --- Voce ASPETTO in cima: è l'azione firma di Vesper (cambia preset:
        #     accent, sfondo, icone) e deve restare la prima voce visibile.
        if preset:
            lst.pack_start(
                self._menu_item("menu", preset.get("icon", "vesper-logo-symbolic"),
                                _t("menu.preset", name=preset.get("name", "")),
                                ["vesper-control-center", "aspetto"], None, None),
                False, False, 0)
            sep()

        # Lingua dell'interfaccia: subito sotto, sempre visibile senza scorrere.
        _lang_top = self._menu_item("menu", "preferences-desktop-locale-symbolic",
                                    _t("menu.language"))
        _lang_top.connect("clicked", lambda _w: self._choose_language())
        lst.pack_start(_lang_top, False, False, 0)
        sep()

        move_to = "bottom" if self.position == "top" else "top"
        move_label = (_t("menu.move_bottom") if move_to == "bottom"
                      else _t("menu.move_top"))
        move_icon = "go-bottom-symbolic" if move_to == "bottom" else "go-top-symbolic"

        # (icona, etichetta, comando, sposta_a, conferma) - solo componenti del
        # DE: niente strumenti specifici di una distro.
        app_items = [
            ("preferences-system-symbolic", _t("app.control_center"),
             ["vesper-control-center"], None, None),
            ("utilities-terminal-symbolic", _t("app.terminal"),
             ["vesper-terminal"], None, None),
            ("system-file-manager-symbolic", _t("app.files"),
             ["vesper-files"], None, None),
            ("accessories-text-editor-symbolic", _t("app.editor"),
             ["vesper-editor"], None, None),
            (None, None, None, None, None),
            # --- strumenti di Vesper ---
            ("multimedia-player-symbolic", _t("app.player"),
             ["vesper-player"], None, None),
            ("video-x-generic-symbolic", _t("app.video"),
             ["vesper-video"], None, None),
            ("audio-input-microphone-symbolic", _t("app.recorder"),
             ["vesper-recorder"], None, None),
            ("drive-harddisk-symbolic", _t("app.disks"),
             ["vesper-disks"], None, None),
            (None, None, None, None, None),
            # Utilità di sessione, comode a portata di menu.
            ("system-lock-screen-symbolic", _t("menu.lock"),
             ["vesper-screensaver"], None, None),
            ("applets-screenshooter-symbolic", _t("menu.screenshot"),
             ["vesper-screenshot", "full", "1"], None, None),
            ("weather-clear-night-symbolic", _t("menu.nightlight"),
             ["vesper-nightlight", "toggle"], None, None),
            ("edit-paste-symbolic", _t("menu.clipboard"),
             ["vesper-clipboard", "menu"], None, None),
            (None, None, None, None, None),
            ("computer-symbolic", _t("app.sysinfo"),
             ["vesper-control-center", "sysinfo"], None, None),
            ("applications-system-symbolic", _t("app.monitor"),
             ["vesper-control-center", "monitor"], None, None),
            ("network-wired-symbolic", _t("app.network"),
             ["vesper-control-center", "rete"], None, None),
            (None, None, None, None, None),
            (move_icon, move_label, None, move_to, None),
            ("view-refresh-symbolic", _t("menu.restart_wm"),
             ["openbox", "--restart"], None, None),
        ]
        for icon, label, cmd, mv, conf in app_items:
            if icon is None:
                sep()
            else:
                lst.pack_start(
                    self._menu_item("menu", icon, label, cmd, mv, conf),
                    False, False, 0)

        # --- APPLICAZIONI installate (file .desktop), raggruppate nelle
        #     categorie standard freedesktop, ogni categoria a fisarmonica.
        #     Così qualunque programma installato compare nel menu senza
        #     configurazione, nella sezione giusta. ---
        by_cat = {}
        for app in scan_desktop_apps():
            by_cat.setdefault(app_category(app), []).append(app)

        if by_cat:
            sep()
        for cat in APP_CAT_ORDER:
            apps = by_cat.get(cat)
            if not apps:
                continue
            state = {"collapsed": True}
            section_rows = []
            # Uppercase in Python (text-transform è GTK4-only: in GTK3 fa
            # fallire il parser CSS).
            header = Gtk.Button()
            header.get_style_context().add_class("vesper-menu-cat")
            hbox_h = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            hico = Gtk.Image.new_from_icon_name(APP_CAT_ICON.get(cat, ""),
                                                Gtk.IconSize.MENU)
            hlbl = Gtk.Label()
            hlbl.set_xalign(0)
            hlbl.set_markup("▸  %s  <small>(%d)</small>"
                            % (cat_label(cat).upper(), len(apps)))
            hbox_h.pack_start(hico, False, False, 0)
            hbox_h.pack_start(hlbl, True, True, 0)
            header.add(hbox_h)
            lst.pack_start(header, False, False, 0)

            for app in apps:
                row = Gtk.Button()
                row.set_relief(Gtk.ReliefStyle.NONE)
                row.get_style_context().add_class("vesper-menu-item")
                row.get_style_context().add_class("vesper-app-item")
                rbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                rbox.pack_start(_app_image(app["icon"], ICON_PX), False, False, 0)
                rlab = Gtk.Label(label=app["name"])
                rlab.set_xalign(0)
                rbox.pack_start(rlab, True, True, 0)
                row.add(rbox)
                if app.get("comment"):
                    row.set_tooltip_text(app["comment"])
                row.set_no_show_all(True)          # parte collassata (no flash)

                def _on_app(_w, a=app):
                    self._close_popup("menu")
                    self._launch_desktop(a)
                row.connect("clicked", _on_app)
                lst.pack_start(row, False, False, 0)
                # nella ricerca si cerca per nome E per descrizione
                hay = (app["name"] + " " + (app.get("comment") or "")).lower()
                app_rows_all.append((row, hay))
                section_rows.append(row)

            def _toggle(_btn, lbl=hlbl, name=cat_label(cat), rows=section_rows,
                        st=state, reveal=_reveal_row):
                st["collapsed"] = not st["collapsed"]
                arrow = "▸" if st["collapsed"] else "▾"
                lbl.set_markup("%s  %s  <small>(%d)</small>"
                               % (arrow, name.upper(), len(rows)))
                for r in rows:
                    r.hide() if st["collapsed"] else reveal(r)
            header.connect("clicked", _toggle)
            cat_sections.append((header, section_rows, state))

        # --- Filtro live ---
        # Durante la ricerca il menu diventa una LISTA PIATTA delle sole
        # applicazioni trovate: si nasconde tutto il resto (voci di Vesper,
        # separatori, intestazioni) e si mostrano solo le righe che combaciano.
        # A campo svuotato si ripristina il menu completo, categorie richiuse.
        row_hay = {row: hay for row, hay in app_rows_all}
        app_row_set = set(row_hay.keys())

        def on_search(entry):
            q = entry.get_text().strip().lower()
            if q:
                for ch in lst.get_children():
                    if ch in app_row_set:
                        _reveal_row(ch) if q in row_hay[ch] else ch.hide()
                    else:
                        ch.hide()          # nasconde cio' che non e' un'app
            else:
                for ch in lst.get_children():
                    if ch in app_row_set:
                        ch.hide()
                    else:
                        ch.set_no_show_all(False)
                        ch.show_all()
                for header, rows, st in cat_sections:
                    header.set_visible(True)
                    for r in rows:
                        r.hide() if st["collapsed"] else _reveal_row(r)
        search.connect("search-changed", on_search)
        if not app_rows_all:
            search.set_no_show_all(True)
            search.hide()

        # Voci di sessione in un FOOTER FISSO fuori dallo scroller, così
        # restano SEMPRE visibili anche con tante applicazioni (altrimenti
        # finiscono in coda alla lista scrollabile e spariscono sotto il bordo).
        footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        footer.get_style_context().add_class("vesper-startmenu-footer")
        footer.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL),
                          False, False, 0)
        # Un'unica voce che apre il dialogo di fine sessione (vesper-logout:
        # Blocca/Esci/Riavvia/Spegni), coerente col menu del desktop.
        # NB: vesper-session AVVIA la sessione, non la chiude: non va qui.
        for icon, label, cmd, mv, conf in [
            ("system-shutdown-symbolic", _t("menu.session"),
             ["vesper-logout"], None, None),
        ]:
            footer.pack_start(self._menu_item("menu", icon, label, cmd, mv, conf),
                              False, False, 0)
        col.pack_end(footer, False, False, 0)

        self._spawn_popup("menu", hbox, align="left", keep_bottom=True)

        # Apertura SEMPRE in cima: anche con gli adjustment di focus
        # neutralizzati il primo layout può lasciare il viewport a un offset
        # != 0. Forziamo il valore a 0 DOPO che il popup ha calcolato la sua
        # altezza, così il menu nasce mostrando le voci di base in cima.
        def _scroll_top():
            adj = scroller.get_vadjustment()
            if adj is not None:
                adj.set_value(adj.get_lower())
            return False
        GLib.idle_add(_scroll_top)

        # Focus alla ricerca per poter digitare subito (la ricerca è FUORI
        # dallo scroller, quindi non sposta la lista). Dopo il reset dello
        # scroll e con priorità più bassa: layout -> scroll 0 -> focus.
        if app_rows_all:
            GLib.idle_add(search.grab_focus, priority=GLib.PRIORITY_LOW)

    def _on_show_desktop(self, _w):
        if have("wmctrl"):
            run_bg(["wmctrl", "-k", "on"])

    def _launch_desktop(self, app):
        """Lancia un'app .desktop (vedi vesper.desktopentry.launch): in
        terminale se Terminal=true, altrimenti diretta."""
        launch_app(app)

    # --- helper comando con output ---
    def _run_out(self, cmd, timeout=20):
        try:
            return subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=timeout).stdout
        except (OSError, subprocess.SubprocessError):
            return ""

    # --- applet WiFi (scan/connessione via vesper-wifi) ---
    # --- Audio (PipeWire/wpctl) e Bluetooth (BlueZ) --------------------------
    def _bg(self, cmd):
        """Esegue un comando in background (fire-and-forget), non blocca la UI."""
        threading.Thread(target=lambda: self._run_out(cmd, 8), daemon=True).start()

    def _refresh_media(self):
        def worker():
            pct = None; muted = False
            try:
                o = self._run_out(["vesper-audio", "get"]).split()
                pct = int(o[0]); muted = (o[1] == "1")
            except Exception:                       # noqa: BLE001
                pass
            try:
                bt = self._run_out(["vesper-bluetooth", "status"]).strip()
            except Exception:                       # noqa: BLE001
                bt = "noadapter"
            try:
                wifi = self._run_out(["vesper-wifi", "status"]).strip()
            except Exception:                       # noqa: BLE001
                wifi = "no-wifi"
            eth = self._read_ethernet()             # rete cablata attiva?
            try:
                batt = self._run_out(["vesper-battery", "status"]).strip()
            except Exception:                       # noqa: BLE001
                batt = "nobattery"
            self._check_low_battery()               # avviso batteria scarica
            # Microfono ON-DEMAND: l'applet compare SOLO quando un'app sta
            # catturando (mic-inuse), non sempre. Lo stato muto/livello serve
            # per l'icona quando e' visibile.
            mic_inuse = False; mic_muted = False
            try:
                if self._run_out(["vesper-audio", "mic-inuse"]).strip() == "1":
                    mic_inuse = True
                    mo = self._run_out(["vesper-audio", "mic-get"]).split()
                    mic_muted = (len(mo) > 1 and mo[1] == "1")
            except Exception:                       # noqa: BLE001
                pass
            GLib.idle_add(self._apply_media_icons, pct, muted, bt, wifi, batt, eth,
                          mic_inuse, mic_muted)
        threading.Thread(target=worker, daemon=True).start()
        return True

    def _check_low_battery(self):
        """Avviso desktop UNA-TANTUM quando la batteria scende sotto il 10% ed e'
        in scarica. Legge direttamente sysfs (nessun subprocess extra). Il flag
        si azzera quando torni in carica o risali sopra il 15%."""
        try:
            import glob
            for base in glob.glob("/sys/class/power_supply/BAT*"):
                try:
                    cap = int(open(base + "/capacity").read().strip())
                    st = open(base + "/status").read().strip().lower()
                except OSError:
                    continue
                disch = "discharg" in st
                if disch and cap <= 10:
                    if not getattr(self, "_lowbatt_warned", False):
                        self._lowbatt_warned = True
                        run_bg(["notify-send", "-a", "Vesper", "-u", "critical",
                                _t("pn.batt.low"),
                                _t("pn.batt.low_body") % cap])
                elif (not disch) or cap > 15:
                    self._lowbatt_warned = False
                return
        except Exception:                           # noqa: BLE001
            pass

    @staticmethod
    def _read_ethernet():
        """Ritorna il nome dell'interfaccia CABLATA connessa (cavo inserito e
        link su), oppure "" se nessuna. Legge /sys/class/net senza privilegi:
        esclude loopback e wireless (quelle con sottodir 'wireless'/'phy80211'),
        e richiede operstate=up con carrier=1."""
        import glob
        for path in sorted(glob.glob("/sys/class/net/*")):
            name = os.path.basename(path)
            if name == "lo":
                continue
            # escludi wireless (hanno 'wireless' o 'phy80211')
            if os.path.exists(path + "/wireless") or \
               os.path.exists(path + "/phy80211"):
                continue
            try:
                oper = open(path + "/operstate").read().strip()
                carrier = open(path + "/carrier").read().strip()
            except OSError:
                continue
            if oper == "up" and carrier == "1":
                return name
        return ""

    def _batt_icon(self, pct, state, ac=False):
        """Nome-icona simbolica batteria dal livello e dallo stato di carica.

        `ac` = rete collegata (rilevata direttamente o dedotta): quando e' vera
        mostriamo comunque l'icona "in carica/collegato" anche se lo stato non e'
        letteralmente `charging` (tipico nelle VM che riportano notcharging/
        unknown pur essendo a spina)."""
        charging = state == "charging" or (ac and state != "discharging")
        # nomi presenti in Adwaita: full/good/low/caution/empty (+ -charging)
        if pct >= 80:
            lvl = "full"
        elif pct >= 45:
            lvl = "good"
        elif pct >= 20:
            lvl = "low"
        else:
            lvl = "caution"
        if state == "full":
            return "battery-full-charged-symbolic"
        if charging:
            return "battery-%s-charging-symbolic" % lvl
        return "battery-%s-symbolic" % lvl

    def _apply_media_icons(self, pct, muted, bt, wifi="no-wifi", batt="nobattery",
                           eth="", mic_present=False, mic_muted=False):
        # Microfono: applet visibile SOLO se un mic e' presente (stile MATE).
        if mic_present:
            self.mic_btn.set_image(_tray_img(
                "microphone-sensitivity-muted-symbolic" if mic_muted
                else "audio-input-microphone-symbolic"))
            self.mic_btn.set_tooltip_text(
                _t("pn.mic.muted_tip") if mic_muted
                else _t("pn.mic.tip"))
            self.mic_btn.show()
        else:
            self.mic_btn.hide()
        if pct is None or muted or pct <= 0:
            ai = "audio-volume-muted-symbolic"
        elif pct < 34:
            ai = "audio-volume-low-symbolic"
        elif pct < 67:
            ai = "audio-volume-medium-symbolic"
        else:
            ai = "audio-volume-high-symbolic"
        self.vol_btn.set_image(_tray_img(ai))
        # Bluetooth: conn=dispositivo collegato, on=acceso, altrimenti spento.
        if bt == "conn":
            bi = "bluetooth-active-symbolic"
        elif bt == "on":
            bi = "bluetooth-symbolic"
        else:
            bi = "bluetooth-disabled-symbolic"
        self.bt_btn.set_image(_tray_img(bi))
        self.bt_btn.set_tooltip_text(
            {"conn": _t("tray.bt.conn"), "on": _t("tray.bt.on"),
             "off": _t("tray.bt.off"),
             "noadapter": _t("tray.bt.noadapter")}.get(bt, _t("tray.bt.default")))
        # Stato collegamento: la rete CABLATA ha priorita' visiva (se il cavo e'
        # inserito e attivo mostriamo l'icona ethernet, non piu' il WiFi
        # sganciato). Altrimenti lo stato WiFi (connesso/disconnesso/assente).
        # Il click sul pulsante apre comunque la gestione WiFi.
        if eth:
            wi = "network-wired-symbolic"
            self.wifi_btn.set_tooltip_text(_t("pn.wifi.eth") % eth)
        elif wifi.startswith("connected"):
            wi = "network-wireless-signal-excellent-symbolic"
            ssid = wifi[len("connected"):].strip()
            self.wifi_btn.set_tooltip_text(_t("pn.wifi.conn_ssid") % ssid if ssid
                                           else _t("pn.wifi.conn"))
        elif wifi == "disconnected":
            wi = "network-wireless-offline-symbolic"
            self.wifi_btn.set_tooltip_text(_t("pn.wifi.disc"))
        else:
            wi = "network-wireless-disabled-symbolic"
            self.wifi_btn.set_tooltip_text(_t("pn.wifi.na"))
        self.wifi_btn.set_image(_tray_img(wi))
        # Batteria / alimentazione
        if batt == "nobattery":
            self.batt_btn.hide()
        elif batt == "ac-only":
            self.batt_btn.set_image(_tray_img("ac-adapter-symbolic"))
            self.batt_btn.set_tooltip_text(_t("pn.batt.ac"))
            self.batt_btn.show()
        else:
            try:
                p = batt.split("\t")
                bpct = int(p[0]); bstate = p[1] if len(p) > 1 else "unknown"
                bac = p[2] if len(p) > 2 else "0"
            except (ValueError, IndexError):
                bpct, bstate, bac = 0, "unknown", "0"
            on_ac = bac == "1"
            self.batt_btn.set_image(_tray_img(self._batt_icon(bpct, bstate, on_ac)))
            lab = {"charging": _t("pn.batt.t_charging"),
                   "discharging": _t("pn.batt.t_discharging"),
                   "full": _t("pn.batt.t_full"),
                   "notcharging": _t("pn.batt.t_notcharging")}.get(bstate, "")
            tip = _t("pn.batt.pct") % bpct
            if lab:
                tip += " (%s)" % lab
            # Mostra sempre lo stato alimentazione: a rete o a batteria.
            if on_ac:
                tip += _t("pn.batt.on_ac")
            elif bstate == "discharging":
                tip += _t("pn.batt.on_batt")
            self.batt_btn.set_tooltip_text(tip)
            self.batt_btn.show()
        return False

    def _vol_scroll(self, _w, ev):
        up = down = False
        if ev.direction == Gdk.ScrollDirection.UP:
            up = True
        elif ev.direction == Gdk.ScrollDirection.DOWN:
            down = True
        elif ev.direction == Gdk.ScrollDirection.SMOOTH:
            _ok, _dx, dy = ev.get_scroll_deltas()
            up = dy < 0; down = dy > 0
        if up:
            self._bg(["vesper-audio", "up"])
        elif down:
            self._bg(["vesper-audio", "down"])
        GLib.timeout_add(200, self._refresh_media_once)
        return True

    def _mic_scroll(self, _w, ev):
        up = down = False
        if ev.direction == Gdk.ScrollDirection.UP:
            up = True
        elif ev.direction == Gdk.ScrollDirection.DOWN:
            down = True
        elif ev.direction == Gdk.ScrollDirection.SMOOTH:
            _ok, _dx, dy = ev.get_scroll_deltas()
            up = dy < 0; down = dy > 0
        if up:
            self._bg(["vesper-audio", "mic-up"])
        elif down:
            self._bg(["vesper-audio", "mic-down"])
        GLib.timeout_add(200, self._refresh_media_once)
        return True

    def _toggle_mic(self, _btn):
        """Popup dell'applet Microfono (source PipeWire): livello, muta e scelta
        dell'ingresso. Speculare al popup Audio, ma solo per l'input."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.get_style_context().add_class("vesper-calbox")
        box.set_size_request(300, -1)
        title = Gtk.Label(); title.set_markup("<b>Microfono</b>"); title.set_xalign(0)
        box.pack_start(title, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        mute_b = Gtk.Button(); mute_b.set_relief(Gtk.ReliefStyle.NONE)
        mute_b.get_style_context().add_class("vesper-icon")
        mute_b.set_image(Gtk.Image.new_from_icon_name(
            "audio-input-microphone-symbolic", Gtk.IconSize.MENU))
        row.pack_start(mute_b, False, False, 0)
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        scale.set_draw_value(True); scale.set_value_pos(Gtk.PositionType.RIGHT)
        scale.set_hexpand(True)
        row.pack_start(scale, True, True, 0)
        box.pack_start(row, False, False, 0)

        status = Gtk.Label(label="..."); status.set_xalign(0)
        status.get_style_context().add_class("vesper-clock-date")
        box.pack_start(status, False, False, 0)
        ins = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.pack_start(ins, False, False, 0)
        self._spawn_popup("mic", box, align="right")

        def on_scale(s):
            self._bg(["vesper-audio", "mic-set", str(int(s.get_value()))])
            GLib.timeout_add(150, self._refresh_media_once)

        def fill(pct, muted, sources):
            if "mic" not in self._popups:
                return False
            scale.set_value(pct if pct is not None else 0)
            scale.connect("value-changed", on_scale)
            mute_b.connect("clicked", lambda _w: (
                self._bg(["vesper-audio", "mic-mute"]),
                GLib.timeout_add(150, self._refresh_media_once)))
            status.set_text(_t("pn.mic.muted") if muted
                            else ("Ingresso:" if sources else "Nessun ingresso."))
            for sid, name, is_def in sources:
                b = Gtk.Button(); b.set_relief(Gtk.ReliefStyle.NONE)
                b.get_style_context().add_class("vesper-menu-item")
                lab = Gtk.Label(label=("● " if is_def else "○ ") + name)
                lab.set_xalign(0); b.add(lab)
                b.connect("clicked", lambda _w, i=sid: (
                    self._bg(["vesper-audio", "mic-default", i]),
                    self._close_popup("mic")))
                ins.pack_start(b, False, False, 0)
            ins.show_all()
            return False

        def worker():
            pct = None; muted = False
            try:
                o = self._run_out(["vesper-audio", "mic-get"]).split()
                pct = int(o[0]); muted = (o[1] == "1")
            except Exception:                       # noqa: BLE001
                pass
            sources = []
            for line in self._run_out(["vesper-audio", "sources"]).splitlines():
                p = line.split("\t")
                if len(p) >= 2 and p[0].strip():
                    sources.append((p[0], p[1], len(p) > 2 and p[2] == "*"))
            GLib.idle_add(fill, pct, muted, sources)
        threading.Thread(target=worker, daemon=True).start()

    def _toggle_volume(self, _btn):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.get_style_context().add_class("vesper-calbox")
        box.set_size_request(300, -1)
        title = Gtk.Label(); title.set_markup("<b>Audio</b>"); title.set_xalign(0)
        box.pack_start(title, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        mute_b = Gtk.Button(); mute_b.set_relief(Gtk.ReliefStyle.NONE)
        mute_b.get_style_context().add_class("vesper-icon")
        mute_b.set_image(Gtk.Image.new_from_icon_name(
            "audio-volume-high-symbolic", Gtk.IconSize.MENU))
        row.pack_start(mute_b, False, False, 0)
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        scale.set_draw_value(True); scale.set_value_pos(Gtk.PositionType.RIGHT)
        scale.set_hexpand(True)
        row.pack_start(scale, True, True, 0)
        box.pack_start(row, False, False, 0)

        status = Gtk.Label(label="..."); status.set_xalign(0)
        status.get_style_context().add_class("vesper-clock-date")
        box.pack_start(status, False, False, 0)
        # Sblocco audio a un clic (utile su portatile reale: se non si sente,
        # forza unmute+volume su ALSA hardware e sink PipeWire, con ritentativi).
        unmute_b = Gtk.Button(label="Sblocca audio (HW)")
        unmute_b.get_style_context().add_class("vesper-menu-item")
        unmute_b.set_tooltip_text("Se non senti nulla: sblocca e alza l'audio su "
                                  "tutti i livelli (ALSA + PipeWire).")
        unmute_b.connect("clicked", lambda _w: (
            self._bg(["vesper-audio-unmute", "2"]),
            GLib.timeout_add(400, self._refresh_media_once)))
        box.pack_start(unmute_b, False, False, 0)
        outs = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.pack_start(outs, False, False, 0)
        self._spawn_popup("audio", box, align="right")

        def on_scale(s):
            self._bg(["vesper-audio", "set", str(int(s.get_value()))])
            GLib.timeout_add(150, self._refresh_media_once)

        def fill(pct, muted, sinks):
            if "audio" not in self._popups:
                return False
            scale.set_value(pct if pct is not None else 0)
            scale.connect("value-changed", on_scale)
            mute_b.connect("clicked", lambda _w: (
                self._bg(["vesper-audio", "mute"]),
                GLib.timeout_add(150, self._refresh_media_once)))
            if pct is None:
                status.set_text("PipeWire non attivo o nessuna uscita audio.")
            else:
                status.set_text("Uscita audio:" if sinks else "")
            for sid, name, is_def in sinks:
                b = Gtk.Button(); b.set_relief(Gtk.ReliefStyle.NONE)
                b.get_style_context().add_class("vesper-menu-item")
                lab = Gtk.Label(label=("● " if is_def else "○ ") + name)
                lab.set_xalign(0); b.add(lab)
                b.connect("clicked", lambda _w, i=sid: (
                    self._bg(["vesper-audio", "default", i]),
                    self._close_popup("audio")))
                outs.pack_start(b, False, False, 0)
            outs.show_all()
            return False

        def worker():
            pct = None; muted = False
            try:
                o = self._run_out(["vesper-audio", "get"]).split()
                pct = int(o[0]); muted = (o[1] == "1")
            except Exception:                       # noqa: BLE001
                pass
            sinks = []
            for line in self._run_out(["vesper-audio", "sinks"]).splitlines():
                p = line.split("\t")
                if len(p) >= 2 and p[0].strip():
                    sinks.append((p[0], p[1], len(p) > 2 and p[2] == "*"))
            GLib.idle_add(fill, pct, muted, sinks)
        threading.Thread(target=worker, daemon=True).start()

    def _toggle_battery(self, _btn):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.get_style_context().add_class("vesper-calbox")
        box.set_size_request(320, -1)
        title = Gtk.Label(); title.set_markup("<b>%s</b>" % _t("pn.batt.power_title"))
        title.set_xalign(0)
        box.pack_start(title, False, False, 0)

        big = Gtk.Label(); big.set_xalign(0)
        big.get_style_context().add_class("vesper-clock")
        box.pack_start(big, False, False, 0)
        bar = Gtk.ProgressBar(); bar.set_show_text(False)
        box.pack_start(bar, False, False, 0)
        state_lbl = Gtk.Label(); state_lbl.set_xalign(0)
        state_lbl.get_style_context().add_class("vesper-clock-date")
        box.pack_start(state_lbl, False, False, 0)

        grid = Gtk.Grid(); grid.set_row_spacing(4); grid.set_column_spacing(14)
        box.pack_start(grid, False, False, 4)
        self._spawn_popup("battery", box, align="right")

        def add_row(r, k, v):
            kl = Gtk.Label(label=k); kl.set_xalign(0)
            kl.get_style_context().add_class("vesper-clock-date")
            vl = Gtk.Label(label=v); vl.set_xalign(1); vl.set_hexpand(True)
            grid.attach(kl, 0, r, 1, 1)
            grid.attach(vl, 1, r, 1, 1)

        def fill(info):
            if "battery" not in self._popups:
                return False
            for c in grid.get_children():
                grid.remove(c)
            if info.get("battery") != "1":
                big.set_text(_t("pn.batt.mains"))
                bar.set_fraction(1.0)
                state_lbl.set_text(_t("pn.batt.ac_nobatt"))
                grid.show_all()
                return False
            pct = int(info.get("percent", "0") or 0)
            big.set_text("%d%%" % pct)
            bar.set_fraction(max(0.0, min(1.0, pct / 100.0)))
            st = info.get("state", "unknown")
            stmap = {"charging": _t("pn.batt.charging"), "discharging": _t("pn.batt.discharging"),
                     "full": _t("pn.batt.full"), "notcharging": _t("pn.batt.notcharging"),
                     "unknown": _t("pn.batt.unknown")}
            ac = info.get("ac", "0") == "1"
            state_lbl.set_text(stmap.get(st, st) +
                               (_t("pn.batt.on_ac") if ac else _t("pn.batt.on_batt")))
            r = 0
            eta = info.get("eta_min")
            if eta:
                try:
                    m = int(eta); hh, mm = m // 60, m % 60
                    lab = ("%dh %02dmin" % (hh, mm)) if hh else ("%d min" % mm)
                    add_row(r, _t("pn.batt.eta_discharge") if st == "discharging"
                            else _t("pn.batt.eta_charge"), lab); r += 1
                except ValueError:
                    pass
            if info.get("power_w"):
                try:
                    add_row(r, _t("pn.batt.power_w"), "%.1f W" % (int(info["power_w"]) / 10.0))
                    r += 1
                except ValueError:
                    pass
            if info.get("voltage_mv"):
                try:
                    add_row(r, _t("pn.batt.voltage"), "%.2f V" % (int(info["voltage_mv"]) / 1000.0))
                    r += 1
                except ValueError:
                    pass
            if info.get("health"):
                add_row(r, _t("pn.batt.health"), info["health"] + "%"); r += 1
            if info.get("cycles"):
                add_row(r, _t("pn.batt.cycles"), info["cycles"]); r += 1
            if info.get("technology"):
                add_row(r, _t("pn.batt.technology"), info["technology"]); r += 1
            if info.get("model"):
                add_row(r, _t("pn.batt.model"), info["model"]); r += 1
            if info.get("manufacturer"):
                add_row(r, _t("pn.batt.manufacturer"), info["manufacturer"]); r += 1
            grid.show_all()
            return False

        def worker():
            info = {}
            for line in self._run_out(["vesper-battery", "info"]).splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    info[k.strip()] = v.strip()
            GLib.idle_add(fill, info)
        threading.Thread(target=worker, daemon=True).start()

    def _toggle_bluetooth(self, _btn):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.get_style_context().add_class("vesper-calbox")
        box.set_size_request(320, -1)
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title = Gtk.Label(); title.set_markup("<b>Bluetooth</b>"); title.set_xalign(0)
        head.pack_start(title, True, True, 0)
        sw = Gtk.Switch(); sw.set_valign(Gtk.Align.CENTER)
        head.pack_end(sw, False, False, 0)
        box.pack_start(head, False, False, 0)

        status = Gtk.Label(label="..."); status.set_xalign(0)
        status.set_line_wrap(True)
        status.get_style_context().add_class("vesper-clock-date")
        box.pack_start(status, False, False, 0)

        scan_b = Gtk.Button(label="Scansiona dispositivi")
        scan_b.get_style_context().add_class("vesper-menu-item")
        box.pack_start(scan_b, False, False, 0)
        adv_b = Gtk.Button(label="Gestione avanzata…")
        adv_b.get_style_context().add_class("vesper-menu-item")
        adv_b.connect("clicked", lambda _w: (
            self._close_popup("bt"),
            run_bg(["vesper-control-center", "bluetooth"])))
        box.pack_start(adv_b, False, False, 0)
        devlist = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.pack_start(devlist, False, False, 0)
        self._spawn_popup("bt", box, align="right")

        def render_devs(devs):
            if "bt" not in self._popups:
                return False
            for c in devlist.get_children():
                devlist.remove(c)
            for mac, name, st in devs:
                b = Gtk.Button(); b.set_relief(Gtk.ReliefStyle.NONE)
                b.get_style_context().add_class("vesper-menu-item")
                hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                ico = "bluetooth-active-symbolic" if st == "conn" else "bluetooth-symbolic"
                hb.pack_start(Gtk.Image.new_from_icon_name(ico, Gtk.IconSize.MENU),
                              False, False, 0)
                lab = Gtk.Label(label=name or mac); lab.set_xalign(0)
                hb.pack_start(lab, True, True, 0)
                if st:
                    tag = Gtk.Label(label="connesso" if st == "conn" else "abbinato")
                    tag.get_style_context().add_class("vesper-clock-date")
                    hb.pack_start(tag, False, False, 0)
                b.add(hb)
                b.connect("clicked", lambda _w, m=mac, s=st: self._bt_toggle_dev(m, s))
                devlist.pack_start(b, False, False, 0)
            devlist.show_all()
            return False

        # riferimenti per aggiornare lo stesso popup da _bt_toggle_dev
        self._bt_ui = {"status": status, "render": render_devs}

        def do_scan(_w=None):
            status.set_text("Scansione in corso (qualche secondo)...")
            def worker():
                devs = []
                for line in self._run_out(["vesper-bluetooth", "scan", "12"], 45).splitlines():
                    p = line.split("\t")
                    if len(p) >= 2:
                        devs.append((p[0], p[1], p[2] if len(p) > 2 else ""))
                GLib.idle_add(lambda: (status.set_text(
                    "Clic su un dispositivo per connettere/disconnettere:"
                    if devs else "Nessun dispositivo trovato."), render_devs(devs)))
            threading.Thread(target=worker, daemon=True).start()
        scan_b.connect("clicked", do_scan)

        def on_switch(s, state):
            self._bg(["vesper-bluetooth", "on" if state else "off"])
            # L'adattatore impiega un attimo ad accendersi/spegnersi davvero:
            # aggiorniamo l'icona in barra piu' volte finche' lo stato si
            # stabilizza (prima con un solo refresh a 400ms l'indicatore non
            # cambiava perche' il power on non era ancora completo).
            for d in (500, 1500, 3000):
                GLib.timeout_add(d, self._refresh_media_once)
            return False
        def load():
            st = self._run_out(["vesper-bluetooth", "status"]).strip()
            devs = []
            if st == "on":
                for line in self._run_out(["vesper-bluetooth", "devices"]).splitlines():
                    p = line.split("\t")
                    if len(p) >= 2:
                        devs.append((p[0], p[1], p[2] if len(p) > 2 else ""))
            def apply():
                if "bt" not in self._popups:
                    return False
                if st == "noadapter":
                    status.set_text("Nessun adattatore Bluetooth rilevato. In VM "
                                    "non e' disponibile: usa un dongle USB.")
                    sw.set_sensitive(False); scan_b.set_sensitive(False)
                    return False
                sw.set_active(st == "on")
                sw.connect("state-set", on_switch)
                status.set_text("Bluetooth acceso." if st == "on"
                                else "Bluetooth spento.")
                render_devs(devs)
                return False
            GLib.idle_add(apply)
        threading.Thread(target=load, daemon=True).start()

    def _bt_toggle_dev(self, mac, st):
        act = "disconnect" if st == "conn" else "connect"
        ui = getattr(self, "_bt_ui", None)
        if ui and "bt" in self._popups:
            ui["status"].set_text("Disconnessione in corso..." if act == "disconnect"
                                  else "Connessione in corso...")

        def worker():
            # 70s: pair/connect ora attendono fino a 60s la conferma sul
            # dispositivo (vedi vesper-bluetooth). Con 25s il pannello uccideva il
            # processo a meta pairing.
            self._run_out(["vesper-bluetooth", act, mac], 70)
            # aggiorna l'indicatore in barra subito e finche' lo stato si assesta
            GLib.idle_add(self._refresh_media_once)
            for d in (800, 2000, 3500):
                GLib.timeout_add(d, self._refresh_media_once)
            # ricarica l'elenco (stato conn/paired aggiornato) nel popup aperto
            devs = []
            for line in self._run_out(["vesper-bluetooth", "devices"]).splitlines():
                p = line.split("\t")
                if len(p) >= 2:
                    devs.append((p[0], p[1], p[2] if len(p) > 2 else ""))
            def apply():
                u = getattr(self, "_bt_ui", None)
                if u and "bt" in self._popups:
                    conn = any(s == "conn" for _m, _n, s in devs)
                    u["status"].set_text("Dispositivo connesso." if conn
                                         else "Nessun dispositivo connesso.")
                    u["render"](devs)
                return False
            GLib.idle_add(apply)
        threading.Thread(target=worker, daemon=True).start()

    def _toggle_wifi(self, _btn):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.get_style_context().add_class("vesper-calbox")
        box.set_size_request(320, -1)
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title = Gtk.Label(); title.set_markup("<b>Reti WiFi</b>"); title.set_xalign(0)
        head.pack_start(title, True, True, 0)
        rescan = Gtk.Button(); rescan.set_relief(Gtk.ReliefStyle.NONE)
        rescan.set_tooltip_text(_t("pn.wifi.rescan"))
        rescan.set_image(Gtk.Image.new_from_icon_name(
            "view-refresh-symbolic", Gtk.IconSize.MENU))
        rescan.connect("clicked", lambda _w: self._wifi_scan())
        head.pack_end(rescan, False, False, 0)
        box.pack_start(head, False, False, 0)
        status = Gtk.Label(label="Scansione in corso..."); status.set_xalign(0)
        status.set_line_wrap(True)
        status.get_style_context().add_class("vesper-clock-date")
        box.pack_start(status, False, False, 0)
        listbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.pack_start(listbox, False, False, 0)
        self._spawn_popup("wifi", box, align="right")
        # riferimenti per aggiornare lo stesso popup da scan/connect
        self._wifi_ui = (status, listbox)
        self._wifi_scan()

    def _wifi_scan(self):
        ui = getattr(self, "_wifi_ui", None)
        if not ui or "wifi" not in self._popups:
            return
        status, _listbox = ui
        status.set_text("Scansione in corso...")

        def worker():
            iface = self._run_out(["vesper-wifi", "iface"]).strip()
            cur = self._run_out(["vesper-wifi", "status"]).strip()
            connected = (cur[len("connected"):].strip()
                         if cur.startswith("connected") else "")
            out = self._run_out(["vesper-wifi", "scan"]) if iface else ""
            nets = []
            for line in out.splitlines():
                p = line.split("\t")
                if len(p) >= 3 and p[0].strip():
                    nets.append((p[0], p[1], p[2]))
            GLib.idle_add(self._wifi_populate, nets, iface, connected)
        threading.Thread(target=worker, daemon=True).start()

    def _wifi_populate(self, nets, iface, connected):
        ui = getattr(self, "_wifi_ui", None)
        if not ui or "wifi" not in self._popups:
            return False
        status, listbox = ui
        for c in listbox.get_children():
            listbox.remove(c)
        if not iface:
            status.set_text("Nessuna scheda WiFi rilevata. In una macchina "
                            "virtuale il WiFi non e' disponibile: usa Ethernet "
                            "o passa un adattatore WiFi USB.")
            return False
        if not nets:
            status.set_text("Nessuna rete in portata (WiFi acceso, nessuna rete "
                            "trovata).")
            return False
        status.set_text("Connesso a «%s». Clic per disconnettere o scegliere "
                        "un'altra rete:" % connected if connected
                        else "Clic su una rete per connetterti:")
        # rete connessa in cima
        nets = sorted(nets, key=lambda n: (n[0] != connected))
        for ssid, sig, flags in nets:
            locked = any(x in flags for x in ("WPA", "PSK", "WEP", "SAE"))
            is_conn = (ssid == connected and connected != "")
            b = Gtk.Button(); b.set_relief(Gtk.ReliefStyle.NONE)
            b.get_style_context().add_class("vesper-menu-item")
            hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            if is_conn:
                ico = "network-wireless-connected-symbolic"
            elif locked:
                ico = "network-wireless-encrypted-symbolic"
            else:
                ico = "network-wireless-symbolic"
            hb.pack_start(Gtk.Image.new_from_icon_name(
                ico, Gtk.IconSize.MENU), False, False, 0)
            lab = Gtk.Label(); lab.set_xalign(0)
            if is_conn:
                lab.set_markup("<b>%s</b>" % GLib.markup_escape_text(ssid))
            else:
                lab.set_text(ssid)
            hb.pack_start(lab, True, True, 0)
            if is_conn:
                tag = Gtk.Label(label="✓ connesso")
                tag.get_style_context().add_class("vesper-ok")
                hb.pack_start(tag, False, False, 0)
            else:
                sg = Gtk.Label(label="%s dBm" % sig)
                sg.get_style_context().add_class("vesper-clock-date")
                hb.pack_start(sg, False, False, 0)
            b.add(hb)
            if is_conn:
                b.connect("clicked", lambda _w, s=ssid: self._wifi_disconnect(s))
            else:
                b.connect("clicked",
                          lambda _w, s=ssid, lk=locked: self._wifi_connect(s, lk))
            listbox.pack_start(b, False, False, 0)
        listbox.show_all()
        return False

    def _wifi_disconnect(self, ssid):
        ui = getattr(self, "_wifi_ui", None)
        if ui and "wifi" in self._popups:
            ui[0].set_text("Disconnessione da «%s»..." % ssid)
        def worker():
            self._run_out(["vesper-wifi", "disconnect"], 10)
            GLib.idle_add(self._refresh_media_once)
            GLib.idle_add(self._wifi_scan)
        threading.Thread(target=worker, daemon=True).start()

    def _wifi_connect(self, ssid, locked):
        psk = ""
        if locked:
            psk = self._ask_password("Password per la rete «%s»" % ssid)
            if psk is None:
                return
        ui = getattr(self, "_wifi_ui", None)
        if ui and "wifi" in self._popups:
            ui[0].set_text("Connessione a «%s»..." % ssid)

        def worker():
            # La passphrase va su STDIN, non tra gli argomenti (niente password
            # in chiaro in `ps`). Rete aperta = stdin vuoto.
            out = ""
            try:
                r = subprocess.run(["vesper-wifi", "connect", ssid], input=psk or "",
                                   capture_output=True, text=True, timeout=45)
                out = (r.stdout or "").strip()
            except (OSError, subprocess.SubprocessError):
                pass
            # verifica reale: attende che wpa_state=COMPLETED sull'SSID scelto
            ok = False
            for _ in range(15):
                time.sleep(1)
                st = self._run_out(["vesper-wifi", "status"]).strip()
                if st.startswith("connected") and st[len("connected"):].strip() == ssid:
                    ok = True
                    break
            GLib.idle_add(self._wifi_after_connect, ssid, ok, out)
        threading.Thread(target=worker, daemon=True).start()

    def _wifi_after_connect(self, ssid, ok, out=""):
        self._refresh_media_once()   # aggiorna subito l'icona WiFi in barra
        ui = getattr(self, "_wifi_ui", None)
        if ui and "wifi" in self._popups:
            if ok:
                # Associato (COMPLETED): distingue il caso "senza IP" (dhcp)
                # da una connessione pienamente riuscita.
                if out == "err-dhcp":
                    ui[0].set_text("Associato a «%s» ma senza IP (DHCP)." % ssid)
                else:
                    ui[0].set_text("Connesso a «%s»." % ssid)
                self._wifi_scan()    # ridisegna con il badge "✓ connesso"
            else:
                ui[0].set_text({
                    "err-auth":  "Password errata per «%s»." % ssid,
                    "err-assoc": ("Associazione a «%s» non riuscita (rete lontana "
                                  "o crittografia non supportata)." % ssid),
                    "err-dhcp":  "Associato a «%s» ma senza IP (DHCP)." % ssid,
                }.get(out, "Connessione a «%s» non riuscita (password errata "
                           "o rete non raggiungibile)." % ssid))
        return False

    def _ask_password(self, prompt):
        d = Gtk.Dialog(title="Connessione WiFi", modal=True)
        # Ancorato al pannello: il dialogo compare sul MONITOR del pannello da
        # cui si e' cliccato (quello attivo), mai su un eventuale schermo spento.
        try:
            d.set_transient_for(self)
        except Exception:
            pass
        self._center_dialog(d)
        d.set_keep_above(True)
        d.add_button("Annulla", Gtk.ResponseType.CANCEL)
        d.add_button("Connetti", Gtk.ResponseType.OK)
        d.set_default_response(Gtk.ResponseType.OK)
        area = d.get_content_area()
        area.set_spacing(8); area.set_border_width(12)
        area.add(Gtk.Label(label=prompt))
        e = Gtk.Entry(); e.set_visibility(False); e.set_activates_default(True)
        # Occhio per mostrare/nascondere quello che si digita.
        e.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY,
                                  "view-reveal-symbolic")
        e.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY,
                                "Mostra/nascondi la password")

        def _toggle_eye(entry, _pos, _ev):
            vis = not entry.get_visibility()
            entry.set_visibility(vis)
            entry.set_icon_from_icon_name(
                Gtk.EntryIconPosition.SECONDARY,
                "view-conceal-symbolic" if vis else "view-reveal-symbolic")
        e.connect("icon-press", _toggle_eye)
        area.add(e)
        d.show_all()
        resp = d.run()
        psk = e.get_text() if resp == Gtk.ResponseType.OK else None
        d.destroy()
        return psk

    # --- applet Schermi (xrandr via vesper-screens) ---
    def _toggle_screens(self, _btn):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.get_style_context().add_class("vesper-calbox")
        box.set_size_request(300, -1)
        title = Gtk.Label(); title.set_markup("<b>Schermi</b>"); title.set_xalign(0)
        box.pack_start(title, False, False, 0)

        outs = []
        for line in self._run_out(["vesper-screens", "outputs"]).splitlines():
            p = line.split("\t")
            if len(p) >= 4 and p[1] == "connected":
                outs.append((p[0], p[2], p[3]))       # nome, primary?, WxH

        if not outs:
            lbl = Gtk.Label(label="Nessuno schermo rilevato."); lbl.set_xalign(0)
            box.pack_start(lbl, False, False, 0)
        else:
            if len(outs) >= 2:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
                for lbl, act in (("Estendi", ["extend"]), ("Duplica", ["mirror"])):
                    b = Gtk.Button(label=lbl)
                    b.get_style_context().add_class("vesper-menu-item")
                    b.connect("clicked", lambda _w, a=act: self._screens_apply(a))
                    row.pack_start(b, True, True, 0)
                box.pack_start(row, False, False, 0)
            for name, prim, res in outs:
                oc = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
                oc.get_style_context().add_class("vesper-dt-row")
                hdr = Gtk.Label(); hdr.set_xalign(0)
                hdr.set_markup("<b>%s</b>%s  <small>%s</small>" % (
                    name, "  (principale)" if prim == "primary" else "", res))
                oc.pack_start(hdr, False, False, 0)
                # Risoluzioni: Gtk.ComboBoxText nativa (ripristinata) - scorre in
                # modo affidabile, anche col touchpad. Scegli la risoluzione e
                # premi Applica.
                r = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
                combo = Gtk.ComboBoxText()
                modes = self._run_out(["vesper-screens", "modes", name]).split()
                for m in modes:
                    combo.append_text(m)
                if modes:
                    combo.set_active(0)
                r.pack_start(combo, True, True, 0)
                ba = Gtk.Button(label="Applica")
                ba.get_style_context().add_class("vesper-menu-item")
                ba.connect("clicked", lambda _w, n=name, c=combo:
                           self._screens_apply(["mode", n, c.get_active_text() or ""]))
                r.pack_start(ba, False, False, 0)
                oc.pack_start(r, False, False, 0)
                if len(outs) >= 2:
                    bo = Gtk.Button(label="Usa solo questo")
                    bo.get_style_context().add_class("vesper-menu-item")
                    bo.connect("clicked",
                               lambda _w, n=name: self._screens_apply(["only", n]))
                    oc.pack_start(bo, False, False, 0)
                box.pack_start(oc, False, False, 0)

        self._spawn_popup("screens", box, align="right")

    def _screens_apply(self, args):
        self._close_popup("screens")
        if len(args) >= 3 and args[0] == "mode" and not args[2]:
            return                                    # nessuna risoluzione scelta
        run_bg(["vesper-screens"] + list(args))
        # Dopo un cambio schermi (es. "solo esterno") xrandr puo' NON far
        # scattare monitors-changed: le barre vanno ripiazzate sul monitor
        # attivo appena lo schermo si assesta, senno' restano su quello spento.
        GLib.timeout_add(700, _reposition_panels)

    def _on_today(self, _w):
        t = time.localtime()
        self.calendar.select_month(t.tm_mon - 1, t.tm_year)
        self.calendar.select_day(t.tm_mday)
        self.spin_h.set_value(t.tm_hour)
        self.spin_m.set_value(t.tm_min)

    def _current_tz(self):
        """Fuso corrente via vesper-datetime (legge /etc/timezone o il symlink)."""
        try:
            out = subprocess.run(["vesper-datetime", "get-tz"], capture_output=True,
                                 text=True, timeout=4).stdout.strip()
            return out or "UTC"
        except (OSError, subprocess.SubprocessError):
            return "UTC"

    def _apply_datetime(self, _btn):
        """Imposta data (dal calendario) + ora (dagli spin) come clock di sistema."""
        y, m0, d = self.calendar.get_date()          # mese 0-based
        s = "%04d-%02d-%02d %02d:%02d:00" % (
            y, m0 + 1, d, int(self.spin_h.get_value()), int(self.spin_m.get_value()))
        try:
            subprocess.run(["vesper-datetime", "set-datetime", s], timeout=8)
        except (OSError, subprocess.SubprocessError):
            pass
        self._tick_clock()
        self._close_popup("calendar")

    def _apply_tz(self, _btn):
        """Cambia il fuso orario di sistema e aggiorna subito l'orologio."""
        tz = self.tz_combo.get_active_text()
        if not tz:
            return
        try:
            subprocess.run(["vesper-datetime", "set-tz", tz], timeout=8)
        except (OSError, subprocess.SubprocessError):
            pass
        try:                                          # ricarica il fuso nel processo
            os.environ.pop("TZ", None)
            time.tzset()
        except Exception:                             # noqa: BLE001
            pass
        self._tick_clock()
        self._close_popup("calendar")

    # --- calendario + regolazione ora/data/fuso (toplevel toggle) ---
    def _toggle_calendar(self, _btn):
        cal_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        cal_box.get_style_context().add_class("vesper-calbox")
        self.calendar = Gtk.Calendar()
        self.calendar.get_style_context().add_class("vesper-calendar")
        cal_box.pack_start(self.calendar, True, True, 0)

        btn_today = Gtk.Button(label="Oggi")
        btn_today.get_style_context().add_class("vesper-menu-item")
        btn_today.connect("clicked", self._on_today)
        cal_box.pack_start(btn_today, False, False, 0)

        cal_box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL),
                           False, False, 2)

        # Riga ORA: HH : MM + Imposta (usa la data selezionata nel calendario).
        t = time.localtime()
        time_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        time_row.get_style_context().add_class("vesper-dt-row")
        time_row.pack_start(Gtk.Label(label="Ora"), False, False, 0)
        self.spin_h = Gtk.SpinButton.new_with_range(0, 23, 1)
        self.spin_h.set_value(t.tm_hour)
        self.spin_m = Gtk.SpinButton.new_with_range(0, 59, 1)
        self.spin_m.set_value(t.tm_min)
        time_row.pack_start(self.spin_h, False, False, 0)
        time_row.pack_start(Gtk.Label(label=":"), False, False, 0)
        time_row.pack_start(self.spin_m, False, False, 0)
        apply_dt = Gtk.Button(label="Imposta")
        apply_dt.get_style_context().add_class("vesper-menu-item")
        apply_dt.connect("clicked", self._apply_datetime)
        time_row.pack_end(apply_dt, False, False, 0)
        cal_box.pack_start(time_row, False, False, 0)

        # Riga FUSO: combo + Imposta.
        tz_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        tz_row.get_style_context().add_class("vesper-dt-row")
        tz_row.pack_start(Gtk.Label(label="Fuso"), False, False, 0)
        self.tz_combo = Gtk.ComboBoxText()
        cur = self._current_tz()
        zones = list(COMMON_TZ)
        if cur not in zones:
            zones.insert(0, cur)
        for z in zones:
            self.tz_combo.append_text(z)
        try:
            self.tz_combo.set_active(zones.index(cur))
        except ValueError:
            self.tz_combo.set_active(0)
        tz_row.pack_start(self.tz_combo, True, True, 0)
        apply_tz = Gtk.Button(label="Imposta")
        apply_tz.get_style_context().add_class("vesper-menu-item")
        apply_tz.connect("clicked", self._apply_tz)
        tz_row.pack_end(apply_tz, False, False, 0)
        cal_box.pack_start(tz_row, False, False, 0)

        self._spawn_popup("calendar", cal_box, align="right")

    # --- lista finestre ---
    def _own_xids(self):
        """XID (interi) delle NOSTRE finestre-popup (menu, audio, wifi, bt,
        calendario, schermi): non devono comparire nella tasklist come se
        fossero programmi aperti. Il menu start resta cosi' fuori dalla barra."""
        xids = set()
        for w in list(self._popups.values()):
            try:
                gw = w.get_window()
                if gw is not None:
                    xids.add(int(gw.get_xid()))
            except Exception:               # noqa: BLE001
                pass
        return xids

    def _refresh_pager(self):
        count, cur = _wmctrl_desktops()
        # ricostruisci i pulsanti se e' cambiato il numero di desktop
        if count != self._n_desktops:
            self._n_desktops = count
            for c in self.pager.get_children():
                self.pager.remove(c)
            self._pager_btns = {}
            if count > 1:
                for i in range(count):
                    b = Gtk.Button(label=str(i + 1))
                    b.set_relief(Gtk.ReliefStyle.NONE)
                    b.get_style_context().add_class("vesper-pager-btn")
                    b.set_tooltip_text(_t("pn.pager.goto") % (i + 1))
                    b.connect("clicked", self._on_pager, i)
                    self.pager.pack_start(b, False, False, 0)
                    self._pager_btns[i] = b
                self.pager.show_all()
                self.pager_sep.show()
            else:
                self.pager_sep.hide()
        # evidenzia il desktop corrente
        if cur != self._cur_desktop:
            self._cur_desktop = cur
            for i, b in self._pager_btns.items():
                ctx = b.get_style_context()
                if i == cur:
                    ctx.add_class("vesper-pager-active")
                else:
                    ctx.remove_class("vesper-pager-active")

    def _on_pager(self, _btn, idx):
        run_bg(["wmctrl", "-s", str(idx)])
        GLib.timeout_add(120, self._refresh_pager)

    def _refresh_tasks(self):
        self._refresh_pager()
        own = self._own_xids()
        wins = [(wid, d, t) for (wid, d, t) in _wmctrl_list()
                if _xid_int(wid) not in own]
        active = _active_window()
        sig = tuple((w, t) for w, _d, t in wins)
        if sig != self._last_sig:
            self._last_sig = sig
            for child in self.tasks.get_children():
                self.tasks.remove(child)
            self._task_btns = {}
            for wid, _desk, title in wins:
                b = Gtk.Button()
                # Label con ellissi: larghezza NATURALE limitata (~20 caratteri)
                # e minimo comprimibile. Cosi' quando ci sono tante finestre i
                # bottoni si stringono da soli (assorbono il deficit di spazio)
                # invece di spingere fuori dal pannello clock e icone a destra.
                lbl = Gtk.Label(label=title)
                lbl.set_ellipsize(Pango.EllipsizeMode.END)
                lbl.set_max_width_chars(20)
                lbl.set_width_chars(0)          # min comprimibile (niente base fissa)
                lbl.set_xalign(0.0)
                b.add(lbl)
                b.set_tooltip_text(title)
                b.get_style_context().add_class("vesper-task")
                b.connect("clicked", self._on_task, wid)
                # (False, False): larghezza naturale quando c'è spazio; sotto
                # pressione GtkBox li comprime fra minimo e naturale, cosi' la
                # tasklist (che occupa il centro, pack True) assorbe il deficit e
                # il lato destro — clock e icone — non viene mai spinto fuori.
                self.tasks.pack_start(b, False, False, 0)
                self._task_btns[wid] = b
            self.tasks.show_all()
        for wid, b in self._task_btns.items():
            ctx = b.get_style_context()
            if active and wid.lower() == active.lower():
                ctx.add_class("vesper-task-active")
            else:
                ctx.remove_class("vesper-task-active")
        return self._alive

    def _on_task(self, _btn, wid):
        active = _active_window()
        if active and wid.lower() == active.lower():
            if have("xdotool"):
                run_bg(["xdotool", "windowminimize", str(int(wid, 16))])
        else:
            run_bg(["wmctrl", "-i", "-a", wid])

    # --- orologio ---
    def _tick_clock(self):
        t = time.localtime()
        self.clock.set_text(time.strftime("%H:%M", t))
        giorni = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]
        mesi = ["gen", "feb", "mar", "apr", "mag", "giu",
                "lug", "ago", "set", "ott", "nov", "dic"]
        self.date.set_text("%s %d %s" % (giorni[t.tm_wday], t.tm_mday,
                                         mesi[t.tm_mon - 1]))
        return self._alive


# Registro globale delle barre vive (una per monitor): serve a ripiazzarle
# tutte dopo un cambio schermi via vesper-screens, quando xrandr non emette
# monitors-changed.
_ALL_PANELS = []


def _reposition_panels():
    """Riposiziona le barre sul loro monitor corrente (fallback ai segnali GTK
    quando xrandr --off / --primary non li scatena)."""
    for p in list(_ALL_PANELS):
        p._safe_place()
    return False


def run():
    # I <margins> di rc.xml non servono più: lo spazio lo riservano gli strut
    # EWMH (vedi Panel._set_struts). Azzerarli qui sistema anche le
    # configurazioni create dalle versioni precedenti, dove lo spazio veniva
    # riservato due volte.
    try:
        if panelcfg.clear_openbox_margins():
            panelcfg.openbox_reconfigure()
    except Exception:                        # noqa: BLE001
        pass

    # UNA barra per monitor: cosi' bar + menu compaiono su OGNI schermo (interno
    # e esterno). Le barre reagiscono ai cambi schermo (monitors-changed /
    # size-changed / refresh di vesper-screens).
    screen = Gdk.Screen.get_default()

    # Stato: numero di monitor dell'ultima COSTRUZIONE e id del rebuild in coda
    # (per il debounce). Vedi on_screen_change.
    _st = {"n": 0, "pending": 0}

    def _mon_count():
        try:
            if hasattr(screen, "get_n_monitors"):
                return max(1, screen.get_n_monitors())
        except Exception:                        # noqa: BLE001
            pass
        return 1

    def build(*_a):
        # (Ri)crea UNA barra per monitor. ROBUSTA: se la creazione di una barra
        # fallisce (stato schermo transitorio durante un cambio modo), non lascia
        # la barra a ZERO -> ritenta poco dopo. Cosi' un assestamento del modo
        # all'avvio non puo' spegnere il pannello in modo definitivo.
        for p in list(_ALL_PANELS):
            try:
                p.destroy()
            except Exception:                    # noqa: BLE001
                pass
        _ALL_PANELS.clear()
        n = _mon_count()
        ok = 0
        for i in range(n):
            try:
                p = Panel(i)
                p.show_all()
                _ALL_PANELS.append(p)
                ok += 1
            except Exception:                    # noqa: BLE001
                pass
        _st["n"] = n
        if ok == 0:
            # Nessuna barra creata (schermo in transizione): ritenta una volta.
            GLib.timeout_add(400, build)
        return False

    def _apply_change():
        _st["pending"] = 0
        n = _mon_count()
        if n == _st["n"] and _ALL_PANELS:
            # STESSO numero di monitor: e' cambiata solo la RISOLUZIONE (tipico
            # dell'auto-resize di VirtualBox o dell'assestamento del modo video
            # all'avvio). NON distruggere la barra: basta ridimensionarla e
            # riposizionarla. Distruggerla e ricrearla mentre si sta ancora
            # mappando era la causa della "barra assente dopo l'avvio".
            for p in list(_ALL_PANELS):
                p._safe_place()
        else:
            # Cambiato il NUMERO di monitor (collegato/scollegato uno schermo):
            # ricostruisci, una barra per schermo.
            build()
        return False

    def on_screen_change(*_a):
        # DEBOUNCE: all'avvio (e ad ogni auto-resize VirtualBox) arriva una
        # RAFFICA di size-changed/monitors-changed/refresh ravvicinati. Agire ad
        # ogni singolo evento faceva rifare la barra a ripetizione e, incrociando
        # la sua stessa mappatura, la lasciava sparita. Coalesciamo la raffica in
        # UNA sola azione dopo un attimo di quiete.
        if _st["pending"]:
            try:
                GLib.source_remove(_st["pending"])
            except Exception:                    # noqa: BLE001
                pass
        _st["pending"] = GLib.timeout_add(350, _apply_change)
        return False

    build()
    screen.connect("monitors-changed", on_screen_change)
    screen.connect("size-changed", on_screen_change)
    # Fallback affidabile ai segnali GTK: xrandr --off/--primary (usati da
    # vesper-screens) spesso NON scatena monitors-changed. Il file di refresh
    # viene toccato da vesper-screens dopo OGNI cambio schermo.
    install_screens_refresh_monitor(on_screen_change)
    Gtk.main()


if __name__ == "__main__":
    run()
