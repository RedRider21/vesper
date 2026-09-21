#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Registro delle licenze commerciali di Vesper — interfaccia grafica.

Strumento del TITOLARE: sta in tools/, non si installa con il desktop e non
finisce in nessun pacchetto. Fa quello che fa `vesper-licgen.py` da riga di
comando, ma con l'elenco sott'occhio e la memoria storica di tutto:

- emissione di una licenza (cliente, postazioni, durata, nota);
- rinnovo, che riemette con la stessa intestazione e una scadenza nuova;
- registrazione dei conteggi: quante installazioni ha dichiarato il cliente,
  quando, e se erano oltre il concordato;
- storico per ogni licenza, con tutte le date.

    tools/vesper-licenze-gui.py [--registro ~/licenze-vesper]

Il registro è un JSON (`registro.json`) accanto alle chiavi: si legge anche a
mano e si mette al sicuro con un backup qualunque.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Pango          # noqa: E402

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE / "src"))

from vesper.licenza import ed25519, modello              # noqa: E402

CARTELLA = Path(os.environ.get("VESPER_LICENZE_HOME",
                               Path.home() / "licenze-vesper"))
GIORNI_AVVISO = 60           # sotto questa soglia la scadenza si segnala

CSS = b"""
window, dialog { background: #050a14; color: #c8f5ff; }
label { color: #c8f5ff; }
.titolo { font-size: 15pt; font-weight: bold; color: #00e5ff; }
.sotto { color: #5a8a9a; font-size: 9pt; }
.sezione { color: #00e5ff; font-weight: bold; }
treeview { background: #0a1a26; color: #c8f5ff; }
treeview:selected { background: #123a4d; color: #ffffff; }
treeview header button { background: #0d2230; color: #8fb0c0; border: none;
  border-bottom: 1px solid #1a3a52; }
entry, spinbutton, textview { background: #0a1a26; color: #c8f5ff;
  border: 1px solid #1a3a52; border-radius: 6px; }
button { background: #0d2230; color: #c8f5ff; border: 1px solid #1a3a52;
  border-radius: 8px; padding: 6px 12px; }
button:hover { background: #123a4d; }
button.primario { background: #00e5ff; color: #050a14; font-weight: bold;
  border: none; }
button.primario:hover { background: #4df0ff; }
.valida { color: #6ee7a8; }
.scade { color: #ffd166; }
.scaduta { color: #ff5a8a; }
.eccedenza { color: #ff5a8a; font-weight: bold; }
frame { border: 1px solid #1a3a52; border-radius: 8px; }
"""


# --- registro ---------------------------------------------------------------
class Registro:
    """Le licenze emesse e la loro storia, su un file JSON."""

    def __init__(self, cartella: Path):
        self.cartella = cartella
        self.file = cartella / "registro.json"
        self.dati = {"licenze": []}
        self.carica()

    def carica(self) -> None:
        try:
            self.dati = json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.dati = {"licenze": []}
        self.dati.setdefault("licenze", [])

    def salva(self) -> None:
        self.cartella.mkdir(parents=True, exist_ok=True)
        self.file.write_text(json.dumps(self.dati, indent=1, ensure_ascii=False)
                             + "\n", encoding="utf-8")

    @property
    def licenze(self) -> list[dict]:
        return self.dati["licenze"]

    def trova(self, id_licenza: str) -> dict | None:
        for v in self.licenze:
            if v.get("id") == id_licenza:
                return v
        return None

    def aggiungi(self, voce: dict) -> None:
        voce.setdefault("storico", [])
        voce["storico"].append({"quando": datetime.now().isoformat(timespec="seconds"),
                                "evento": "emessa",
                                "dettaglio": "%d postazioni, scadenza %s"
                                % (voce.get("postazioni", 0),
                                   voce.get("scadenza") or "nessuna")})
        self.licenze.append(voce)
        self.salva()

    def annota(self, id_licenza: str, evento: str, dettaglio: str = "",
               extra: dict | None = None) -> None:
        v = self.trova(id_licenza)
        if v is None:
            return
        riga = {"quando": datetime.now().isoformat(timespec="seconds"),
                "evento": evento, "dettaglio": dettaglio}
        if extra:
            riga.update(extra)
        v.setdefault("storico", []).append(riga)
        self.salva()


def stato_licenza(voce: dict) -> tuple[str, str]:
    """(testo, classe CSS) leggendo la scadenza."""
    scad = voce.get("scadenza")
    if not scad:
        return "valida (senza scadenza)", "valida"
    try:
        giorno = date.fromisoformat(scad)
    except ValueError:
        return "scadenza illeggibile", "scaduta"
    mancano = (giorno - date.today()).days
    if mancano < 0:
        return "scaduta da %d giorni" % -mancano, "scaduta"
    if mancano <= GIORNI_AVVISO:
        return "scade fra %d giorni" % mancano, "scade"
    return "valida", "valida"


# --- dialogo di emissione ---------------------------------------------------
class DialogoEmissione(Gtk.Dialog):
    def __init__(self, padre, voce: dict | None = None):
        rinnovo = voce is not None
        super().__init__(title="Rinnova licenza" if rinnovo else "Nuova licenza",
                         transient_for=padre, modal=True)
        self.set_default_size(460, -1)
        self.add_button("Annulla", Gtk.ResponseType.CANCEL)
        b = self.add_button("Rinnova" if rinnovo else "Emetti",
                            Gtk.ResponseType.OK)
        b.get_style_context().add_class("primario")
        self.set_default_response(Gtk.ResponseType.OK)

        griglia = Gtk.Grid(row_spacing=8, column_spacing=10)
        griglia.set_border_width(14)
        self.get_content_area().add(griglia)

        def riga(n, etichetta, widget):
            lab = Gtk.Label(label=etichetta); lab.set_xalign(1)
            griglia.attach(lab, 0, n, 1, 1)
            widget.set_hexpand(True)
            griglia.attach(widget, 1, n, 1, 1)
            return widget

        self.cliente = riga(0, "Cliente", Gtk.Entry())
        self.cliente.set_placeholder_text("ragione sociale")
        self.postazioni = riga(1, "Postazioni",
                               Gtk.SpinButton.new_with_range(1, 100000, 1))
        self.postazioni.set_value(10)
        self.mesi = riga(2, "Durata (mesi)",
                         Gtk.SpinButton.new_with_range(0, 120, 1))
        self.mesi.set_value(12)
        self.nota = riga(3, "Nota / contratto", Gtk.Entry())
        self.nota.set_placeholder_text("es. contratto 2026/017")

        avviso = Gtk.Label()
        avviso.set_markup("<small>Durata 0 = senza scadenza: sconsigliata, la "
                          "scadenza annuale\nè ciò che dà un momento di "
                          "riconciliazione obbligato.\n\nTutto resta in locale: "
                          "nessuna attivazione in rete, il conteggio\npassa dai "
                          "rapporti che il cliente consegna.</small>")
        avviso.set_xalign(0)
        avviso.get_style_context().add_class("sotto")
        griglia.attach(avviso, 0, 4, 2, 1)

        if rinnovo:
            self.cliente.set_text(voce.get("cliente", ""))
            self.cliente.set_sensitive(False)
            self.postazioni.set_value(voce.get("postazioni", 10))
            self.nota.set_text(voce.get("nota", ""))
        self.show_all()

    def valori(self) -> dict:
        return {
            "cliente": self.cliente.get_text().strip(),
            "postazioni": int(self.postazioni.get_value()),
            "mesi": int(self.mesi.get_value()),
            "nota": self.nota.get_text().strip(),
        }


# --- finestra principale ----------------------------------------------------
class Finestra(Gtk.Window):
    def __init__(self, cartella: Path):
        super().__init__(title="Vesper — registro delle licenze")
        self.set_default_size(1000, 620)
        self.cartella = cartella
        self.registro = Registro(cartella)
        self.privata = cartella / "privata.key"

        prov = Gtk.CssProvider()
        try:
            prov.load_from_data(CSS)
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(), prov,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        except Exception:                            # noqa: BLE001
            pass

        radice = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        radice.set_border_width(14)
        self.add(radice)

        # intestazione
        testa = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        titoli = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        t = Gtk.Label(label="Licenze commerciali di Vesper"); t.set_xalign(0)
        t.get_style_context().add_class("titolo")
        self.sotto = Gtk.Label(); self.sotto.set_xalign(0)
        self.sotto.get_style_context().add_class("sotto")
        titoli.pack_start(t, False, False, 0)
        titoli.pack_start(self.sotto, False, False, 0)
        testa.pack_start(titoli, True, True, 0)

        b_nuova = Gtk.Button(label="Nuova licenza")
        b_nuova.get_style_context().add_class("primario")
        b_nuova.connect("clicked", self.su_nuova)
        testa.pack_end(b_nuova, False, False, 0)
        radice.pack_start(testa, False, False, 0)

        # elenco
        self.store = Gtk.ListStore(str, str, int, str, str, str, str, str)
        # cliente, id, postazioni, emessa, scadenza, stato, installazioni, nota
        self.vista = Gtk.TreeView(model=self.store)
        self.vista.set_headers_visible(True)
        for i, (titolo, larg) in enumerate([
                ("Cliente", 210), ("Licenza", 150), ("Post.", 60),
                ("Emessa", 100), ("Scadenza", 100), ("Stato", 150),
                ("Installaz.", 90), ("Nota", 160)]):
            r = Gtk.CellRendererText()
            r.set_property("ellipsize", Pango.EllipsizeMode.END)
            col = Gtk.TreeViewColumn(titolo, r, text=i)
            col.set_min_width(larg)
            col.set_resizable(True)
            col.set_sort_column_id(i)
            self.vista.append_column(col)
        self.vista.get_selection().connect("changed", self.su_selezione)
        self.vista.connect("row-activated", lambda *_a: self.su_dettagli(None))

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.add(self.vista)
        sw.set_vexpand(True)
        radice.pack_start(sw, True, True, 0)

        # azioni sulla licenza scelta
        barra = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.azioni = []
        for etichetta, funzione in (
                ("Storico…", self.su_dettagli),
                ("Conta installazioni…", self.su_conta),
                ("Rinnova…", self.su_rinnova),
                ("Verifica file", self.su_verifica),
                ("Apri cartella", self.su_apri_cartella)):
            b = Gtk.Button(label=etichetta)
            b.connect("clicked", funzione)
            b.set_sensitive(False)
            barra.pack_start(b, False, False, 0)
            self.azioni.append(b)
        self.stato = Gtk.Label(); self.stato.set_xalign(1)
        self.stato.get_style_context().add_class("sotto")
        barra.pack_end(self.stato, True, True, 0)
        radice.pack_start(barra, False, False, 0)

        self.connect("destroy", Gtk.main_quit)
        self.aggiorna()

    # -- dati -------------------------------------------------------------
    def aggiorna(self) -> None:
        self.registro.carica()
        self.store.clear()
        scadute = in_scadenza = 0
        for v in self.registro.licenze:
            testo, classe = stato_licenza(v)
            scadute += classe == "scaduta"
            in_scadenza += classe == "scade"
            ultimo = ""
            for riga in reversed(v.get("storico", [])):
                if riga.get("evento") == "conteggio":
                    n = riga.get("installazioni", "?")
                    ultimo = "%s%s" % (n, " !" if isinstance(n, int)
                                       and n > v.get("postazioni", 0) else "")
                    break
            self.store.append([v.get("cliente", ""), v.get("id", ""),
                               v.get("postazioni", 0), v.get("emessa", ""),
                               v.get("scadenza", "—"), testo, ultimo or "—",
                               v.get("nota", "")])
        pezzi = ["%d licenze" % len(self.registro.licenze)]
        if in_scadenza:
            pezzi.append("%d in scadenza" % in_scadenza)
        if scadute:
            pezzi.append("%d scadute" % scadute)
        chiave = "chiave %s" % (modello.id_chiave(
            bytes.fromhex((self.cartella / "pubblica.hex").read_text().strip()))
            if (self.cartella / "pubblica.hex").exists() else "assente")
        pezzi.append(chiave)
        self.sotto.set_text(" · ".join(pezzi) + "  ·  " + str(self.cartella))
        if not self.privata.exists():
            self.avviso("Chiave privata assente",
                        "Non trovo %s.\n\nSenza la chiave privata non si "
                        "possono emettere licenze. Generala con:\n\n"
                        "    tools/vesper-licgen.py chiavi --out %s"
                        % (self.privata, self.cartella))

    def scelta(self) -> dict | None:
        modello_, iter_ = self.vista.get_selection().get_selected()
        if iter_ is None:
            return None
        return self.registro.trova(modello_[iter_][1])

    def su_selezione(self, _sel) -> None:
        attiva = self.scelta() is not None
        for b in self.azioni:
            b.set_sensitive(attiva)

    # -- azioni -----------------------------------------------------------
    def su_nuova(self, _b) -> None:
        self._emetti(None)

    def su_rinnova(self, _b) -> None:
        v = self.scelta()
        if v:
            self._emetti(v)

    def _emetti(self, precedente: dict | None) -> None:
        if not self.privata.exists():
            self.avviso("Chiave privata assente",
                        "Serve %s per firmare." % self.privata)
            return
        d = DialogoEmissione(self, precedente)
        if d.run() != Gtk.ResponseType.OK:
            d.destroy()
            return
        val = d.valori()
        d.destroy()
        if not val["cliente"]:
            self.avviso("Manca il cliente", "Il nome del cliente è obbligatorio.")
            return

        sicuro = "".join(c if c.isalnum() or c in "-_" else "-"
                         for c in val["cliente"].lower())[:40]
        destinazione = self.cartella / "emesse" / ("%s-%s.licenza.json"
                                                   % (sicuro, date.today().isoformat()))
        destinazione.parent.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, str(RADICE / "tools" / "vesper-licgen.py"),
               "emetti", "--chiave", str(self.privata),
               "--cliente", val["cliente"],
               "--postazioni", str(val["postazioni"]),
               "--mesi", str(val["mesi"]),
               "--out", str(destinazione)]
        if val["nota"]:
            cmd += ["--nota", val["nota"]]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError) as e:
            self.avviso("Emissione non riuscita", str(e))
            return
        if r.returncode != 0:
            self.avviso("Emissione non riuscita", r.stderr or r.stdout)
            return

        doc = json.loads(destinazione.read_text(encoding="utf-8"))
        dati = doc["licenza"]
        voce = {"id": dati["id"], "cliente": dati["cliente"],
                "postazioni": dati["postazioni"], "emessa": dati["emessa"],
                "scadenza": dati.get("scadenza", ""),
                "nota": dati.get("nota", ""),
                "file": str(destinazione)}
        if precedente:
            voce["rinnovo_di"] = precedente.get("id", "")
            self.registro.annota(precedente["id"], "rinnovata",
                                 "sostituita da %s" % voce["id"])
        self.registro.aggiungi(voce)
        self.aggiorna()
        self.stato.set_text("emessa %s → %s" % (voce["id"], destinazione.name))
        self.avviso("Licenza emessa",
                    "%s — %d postazioni, scadenza %s\n\nFile:\n%s\n\n"
                    "Consegna al cliente questo file e il pacchetto\n"
                    "vesper_*_commerciale.deb."
                    % (voce["cliente"], voce["postazioni"],
                       voce["scadenza"] or "nessuna", destinazione),
                    errore=False)

    def su_verifica(self, _b) -> None:
        v = self.scelta()
        if not v:
            return
        percorso = Path(v.get("file", ""))
        try:
            doc = json.loads(percorso.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            self.avviso("File non leggibile", "%s\n%s" % (percorso, e))
            return
        esito = modello.verifica(doc)
        self.registro.annota(v["id"], "verifica", esito.motivo)
        self.avviso("Verifica di %s" % v["id"],
                    "%s\n\n%s" % (esito.motivo.upper(), percorso),
                    errore=not esito)

    def su_conta(self, _b) -> None:
        v = self.scelta()
        if not v:
            return
        d = Gtk.FileChooserDialog(title="Rapporti mandati dal cliente",
                                  transient_for=self,
                                  action=Gtk.FileChooserAction.OPEN)
        d.add_buttons("Annulla", Gtk.ResponseType.CANCEL,
                      "Conta", Gtk.ResponseType.OK)
        d.set_select_multiple(True)
        f = Gtk.FileFilter(); f.set_name("Rapporti JSON"); f.add_pattern("*.json")
        d.add_filter(f)
        if d.run() != Gtk.ResponseType.OK:
            d.destroy()
            return
        file = d.get_filenames()
        d.destroy()
        if not file:
            return

        cmd = [sys.executable, str(RADICE / "tools" / "vesper-licgen.py"),
               "conta", "--licenza", v.get("file", "")] + file
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as e:
            self.avviso("Conteggio non riuscito", str(e))
            return
        uscita = r.stdout or r.stderr
        quante = None
        for riga in uscita.splitlines():
            if riga.startswith("contate"):
                try:
                    quante = int(riga.split(":")[1].strip().split()[0])
                except (IndexError, ValueError):
                    pass
        self.registro.annota(v["id"], "conteggio",
                             "%d file di rapporto" % len(file),
                             {"installazioni": quante} if quante is not None else None)
        self.aggiorna()
        eccede = quante is not None and quante > v.get("postazioni", 0)
        self.avviso("Conteggio per %s" % v.get("cliente", ""), uscita,
                    errore=eccede, monospazio=True)

    def su_dettagli(self, _b) -> None:
        v = self.scelta()
        if not v:
            return
        d = Gtk.Dialog(title="Storico di %s" % v.get("id", ""),
                       transient_for=self, modal=True)
        d.set_default_size(620, 440)
        d.add_button("Chiudi", Gtk.ResponseType.CLOSE)
        box = d.get_content_area()
        box.set_spacing(8)
        box.set_border_width(12)

        testa = Gtk.Label(); testa.set_xalign(0)
        testo_stato, classe = stato_licenza(v)
        testa.set_markup(
            "<b>%s</b>\n<small>%s · %d postazioni · emessa il %s · "
            "scadenza %s</small>"
            % (GLib.markup_escape_text(v.get("cliente", "")),
               GLib.markup_escape_text(v.get("id", "")),
               v.get("postazioni", 0), v.get("emessa", "?"),
               v.get("scadenza") or "nessuna"))
        box.pack_start(testa, False, False, 0)
        s = Gtk.Label(label=testo_stato); s.set_xalign(0)
        s.get_style_context().add_class(classe)
        box.pack_start(s, False, False, 0)
        if v.get("nota"):
            n = Gtk.Label(label=v["nota"]); n.set_xalign(0)
            n.get_style_context().add_class("sotto")
            box.pack_start(n, False, False, 0)

        sep = Gtk.Label(label="Storico"); sep.set_xalign(0)
        sep.get_style_context().add_class("sezione")
        box.pack_start(sep, False, False, 4)

        store = Gtk.ListStore(str, str, str)
        for riga in v.get("storico", []):
            # "2026-09-21T09:12:00" -> "2026-09-21 09:12": i secondi non
            # servono, e la data intera deve restare leggibile.
            quando = riga.get("quando", "").replace("T", " ")[:16]
            extra = riga.get("dettaglio", "")
            if riga.get("installazioni") is not None:
                extra = "%s installazioni — %s" % (riga["installazioni"], extra)
            store.append([quando, riga.get("evento", ""), extra])
        vista = Gtk.TreeView(model=store)
        for i, (titolo, larghezza) in enumerate((("Quando", 130),
                                                 ("Evento", 90),
                                                 ("Dettaglio", 240))):
            r = Gtk.CellRendererText()
            r.set_property("ellipsize", Pango.EllipsizeMode.END)
            col = Gtk.TreeViewColumn(titolo, r, text=i)
            col.set_min_width(larghezza)
            col.set_resizable(True)
            vista.append_column(col)
        sw = Gtk.ScrolledWindow(); sw.add(vista); sw.set_vexpand(True)
        box.pack_start(sw, True, True, 0)

        percorso = Gtk.Label(label=v.get("file", "")); percorso.set_xalign(0)
        percorso.set_selectable(True)
        percorso.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        percorso.get_style_context().add_class("sotto")
        box.pack_start(percorso, False, False, 0)

        d.show_all()
        d.run()
        d.destroy()

    def su_apri_cartella(self, _b) -> None:
        v = self.scelta()
        dove = Path(v.get("file", "")).parent if v else self.cartella
        for cmd in (["vesper-files", str(dove)], ["xdg-open", str(dove)]):
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                return
            except (OSError, FileNotFoundError):
                continue
        self.stato.set_text(str(dove))

    # -- utilità ----------------------------------------------------------
    def avviso(self, titolo: str, corpo: str, errore: bool = True,
               monospazio: bool = False) -> None:
        d = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=Gtk.MessageType.ERROR if errore else Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.CLOSE, text=titolo)
        d.format_secondary_text(corpo)
        if monospazio:
            for lab in d.get_message_area().get_children():
                try:
                    lab.modify_font(Pango.FontDescription("Monospace 9"))
                except Exception:                    # noqa: BLE001
                    pass
        d.run()
        d.destroy()


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cartella = CARTELLA
    if "--registro" in argv:
        i = argv.index("--registro")
        if i + 1 < len(argv):
            cartella = Path(argv[i + 1]).expanduser()
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    Finestra(cartella).show_all()
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
