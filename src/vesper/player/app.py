# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Lettore audio di Vesper - GTK3 + GStreamer (playbin).

Sostituisce il vecchio "Test Audio": e' un vero lettore (playlist, seek,
volume, precedente/successivo, ripeti) che serve anche a PROVARE l'uscita
audio (pulsante "Prova audio" che carica il brano campione bundle).

Backend: GStreamer 'playbin' via PyGObject -> usa autoaudiosink, quindi esce
da PipeWire/Pulse/ALSA senza configurazione. Formati coperti dai plugin gst
installati on-demand dal launcher (good/bad/libav: MP3/AAC/Opus/FLAC/OGG/WAV...).
"""
import os
import subprocess
import sys

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gst", "1.0")
from gi.repository import Gtk, Gdk, GLib, Gst  # noqa: E402

# Tema di Vesper (accent del preset): riusa il CSS comune del pannello, come le
# altre app. Import "morbido": il player resta usabile anche senza.
try:
    from vesper.common import apply_css
except Exception:                       # noqa: BLE001
    def apply_css():
        return


def _accent():
    """Accent del preset attivo (#rrggbb). Import morbido: se i preset non
    c'e' (uso fuori dalla live), ripiega sul ciano di default."""
    try:
        from vesper.profiles import model
        ac = model.accent()
        if isinstance(ac, str) and ac.startswith("#") and len(ac) == 7:
            return ac
    except Exception:                   # noqa: BLE001
        pass
    return "#00e5ff"


def _rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _mix(hex_color, factor):
    """factor<1 scurisce, factor>1 schiarisce (clamp a 255)."""
    r, g, b = _rgb(hex_color)
    return "#%02x%02x%02x" % (min(255, int(r * factor)),
                              min(255, int(g * factor)),
                              min(255, int(b * factor)))


APP_NAME = "Lettore audio"
AUDIO_EXT = (".mp3", ".flac", ".ogg", ".oga", ".opus", ".wav", ".m4a",
             ".aac", ".wma", ".aiff", ".ape", ".mka", ".mp2", ".m4b")

# Brano campione bundle (per il pulsante "Prova audio").
SAMPLE_CANDIDATES = [
    os.path.expanduser("~/Music/vesper-suono-prova.wav"),
    "/home/nexus/Music/vesper-suono-prova.wav",
]

# Palette Nebula (coerente col resto del desktop) + accent del profilo iniettato.
BG = "#070b12"
CARD = "#0d1622"
CARD2 = "#111e2c"
TEXT = "#dff6ff"
DIM = "#6f93a6"
BORDER = "#17293a"


def _build_css(accent):
    ar, ag, ab = _rgb(accent)
    a = "%d,%d,%d" % (ar, ag, ab)
    dark = _mix(accent, 0.55)
    return ("""
.vesper-player {{ background: {BG}; color: {TEXT};
  font-family: "DejaVu Sans", "Cantarell", sans-serif; }}

/* Copertina: card arrotondata con lieve gradiente verso l'accent. */
.vesper-cover {{ border-radius: 20px;
  background-image: linear-gradient(135deg, {CARD2}, rgba({a},0.14));
  border: 1px solid {BORDER}; }}
.vesper-note {{ font-size: 62pt; color: rgba({a},0.92); }}
.vesper-note.playing {{ color: {accent}; }}

.vesper-title {{ font-weight: 700; font-size: 15pt; color: {TEXT}; }}
.vesper-sub {{ color: {DIM}; font-size: 9.5pt; }}
.vesper-time {{ color: {DIM}; font-size: 9pt; font-feature-settings: "tnum"; }}

/* Bottoni "ghost" piatti, arrotondati, con hover morbido in accent. */
.vesper-player button {{ background: transparent; border: none; border-radius: 10px;
  padding: 8px; color: {TEXT}; outline: none; box-shadow: none;
  transition: background 120ms ease, color 120ms ease; }}
.vesper-player button image {{ color: {TEXT}; }}
.vesper-player button:hover {{ background: rgba({a},0.14); }}
.vesper-player button:hover image {{ color: {accent}; }}
.vesper-player button:active {{ background: rgba({a},0.24); }}

/* Play/Pausa: pillola circolare piena in accent. */
.vesper-player button.vesper-play {{ background-image: linear-gradient(135deg, {accent}, {dark});
  border-radius: 50%; padding: 14px; min-width: 30px; min-height: 30px; }}
.vesper-player button.vesper-play image {{ color: {BG}; }}
.vesper-player button.vesper-play:hover {{ background-image: linear-gradient(135deg, {accent}, {accent}); }}
.vesper-player button.vesper-play:hover image {{ color: {BG}; }}

/* Toggle "ripeti" attivo: acceso in accent. */
.vesper-player button.vesper-on {{ background: rgba({a},0.18); }}
.vesper-player button.vesper-on image {{ color: {accent}; }}

/* Barre (seek/volume): trough sottile, highlight accent, cursore tondo. */
.vesper-player scale {{ padding: 6px 0; }}
.vesper-player scale trough {{ min-height: 5px; border-radius: 3px;
  background: {BORDER}; border: none; }}
.vesper-player scale highlight {{ border-radius: 3px;
  background-image: linear-gradient(90deg, {dark}, {accent}); }}
.vesper-player scale slider {{ min-width: 15px; min-height: 15px; margin: -6px;
  border-radius: 50%; background: {accent}; border: 3px solid {BG};
  box-shadow: 0 0 0 1px {accent}; }}

/* Playlist: righe piatte, hover/selezione arrotondati. */
.vesper-list {{ background: {CARD}; border-radius: 12px; border: 1px solid {BORDER};
  padding: 4px; }}
.vesper-list row {{ border-radius: 8px; padding: 1px; }}
.vesper-list row:hover {{ background: rgba({a},0.10); }}
.vesper-list row:selected {{ background: rgba({a},0.20); }}
.vesper-list row:selected label {{ color: {accent}; font-weight: 600; }}
.vesper-list row image {{ color: {DIM}; }}
.vesper-list row:selected image {{ color: {accent}; }}

/* Pulsante primario "Prova audio". */
.vesper-player button.vesper-primary {{ background: rgba({a},0.12); border: 1px solid {accent};
  border-radius: 10px; color: {accent}; padding: 8px 16px; font-weight: 600; }}
.vesper-player button.vesper-primary:hover {{ background: rgba({a},0.22); }}
.vesper-player button.vesper-primary image {{ color: {accent}; }}

scrolledwindow undershoot, scrolledwindow overshoot {{ background: none; }}
""".format(BG=BG, CARD=CARD, CARD2=CARD2, TEXT=TEXT, DIM=DIM, BORDER=BORDER,
           accent=accent, dark=dark, a=a)).encode()


def _fmt_time(ns):
    """Nanosecondi -> 'm:ss' (o 'h:mm:ss' oltre l'ora)."""
    if ns is None or ns < 0:
        return "0:00"
    s = int(ns // Gst.SECOND)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return "%d:%02d:%02d" % (h, m, sec)
    return "%d:%02d" % (m, sec)


class Player(Gtk.Window):
    def __init__(self, files=None):
        super().__init__(title=APP_NAME)
        self.set_default_size(600, 620)
        self.set_icon_name("vesper-player")
        apply_css()

        self.accent = _accent()
        self._css = Gtk.CssProvider()
        try:
            # Priorita' USER: sopra il tema base e all'accent.css del profilo,
            # cosi' il look flat del player vince e resta coerente col profilo.
            self._css.load_from_data(_build_css(self.accent))
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(), self._css,
                Gtk.STYLE_PROVIDER_PRIORITY_USER)
        except Exception:                   # noqa: BLE001
            pass                            # CSS non valido non deve bloccare l'app
        self.get_style_context().add_class("vesper-player")

        # --- stato ---
        self.playlist = []       # percorsi file
        self.current = -1        # indice brano corrente (-1 = nessuno)
        self.playing = False
        self.repeat = False
        self._seeking = False    # l'utente sta trascinando la barra
        self._duration = 0

        # --- GStreamer ---
        Gst.init(None)
        self.pipe = Gst.ElementFactory.make("playbin", "vesper-playbin")
        bus = self.pipe.get_bus()
        bus.add_signal_watch()
        bus.connect("message::eos", self._on_eos)
        bus.connect("message::error", self._on_error)
        bus.connect("message::state-changed", self._on_state)

        self._build_ui()
        self.connect("destroy", self._on_destroy)

        # File passati da riga di comando / gestore file.
        start = [f for f in (files or []) if os.path.isfile(f)]
        if start:
            self._add_paths(start)
            self._play_index(0)

        self.show_all()
        GLib.timeout_add(500, self._tick)

    # ------------------------------------------------------------------ UI
    def _icon_btn(self, icon, tip, cb, cls=None):
        b = Gtk.Button()
        b.set_relief(Gtk.ReliefStyle.NONE)
        b.set_tooltip_text(tip)
        if cls:
            b.get_style_context().add_class(cls)
        b.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.LARGE_TOOLBAR))
        b.set_always_show_image(True)
        b.connect("clicked", lambda _w: cb())
        return b

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        root.set_border_width(18)
        self.add(root)

        # --- Copertina (card con nota musicale al centro) --------------------
        cover = Gtk.Box()
        cover.get_style_context().add_class("vesper-cover")
        cover.set_size_request(168, 168)
        cover.set_halign(Gtk.Align.CENTER)
        self.note_lbl = Gtk.Label(label="♫")   # ♫
        self.note_lbl.get_style_context().add_class("vesper-note")
        self.note_lbl.set_hexpand(True)
        self.note_lbl.set_vexpand(True)
        self.note_lbl.set_halign(Gtk.Align.CENTER)
        self.note_lbl.set_valign(Gtk.Align.CENTER)
        cover.pack_start(self.note_lbl, True, True, 0)
        root.pack_start(cover, False, False, 2)

        # --- Titolo + sottotitolo (centrati) --------------------------------
        self.title_lbl = Gtk.Label(label="Nessun brano")
        self.title_lbl.set_justify(Gtk.Justification.CENTER)
        self.title_lbl.set_ellipsize(3)
        self.title_lbl.set_max_width_chars(48)
        self.title_lbl.get_style_context().add_class("vesper-title")
        self.sub_lbl = Gtk.Label(label="Apri un file o premi «Prova audio»")
        self.sub_lbl.set_justify(Gtk.Justification.CENTER)
        self.sub_lbl.set_ellipsize(3)
        self.sub_lbl.set_max_width_chars(60)
        self.sub_lbl.get_style_context().add_class("vesper-sub")
        root.pack_start(self.title_lbl, False, False, 0)
        root.pack_start(self.sub_lbl, False, False, 0)

        # --- Barra di avanzamento + tempi -----------------------------------
        seek_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.pos_lbl = Gtk.Label(label="0:00")
        self.pos_lbl.get_style_context().add_class("vesper-time")
        self.dur_lbl = Gtk.Label(label="0:00")
        self.dur_lbl.get_style_context().add_class("vesper-time")
        self.seek = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1000, 1)
        self.seek.set_draw_value(False)
        self.seek.set_hexpand(True)
        self.seek.connect("button-press-event", self._seek_press)
        self.seek.connect("button-release-event", self._seek_release)
        seek_row.pack_start(self.pos_lbl, False, False, 0)
        seek_row.pack_start(self.seek, True, True, 0)
        seek_row.pack_start(self.dur_lbl, False, False, 0)
        root.pack_start(seek_row, False, False, 0)

        # --- Comandi di riproduzione (centrati, play circolare) -------------
        ctl = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        ctl.set_halign(Gtk.Align.CENTER)
        self.repeat_btn = Gtk.ToggleButton()
        self.repeat_btn.set_relief(Gtk.ReliefStyle.NONE)
        self.repeat_btn.set_tooltip_text("Ripeti la playlist")
        self.repeat_btn.set_image(Gtk.Image.new_from_icon_name(
            "media-playlist-repeat-symbolic", Gtk.IconSize.LARGE_TOOLBAR))
        self.repeat_btn.set_always_show_image(True)
        self.repeat_btn.connect("toggled", self._on_repeat)
        ctl.pack_start(self.repeat_btn, False, False, 0)
        ctl.pack_start(self._icon_btn("media-skip-backward-symbolic",
                                      "Precedente", self.prev), False, False, 0)
        self.play_btn = self._icon_btn("media-playback-start-symbolic",
                                       "Riproduci/Pausa", self.toggle_play,
                                       cls="vesper-play")
        ctl.pack_start(self.play_btn, False, False, 0)
        ctl.pack_start(self._icon_btn("media-playback-stop-symbolic",
                                      "Ferma", self.stop), False, False, 0)
        ctl.pack_start(self._icon_btn("media-skip-forward-symbolic",
                                      "Successivo", self.next), False, False, 0)
        root.pack_start(ctl, False, False, 2)

        # --- Volume ----------------------------------------------------------
        vol_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        vol_row.pack_start(Gtk.Image.new_from_icon_name(
            "audio-volume-high-symbolic", Gtk.IconSize.MENU), False, False, 0)
        self.vol = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.vol.set_draw_value(False)
        self.vol.set_value(80)
        self.vol.set_hexpand(True)
        self.pipe.set_property("volume", 0.8)
        self.vol.connect("value-changed", self._on_volume)
        vol_row.pack_start(self.vol, True, True, 0)
        root.pack_start(vol_row, False, False, 0)

        # --- Playlist --------------------------------------------------------
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.listbox = Gtk.ListBox()
        self.listbox.get_style_context().add_class("vesper-list")
        self.listbox.connect("row-activated", self._on_row)
        sw.add(self.listbox)
        root.pack_start(sw, True, True, 0)

        # --- Azioni file -----------------------------------------------------
        act = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        act.pack_start(self._icon_btn("document-open-symbolic",
                                      "Apri file audio", self.open_files),
                       False, False, 0)
        act.pack_start(self._icon_btn("folder-open-symbolic",
                                      "Apri una cartella", self.open_folder),
                       False, False, 0)
        act.pack_start(self._icon_btn("edit-clear-all-symbolic",
                                      "Svuota la playlist", self.clear),
                       False, False, 0)
        test_b = Gtk.Button(label="Prova audio")
        test_b.set_image(Gtk.Image.new_from_icon_name(
            "audio-speakers-symbolic", Gtk.IconSize.MENU))
        test_b.set_always_show_image(True)
        test_b.get_style_context().add_class("vesper-primary")
        test_b.set_tooltip_text("Riproduce il brano campione per verificare l'uscita audio")
        test_b.connect("clicked", lambda _w: self.play_sample())
        act.pack_end(test_b, False, False, 0)
        root.pack_start(act, False, False, 0)

    def _on_repeat(self, b):
        self.repeat = b.get_active()
        ctx = b.get_style_context()
        if self.repeat:
            ctx.add_class("vesper-on")
        else:
            ctx.remove_class("vesper-on")

    # -------------------------------------------------------- playlist mgmt
    def _add_paths(self, paths):
        added = 0
        for p in paths:
            ap = os.path.abspath(p)
            if ap in self.playlist:
                continue
            self.playlist.append(ap)
            row = Gtk.ListBoxRow()
            hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            hb.set_margin_top(3); hb.set_margin_bottom(3)
            hb.set_margin_start(6); hb.set_margin_end(6)
            hb.pack_start(Gtk.Image.new_from_icon_name(
                "audio-x-generic-symbolic", Gtk.IconSize.MENU), False, False, 0)
            lab = Gtk.Label(label=os.path.basename(ap))
            lab.set_xalign(0); lab.set_ellipsize(3)
            hb.pack_start(lab, True, True, 0)
            row.add(hb)
            row.show_all()
            self.listbox.add(row)
            added += 1
        return added

    def _on_row(self, _list, row):
        idx = row.get_index()
        if 0 <= idx < len(self.playlist):
            self._play_index(idx)

    def clear(self):
        self.stop()
        self.playlist = []
        self.current = -1
        for c in self.listbox.get_children():
            self.listbox.remove(c)
        self.title_lbl.set_text("Nessun brano")
        self.sub_lbl.set_text("Apri un file o premi «Prova audio»")

    # --------------------------------------------------------- open dialogs
    def _audio_filter(self):
        f = Gtk.FileFilter()
        f.set_name("File audio")
        for ext in AUDIO_EXT:
            f.add_pattern("*" + ext)
            f.add_pattern("*" + ext.upper())
        return f

    def open_files(self):
        d = Gtk.FileChooserDialog(
            title="Apri file audio", transient_for=self,
            action=Gtk.FileChooserAction.OPEN)
        d.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                      Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        d.set_select_multiple(True)
        d.add_filter(self._audio_filter())
        music = os.path.expanduser("~/Music")
        if os.path.isdir(music):
            d.set_current_folder(music)
        if d.run() == Gtk.ResponseType.OK:
            paths = sorted(d.get_filenames())
            first_new = len(self.playlist)
            if self._add_paths(paths) and not self.playing:
                self._play_index(first_new)
        d.destroy()

    def open_folder(self):
        d = Gtk.FileChooserDialog(
            title="Apri una cartella di musica", transient_for=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER)
        d.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                      Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        if d.run() == Gtk.ResponseType.OK:
            folder = d.get_filename()
            found = []
            try:
                for fn in sorted(os.listdir(folder)):
                    if fn.lower().endswith(AUDIO_EXT):
                        found.append(os.path.join(folder, fn))
            except OSError:
                found = []
            first_new = len(self.playlist)
            if found and self._add_paths(found) and not self.playing:
                self._play_index(first_new)
        d.destroy()

    def _unmute(self):
        """Forza lo sblocco audio (ALSA + PipeWire) in background: cosi' premere
        «Prova audio» sblocca anche l'uscita su HW reale, senza digitare nulla."""
        try:
            subprocess.Popen(["vesper-audio-unmute", "2"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:                   # noqa: BLE001
            pass

    def play_sample(self):
        self._unmute()
        for p in SAMPLE_CANDIDATES:
            if os.path.isfile(p):
                first_new = len(self.playlist)
                # se gia' in playlist, riproducilo dalla sua posizione
                if os.path.abspath(p) in self.playlist:
                    self._play_index(self.playlist.index(os.path.abspath(p)))
                elif self._add_paths([p]):
                    self._play_index(first_new)
                return
        self.sub_lbl.set_text("Brano campione non trovato in ~/Music.")

    # ---------------------------------------------------------- riproduzione
    def _play_index(self, idx):
        if not (0 <= idx < len(self.playlist)):
            return
        self.current = idx
        path = self.playlist[idx]
        self.pipe.set_state(Gst.State.NULL)
        self.pipe.set_property("uri", Gst.filename_to_uri(path))
        self.pipe.set_state(Gst.State.PLAYING)
        self.playing = True
        self._duration = 0
        self._update_play_icon()
        self.title_lbl.set_text(os.path.basename(path))
        self.sub_lbl.set_text(os.path.dirname(path))
        row = self.listbox.get_row_at_index(idx)
        if row is not None:
            self.listbox.select_row(row)

    def toggle_play(self):
        if self.current < 0:
            if self.playlist:
                self._play_index(0)
            else:
                self.play_sample()
            return
        if self.playing:
            self.pipe.set_state(Gst.State.PAUSED)
            self.playing = False
        else:
            self.pipe.set_state(Gst.State.PLAYING)
            self.playing = True
        self._update_play_icon()

    def stop(self):
        self.pipe.set_state(Gst.State.NULL)
        self.playing = False
        self._duration = 0
        self.seek.set_value(0)
        self.pos_lbl.set_text("0:00")
        self._update_play_icon()

    def next(self):
        if not self.playlist:
            return
        nxt = self.current + 1
        if nxt >= len(self.playlist):
            if not self.repeat:
                self.stop()
                return
            nxt = 0
        self._play_index(nxt)

    def prev(self):
        if not self.playlist:
            return
        # <3s dall'inizio -> brano precedente; altrimenti riparti dall'inizio.
        pos = self._query(self.pipe.query_position)
        if pos is not None and pos > 3 * Gst.SECOND:
            self._play_index(self.current)
            return
        prv = self.current - 1
        if prv < 0:
            prv = len(self.playlist) - 1 if self.repeat else 0
        self._play_index(prv)

    def _update_play_icon(self):
        icon = ("media-playback-pause-symbolic" if self.playing
                else "media-playback-start-symbolic")
        self.play_btn.set_image(Gtk.Image.new_from_icon_name(
            icon, Gtk.IconSize.LARGE_TOOLBAR))
        # La nota sulla copertina si "accende" in accent quando si riproduce.
        ctx = self.note_lbl.get_style_context()
        if self.playing:
            ctx.add_class("playing")
        else:
            ctx.remove_class("playing")

    # ------------------------------------------------------------- volume
    def _on_volume(self, scale):
        self.pipe.set_property("volume", scale.get_value() / 100.0)

    # -------------------------------------------------------------- seek
    def _seek_press(self, *_a):
        self._seeking = True
        return False

    def _seek_release(self, *_a):
        if self._duration > 0:
            frac = self.seek.get_value() / 1000.0
            self.pipe.seek_simple(
                Gst.Format.TIME,
                Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
                int(frac * self._duration))
        self._seeking = False
        return False

    # ------------------------------------------------------- bus/tick GStreamer
    @staticmethod
    def _query(fn):
        ok, val = fn(Gst.Format.TIME)
        return val if ok else None

    def _tick(self):
        if self.playing and not self._seeking:
            if self._duration <= 0:
                d = self._query(self.pipe.query_duration)
                if d:
                    self._duration = d
                    self.dur_lbl.set_text(_fmt_time(d))
            pos = self._query(self.pipe.query_position)
            if pos is not None:
                self.pos_lbl.set_text(_fmt_time(pos))
                if self._duration > 0:
                    self.seek.set_value(1000.0 * pos / self._duration)
        return True

    def _on_eos(self, _bus, _msg):
        self.next()

    def _on_error(self, _bus, msg):
        err, _dbg = msg.parse_error()
        self.sub_lbl.set_text("Errore: %s" % err.message)
        self.stop()

    def _on_state(self, _bus, msg):
        if msg.src is self.pipe:
            _old, new, _pending = msg.parse_state_changed()
            if new == Gst.State.PLAYING and self._duration <= 0:
                d = self._query(self.pipe.query_duration)
                if d:
                    self._duration = d
                    self.dur_lbl.set_text(_fmt_time(d))

    def _on_destroy(self, *_a):
        try:
            self.pipe.set_state(Gst.State.NULL)
        except Exception:                   # noqa: BLE001
            pass
        Gtk.main_quit()


def main(argv=None):
    Player(argv or sys.argv[1:])
    Gtk.main()


if __name__ == "__main__":
    main()
