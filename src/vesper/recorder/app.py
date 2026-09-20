# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""vesper-recorder - registratore vocale di Vesper (GTK3 + Cairo).

Cattura dal microfono con `arecord` (ALSA, gia' nella base; instradato via il
bridge ALSA di PipeWire), mostra in tempo reale la forma d'onda (alti/bassi
della voce) e un indicatore di livello, registra su file WAV e permette di
riascoltare. Nessuna dipendenza nuova: solo alsa-utils + GTK3/Cairo.

Privacy: la cattura parte solo con la finestra aperta (per il monitor del
livello) e il file viene scritto solo quando premi Registra.
"""
import math
import os
import struct
import subprocess
import threading
import wave
from datetime import datetime

import cairo

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk  # noqa: E402
try:
    from gi.repository import Pango  # noqa: E402,F401
except Exception:                       # noqa: BLE001
    Pango = None

try:
    from vesper.i18n import t as _t
except Exception:                       # noqa: BLE001
    def _t(chiave, **kw):               # ripiego: mostra la chiave
        return chiave

RATE = 16000            # Hz (voce: 16 kHz e' piu' che sufficiente e leggero)
CH = 1                  # mono
BYTES = 2              # S16_LE
CHUNK = 1024           # campioni per lettura
NBARS = 160            # storia dei picchi per la forma d'onda (modalita' "Onda")


def _cartella_musica():
    """Cartella Musica dell'utente secondo XDG: il nome e' gia' nella lingua
    del sistema, quindi non se ne inventa uno nostro (prima era "~/Musica",
    che fuori dall'italiano creava una cartella sbagliata)."""
    conf = os.path.join(os.environ.get("XDG_CONFIG_HOME",
                                       os.path.expanduser("~/.config")),
                        "user-dirs.dirs")
    try:
        for riga in open(conf, encoding="utf-8"):
            if riga.startswith("XDG_MUSIC_DIR="):
                val = riga.split("=", 1)[1].strip().strip('"')
                val = val.replace("$HOME", os.path.expanduser("~"))
                if os.path.isdir(val):
                    return val
    except OSError:
        pass
    for nome in ("Music", "Musica", "Musik", "Musique", "Música"):
        via = os.path.expanduser("~/" + nome)
        if os.path.isdir(via):
            return via
    return os.path.expanduser("~")


# Sottocartella col nome del programma: stabile, non cambia cambiando lingua.
OUTDIR = os.path.join(_cartella_musica(), "Vesper")

# --- Analizzatore di SPETTRO (movimento "veritiero rispetto alle frequenze") ---
NBANDS = 28             # barre = bande di frequenza (log-spaziate)
FFTN = 512             # punti FFT (potenza di 2); risoluzione ~31 Hz a 16 kHz
_HANN = [0.5 - 0.5 * math.cos(2 * math.pi * i / (FFTN - 1)) for i in range(FFTN)]
# Bordi delle bande in indici di bin FFT, spaziati logaritmicamente (2..N/2).
_EDGES = [max(1, int(2 * (float(FFTN // 2) / 2) ** (k / float(NBANDS))))
          for k in range(NBANDS + 1)]
_FALL = 0.80            # decadimento (peak-hold): le barre scendono morbide


def _fft(re, im):
    """FFT radix-2 in-place (Cooley-Tukey iterativa). len = potenza di 2."""
    n = len(re)
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j |= bit
        if i < j:
            re[i], re[j] = re[j], re[i]
            im[i], im[j] = im[j], im[i]
    length = 2
    while length <= n:
        ang = -2.0 * math.pi / length
        wr, wi = math.cos(ang), math.sin(ang)
        half = length >> 1
        for i in range(0, n, length):
            cr_, ci = 1.0, 0.0
            for k in range(half):
                a = i + k
                b = a + half
                tr = cr_ * re[b] - ci * im[b]
                ti = cr_ * im[b] + ci * re[b]
                re[b] = re[a] - tr
                im[b] = im[a] - ti
                re[a] += tr
                im[a] += ti
                cr_, ci = cr_ * wr - ci * wi, cr_ * wi + ci * wr
        length <<= 1


def _spectrum(vals):
    """Da un blocco di campioni int16 -> NBANDS magnitudini 0..1 per banda di
    frequenza (finestra di Hann + FFT + raggruppamento log + scala percettiva)."""
    re = [0.0] * FFTN
    im = [0.0] * FFTN
    m = min(len(vals), FFTN)
    for i in range(m):
        re[i] = (vals[i] / 32768.0) * _HANN[i]
    _fft(re, im)
    gain = 4.0 / FFTN
    half = FFTN // 2
    out = []
    for k in range(NBANDS):
        a = _EDGES[k]
        b = max(a + 1, _EDGES[k + 1])
        mx = 0.0
        j = a
        while j < b and j < half:
            mag = re[j] * re[j] + im[j] * im[j]
            if mag > mx:
                mx = mag
            j += 1
        v = math.sqrt(mx) * gain
        if v > 1.0:
            v = 1.0
        out.append(v ** 0.5)          # percettivo: alza i toni deboli
    return out

# Palette di Vesper (coerente col resto del desktop)
GROUND = (5 / 255, 10 / 255, 20 / 255)
ACCENT = (0.0, 0.898, 1.0)          # #00e5ff
DIM = (0.35, 0.54, 0.60)
ALARM = (1.0, 0.353, 0.541)         # #ff5a8a

CSS = b"""
window { background:#050a14; color:#d4f3ff; }
.rec-title { font-weight:700; font-size:15px; color:#d4f3ff; }
.rec-sub { color:#6f97a8; font-size:12px; }
.rec-time { font-family:monospace; font-size:22px; color:#00e5ff; }
button { background:#0a1a26; color:#d4f3ff; border:1px solid #173247;
         border-radius:6px; padding:8px 14px; }
button:hover { border-color:#00e5ff; }
button:checked { background:#0a2a3a; color:#00e5ff; border-color:#00e5ff; }
.rec-go { background:#00e5ff; color:#050a14; font-weight:700; border:none; }
.rec-stop { background:#ff5a8a; color:#050a14; font-weight:700; border:none; }
"""


class Recorder(Gtk.Window):
    def __init__(self):
        super().__init__(title=_t("rc.app"))
        self.set_default_size(600, 340)
        self.set_icon_name("audio-input-microphone-symbolic")

        try:
            prov = Gtk.CssProvider()
            prov.load_from_data(CSS)
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(), prov,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        except Exception:               # noqa: BLE001
            pass

        self.bands = [0.0] * NBANDS     # magnitudini per banda di frequenza (spettro)
        self.levels = [0.0] * NBARS     # storia dei picchi (modalita' "Onda")
        self.viz = "spec"               # "spec" (frequenze) | "wave" (ampiezza)
        self.peak = 0.0                 # livello complessivo (per la barra livello)
        self.recording = False
        self.wav = None
        self.frames = 0
        self.proc = None
        self._stop = False
        self.last_file = None
        self._start_mono = 0.0
        # Riproduzione: livelli precalcolati dal WAV, scorsi in sync con l'ascolto
        self.playing = False
        self._play_peaks = []
        self._play_start = 0.0
        self._play_dur = 0.0
        self._play_proc = None

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.set_border_width(14)
        self.add(root)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        t = Gtk.Label(label=_t("rc.app")); t.set_xalign(0)
        t.get_style_context().add_class("rec-title")
        head.pack_start(t, True, True, 0)
        # Selettore visualizzazione: Spettro (frequenze) oppure Onda (ampiezza).
        self._viz_guard = False
        self.btn_spec = Gtk.ToggleButton(label=_t("rc.spectrum"))
        self.btn_spec.set_active(True)
        self.btn_wave = Gtk.ToggleButton(label=_t("rc.wave"))
        self.btn_spec.connect("toggled", self._on_viz, "spec")
        self.btn_wave.connect("toggled", self._on_viz, "wave")
        seg = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        seg.get_style_context().add_class("linked")
        seg.pack_start(self.btn_spec, False, False, 0)
        seg.pack_start(self.btn_wave, False, False, 0)
        head.pack_start(seg, False, False, 0)
        self.time_lbl = Gtk.Label(label="00:00")
        self.time_lbl.get_style_context().add_class("rec-time")
        head.pack_start(self.time_lbl, False, False, 0)
        root.pack_start(head, False, False, 0)

        # Forma d'onda live (alti/bassi della voce)
        self.canvas = Gtk.DrawingArea()
        self.canvas.set_size_request(-1, 150)
        self.canvas.connect("draw", self._on_draw)
        root.pack_start(self.canvas, True, True, 0)

        # Barra di livello corrente
        self.level = Gtk.LevelBar()
        self.level.set_min_value(0.0); self.level.set_max_value(1.0)
        root.pack_start(self.level, False, False, 0)

        # Comandi
        ctr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.rec_btn = Gtk.Button(label=_t("rc.record"))
        self.rec_btn.get_style_context().add_class("rec-go")
        self.rec_btn.connect("clicked", self._toggle_record)
        ctr.pack_start(self.rec_btn, False, False, 0)
        self.play_btn = Gtk.Button(label=_t("rc.replay"))
        self.play_btn.set_sensitive(False)
        self.play_btn.connect("clicked", self._play_last)
        ctr.pack_start(self.play_btn, False, False, 0)
        open_btn = Gtk.Button(label=_t("rc.folder"))
        open_btn.connect("clicked", self._open_folder)
        ctr.pack_end(open_btn, False, False, 0)
        root.pack_start(ctr, False, False, 0)

        self.status = Gtk.Label(label=_t("rc.ready_hint"))
        self.status.set_xalign(0)
        self.status.get_style_context().add_class("rec-sub")
        root.pack_start(self.status, False, False, 0)

        self.connect("destroy", self._on_destroy)
        self.show_all()

        # Ridisegno periodico. La cattura dal microfono parte SOLO durante la
        # registrazione: cosi' l'onda si ferma allo Stop (non scorre col rumore
        # ambientale), il mic e' usato solo quando serve (privacy) e l'applet
        # microfono della barra compare on-demand mentre registri.
        GLib.timeout_add(33, self._tick)          # ~30 fps
        GLib.timeout_add(250, self._tick_time)

    # -------------------------------------------------- cattura
    def _cap_loop(self):
        cmd = ["arecord", "-q", "-f", "S16_LE", "-c", str(CH),
               "-r", str(RATE), "-t", "raw"]
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL)
        except (OSError, FileNotFoundError):
            GLib.idle_add(self._no_mic)
            return
        nbytes = CHUNK * BYTES
        # Gira SOLO durante la registrazione: quando recording diventa False (o
        # alla chiusura) il loop esce, chiude il WAV e ferma arecord.
        while not self._stop and self.recording:
            data = self.proc.stdout.read(nbytes)
            if not data:
                break
            cnt = len(data) // 2
            if cnt:
                vals = struct.unpack("<%dh" % cnt, data[:cnt * 2])
                peak = max((abs(v) for v in vals), default=0) / 32768.0
                new = _spectrum(vals)
                self.bands = [max(new[i], self.bands[i] * _FALL)
                              for i in range(NBANDS)]
                self.levels.append(peak)          # storia per la modalita' Onda
                if len(self.levels) > NBARS:
                    self.levels.pop(0)
            else:
                peak = 0.0
            self.peak = peak
            if self.wav is not None:
                try:
                    self.wav.writeframes(data)
                    self.frames += cnt
                except Exception:          # noqa: BLE001
                    pass
        # Fine cattura: spettro e livello a riposo, WAV finalizzato, arecord chiuso.
        self.bands = [0.0] * NBANDS
        self.peak = 0.0
        try:
            if self.wav:
                self.wav.close()
        except Exception:                  # noqa: BLE001
            pass
        self.wav = None
        try:
            if self.proc:
                self.proc.terminate()
        except Exception:                  # noqa: BLE001
            pass
        self.proc = None

    def _no_mic(self):
        # arecord non parte: ripristina lo stato "non in registrazione".
        self.recording = False
        self.rec_btn.set_label(_t("rc.record"))
        self.rec_btn.get_style_context().remove_class("rec-stop")
        self.rec_btn.get_style_context().add_class("rec-go")
        self.status.set_text(_t("rc.nomic"))
        try:
            if self.wav:
                self.wav.close()
        except Exception:                  # noqa: BLE001
            pass
        self.wav = None
        return False

    def _on_viz(self, btn, mode):
        """Selettore Spettro/Onda: uno solo attivo, mai entrambi spenti."""
        if self._viz_guard:
            return
        self._viz_guard = True
        if btn.get_active():
            self.viz = mode
            self.btn_spec.set_active(mode == "spec")
            self.btn_wave.set_active(mode == "wave")
        else:
            (self.btn_spec if self.viz == "spec" else self.btn_wave).set_active(True)
        self._viz_guard = False

    # -------------------------------------------------- disegno
    def _tick(self):
        self.canvas.queue_draw()
        self.level.set_value(min(1.0, self.peak))
        return True

    def _tick_time(self):
        if self.recording:
            el = int(GLib.get_monotonic_time() / 1e6 - self._start_mono)
            self.time_lbl.set_text("%02d:%02d" % (el // 60, el % 60))
        return True

    @staticmethod
    def _rrect(cr, x, y, w, h, r):
        """Sub-path rettangolo ad angoli arrotondati."""
        r = min(r, w / 2.0, h / 2.0)
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
        cr.close_path()

    def _on_draw(self, area, cr):
        w = area.get_allocated_width()
        h = area.get_allocated_height()
        mid = h / 2.0
        # Fondo con leggera sfumatura verticale.
        bg = cairo.LinearGradient(0, 0, 0, h)
        bg.add_color_stop_rgb(0, 0.03, 0.06, 0.11)
        bg.add_color_stop_rgb(1, GROUND[0], GROUND[1], GROUND[2])
        cr.set_source(bg); cr.paint()

        # Colore per stato: registrazione = rosa allarme, altrimenti accent.
        r, g, b = ALARM if self.recording else ACCENT
        amp = h * 0.46
        grad = cairo.LinearGradient(0, mid - amp, 0, mid + amp)
        grad.add_color_stop_rgba(0.0, r, g, b, 0.95)
        grad.add_color_stop_rgba(0.5, r, g, b, 0.45)
        grad.add_color_stop_rgba(1.0, r, g, b, 0.95)
        if self.viz == "wave":
            # Onda (ampiezza): envelope speculare riempito.
            lv = self.levels
            m = len(lv)
            if m >= 2:
                step = w / float(m - 1)
                cr.new_path()
                cr.move_to(0, mid - lv[0] * amp)
                for i in range(1, m):
                    cr.line_to(i * step, mid - lv[i] * amp)
                for i in range(m - 1, -1, -1):
                    cr.line_to(i * step, mid + lv[i] * amp)
                cr.close_path()
                cr.set_source(grad); cr.fill_preserve()
                cr.set_source_rgba(r, g, b, 0.95); cr.set_line_width(1.2); cr.stroke()
        else:
            # Spettro (frequenze): barre per banda, speculari attorno al centro.
            n = NBANDS
            gap = 3.0
            bw = (w - gap * (n + 1)) / n
            if bw < 1:
                bw = 1
            cr.new_path()
            for i in range(n):
                val = self.bands[i] if i < len(self.bands) else 0.0
                bh = max(2.0, val * amp)
                x = gap + i * (bw + gap)
                self._rrect(cr, x, mid - bh, bw, bh * 2.0, min(bw * 0.45, 4.0))
            cr.set_source(grad); cr.fill()
        # Linea centrale sottile.
        cr.set_source_rgba(DIM[0], DIM[1], DIM[2], 0.35)
        cr.set_line_width(1)
        cr.move_to(0, mid); cr.line_to(w, mid); cr.stroke()
        return False

    # -------------------------------------------------- record / play
    def _toggle_record(self, _b):
        if self.recording:
            # Stop: basta azzerare recording -> _cap_loop esce, chiude il WAV e
            # ferma arecord; l'onda resta ferma sull'ultimo tracciato.
            self.recording = False
            self.rec_btn.set_label(_t("rc.record"))
            self.rec_btn.get_style_context().remove_class("rec-stop")
            self.rec_btn.get_style_context().add_class("rec-go")
            if self.last_file:
                self.play_btn.set_sensitive(True)
                self.status.set_text(_t("rc.saved") % self.last_file)
            return
        # start
        try:
            os.makedirs(OUTDIR, exist_ok=True)
            path = os.path.join(
                OUTDIR, "rec-%s.wav" % datetime.now().strftime("%Y%m%d-%H%M%S"))
            w = wave.open(path, "wb")
            w.setnchannels(CH); w.setsampwidth(BYTES); w.setframerate(RATE)
            self.wav = w
            self.last_file = path
            self.frames = 0
            self.bands = [0.0] * NBANDS            # spettro pulito per la sessione
            self.peak = 0.0
            self._stop = False
            self.playing = False                   # una registrazione ferma l'ascolto
            try:
                if self._play_proc and self._play_proc.poll() is None:
                    self._play_proc.terminate()
            except Exception:                      # noqa: BLE001
                pass
            self._start_mono = GLib.get_monotonic_time() / 1e6
            self.recording = True
            self.time_lbl.set_text("00:00")
            self.rec_btn.set_label(_t("rc.stop"))
            self.rec_btn.get_style_context().remove_class("rec-go")
            self.rec_btn.get_style_context().add_class("rec-stop")
            self.status.set_text(_t("rc.recording"))
            threading.Thread(target=self._cap_loop, daemon=True).start()
        except Exception as e:             # noqa: BLE001
            self.status.set_text(_t("rc.rec_fail") % e)

    def _play_last(self, _b):
        if self.recording:
            return
        if self.playing:                     # gia' in riproduzione -> STOP
            self._stop_play()
            return
        if not self.last_file or not os.path.exists(self.last_file):
            return
        # Precalcola lo spettro per finestre CHUNK dal WAV (mono S16), cosi' in
        # riascolto la banda si muove come in registrazione, sincronizzata.
        try:
            wf = wave.open(self.last_file, "rb")
            rate = wf.getframerate() or RATE
            raw = wf.readframes(wf.getnframes())
            wf.close()
        except Exception as e:              # noqa: BLE001
            self.status.set_text(_t("rc.read_fail") % e)
            return
        total = len(raw) // 2
        bands = []
        peaks = []
        i = 0
        while i < total:
            seg = raw[i * 2:(i + CHUNK) * 2]
            cnt = len(seg) // 2
            if cnt:
                vals = struct.unpack("<%dh" % cnt, seg[:cnt * 2])
                bands.append(_spectrum(vals))
                peaks.append(max((abs(v) for v in vals), default=0) / 32768.0)
            else:
                bands.append([0.0] * NBANDS)
                peaks.append(0.0)
            i += CHUNK
        self._play_bands = bands
        self._play_peaks = peaks
        self._play_rate = rate
        self._play_dur = total / float(rate)
        self.bands = [0.0] * NBANDS
        self.levels = [0.0] * NBARS
        try:
            self._play_proc = subprocess.Popen(["aplay", "-q", self.last_file],
                                               stderr=subprocess.DEVNULL)
        except (OSError, FileNotFoundError):
            self.status.set_text(_t("rc.noaplay"))
            return
        self.playing = True
        self.play_btn.set_label(_t("rc.stop"))   # il pulsante diventa Stop
        self._play_start = GLib.get_monotonic_time() / 1e6
        self.status.set_text(_t("rc.playing") % os.path.basename(self.last_file))
        GLib.timeout_add(33, self._play_tick)

    def _stop_play(self):
        """Ferma la riproduzione (pulsante Stop o fine file) e ripristina il
        pulsante a 'Riascolta'."""
        self.playing = False
        proc = getattr(self, "_play_proc", None)
        if proc is not None:
            try:
                proc.terminate()
            except Exception:                # noqa: BLE001
                pass
            self._play_proc = None
        self.bands = [0.0] * NBANDS
        self.peak = 0.0
        self.play_btn.set_label(_t("rc.replay"))
        self.status.set_text(_t("rc.ready"))

    def _play_tick(self):
        if not self.playing:
            return False
        el = GLib.get_monotonic_time() / 1e6 - self._play_start
        done = (self._play_proc is not None and self._play_proc.poll() is not None)
        if el >= self._play_dur or done:
            self._stop_play()                # fine file: ripristina il pulsante
            return False
        chunk_dur = CHUNK / float(getattr(self, "_play_rate", RATE))
        idx = int(el / chunk_dur)
        if 0 <= idx < len(self._play_bands):
            new = self._play_bands[idx]
            self.bands = [max(new[i], self.bands[i] * _FALL) for i in range(NBANDS)]
            # finestra scorrevole dei picchi per la modalita' Onda
            lo = max(0, idx - NBARS + 1)
            win = self._play_peaks[lo:idx + 1]
            self.levels = [0.0] * (NBARS - len(win)) + list(win)
            self.peak = self._play_peaks[idx]
        return True

    def _open_folder(self, _b):
        try:
            os.makedirs(OUTDIR, exist_ok=True)
            # il file manager di Vesper; se manca, quello del sistema
            for cmd in (["vesper-files", OUTDIR], ["xdg-open", OUTDIR]):
                try:
                    subprocess.Popen(cmd, stderr=subprocess.DEVNULL)
                    break
                except (OSError, FileNotFoundError):
                    continue
            else:
                self.status.set_text(_t("rc.folder_path") % OUTDIR)
        except OSError:
            self.status.set_text(_t("rc.folder_path") % OUTDIR)

    def _on_destroy(self, _w):
        self._stop = True
        self.recording = False
        try:
            if self.recording and self.wav:
                self.wav.close()
        except Exception:                  # noqa: BLE001
            pass
        try:
            if self.proc:
                self.proc.terminate()
        except Exception:                  # noqa: BLE001
            pass
        Gtk.main_quit()


def main():
    Recorder()
    Gtk.main()


if __name__ == "__main__":
    main()
