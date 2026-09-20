# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Visualizzatore video di Vesper - GTK3 + GStreamer (playbin + gtksink).

Riproduttore video nativo, coerente col Lettore audio (stesso stile flat e
accent del profilo). Il video e' reso da 'gtksink': un widget GTK vero, quindi
niente hack XID/GstVideoOverlay e funziona su qualunque backend (X/efifb/VM).

Funzioni: apri file/cartella, playlist prev/successivo, play/pausa/stop, seek,
volume, schermo intero (F11 / doppio clic) con barra comandi ad auto-nascondita.
Backend: playbin -> autoaudiosink per l'audio (esce da PipeWire), gtksink per
il video. Codec dai plugin gst (good/bad/libav): H.264/VP8/VP9/AAC/Opus/MP3...
"""
import os
import sys

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gst", "1.0")
from gi.repository import Gtk, Gdk, GLib, Gst  # noqa: E402

try:
    from vesper.common import apply_css
except Exception:                       # noqa: BLE001
    def apply_css():
        return

try:
    from vesper.i18n import t as _t
except Exception:                       # noqa: BLE001
    def _t(chiave, **kw):               # ripiego: mostra la chiave
        return chiave


def _accent():
    """Accent del profilo attivo (#rrggbb); default ciano fuori dalla live."""
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
    r, g, b = _rgb(hex_color)
    return "#%02x%02x%02x" % (min(255, int(r * factor)),
                              min(255, int(g * factor)),
                              min(255, int(b * factor)))


APP_NAME = _t("vd.app")
VIDEO_EXT = (".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4v", ".mpg", ".mpeg",
             ".wmv", ".flv", ".ogv", ".ts", ".3gp", ".m2ts")

TEXT = "#dff6ff"
DIM = "#8fb0c0"
BAR = "#0b1119"


def _build_css(accent):
    ar, ag, ab = _rgb(accent)
    a = "%d,%d,%d" % (ar, ag, ab)
    dark = _mix(accent, 0.55)
    return ("""
.vesper-video {{ background: #000000; color: {TEXT};
  font-family: "DejaVu Sans", "Cantarell", sans-serif; }}
.vesper-stage {{ background: #000000; }}

/* Barra comandi: fondo scuro semitrasparente, look flat. */
.vesper-bar {{ background: rgba(9,14,22,0.94); border-top: 1px solid rgba({a},0.25);
  padding: 8px 12px; }}
.vesper-bar label.time {{ color: {DIM}; font-size: 9pt; font-feature-settings: "tnum"; }}
.vesper-bar label.title {{ color: {TEXT}; font-weight: 600; }}

.vesper-video button {{ background: transparent; border: none; border-radius: 10px;
  padding: 7px; color: {TEXT}; box-shadow: none; outline: none;
  transition: background 120ms ease, color 120ms ease; }}
.vesper-video button image {{ color: {TEXT}; }}
.vesper-video button:hover {{ background: rgba({a},0.16); }}
.vesper-video button:hover image {{ color: {accent}; }}
.vesper-video button:active {{ background: rgba({a},0.26); }}

.vesper-video button.vesper-play {{ background-image: linear-gradient(135deg, {accent}, {dark});
  border-radius: 50%; padding: 12px; min-width: 26px; min-height: 26px; }}
.vesper-video button.vesper-play image {{ color: #000000; }}
.vesper-video button.vesper-play:hover image {{ color: #000000; }}
.vesper-video button.vesper-on {{ background: rgba({a},0.20); }}
.vesper-video button.vesper-on image {{ color: {accent}; }}

.vesper-video scale {{ padding: 5px 0; }}
.vesper-video scale trough {{ min-height: 5px; border-radius: 3px;
  background: rgba(255,255,255,0.14); border: none; }}
.vesper-video scale highlight {{ border-radius: 3px;
  background-image: linear-gradient(90deg, {dark}, {accent}); }}
.vesper-video scale slider {{ min-width: 14px; min-height: 14px; margin: -6px;
  border-radius: 50%; background: {accent}; border: 3px solid {BAR};
  box-shadow: 0 0 0 1px {accent}; }}

/* Placeholder quando non c'e' nulla in riproduzione: "copertina" tonda con
   triangolo play in accent, in stile coerente col Lettore audio. */
.vesper-hint {{ color: {DIM}; font-size: 11.5pt; }}
.vesper-vcover {{ border-radius: 90px;
  background-image: radial-gradient(circle at 38% 32%, rgba({a},0.22), rgba({a},0.05) 70%);
  border: 1px solid rgba({a},0.35); }}
.vesper-hint-note {{ color: {accent}; font-size: 50pt; margin-left: 8px; }}
""".format(TEXT=TEXT, DIM=DIM, BAR=BAR, accent=accent, dark=dark, a=a)).encode()


def _fmt_time(ns):
    if ns is None or ns < 0:
        return "0:00"
    s = int(ns // Gst.SECOND)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return "%d:%02d:%02d" % (h, m, sec)
    return "%d:%02d" % (m, sec)


class Video(Gtk.Window):
    def __init__(self, files=None):
        super().__init__(title=APP_NAME)
        self.set_default_size(860, 540)
        self.set_icon_name("vesper-video")
        apply_css()

        self.accent = _accent()
        self._css = Gtk.CssProvider()
        try:
            self._css.load_from_data(_build_css(self.accent))
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(), self._css,
                Gtk.STYLE_PROVIDER_PRIORITY_USER)
        except Exception:                   # noqa: BLE001
            pass
        self.get_style_context().add_class("vesper-video")

        # --- stato ---
        self.playlist = []
        self.current = -1
        self.playing = False
        self.repeat = False
        self.fullscreen_on = False
        self._seeking = False
        self._duration = 0
        self._hide_id = 0

        # --- GStreamer: playbin + gtksink (widget GTK per il video) ---
        Gst.init(None)
        self.pipe = Gst.ElementFactory.make("playbin", "vesper-playbin")
        self.sink = Gst.ElementFactory.make("gtksink", "vesper-gtksink")
        self._video_widget = None
        if self.sink is not None and self.pipe is not None:
            self.pipe.set_property("video-sink", self.sink)
            try:
                self._video_widget = self.sink.props.widget
            except Exception:               # noqa: BLE001
                self._video_widget = None
        bus = self.pipe.get_bus()
        bus.add_signal_watch()
        bus.connect("message::eos", self._on_eos)
        bus.connect("message::error", self._on_error)
        bus.connect("message::state-changed", self._on_state)

        self._build_ui()
        self.connect("destroy", self._on_destroy)
        self.connect("key-press-event", self._on_key)
        self.connect("motion-notify-event", self._on_motion)
        self.add_events(Gdk.EventMask.POINTER_MOTION_MASK)

        start = [f for f in (files or []) if os.path.isfile(f)]
        if start:
            self._add_paths(start)
            self._play_index(0)

        self.show_all()
        # show_all riespone il placeholder: nascondilo se sta gia' riproducendo.
        if self.current >= 0 and getattr(self, "hint", None) is not None:
            self.hint.hide()
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
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(root)

        # --- Palco video (o placeholder) ------------------------------------
        self.stage = Gtk.EventBox()
        self.stage.get_style_context().add_class("vesper-stage")
        self.stage.connect("button-press-event", self._on_stage_click)
        self.stage.add_events(Gdk.EventMask.POINTER_MOTION_MASK)
        # Overlay: il video riempie il palco, il placeholder gli sta SOPRA
        # centrato e viene nascosto appena parte la riproduzione.
        overlay = Gtk.Overlay()
        if self._video_widget is not None:
            self._video_widget.set_hexpand(True)
            self._video_widget.set_vexpand(True)
            overlay.add(self._video_widget)
            self.hint = self._make_hint()
        else:
            self.hint = self._make_hint(
                _t("vd.no_gtksink"))
        self.hint.set_halign(Gtk.Align.CENTER)
        self.hint.set_valign(Gtk.Align.CENTER)
        overlay.add_overlay(self.hint)
        self.stage.add(overlay)
        root.pack_start(self.stage, True, True, 0)

        # --- Barra comandi ---------------------------------------------------
        self.bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.bar.get_style_context().add_class("vesper-bar")

        seek_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.pos_lbl = Gtk.Label(label="0:00")
        self.pos_lbl.get_style_context().add_class("time")
        self.dur_lbl = Gtk.Label(label="0:00")
        self.dur_lbl.get_style_context().add_class("time")
        self.seek = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1000, 1)
        self.seek.set_draw_value(False)
        self.seek.set_hexpand(True)
        self.seek.connect("button-press-event", self._seek_press)
        self.seek.connect("button-release-event", self._seek_release)
        seek_row.pack_start(self.pos_lbl, False, False, 0)
        seek_row.pack_start(self.seek, True, True, 0)
        seek_row.pack_start(self.dur_lbl, False, False, 0)
        self.bar.pack_start(seek_row, False, False, 0)

        ctl = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        ctl.pack_start(self._icon_btn("media-skip-backward-symbolic",
                                      _t("vd.tt.prev"), self.prev),
                       False, False, 0)
        self.play_btn = self._icon_btn("media-playback-start-symbolic",
                                       _t("vd.tt.play"), self.toggle_play,
                                       cls="vesper-play")
        ctl.pack_start(self.play_btn, False, False, 0)
        ctl.pack_start(self._icon_btn("media-playback-stop-symbolic",
                                      _t("vd.tt.stop"), self.stop),
                       False, False, 0)
        ctl.pack_start(self._icon_btn("media-skip-forward-symbolic",
                                      _t("vd.tt.next"), self.next),
                       False, False, 0)

        # titolo brano al centro
        self.title_lbl = Gtk.Label(label=_t("vd.novideo"))
        self.title_lbl.get_style_context().add_class("title")
        self.title_lbl.set_ellipsize(3)
        ctl.pack_start(self.title_lbl, True, True, 8)

        # volume
        ctl.pack_start(Gtk.Image.new_from_icon_name(
            "audio-volume-high-symbolic", Gtk.IconSize.MENU), False, False, 0)
        self.vol = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.vol.set_draw_value(False)
        self.vol.set_value(80)
        self.vol.set_size_request(110, -1)
        self.pipe.set_property("volume", 0.8)
        self.vol.connect("value-changed", self._on_volume)
        ctl.pack_start(self.vol, False, False, 0)

        ctl.pack_start(self._icon_btn("document-open-symbolic",
                                      _t("vd.open_title"), self.open_files),
                       False, False, 0)
        ctl.pack_start(self._icon_btn("folder-open-symbolic",
                                      _t("vd.tt.openfolder"), self.open_folder),
                       False, False, 0)
        self.fs_btn = self._icon_btn("view-fullscreen-symbolic",
                                     _t("vd.tt.full"),
                                     self.toggle_fullscreen)
        ctl.pack_start(self.fs_btn, False, False, 0)
        self.bar.pack_start(ctl, False, False, 0)

        root.pack_start(self.bar, False, False, 0)

    def _make_hint(self, text=None):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        # copertina tonda con triangolo play in accent
        cover = Gtk.Box()
        cover.get_style_context().add_class("vesper-vcover")
        cover.set_size_request(180, 180)
        cover.set_halign(Gtk.Align.CENTER)
        note = Gtk.Label(label="▶")   # ▶
        note.get_style_context().add_class("vesper-hint-note")
        note.set_hexpand(True)
        note.set_vexpand(True)
        note.set_halign(Gtk.Align.CENTER)
        note.set_valign(Gtk.Align.CENTER)
        cover.pack_start(note, True, True, 0)
        lab = Gtk.Label(label=text or _t("vd.drophere"))
        lab.get_style_context().add_class("vesper-hint")
        box.pack_start(cover, False, False, 0)
        box.pack_start(lab, False, False, 0)
        return box

    # -------------------------------------------------------- playlist mgmt
    def _add_paths(self, paths):
        added = 0
        for p in paths:
            ap = os.path.abspath(p)
            if ap in self.playlist:
                continue
            self.playlist.append(ap)
            added += 1
        return added

    # --------------------------------------------------------- open dialogs
    def _video_filter(self):
        f = Gtk.FileFilter()
        f.set_name(_t("vd.videofiles"))
        for ext in VIDEO_EXT:
            f.add_pattern("*" + ext)
            f.add_pattern("*" + ext.upper())
        return f

    def open_files(self):
        d = Gtk.FileChooserDialog(
            title=_t("vd.open_title"), transient_for=self,
            action=Gtk.FileChooserAction.OPEN)
        d.add_buttons(_t("vd.cancel"), Gtk.ResponseType.CANCEL,
                      _t("vd.open"), Gtk.ResponseType.OK)
        d.set_select_multiple(True)
        d.add_filter(self._video_filter())
        vids = os.path.expanduser("~/Videos")
        if os.path.isdir(vids):
            d.set_current_folder(vids)
        if d.run() == Gtk.ResponseType.OK:
            paths = sorted(d.get_filenames())
            first_new = len(self.playlist)
            if self._add_paths(paths):
                self._play_index(first_new)
        d.destroy()

    def open_folder(self):
        d = Gtk.FileChooserDialog(
            title=_t("vd.folder_title"), transient_for=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER)
        d.add_buttons(_t("vd.cancel"), Gtk.ResponseType.CANCEL,
                      _t("vd.open"), Gtk.ResponseType.OK)
        if d.run() == Gtk.ResponseType.OK:
            folder = d.get_filename()
            found = []
            try:
                for fn in sorted(os.listdir(folder)):
                    if fn.lower().endswith(VIDEO_EXT):
                        found.append(os.path.join(folder, fn))
            except OSError:
                found = []
            first_new = len(self.playlist)
            if found and self._add_paths(found):
                self._play_index(first_new)
        d.destroy()

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
        name = os.path.basename(path)
        self.title_lbl.set_text(name)
        self.set_title("%s - %s" % (name, APP_NAME))
        if getattr(self, "hint", None) is not None:
            self.hint.hide()

    def toggle_play(self):
        if self.current < 0:
            if self.playlist:
                self._play_index(0)
            else:
                self.open_files()
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

    # ------------------------------------------------------- schermo intero
    def toggle_fullscreen(self):
        if self.fullscreen_on:
            self.unfullscreen()
        else:
            self.fullscreen()

    def _on_key(self, _w, ev):
        kv = ev.keyval
        if kv == Gdk.KEY_F11:
            self.toggle_fullscreen()
            return True
        if kv == Gdk.KEY_Escape and self.fullscreen_on:
            self.unfullscreen()
            return True
        if kv == Gdk.KEY_space:
            self.toggle_play()
            return True
        return False

    def do_window_state_event(self, ev):
        # traccia lo stato fullscreen reale (via WM) e gestisce autohide barra
        self.fullscreen_on = bool(
            ev.new_window_state & Gdk.WindowState.FULLSCREEN)
        if self.fullscreen_on:
            self.fs_btn.set_tooltip_text(_t("vd.tt.unfull"))
            self._arm_autohide()
        else:
            self.fs_btn.set_tooltip_text(_t("vd.tt.full"))
            self._show_bar()
        return False

    def _on_stage_click(self, _w, ev):
        if ev.type == Gdk.EventType._2BUTTON_PRESS:   # doppio clic
            self.toggle_fullscreen()
            return True
        return False

    def _on_motion(self, *_a):
        if self.fullscreen_on:
            self._show_bar()
            self._arm_autohide()
        return False

    def _show_bar(self):
        self.bar.show()
        win = self.get_window()
        if win is not None:
            win.set_cursor(None)

    def _arm_autohide(self):
        if self._hide_id:
            GLib.source_remove(self._hide_id)
        self._hide_id = GLib.timeout_add(2500, self._hide_bar)

    def _hide_bar(self):
        self._hide_id = 0
        if self.fullscreen_on:
            self.bar.hide()
            win = self.get_window()
            if win is not None:
                blank = Gdk.Cursor.new_for_display(
                    Gdk.Display.get_default(), Gdk.CursorType.BLANK_CURSOR)
                win.set_cursor(blank)
        return False

    # ------------------------------------------------------- bus/tick
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
        self.title_lbl.set_text(_t("vd.error") % err.message)
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
    Video(argv or sys.argv[1:])
    Gtk.main()


if __name__ == "__main__":
    main()
