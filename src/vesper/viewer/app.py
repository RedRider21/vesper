# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Visualizzatore di immagini di Vesper - GTK3 + GdkPixbuf.

Quello che serve davvero guardando le foto: sfogliare la cartella, zoom,
rotazione, schermo intero, presentazione, e le due cose che su un desktop
fanno comodo per davvero - «imposta come sfondo» e il cestino.

L'immagine la disegna Cairo su una DrawingArea: lo zoom resta nitido, la
rotazione non costa nulla e la trasparenza si vede sulla scacchiera come in
qualunque editor. Le GIF animate scorrono (GdkPixbufAnimation).
"""
import os
import subprocess
import sys

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, Gio, GLib, GdkPixbuf, Pango  # noqa: E402

try:
    from vesper.common import apply_css
except Exception:                                   # noqa: BLE001
    def apply_css():
        return

try:
    from vesper.i18n import t as _t, taccel as _ta
except Exception:                                   # noqa: BLE001
    def _t(chiave, **kw):                           # ripiego: mostra la chiave
        return chiave

    def _ta(etichetta):
        return etichetta

APP_NAME = _t("iv.app")

# Estensioni riconosciute: quelle che GdkPixbuf sa caricare quasi ovunque.
ESTENSIONI = (".png", ".jpg", ".jpeg", ".jpe", ".gif", ".bmp", ".webp",
              ".tif", ".tiff", ".ico", ".xpm", ".pnm", ".ppm", ".pgm",
              ".svg", ".avif", ".jxl", ".heif", ".heic")

ZOOM_MIN, ZOOM_MAX = 0.02, 40.0
PASSI_ZOOM = 1.25


def _accento() -> str:
    try:
        from vesper.profiles import model
        ac = model.accent()
        if isinstance(ac, str) and ac.startswith("#") and len(ac) == 7:
            return ac
    except Exception:                               # noqa: BLE001
        pass
    return "#00e5ff"


def _rgb(colore: str):
    h = colore.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _chiaro() -> bool:
    try:
        from vesper import palette
        return palette.is_light()
    except Exception:                               # noqa: BLE001
        return False


def _peso(byte: float) -> str:
    for unita in ("B", "kB", "MB", "GB"):
        if byte < 1024 or unita == "GB":
            return ("%.0f %s" if unita == "B" else "%.1f %s") % (byte, unita)
        byte /= 1024
    return ""


def immagini_in(cartella: str) -> list:
    """Le immagini di una cartella, in ordine come le mostra il file manager."""
    try:
        nomi = [n for n in os.listdir(cartella)
                if n.lower().endswith(ESTENSIONI)
                and os.path.isfile(os.path.join(cartella, n))]
    except OSError:
        return []
    nomi.sort(key=lambda n: n.lower())
    return [os.path.join(cartella, n) for n in nomi]


class Visualizzatore(Gtk.Window):

    def __init__(self, percorsi=None):
        super().__init__(title=APP_NAME)
        self.set_default_size(980, 700)
        self.set_icon_name("multimedia-photo-viewer")
        apply_css()

        self.elenco = []            # immagini della cartella corrente
        self.indice = -1
        self.pixbuf = None          # immagine a dimensione piena
        self.animazione = None      # GdkPixbufAnimation per le GIF
        self.iter_anim = None
        self.timer_anim = None
        self.zoom = 1.0
        self.adatta = True          # zoom automatico alla finestra
        self.rotazione = 0          # gradi, multipli di 90
        self.offset = [0.0, 0.0]    # spostamento quando l'immagine è più grande
        self.trascino = None
        self.presentazione = None
        self.pausa_presentazione = 4
        self._zoom_mostrato = -1

        radice = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(radice)
        radice.pack_start(self._barra(), False, False, 0)

        self.tela = Gtk.DrawingArea()
        self.tela.add_events(Gdk.EventMask.BUTTON_PRESS_MASK
                             | Gdk.EventMask.BUTTON_RELEASE_MASK
                             | Gdk.EventMask.POINTER_MOTION_MASK
                             | Gdk.EventMask.SCROLL_MASK
                             | Gdk.EventMask.SMOOTH_SCROLL_MASK)
        self.tela.connect("draw", self._disegna)
        self.tela.connect("button-press-event", self._premuto)
        self.tela.connect("button-release-event", self._rilasciato)
        self.tela.connect("motion-notify-event", self._mosso)
        self.tela.connect("scroll-event", self._rotella)
        radice.pack_start(self.tela, True, True, 0)

        radice.pack_start(self._stato(), False, False, 0)

        self._accel()
        self.connect("key-press-event", self._tasti)
        self.connect("destroy", lambda _w: Gtk.main_quit())
        self.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self.drag_dest_add_uri_targets()
        self.connect("drag-data-received", self._trascinati)

        self.apri(percorsi[0] if percorsi else None)
        self.show_all()

    # --- interfaccia -----------------------------------------------------
    def _bottone(self, icona, tooltip, callback):
        b = Gtk.Button(relief=Gtk.ReliefStyle.NONE)
        b.add(Gtk.Image.new_from_icon_name(icona, Gtk.IconSize.LARGE_TOOLBAR))
        b.set_tooltip_text(tooltip)
        b.set_focus_on_click(False)
        b.connect("clicked", lambda _b: callback())
        return b

    def _barra(self):
        barra = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        barra.set_border_width(4)
        for icona, testo, cb in (
                ("document-open-symbolic", _t("iv.tt.open"), self.apri_dialogo),
                ("go-previous-symbolic", _t("iv.tt.prev"), self.precedente),
                ("go-next-symbolic", _t("iv.tt.next"), self.successiva),
                ("zoom-out-symbolic", _t("iv.tt.zoomout"),
                 lambda: self.cambia_zoom(1 / PASSI_ZOOM)),
                ("zoom-fit-best-symbolic", _t("iv.tt.fit"),
                 self.adatta_finestra),
                ("zoom-original-symbolic", _t("iv.tt.real"),
                 self.dimensione_reale),
                ("zoom-in-symbolic", _t("iv.tt.zoomin"),
                 lambda: self.cambia_zoom(PASSI_ZOOM)),
                ("object-rotate-left-symbolic", _t("iv.tt.rotleft"),
                 lambda: self.ruota(-90)),
                ("object-rotate-right-symbolic", _t("iv.tt.rotright"),
                 lambda: self.ruota(90)),
                ("view-fullscreen-symbolic", _t("iv.tt.full"),
                 self.schermo_intero),
                ("media-playback-start-symbolic", _t("iv.tt.slideshow"),
                 self.presenta)):
            barra.pack_start(self._bottone(icona, testo, cb), False, False, 0)

        menu_b = Gtk.MenuButton()
        menu_b.set_relief(Gtk.ReliefStyle.NONE)
        menu_b.add(Gtk.Image.new_from_icon_name("open-menu-symbolic",
                                                Gtk.IconSize.LARGE_TOOLBAR))
        menu_b.set_tooltip_text(_t("iv.options"))
        menu_b.set_popup(self._menu())
        barra.pack_end(menu_b, False, False, 0)
        return barra

    def _voce(self, menu, etichetta, callback, scorciatoia=""):
        it = Gtk.MenuItem()
        riga = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        lab = Gtk.Label(label=etichetta); lab.set_xalign(0)
        riga.pack_start(lab, True, True, 0)
        if scorciatoia:
            acc = Gtk.Label(label=_ta(scorciatoia))
            acc.get_style_context().add_class("vesper-val")
            riga.pack_end(acc, False, False, 0)
        it.add(riga)
        it.connect("activate", lambda _i: callback())
        menu.append(it)

    def _menu(self):
        m = Gtk.Menu()
        self._voce(m, _t("iv.wallpaper"), self.come_sfondo, "Ctrl+B")
        self._voce(m, _t("iv.openfolder"), self.apri_cartella, "Ctrl+E")
        self._voce(m, _t("iv.copy"), self.copia, "Ctrl+C")
        m.append(Gtk.SeparatorMenuItem())
        self._voce(m, _t("iv.trash"), self.cestina, "Canc")
        self._voce(m, _t("iv.props"), self.proprieta, "Ctrl+I")
        m.append(Gtk.SeparatorMenuItem())
        self._voce(m, _t("iv.shortcuts"), self.mostra_scorciatoie,
                   "Ctrl+Maiusc+H")
        self._voce(m, _t("iv.close"), lambda: self.destroy(), "Ctrl+Q")
        m.show_all()
        return m

    def _stato(self):
        barra = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        barra.set_border_width(4)
        self.lbl_nome = Gtk.Label(label="")
        self.lbl_nome.set_xalign(0)
        self.lbl_nome.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        barra.pack_start(self.lbl_nome, True, True, 0)
        self.lbl_info = Gtk.Label(label="")
        self.lbl_info.get_style_context().add_class("vesper-val")
        barra.pack_end(self.lbl_info, False, False, 0)
        return barra

    # --- caricamento ------------------------------------------------------
    def apri(self, percorso):
        """Apre un file (e sfoglia la sua cartella) oppure una cartella."""
        if not percorso:
            self._aggiorna_stato()
            return
        percorso = os.path.abspath(os.path.expanduser(percorso))
        if os.path.isdir(percorso):
            self.elenco = immagini_in(percorso)
            self.indice = 0 if self.elenco else -1
        else:
            self.elenco = immagini_in(os.path.dirname(percorso)) or [percorso]
            try:
                self.indice = self.elenco.index(percorso)
            except ValueError:
                self.elenco = [percorso]
                self.indice = 0
        self.carica()

    def carica(self):
        self._ferma_animazione()
        if not (0 <= self.indice < len(self.elenco)):
            self.pixbuf = None
            self._aggiorna_stato()
            self.tela.queue_draw()
            return
        percorso = self.elenco[self.indice]
        try:
            if percorso.lower().endswith(".gif"):
                self.animazione = GdkPixbuf.PixbufAnimation.new_from_file(percorso)
                if self.animazione.is_static_image():
                    self.pixbuf = self.animazione.get_static_image()
                    self.animazione = None
                else:
                    self.iter_anim = self.animazione.get_iter(None)
                    self.pixbuf = self.iter_anim.get_pixbuf()
                    self._prossimo_fotogramma()
            else:
                self.pixbuf = GdkPixbuf.Pixbuf.new_from_file(percorso)
        except GLib.Error as e:
            self.pixbuf = None
            self.lbl_nome.set_text(_t("iv.cantopen")
                                   % (os.path.basename(percorso), e.message))
        self.rotazione = 0
        self.offset = [0.0, 0.0]
        self.adatta = True
        self._aggiorna_stato()
        self.tela.queue_draw()

    def _prossimo_fotogramma(self):
        """Fa scorrere una GIF: si riarma da sola col ritardo del fotogramma."""
        if self.iter_anim is None:
            return False
        ritardo = self.iter_anim.get_delay_time()
        self.timer_anim = GLib.timeout_add(max(20, ritardo), self._avanza_gif)
        return False

    def _avanza_gif(self):
        if self.iter_anim is None:
            return False
        self.iter_anim.advance(None)
        self.pixbuf = self.iter_anim.get_pixbuf()
        self.tela.queue_draw()
        self._prossimo_fotogramma()
        return False

    def _ferma_animazione(self):
        if self.timer_anim:
            GLib.source_remove(self.timer_anim)
        self.timer_anim = None
        self.iter_anim = None
        self.animazione = None

    # --- disegno ----------------------------------------------------------
    def _misure(self):
        """(larghezza, altezza) dell'immagine tenendo conto della rotazione."""
        if self.pixbuf is None:
            return 0, 0
        w, h = self.pixbuf.get_width(), self.pixbuf.get_height()
        return (h, w) if self.rotazione % 180 else (w, h)

    def _zoom_effettivo(self):
        if not self.adatta:
            return self.zoom
        iw, ih = self._misure()
        if not iw or not ih:
            return 1.0
        a = self.tela.get_allocation()
        scala = min(a.width / iw, a.height / ih)
        return min(scala, 1.0) if scala > 0 else 1.0   # non ingrandire da sola

    def _disegna(self, _w, cr):
        a = self.tela.get_allocation()
        fondo = (0.96, 0.97, 0.98) if _chiaro() else (0.03, 0.05, 0.08)
        cr.set_source_rgb(*fondo)
        cr.paint()
        if self.pixbuf is None:
            self._disegna_vuoto(cr, a)
            return False
        scala = self._zoom_effettivo()
        iw, ih = self._misure()
        dw, dh = iw * scala, ih * scala
        x = (a.width - dw) / 2 + self.offset[0]
        y = (a.height - dh) / 2 + self.offset[1]
        # scacchiera sotto le immagini con trasparenza
        if self.pixbuf.get_has_alpha():
            self._scacchiera(cr, x, y, dw, dh)
        cr.save()
        cr.translate(x + dw / 2, y + dh / 2)
        cr.rotate(self.rotazione * 3.141592653589793 / 180)
        cr.scale(scala, scala)
        w, h = self.pixbuf.get_width(), self.pixbuf.get_height()
        Gdk.cairo_set_source_pixbuf(cr, self.pixbuf, -w / 2, -h / 2)
        cr.get_source().set_filter(1 if scala >= 1 else 2)   # nitido / morbido
        cr.paint()
        cr.restore()
        if round(scala * 100) != self._zoom_mostrato:
            self._zoom_mostrato = round(scala * 100)
            self._aggiorna_stato()
        return False

    @staticmethod
    def _scacchiera(cr, x, y, w, h):
        cr.save()
        cr.rectangle(x, y, w, h)
        cr.clip()
        passo = 12
        cr.set_source_rgb(0.82, 0.84, 0.86)
        cr.rectangle(x, y, w, h)
        cr.fill()
        cr.set_source_rgb(0.72, 0.74, 0.77)
        riga = 0
        py = y
        while py < y + h:
            px = x + (passo if riga % 2 else 0)
            while px < x + w:
                cr.rectangle(px, py, passo, passo)
                px += passo * 2
            cr.fill()
            py += passo
            riga += 1
        cr.restore()

    def _disegna_vuoto(self, cr, a):
        cr.set_source_rgb(*_rgb(_accento()))
        cr.set_line_width(2)
        lato = 96
        x, y = (a.width - lato) / 2, (a.height - lato) / 2 - 20
        cr.rectangle(x, y, lato, lato * 0.72)
        cr.stroke()
        cr.arc(x + lato * 0.28, y + lato * 0.22, 7, 0, 6.2831853)
        cr.stroke()
        cr.move_to(x + 8, y + lato * 0.66)
        cr.line_to(x + lato * 0.42, y + lato * 0.3)
        cr.line_to(x + lato * 0.72, y + lato * 0.66)
        cr.stroke()
        cr.select_font_face("Sans")
        cr.set_font_size(14)
        testo = _t("iv.drophere")
        est = cr.text_extents(testo)
        cr.move_to((a.width - est.width) / 2, y + lato + 26)
        cr.show_text(testo)

    # --- interazione col mouse -------------------------------------------
    def _premuto(self, _w, ev):
        if ev.type == Gdk.EventType._2BUTTON_PRESS and ev.button == 1:
            self.schermo_intero()
            return True
        if ev.button == 1:
            self.trascino = (ev.x, ev.y, self.offset[0], self.offset[1])
        elif ev.button == 3:
            self._menu().popup_at_pointer(ev)
        elif ev.button == 8:                        # tasti laterali del mouse
            self.precedente()
        elif ev.button == 9:
            self.successiva()
        return True

    def _rilasciato(self, _w, _ev):
        self.trascino = None
        return True

    def _mosso(self, _w, ev):
        if not self.trascino or self.pixbuf is None:
            return False
        x0, y0, ox, oy = self.trascino
        self.adatta = False if self._zoom_effettivo() > self._adattamento() else self.adatta
        self.offset = [ox + (ev.x - x0), oy + (ev.y - y0)]
        self._limita_offset()
        self.tela.queue_draw()
        return True

    def _rotella(self, _w, ev):
        su = ev.direction == Gdk.ScrollDirection.UP or \
            (ev.direction == Gdk.ScrollDirection.SMOOTH and ev.delta_y < 0)
        giu = ev.direction == Gdk.ScrollDirection.DOWN or \
            (ev.direction == Gdk.ScrollDirection.SMOOTH and ev.delta_y > 0)
        if ev.state & Gdk.ModifierType.CONTROL_MASK:
            if su:
                self.cambia_zoom(PASSI_ZOOM)
            elif giu:
                self.cambia_zoom(1 / PASSI_ZOOM)
        else:
            if su:
                self.precedente()
            elif giu:
                self.successiva()
        return True

    def _adattamento(self):
        """Lo zoom che l'immagine avrebbe in modalità «adatta»."""
        iw, ih = self._misure()
        if not iw or not ih:
            return 1.0
        a = self.tela.get_allocation()
        return min(min(a.width / iw, a.height / ih), 1.0)

    def _limita_offset(self):
        """Niente immagine trascinata fuori dallo schermo: se ci sta tutta,
        resta centrata."""
        scala = self._zoom_effettivo()
        iw, ih = self._misure()
        a = self.tela.get_allocation()
        for asse, (dim, vista) in enumerate(((iw * scala, a.width),
                                             (ih * scala, a.height))):
            margine = max(0.0, (dim - vista) / 2)
            self.offset[asse] = max(-margine, min(margine, self.offset[asse]))

    # --- zoom, rotazione, navigazione ------------------------------------
    def cambia_zoom(self, fattore):
        if self.pixbuf is None:
            return
        base = self._zoom_effettivo()
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, base * fattore))
        self.adatta = False
        self._limita_offset()
        self._aggiorna_stato()
        self.tela.queue_draw()

    def adatta_finestra(self):
        self.adatta = True
        self.offset = [0.0, 0.0]
        self._aggiorna_stato()
        self.tela.queue_draw()

    def dimensione_reale(self):
        self.zoom = 1.0
        self.adatta = False
        self.offset = [0.0, 0.0]
        self._aggiorna_stato()
        self.tela.queue_draw()

    def ruota(self, gradi):
        if self.pixbuf is None:
            return
        self.rotazione = (self.rotazione + gradi) % 360
        self.offset = [0.0, 0.0]
        self.tela.queue_draw()

    def successiva(self):
        if len(self.elenco) > 1:
            self.indice = (self.indice + 1) % len(self.elenco)
            self.carica()

    def precedente(self):
        if len(self.elenco) > 1:
            self.indice = (self.indice - 1) % len(self.elenco)
            self.carica()

    def prima(self):
        if self.elenco:
            self.indice = 0
            self.carica()

    def ultima(self):
        if self.elenco:
            self.indice = len(self.elenco) - 1
            self.carica()

    def schermo_intero(self):
        finestra = self.get_window()
        if finestra and (finestra.get_state() & Gdk.WindowState.FULLSCREEN):
            self.unfullscreen()
        else:
            self.fullscreen()

    def presenta(self):
        """Avvia o ferma la presentazione (un'immagine ogni N secondi)."""
        if self.presentazione:
            GLib.source_remove(self.presentazione)
            self.presentazione = None
            self._aggiorna_stato()
            return
        self.fullscreen()

        def passa():
            self.successiva()
            return True
        self.presentazione = GLib.timeout_add_seconds(self.pausa_presentazione,
                                                      passa)
        self._aggiorna_stato()

    # --- azioni sul file --------------------------------------------------
    def percorso(self):
        return self.elenco[self.indice] if 0 <= self.indice < len(self.elenco) \
            else None

    def apri_dialogo(self):
        dlg = Gtk.FileChooserDialog(title=_t("iv.open"), transient_for=self,
                                    action=Gtk.FileChooserAction.OPEN)
        dlg.add_buttons(_t("iv.cancel"), Gtk.ResponseType.CANCEL,
                        _t("iv.openbtn"), Gtk.ResponseType.ACCEPT)
        f = Gtk.FileFilter(); f.set_name(_t("iv.app"))
        f.add_pixbuf_formats()
        dlg.add_filter(f)
        attuale = self.percorso()
        if attuale:
            dlg.set_current_folder(os.path.dirname(attuale))
        if dlg.run() == Gtk.ResponseType.ACCEPT:
            scelto = dlg.get_filename()
            dlg.destroy()
            self.apri(scelto)
            return
        dlg.destroy()

    def come_sfondo(self):
        p = self.percorso()
        if not p:
            return
        try:
            subprocess.Popen(["vesper-wallpaper", "set", p],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            self.messaggio(_t("iv.wallpaper_done"))
        except OSError as e:
            self.messaggio(_t("iv.wallpaper_fail") % e)

    def apri_cartella(self):
        p = self.percorso()
        if p:
            try:
                subprocess.Popen(["vesper-files", os.path.dirname(p)],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            except OSError:
                pass

    def copia(self):
        if self.pixbuf is None:
            return
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_image(self.pixbuf)
        self.messaggio(_t("iv.copied"))

    def cestina(self):
        p = self.percorso()
        if not p:
            return
        d = Gtk.MessageDialog(transient_for=self, modal=True,
                              message_type=Gtk.MessageType.QUESTION,
                              buttons=Gtk.ButtonsType.OK_CANCEL,
                              text=_t("iv.trash_q")
                                   % os.path.basename(p))
        risposta = d.run()
        d.destroy()
        if risposta != Gtk.ResponseType.OK:
            return
        try:
            Gio.File.new_for_path(p).trash(None)
        except GLib.Error as e:
            self.messaggio(_t("iv.trash_fail") % e.message)
            return
        del self.elenco[self.indice]
        if self.indice >= len(self.elenco):
            self.indice = len(self.elenco) - 1
        self.carica()

    def proprieta(self):
        p = self.percorso()
        if not p or self.pixbuf is None:
            return
        try:
            st = os.stat(p)
            peso, quando = _peso(st.st_size), GLib.DateTime.new_from_unix_local(
                int(st.st_mtime)).format("%d/%m/%Y %H:%M")
        except OSError:
            peso, quando = "?", "?"
        righe = [(_t("iv.p.name"), os.path.basename(p)),
                 (_t("iv.p.folder"), os.path.dirname(p)),
                 (_t("iv.p.size"), _t("iv.p.pixels") % (self.pixbuf.get_width(),
                                                   self.pixbuf.get_height())),
                 (_t("iv.p.weight"), peso), (_t("iv.p.changed"), quando),
                 (_t("iv.p.alpha"), _t("iv.yes") if self.pixbuf.get_has_alpha() else _t("iv.no"))]
        dlg = Gtk.Dialog(title=_t("iv.props"), transient_for=self, modal=True)
        dlg.add_button(_t("iv.close"), Gtk.ResponseType.CLOSE)
        griglia = Gtk.Grid(column_spacing=16, row_spacing=6)
        griglia.set_border_width(14)
        for r, (k, v) in enumerate(righe):
            a = Gtk.Label(label=k); a.set_xalign(0)
            a.get_style_context().add_class("vesper-key")
            b = Gtk.Label(label=v); b.set_xalign(0); b.set_selectable(True)
            b.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            griglia.attach(a, 0, r, 1, 1)
            griglia.attach(b, 1, r, 1, 1)
        dlg.get_content_area().add(griglia)
        dlg.show_all()
        dlg.run()
        dlg.destroy()

    # --- stato ------------------------------------------------------------
    def messaggio(self, testo):
        self.lbl_info.set_text(testo)
        GLib.timeout_add_seconds(4, lambda: (self._aggiorna_stato(), False)[1])

    def _aggiorna_stato(self):
        p = self.percorso()
        if not p:
            self.set_title(APP_NAME)
            self.lbl_nome.set_text(_t("iv.none"))
            self.lbl_info.set_text("")
            return False
        nome = os.path.basename(p)
        self.set_title("%s - %s" % (nome, APP_NAME))
        posizione = (_t("iv.counter") % (self.indice + 1, len(self.elenco))
                     if len(self.elenco) > 1 else "")
        self.lbl_nome.set_text(posizione + nome)
        if self.pixbuf is not None:
            try:
                peso = _peso(os.path.getsize(p))
            except OSError:
                peso = "?"
            pezzi = ["%d x %d" % (self.pixbuf.get_width(),
                                  self.pixbuf.get_height()),
                     peso, "%d%%" % round(self._zoom_effettivo() * 100)]
            if self.presentazione:
                pezzi.append(_t("iv.slideshow"))
            self.lbl_info.set_text("   ".join(pezzi))
        return False

    def _trascinati(self, _w, ctx, _x, _y, dati, _info, ora):
        for uri in (dati.get_uris() or []):
            percorso = Gio.File.new_for_uri(uri).get_path()
            if percorso:
                self.apri(percorso)
                break
        Gtk.drag_finish(ctx, True, False, ora)

    # --- scorciatoie ------------------------------------------------------
    # Una lista sola per acceleratori e finestra d'aiuto, come nell'editor.
    def _elenco_scorciatoie(self):
        C = Gdk.ModifierType.CONTROL_MASK
        S = Gdk.ModifierType.SHIFT_MASK
        return [
            (_t("iv.g.browse"), [
                ("o", C, "Ctrl+O", _t("iv.open"), self.apri_dialogo),
                ("Page_Down", 0, "PagGiù", _t("iv.a.next"), self.successiva),
                ("Page_Up", 0, "PagSu", _t("iv.a.prev"), self.precedente),
                ("space", 0, "Spazio", _t("iv.a.next"), self.successiva),
                ("BackSpace", 0, "Backspace", _t("iv.a.prev"),
                 self.precedente),
                ("Home", 0, "Inizio", _t("iv.a.first"), self.prima),
                ("End", 0, "Fine", _t("iv.a.last"), self.ultima),
            ]),
            (_t("iv.g.see"), [
                ("plus", C, "Ctrl++", _t("iv.a.zoomin"),
                 lambda: self.cambia_zoom(PASSI_ZOOM)),
                ("equal", C, "Ctrl+=", _t("iv.a.zoomin"),
                 lambda: self.cambia_zoom(PASSI_ZOOM)),
                ("minus", C, "Ctrl+-", _t("iv.a.zoomout"),
                 lambda: self.cambia_zoom(1 / PASSI_ZOOM)),
                ("0", C, "Ctrl+0", _t("iv.a.fit"), self.adatta_finestra),
                ("1", C, "Ctrl+1", _t("iv.a.real"), self.dimensione_reale),
                ("r", C, "Ctrl+R", _t("iv.a.rotright"), lambda: self.ruota(90)),
                ("r", C | S, "Ctrl+Maiusc+R", _t("iv.a.rotleft"),
                 lambda: self.ruota(-90)),
                ("F11", 0, "F11", _t("iv.a.full"), self.schermo_intero),
                ("F5", 0, "F5", _t("iv.a.slideshow"), self.presenta),
            ]),
            (_t("iv.g.do"), [
                ("b", C, "Ctrl+B", _t("iv.wallpaper"), self.come_sfondo),
                ("e", C, "Ctrl+E", _t("iv.openfolder"), self.apri_cartella),
                ("c", C, "Ctrl+C", _t("iv.copy"), self.copia),
                ("Delete", 0, "Canc", _t("iv.trash"), self.cestina),
                ("i", C, "Ctrl+I", _t("iv.props"), self.proprieta),
                ("h", C | S, "Ctrl+Maiusc+H", _t("iv.a.thislist"),
                 self.mostra_scorciatoie),
                ("q", C, "Ctrl+Q", _t("iv.close"), lambda: self.destroy()),
                ("w", C, "Ctrl+W", _t("iv.close"), lambda: self.destroy()),
            ]),
        ]

    def _accel(self):
        gruppo = Gtk.AccelGroup()
        self.add_accel_group(gruppo)
        for _titolo, voci in self._elenco_scorciatoie():
            for tasto, mod, _testo, _desc, cb in voci:
                gruppo.connect(Gdk.keyval_from_name(tasto), mod,
                               Gtk.AccelFlags.VISIBLE,
                               lambda *_a, cb=cb: (cb(), True)[1])

    def _tasti(self, _w, ev):
        # Esc: prima esce dalla presentazione, poi dallo schermo intero.
        if ev.keyval == Gdk.KEY_Escape:
            if self.presentazione:
                self.presenta()
                return True
            finestra = self.get_window()
            if finestra and (finestra.get_state() & Gdk.WindowState.FULLSCREEN):
                self.unfullscreen()
                return True
        if ev.keyval in (Gdk.KEY_Left, Gdk.KEY_Right) and \
                self._zoom_effettivo() <= self._adattamento():
            # con l'immagine intera a schermo le frecce sfogliano
            (self.precedente if ev.keyval == Gdk.KEY_Left
             else self.successiva)()
            return True
        return False

    def mostra_scorciatoie(self):
        dlg = Gtk.Dialog(title=_t("iv.shortcuts"), transient_for=self,
                         modal=True)
        dlg.add_button(_t("iv.close"), Gtk.ResponseType.CLOSE)
        dlg.set_default_size(460, 520)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(12)
        for titolo, voci in self._elenco_scorciatoie():
            t = Gtk.Label(); t.set_xalign(0)
            t.set_markup("<b>%s</b>" % GLib.markup_escape_text(titolo))
            box.pack_start(t, False, False, 6)
            griglia = Gtk.Grid(column_spacing=18, row_spacing=3)
            visti, r = set(), 0
            for _k, _m, testo, desc, _cb in voci:
                if desc in visti:
                    continue
                visti.add(desc)
                a = Gtk.Label(label=_ta(testo)); a.set_xalign(1)
                a.get_style_context().add_class("vesper-val")
                b = Gtk.Label(label=desc); b.set_xalign(0)
                griglia.attach(a, 0, r, 1, 1)
                griglia.attach(b, 1, r, 1, 1)
                r += 1
            box.pack_start(griglia, False, False, 0)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.add(box)
        dlg.get_content_area().pack_start(sw, True, True, 0)
        dlg.show_all()
        dlg.run()
        dlg.destroy()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-h", "--help", "aiuto"):
        print(_t("cli.viewer.usage") + "\n"
              + _t("cli.shortcuts_hint") % _ta("Ctrl+Maiusc+H"))
        return 0
    Visualizzatore(argv)
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
