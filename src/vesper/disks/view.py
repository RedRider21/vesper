# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Gestore dischi di Vesper - interfaccia GTK3.

Riusa lo stile del Centro di Controllo (vesper.common) per restare coerente col
resto del desktop e col colore del profilo attivo.

La GUI e' volutamente sottile: tutta la logica sta in model.py (enumerazione) e
mount.py (montaggio). Cosi' il giorno in cui il file manager Python di Vesper
avra' la sua barra "Dispositivi" bastera' importare model.py, senza portarsi
dietro nulla di questa finestra.

Impostazione FORENSIC: il pulsante grande e' "Monta sola lettura". Il montaggio
in scrittura c'e', ma chiede conferma e lo dice chiaramente.
"""
from __future__ import annotations

import threading

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Pango  # noqa: E402

from vesper.common import panel_window, icon_button, have, run_bg
from vesper.disks import model, mount

try:
    from vesper.i18n import t as _t
except Exception:                # noqa: BLE001
    def _t(key, **kw):           # fallback: non rompe mai la UI
        return key


def _riga_dettaglio(griglia, r, etichetta, valore):
    k = Gtk.Label(label=etichetta)
    k.set_xalign(0)
    k.get_style_context().add_class("vesper-key")
    v = Gtk.Label(label=valore or "-")
    v.set_xalign(0)
    v.set_selectable(True)
    v.set_ellipsize(Pango.EllipsizeMode.END)
    v.get_style_context().add_class("vesper-val")
    griglia.attach(k, 0, r, 1, 1)
    griglia.attach(v, 1, r, 1, 1)
    return v


def open_disks(_btn=None):
    win, body = panel_window(_t("dk.title"), 760, 620)

    intro = Gtk.Label(label=_t("dk.intro"))
    intro.set_xalign(0)
    intro.set_line_wrap(True)
    intro.get_style_context().add_class("vesper-val")
    body.pack_start(intro, False, False, 0)

    # --- elenco ad albero: disco -> partizioni --------------------------
    # colonne: percorso(nascosto), dispositivo, dimensione, filesystem,
    #          etichetta, montato
    store = Gtk.TreeStore(str, str, str, str, str, str)
    tree = Gtk.TreeView(model=store)
    tree.set_headers_visible(True)
    for i, (titolo, col) in enumerate(
            ((_t("dk.col_device"), 1), (_t("dk.col_size"), 2), (_t("dk.col_fs"), 3),
             (_t("dk.col_label"), 4), (_t("dk.col_mounted"), 5))):
        rend = Gtk.CellRendererText()
        rend.set_property("ellipsize", Pango.EllipsizeMode.END)
        c = Gtk.TreeViewColumn(titolo, rend, text=col)
        c.set_resizable(True)
        if col == 1:
            c.set_min_width(150)
        tree.append_column(c)

    sc = Gtk.ScrolledWindow()
    sc.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    sc.set_size_request(-1, 240)
    sc.add(tree)
    body.pack_start(sc, True, True, 0)

    stato = Gtk.Label(label="")
    stato.set_xalign(0)
    stato.set_line_wrap(True)
    stato.get_style_context().add_class("vesper-val")

    # --- dettaglio del selezionato --------------------------------------
    det = Gtk.Grid(column_spacing=12, row_spacing=4)
    det.set_margin_top(8)
    body.pack_start(det, False, False, 0)
    v_perc = _riga_dettaglio(det, 0, _t("dk.path"), "-")
    v_tipo = _riga_dettaglio(det, 1, _t("dk.type"), "-")
    v_uuid = _riga_dettaglio(det, 2, "UUID", "-")
    v_uso = _riga_dettaglio(det, 3, _t("dk.space"), "-")
    v_smart = _riga_dettaglio(det, 4, "SMART", "-")
    v_prot = _riga_dettaglio(det, 5, _t("dk.protection"), "-")

    body.pack_start(stato, False, False, 0)

    azioni = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    azioni.set_margin_top(6)
    body.pack_start(azioni, False, False, 0)
    azioni2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    body.pack_start(azioni2, False, False, 0)

    # In Vesper montare vuol dire montare NORMALMENTE (lettura e scrittura):
    # e' un desktop, non una distro forensic. La sola lettura resta un pulsante
    # a parte, per chiavette sospette o dischi da non toccare.
    b_rw = icon_button(_t("dk.mount_rw"), "drive-harddisk-symbolic", primary=True)
    b_ro = icon_button(_t("dk.mount_ro"), "changes-prevent-symbolic")
    b_um = icon_button(_t("dk.unmount"), "media-eject-symbolic")
    b_apri = icon_button(_t("dk.open_folder"), "folder-open-symbolic")
    for b in (b_rw, b_ro, b_um, b_apri):
        azioni.pack_start(b, False, False, 0)

    b_prot = icon_button(_t("dk.lock_write"), "changes-prevent-symbolic")
    b_img = icon_button(_t("dk.image_dd"), "media-floppy-symbolic")
    b_agg = icon_button(_t("v.refresh"), "view-refresh-symbolic")
    for b in (b_prot, b_img, b_agg):
        azioni2.pack_start(b, False, False, 0)

    ctx = {"nodi": [], "sel": None, "busy": False}

    # --- costruzione elenco ---------------------------------------------
    def ricarica(_w=None):
        sel_path = ctx["sel"].path if ctx["sel"] else None
        store.clear()
        ctx["nodi"] = model.list_devices()
        iter_da_riselezionare = [None]

        def aggiungi(n, padre):
            it = store.append(padre, [
                n.path,
                n.name if padre is None else "   " + n.name,
                model.human(n.size),
                n.fstype or ("-" if n.is_disk else _t("dk.none")),
                n.label or (n.model if n.is_disk else ""),
                n.mountpoint or "",
            ])
            if n.path == sel_path:
                iter_da_riselezionare[0] = it
            for c in n.children:
                aggiungi(c, it)

        for d in ctx["nodi"]:
            aggiungi(d, None)
        tree.expand_all()
        if iter_da_riselezionare[0] is not None:
            tree.get_selection().select_iter(iter_da_riselezionare[0])
        else:
            aggiorna_dettaglio()

    def nodo_selezionato():
        m, it = tree.get_selection().get_selected()
        if it is None:
            return None
        return model.find(ctx["nodi"], m[it][0])

    def aggiorna_dettaglio(*_a):
        n = nodo_selezionato()
        ctx["sel"] = n
        if n is None:
            for v in (v_perc, v_tipo, v_uuid, v_uso, v_smart, v_prot):
                v.set_text("-")
            for b in (b_ro, b_rw, b_um, b_apri, b_prot, b_img):
                b.set_sensitive(False)
            return
        v_perc.set_text(n.path)
        v_tipo.set_text("%s  %s" % (n.type, n.descrizione))
        v_uuid.set_text(n.uuid or "-")

        u = model.uso(n.mountpoint) if n.mounted else None
        v_uso.set_text(_t("dk.used_on") % (model.human(u[0]), model.human(u[1]))
                       if u else "-")
        v_prot.set_text(_t("dk.write_locked") if model.protetto_in_scrittura(n.path)
                        else _t("dk.writable"))
        v_smart.set_text(_t("dk.reading") if n.is_disk else "-")
        if n.is_disk:
            def leggi_smart(path=n.path):
                s = model.smart(path)
                def mostra():
                    if ctx["sel"] is not None and ctx["sel"].path == path:
                        if s is None:
                            v_smart.set_text(_t("dk.unavailable"))
                        else:
                            ore = (_t("dk.power_hours") % s["ore"]) if s["ore"] else ""
                            v_smart.set_text("%s%s" % (s["stato"], ore))
                    return False
                GLib.idle_add(mostra)
            threading.Thread(target=leggi_smart, daemon=True).start()

        montabile = n.mountable and not n.mounted and not ctx["busy"]
        b_ro.set_sensitive(montabile)
        b_rw.set_sensitive(montabile)
        b_um.set_sensitive(n.mounted and not ctx["busy"])
        b_apri.set_sensitive(n.mounted)
        b_prot.set_sensitive(n.is_disk and not ctx["busy"])
        b_img.set_sensitive(not ctx["busy"])
        b_prot.set_label(_t("dk.unlock_write") if model.protetto_in_scrittura(n.path)
                         else _t("dk.lock_write"))

    tree.get_selection().connect("changed", aggiorna_dettaglio)

    # --- operazioni (in thread: non bloccano la finestra) ----------------
    def esegui(fn, msg_attesa):
        ctx["busy"] = True
        stato.set_text(msg_attesa)
        for b in (b_ro, b_rw, b_um, b_prot, b_img):
            b.set_sensitive(False)

        def worker():
            ok, msg = fn()
            def fine():
                ctx["busy"] = False
                stato.set_text((_t("dk.ok_msg") if ok else _t("dk.err_msg")) % msg)
                ricarica()
                return False
            GLib.idle_add(fine)
        threading.Thread(target=worker, daemon=True).start()

    def on_ro(_w):
        n = ctx["sel"]
        if n:
            esegui(lambda: mount.mount_ro(n), _t("dk.mounting_ro") % n.path)

    def on_rw(_w):
        n = ctx["sel"]
        if n:
            esegui(lambda: mount.mount_rw(n), _t("dk.mounting_rw") % n.path)

    def on_um(_w):
        n = ctx["sel"]
        if n:
            esegui(lambda: mount.smonta(n), _t("dk.unmounting") % n.mountpoint)

    def on_prot(_w):
        n = ctx["sel"]
        if not n:
            return
        attiva = not model.protetto_in_scrittura(n.path)
        esegui(lambda: mount.write_protect(n.path, attiva),
               _t("dk.prot_enabling") if attiva else _t("dk.prot_disabling"))

    def on_apri(_w):
        n = ctx["sel"]
        if n and n.mounted:
            run_bg(["pcmanfm", n.mountpoint] if have("pcmanfm") else ["xdg-open", n.mountpoint])

    def on_img(_w):
        """Immagine grezza del dispositivo. Gira in un TERMINALE, non qui:
        dd puo' durare ore e l'avanzamento va visto (status=progress)."""
        n = ctx["sel"]
        if not n:
            return
        ch = Gtk.FileChooserDialog(title=_t("dk.save_image") % n.path,
                                   transient_for=win,
                                   action=Gtk.FileChooserAction.SAVE)
        ch.add_buttons(_t("v.cancel"), Gtk.ResponseType.CANCEL, _t("v.save"), Gtk.ResponseType.OK)
        ch.set_current_name("%s.img" % n.name)
        r = ch.run()
        dest = ch.get_filename()
        ch.destroy()
        if r != Gtk.ResponseType.OK or not dest:
            return
        cmd = ("doas dd if=%s of=%s bs=4M conv=noerror,sync status=progress; "
               "echo; echo '%s'; read x" % (n.path, dest, _t("dk.press_enter")))
        if have("lxterminal"):
            run_bg(["lxterminal", "-e", cmd])
        else:
            run_bg(["xterm", "-e", cmd])
        stato.set_text(_t("dk.copy_started"))

    b_ro.connect("clicked", on_ro)
    b_rw.connect("clicked", on_rw)
    b_um.connect("clicked", on_um)
    b_prot.connect("clicked", on_prot)
    b_apri.connect("clicked", on_apri)
    b_img.connect("clicked", on_img)
    b_agg.connect("clicked", ricarica)

    ricarica()
    win.show_all()
    return win


def main():
    win = open_disks()
    win.connect("destroy", Gtk.main_quit)
    Gtk.main()


if __name__ == "__main__":
    main()
