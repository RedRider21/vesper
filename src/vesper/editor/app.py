# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Editor di testo di Vesper - GTK3 + GtkSourceView 4.

Nello spirito di pluma/gedit ma senza portarsi dietro mezzo DE: schede,
colorazione della sintassi, numeri di riga, cerca/sostituisci, vai a riga,
stampa, zoom, e scorciatoie da tastiera per tutto (elenco con Ctrl+Maiusc+H).

Colori: due schemi GtkSourceView nostri (data/sourceview-styles) che seguono
l'accento del preset e la modalita' chiara/scura del desktop.

Impostazioni in ~/.config/vesper/editor.json.
"""
import json
import os
import sys

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GtkSource", "4")
from gi.repository import Gtk, Gdk, Gio, GLib, Pango, GtkSource  # noqa: E402

try:
    from vesper import paths
except Exception:                                   # noqa: BLE001
    paths = None

# Tema comune del desktop; import "morbido" come negli altri strumenti.
try:
    from vesper.common import apply_css
except Exception:                                   # noqa: BLE001
    def apply_css():
        return

APP_NAME = "Editor di testo"

# Impostazioni predefinite (le stesse chiavi finiscono in editor.json).
DEFAULTS = {
    "font": "Monospace 11",
    "numeri_riga": True,
    "riga_corrente": True,
    "a_capo": False,
    "spazi_invece_tab": False,
    "larghezza_tab": 4,
    "rientro_automatico": True,
    "mostra_spazi": False,
    "margine_destro": 0,           # 0 = nascosto, altrimenti la colonna
    "mappa": False,                # minimappa laterale
    "backup": True,                # salva una copia file~ accanto all'originale
    "larghezza": 900,
    "altezza": 620,
}


# ---------------------------------------------------------------------------
# Impostazioni e colori
# ---------------------------------------------------------------------------
def _conf_file():
    if paths is not None:
        return str(paths.config("editor.json"))
    return os.path.expanduser("~/.config/vesper/editor.json")


def carica_conf() -> dict:
    conf = dict(DEFAULTS)
    try:
        with open(_conf_file(), encoding="utf-8") as f:
            letto = json.load(f)
        if isinstance(letto, dict):
            for k, v in letto.items():
                if k in DEFAULTS and isinstance(v, type(DEFAULTS[k])):
                    conf[k] = v
    except Exception:                               # noqa: BLE001
        pass
    return conf


def salva_conf(conf: dict) -> None:
    try:
        p = _conf_file()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(conf, f, indent=1, ensure_ascii=False)
            f.write("\n")
    except Exception:                               # noqa: BLE001
        pass


def _accento() -> str:
    """Accent del preset attivo, con ripiego sul ciano di Vesper."""
    try:
        from vesper.profiles import model
        ac = model.accent()
        if isinstance(ac, str) and ac.startswith("#") and len(ac) == 7:
            return ac
    except Exception:                               # noqa: BLE001
        pass
    return "#00e5ff"


def _mix(colore: str, fattore: float) -> str:
    h = colore.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % (min(255, int(r * fattore)),
                              min(255, int(g * fattore)),
                              min(255, int(b * fattore)))


def _chiaro() -> bool:
    try:
        from vesper import palette
        return palette.is_light()
    except Exception:                               # noqa: BLE001
        return False


def _schema_colore(chiaro: bool):
    """Prepara (e restituisce) lo schema GtkSourceView di Vesper.

    Il modello sta nei dati installati con i segnaposto dell'accento; qui lo
    riscriviamo in cache col colore del preset e lo diamo in pasto al manager.
    """
    nome = "vesper-light" if chiaro else "vesper-dark"
    mgr = GtkSource.StyleSchemeManager.get_default()
    modello = None
    if paths is not None:
        modello = paths.find_data("sourceview-styles", nome + ".xml")
        if modello is None:
            modello = paths.find_data("sourceview-styles",
                                      "vesper-dark.xml" if not chiaro else
                                      "vesper-light.xml")
    if modello is not None:
        try:
            ac = _accento()
            testo = open(modello, encoding="utf-8").read()
            testo = (testo.replace("@ACCENT_SCURO@", _mix(ac, 0.62))
                          .replace("@ACCENT_CHIARO@", _mix(ac, 1.35))
                          .replace("@ACCENT@", ac))
            if paths is not None:
                dest_dir = paths.cache("sourceview-styles")
            else:
                dest_dir = os.path.expanduser("~/.cache/vesper/sourceview-styles")
            os.makedirs(dest_dir, exist_ok=True)
            with open(os.path.join(str(dest_dir), nome + ".xml"), "w",
                      encoding="utf-8") as f:
                f.write(testo)
            percorsi = list(mgr.get_search_path() or [])
            if str(dest_dir) not in percorsi:
                mgr.set_search_path([str(dest_dir)] + percorsi)
            mgr.force_rescan()
        except Exception:                           # noqa: BLE001
            pass
    schema = mgr.get_scheme(nome)
    if schema is None:                              # ripieghi di sistema
        for alt in (("Adwaita", "classic", "tango") if chiaro else
                    ("Adwaita-dark", "oblivion", "cobalt", "classic")):
            schema = mgr.get_scheme(alt)
            if schema is not None:
                break
    return schema


def _css_editor() -> bytes:
    """Ritocchi CSS specifici dell'editor (schede, barre, campo ricerca)."""
    ac = _accento()
    return ("""
    .vesper-editor-barra { padding: 4px 6px; }
    .vesper-editor-stato { padding: 2px 8px; font-size: 90%%; }
    .vesper-editor-stato label { color: alpha(currentColor, 0.75); }
    .vesper-editor-modificato { color: %s; font-weight: bold; }
    .vesper-editor-trova entry { min-width: 220px; }
    .vesper-editor-tab button { padding: 0; margin: 0;
        min-width: 20px; min-height: 20px;
        background: none; border: none; box-shadow: none;
        opacity: 0.55; }
    .vesper-editor-tab button:hover { opacity: 1; }
    notebook tab { padding: 4px 8px; }
    .vesper-editor-trova.vesper-nulla entry { color: #ff5a8a; }
    """ % ac).encode("ascii", "replace")


# ---------------------------------------------------------------------------
# Lettura/scrittura dei file
# ---------------------------------------------------------------------------
CODIFICHE = ("utf-8", "utf-8-sig", "latin-1")


def leggi_file(percorso: str):
    """Ritorna (testo, codifica). Solleva ValueError sui file binari."""
    with open(percorso, "rb") as f:
        crudo = f.read()
    if b"\x00" in crudo[:4096]:
        raise ValueError("sembra un file binario, non di testo")
    for cod in CODIFICHE:
        try:
            return crudo.decode(cod), ("utf-8" if cod == "utf-8-sig" else cod)
        except UnicodeDecodeError:
            continue
    return crudo.decode("utf-8", "replace"), "utf-8"


def _cerca_da(ricerca, partenza, avanti: bool):
    """Occorrenza successiva/precedente a partire da un iteratore.

    In GtkSourceView 4 convivono forward()/forward2(): cambia solo il valore
    "ha girato in fondo", che a noi non serve. Proviamo l'una e poi l'altra.
    """
    for nome in (("forward2", "forward") if avanti
                 else ("backward2", "backward")):
        metodo = getattr(ricerca, nome, None)
        if metodo is None:
            continue
        try:
            esito = metodo(partenza)
        except TypeError:
            continue
        if not esito or not esito[0]:
            return None
        return esito[1], esito[2]
    return None


def _sostituisci_uno(ricerca, inizio, fine, nuovo: str) -> None:
    """Sostituisce l'occorrenza scelta (replace2 o replace, vedi sopra)."""
    for nome in ("replace2", "replace"):
        metodo = getattr(ricerca, nome, None)
        if metodo is None:
            continue
        try:
            metodo(inizio, fine, nuovo, -1)
            return
        except TypeError:
            continue

# ---------------------------------------------------------------------------
# Documento = una scheda
# ---------------------------------------------------------------------------
class Documento(Gtk.Box):
    """Una scheda: vista sorgente + stato del file che rappresenta."""

    def __init__(self, editor, percorso: str | None = None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.editor = editor
        self.percorso = percorso
        self.codifica = "utf-8"
        self.mtime = 0.0
        self.avvisato_esterno = False

        self.buffer = GtkSource.Buffer()
        self.buffer.set_highlight_matching_brackets(True)
        self.vista = GtkSource.View(buffer=self.buffer)
        self.vista.set_monospace(True)
        self.vista.set_smart_home_end(GtkSource.SmartHomeEndType.BEFORE)
        self.vista.set_left_margin(6)
        self.vista.set_right_margin(6)
        self.vista.set_pixels_above_lines(1)
        self.css = Gtk.CssProvider()
        self.vista.get_style_context().add_provider(
            self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        scorri = Gtk.ScrolledWindow()
        scorri.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scorri.add(self.vista)
        self.pack_start(scorri, True, True, 0)

        # minimappa (si mostra/nasconde dalle impostazioni)
        self.mappa = GtkSource.Map()
        self.mappa.set_view(self.vista)
        self.mappa.set_no_show_all(True)
        self.pack_start(self.mappa, False, False, 0)

        # ricerca: impostazioni e contesto sono per-documento
        self.ricerca_cfg = GtkSource.SearchSettings()
        self.ricerca_cfg.set_wrap_around(True)
        self.ricerca = GtkSource.SearchContext(buffer=self.buffer,
                                               settings=self.ricerca_cfg)
        self.ricerca.set_highlight(True)

        # etichetta della scheda, col suo pulsante di chiusura
        self.tab = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.tab.get_style_context().add_class("vesper-editor-tab")
        self.tab_label = Gtk.Label()
        self.tab_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.tab_label.set_max_width_chars(22)
        chiudi = Gtk.Button(relief=Gtk.ReliefStyle.NONE)
        chiudi.set_focus_on_click(False)
        chiudi.set_image(Gtk.Image.new_from_icon_name("window-close-symbolic",
                                                      Gtk.IconSize.MENU))
        chiudi.set_tooltip_text("Chiudi la scheda (Ctrl+W)")
        chiudi.connect("clicked", lambda _b: editor.chiudi_documento(self))
        self.tab.pack_start(self.tab_label, True, True, 0)
        self.tab.pack_end(chiudi, False, False, 0)
        self.tab.show_all()

        self._etichetta(self.nome())
        self.buffer.connect("modified-changed", self._su_modifica)
        self.buffer.connect("mark-set", lambda *_a: editor.aggiorna_stato())
        self.buffer.connect("changed", lambda *_a: editor.aggiorna_stato())

        if percorso:
            self.carica(percorso)
        self.show_all()
        self.mappa.set_visible(bool(editor.conf.get("mappa")))

    def _etichetta(self, testo: str):
        self.tab_label.set_text(testo)
        self.tab_label.set_width_chars(min(22, max(6, len(testo))))

    # --- nomi e stato -----------------------------------------------------
    def nome(self) -> str:
        return os.path.basename(self.percorso) if self.percorso \
            else "Senza nome"

    def titolo(self) -> str:
        stella = "*" if self.buffer.get_modified() else ""
        if self.percorso:
            casa = os.path.expanduser("~")
            p = self.percorso
            if p.startswith(casa + os.sep):
                p = "~" + p[len(casa):]
            return f"{stella}{self.nome()} ({os.path.dirname(p) or '/'})"
        return stella + self.nome()

    def _su_modifica(self, _buf):
        mod = self.buffer.get_modified()
        self._etichetta(("*" if mod else "") + self.nome())
        ctx = self.tab_label.get_style_context()
        (ctx.add_class if mod else ctx.remove_class)("vesper-editor-modificato")
        self.editor.aggiorna_titolo()

    # --- file -------------------------------------------------------------
    def carica(self, percorso: str) -> bool:
        try:
            testo, cod = leggi_file(percorso)
        except Exception as e:                      # noqa: BLE001
            self.editor.avviso("Non riesco ad aprire il file",
                               f"{percorso}\n{e}")
            return False
        self.percorso = percorso
        self.codifica = cod
        self.buffer.begin_not_undoable_action()
        self.buffer.set_text(testo)
        self.buffer.end_not_undoable_action()
        self.buffer.set_modified(False)
        self.buffer.place_cursor(self.buffer.get_start_iter())
        try:
            self.mtime = os.path.getmtime(percorso)
        except OSError:
            self.mtime = 0.0
        self.avvisato_esterno = False
        self.rileva_linguaggio()
        self._etichetta(self.nome())
        self.tab.set_tooltip_text(percorso)
        return True

    def salva(self, percorso: str | None = None) -> bool:
        dest = percorso or self.percorso
        if not dest:
            return False
        inizio, fine = self.buffer.get_bounds()
        testo = self.buffer.get_text(inizio, fine, True)
        if testo and not testo.endswith("\n"):
            testo += "\n"                           # POSIX: riga finale
        try:
            if self.editor.conf.get("backup") and os.path.exists(dest):
                try:
                    with open(dest, "rb") as vecchio, \
                         open(dest + "~", "wb") as copia:
                        copia.write(vecchio.read())
                except OSError:
                    pass                            # il backup non è critico
            tmp = dest + ".vesper-tmp"
            with open(tmp, "w", encoding=self.codifica, errors="replace") as f:
                f.write(testo)
            os.replace(tmp, dest)
        except Exception as e:                      # noqa: BLE001
            self.editor.avviso("Non riesco a salvare", f"{dest}\n{e}")
            return False
        primo_salvataggio = dest != self.percorso
        self.percorso = dest
        self.buffer.set_modified(False)
        try:
            self.mtime = os.path.getmtime(dest)
        except OSError:
            self.mtime = 0.0
        self.avvisato_esterno = False
        if primo_salvataggio:
            self.rileva_linguaggio()
        self._etichetta(self.nome())
        self.tab.set_tooltip_text(dest)
        return True

    def cambiato_fuori(self) -> bool:
        """True se il file è stato toccato da qualcun altro dopo l'apertura."""
        if not self.percorso or not self.mtime:
            return False
        try:
            return os.path.getmtime(self.percorso) > self.mtime + 0.001
        except OSError:
            return False

    # --- linguaggio e aspetto --------------------------------------------
    def rileva_linguaggio(self):
        lm = GtkSource.LanguageManager.get_default()
        lang = None
        if self.percorso:
            lang = lm.guess_language(self.percorso, None)
            # per i .py GtkSourceView propone ancora "Python 2": nel 2026 la
            # scelta sensata e' Python 3.
            if lang is not None and lang.get_id() == "python":
                lang = lm.get_language("python3") or lang
            if lang is None:
                # niente estensione: proviamo con lo shebang
                riga = self.buffer.get_iter_at_line(0)
                fine = riga.copy()
                fine.forward_to_line_end()
                prima = self.buffer.get_text(riga, fine, True)
                if prima.startswith("#!"):
                    for nome, ident in (("python", "python3"), ("sh", "sh"),
                                        ("bash", "sh"), ("perl", "perl"),
                                        ("ruby", "ruby"), ("node", "js")):
                        if nome in prima:
                            lang = lm.get_language(ident)
                            break
        self.buffer.set_language(lang)

    def applica_conf(self, conf: dict, schema):
        v = self.vista
        v.set_show_line_numbers(bool(conf["numeri_riga"]))
        v.set_highlight_current_line(bool(conf["riga_corrente"]))
        v.set_wrap_mode(Gtk.WrapMode.WORD_CHAR if conf["a_capo"]
                        else Gtk.WrapMode.NONE)
        v.set_insert_spaces_instead_of_tabs(bool(conf["spazi_invece_tab"]))
        v.set_tab_width(max(1, int(conf["larghezza_tab"])))
        v.set_indent_width(max(1, int(conf["larghezza_tab"])))
        v.set_auto_indent(bool(conf["rientro_automatico"]))
        v.set_show_right_margin(int(conf["margine_destro"]) > 0)
        if int(conf["margine_destro"]) > 0:
            v.set_right_margin_position(int(conf["margine_destro"]))
        # spazi visibili: in GtkSourceView 4 si passa dallo "space drawer"
        try:
            sd = v.get_space_drawer()
            tipi = (GtkSource.SpaceTypeFlags.SPACE | GtkSource.SpaceTypeFlags.TAB
                    | GtkSource.SpaceTypeFlags.NEWLINE) \
                if conf["mostra_spazi"] else GtkSource.SpaceTypeFlags.NONE
            sd.set_types_for_locations(GtkSource.SpaceLocationFlags.ALL, tipi)
            sd.set_enable_matrix(True)
        except Exception:                           # noqa: BLE001
            pass
        self.mappa.set_visible(bool(conf["mappa"]))
        if schema is not None:
            self.buffer.set_style_scheme(schema)
        self.applica_font(conf["font"])

    def applica_font(self, descrizione: str):
        fd = Pango.FontDescription(descrizione)
        famiglia = fd.get_family() or "Monospace"
        punti = fd.get_size() / Pango.SCALE or 11
        css = ("textview { font-family: \"%s\"; font-size: %.1fpt; }"
               % (famiglia, punti)).encode()
        try:
            self.css.load_from_data(css)
        except Exception:                           # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Finestra dell'editor
# ---------------------------------------------------------------------------
class Editor(Gtk.Window):

    def __init__(self, file_iniziali=None, riga=None):
        super().__init__(title=APP_NAME)
        self.conf = carica_conf()
        self.schema = _schema_colore(_chiaro())
        self.set_default_size(int(self.conf["larghezza"]),
                              int(self.conf["altezza"]))
        self.set_icon_name("accessories-text-editor")
        apply_css()
        self._css_extra()

        radice = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(radice)
        radice.pack_start(self._barra_strumenti(), False, False, 0)

        self.note = Gtk.Notebook()
        self.note.set_scrollable(True)
        self.note.set_show_border(False)
        self.note.connect("switch-page", self._cambio_scheda)
        radice.pack_start(self.note, True, True, 0)

        self.trova_rivelatore = Gtk.Revealer()
        self.trova_rivelatore.set_transition_type(
            Gtk.RevealerTransitionType.SLIDE_UP)
        self.trova_rivelatore.add(self._barra_ricerca())
        radice.pack_start(self.trova_rivelatore, False, False, 0)

        radice.pack_start(self._barra_stato(), False, False, 0)

        self._accel()
        self.connect("key-press-event", self._tasti)
        self.connect("delete-event", lambda *_a: not self.esci())
        self.connect("focus-in-event", self._controlla_file_esterni)
        # trascinare file dentro la finestra li apre
        self.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self.drag_dest_add_uri_targets()
        self.connect("drag-data-received", self._trascinati)

        aperti = 0
        for f in (file_iniziali or []):
            if self.apri(os.path.abspath(f), in_coda=True):
                aperti += 1
        if aperti == 0:
            self.nuovo()
        self.show_all()
        self.trova_rivelatore.set_reveal_child(False)
        if riga:
            GLib.idle_add(self.vai_a_riga, riga)
        GLib.idle_add(self.aggiorna_stato)

    # --- costruzione UI ---------------------------------------------------
    def _css_extra(self):
        try:
            prov = Gtk.CssProvider()
            prov.load_from_data(_css_editor())
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(), prov,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        except Exception:                           # noqa: BLE001
            pass

    def _bottone(self, icona, tooltip, callback):
        b = Gtk.Button(relief=Gtk.ReliefStyle.NONE)
        b.add(Gtk.Image.new_from_icon_name(icona, Gtk.IconSize.LARGE_TOOLBAR))
        b.set_tooltip_text(tooltip)
        b.set_focus_on_click(False)
        b.connect("clicked", lambda _b: callback())
        return b

    def _barra_strumenti(self):
        barra = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        barra.get_style_context().add_class("vesper-editor-barra")
        for icona, testo, cb in (
                ("document-new-symbolic", "Nuovo (Ctrl+N)", self.nuovo),
                ("document-open-symbolic", "Apri (Ctrl+O)", self.apri_dialogo),
                ("document-save-symbolic", "Salva (Ctrl+S)", self.salva),
                ("document-save-as-symbolic", "Salva come (Ctrl+Maiusc+S)",
                 self.salva_come)):
            barra.pack_start(self._bottone(icona, testo, cb), False, False, 0)
        barra.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL),
                         False, False, 6)
        for icona, testo, cb in (
                ("edit-undo-symbolic", "Annulla (Ctrl+Z)", self.annulla),
                ("edit-redo-symbolic", "Ripeti (Ctrl+Maiusc+Z)", self.ripeti),
                ("edit-find-symbolic", "Trova (Ctrl+F)", self.mostra_trova),
                ("edit-find-replace-symbolic", "Sostituisci (Ctrl+H)",
                 self.mostra_sostituisci)):
            barra.pack_start(self._bottone(icona, testo, cb), False, False, 0)

        # menu delle preferenze e delle azioni meno frequenti
        menu_b = Gtk.MenuButton()
        menu_b.set_relief(Gtk.ReliefStyle.NONE)
        menu_b.add(Gtk.Image.new_from_icon_name("open-menu-symbolic",
                                                Gtk.IconSize.LARGE_TOOLBAR))
        menu_b.set_tooltip_text("Opzioni")
        menu_b.set_popup(self._menu())
        barra.pack_end(menu_b, False, False, 0)
        self.lbl_lingua = Gtk.Label(label="Testo semplice")
        self.lbl_lingua.get_style_context().add_class("vesper-val")
        barra.pack_end(self.lbl_lingua, False, False, 8)
        return barra

    def _voce(self, menu, etichetta, callback, scorciatoia=""):
        it = Gtk.MenuItem()
        riga = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        lab = Gtk.Label(label=etichetta); lab.set_xalign(0)
        riga.pack_start(lab, True, True, 0)
        if scorciatoia:
            acc = Gtk.Label(label=scorciatoia)
            acc.get_style_context().add_class("vesper-val")
            riga.pack_end(acc, False, False, 0)
        it.add(riga)
        it.connect("activate", lambda _i: callback())
        menu.append(it)
        return it

    def _interruttore(self, menu, etichetta, chiave):
        it = Gtk.CheckMenuItem(label=etichetta)
        it.set_active(bool(self.conf[chiave]))

        def cambia(widget):
            self.conf[chiave] = widget.get_active()
            salva_conf(self.conf)
            self.applica_conf()
        it.connect("toggled", cambia)
        menu.append(it)
        return it

    def _menu(self):
        m = Gtk.Menu()
        self._voce(m, "Ricarica dal disco", self.ricarica, "Ctrl+R")
        self._voce(m, "Stampa...", self.stampa, "Ctrl+P")
        self._voce(m, "Vai a riga...", self.dialogo_vai_a_riga, "Ctrl+I")
        m.append(Gtk.SeparatorMenuItem())
        self._interruttore(m, "Numeri di riga", "numeri_riga")
        self._interruttore(m, "Evidenzia la riga corrente", "riga_corrente")
        self._interruttore(m, "A capo automatico", "a_capo")
        self._interruttore(m, "Spazi al posto delle tabulazioni",
                           "spazi_invece_tab")
        self._interruttore(m, "Rientro automatico", "rientro_automatico")
        self._interruttore(m, "Mostra spazi e tabulazioni", "mostra_spazi")
        self._interruttore(m, "Minimappa", "mappa")
        self._interruttore(m, "Copia di sicurezza (file~)", "backup")
        m.append(Gtk.SeparatorMenuItem())
        self._voce(m, "Linguaggio...", self.dialogo_linguaggio)
        self._voce(m, "Carattere...", self.dialogo_font)
        sub = Gtk.Menu()
        for n in (2, 4, 8):
            v = Gtk.MenuItem(label="%d spazi" % n)
            v.connect("activate", lambda _i, n=n: self.imposta_tab(n))
            sub.append(v)
        tab_it = Gtk.MenuItem(label="Larghezza tabulazione")
        tab_it.set_submenu(sub)
        m.append(tab_it)
        m.append(Gtk.SeparatorMenuItem())
        self._voce(m, "Scorciatoie da tastiera", self.mostra_scorciatoie,
                   "Ctrl+Maiusc+H")
        self._voce(m, "Chiudi scheda", self.chiudi_corrente, "Ctrl+W")
        self._voce(m, "Esci", self.esci, "Ctrl+Q")
        m.show_all()
        return m

    def _barra_ricerca(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.get_style_context().add_class("vesper-editor-trova")
        self.box_trova = box
        box.set_border_width(6)

        riga1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.e_trova = Gtk.SearchEntry()
        self.e_trova.set_placeholder_text("Trova")
        self.e_trova.connect("search-changed", lambda _e: self._aggiorna_ricerca())
        self.e_trova.connect("activate", lambda _e: self.trova_avanti())
        self.e_trova.connect("stop-search", lambda _e: self.nascondi_trova())
        riga1.pack_start(self.e_trova, True, True, 0)
        riga1.pack_start(self._bottone("go-up-symbolic",
                                       "Precedente (Maiusc+F3)",
                                       self.trova_indietro), False, False, 0)
        riga1.pack_start(self._bottone("go-down-symbolic",
                                       "Successiva (F3)",
                                       self.trova_avanti), False, False, 0)
        self.lbl_occorrenze = Gtk.Label(label="")
        self.lbl_occorrenze.get_style_context().add_class("vesper-val")
        riga1.pack_start(self.lbl_occorrenze, False, False, 4)
        self.chk_maiuscole = Gtk.CheckButton(label="Maiuscole/minuscole")
        self.chk_maiuscole.connect("toggled", lambda _c: self._aggiorna_ricerca())
        riga1.pack_start(self.chk_maiuscole, False, False, 0)
        self.chk_parola = Gtk.CheckButton(label="Parola intera")
        self.chk_parola.connect("toggled", lambda _c: self._aggiorna_ricerca())
        riga1.pack_start(self.chk_parola, False, False, 0)
        self.chk_regex = Gtk.CheckButton(label="Espressione regolare")
        self.chk_regex.connect("toggled", lambda _c: self._aggiorna_ricerca())
        riga1.pack_start(self.chk_regex, False, False, 0)
        riga1.pack_end(self._bottone("window-close-symbolic", "Chiudi (Esc)",
                                     self.nascondi_trova), False, False, 0)
        box.pack_start(riga1, False, False, 0)

        self.riga_sost = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                                 spacing=6)
        self.e_sost = Gtk.Entry()
        self.e_sost.set_placeholder_text("Sostituisci con")
        self.e_sost.connect("activate", lambda _e: self.sostituisci())
        self.riga_sost.pack_start(self.e_sost, True, True, 0)
        b_uno = Gtk.Button(label="Sostituisci")
        b_uno.connect("clicked", lambda _b: self.sostituisci())
        b_tutti = Gtk.Button(label="Tutte")
        b_tutti.connect("clicked", lambda _b: self.sostituisci_tutto())
        self.riga_sost.pack_start(b_uno, False, False, 0)
        self.riga_sost.pack_start(b_tutti, False, False, 0)
        self.riga_sost.set_no_show_all(True)
        box.pack_start(self.riga_sost, False, False, 0)
        box.show_all()
        return box

    def _barra_stato(self):
        barra = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        barra.get_style_context().add_class("vesper-editor-stato")
        self.lbl_pos = Gtk.Label(label="Riga 1, colonna 1")
        self.lbl_pos.set_xalign(0)
        barra.pack_start(self.lbl_pos, False, False, 0)
        self.lbl_info = Gtk.Label(label="")
        barra.pack_end(self.lbl_info, False, False, 0)
        return barra

    # --- scorciatoie da tastiera -----------------------------------------
    # Elenco unico: serve sia a registrare gli acceleratori sia a comporre la
    # finestra di aiuto (Ctrl+Maiusc+H), cosi' le due cose non divergono mai.
    def _elenco_scorciatoie(self):
        C = Gdk.ModifierType.CONTROL_MASK
        S = Gdk.ModifierType.SHIFT_MASK
        A = Gdk.ModifierType.MOD1_MASK
        return [
            ("File", [
                ("n", C, "Ctrl+N", "Nuovo documento", self.nuovo),
                ("o", C, "Ctrl+O", "Apri un file", self.apri_dialogo),
                ("s", C, "Ctrl+S", "Salva", self.salva),
                ("s", C | S, "Ctrl+Maiusc+S", "Salva come", self.salva_come),
                ("r", C, "Ctrl+R", "Ricarica dal disco", self.ricarica),
                ("p", C, "Ctrl+P", "Stampa", self.stampa),
                ("w", C, "Ctrl+W", "Chiudi la scheda", self.chiudi_corrente),
                ("q", C, "Ctrl+Q", "Esci", self.esci),
            ]),
            ("Modifica", [
                ("z", C, "Ctrl+Z", "Annulla", self.annulla),
                ("z", C | S, "Ctrl+Maiusc+Z", "Ripeti", self.ripeti),
                ("y", C, "Ctrl+Y", "Ripeti", self.ripeti),
                ("d", C, "Ctrl+D", "Elimina la riga", self.elimina_riga),
                ("d", C | S, "Ctrl+Maiusc+D", "Duplica la riga",
                 self.duplica_riga),
                ("Up", A, "Alt+Su", "Sposta la riga in alto",
                 lambda: self.sposta_riga(-1)),
                ("Down", A, "Alt+Giu", "Sposta la riga in basso",
                 lambda: self.sposta_riga(1)),
                ("slash", C, "Ctrl+/", "Commenta o decommenta",
                 self.commenta),
            ]),
            ("Ricerca", [
                ("f", C, "Ctrl+F", "Trova", self.mostra_trova),
                ("h", C, "Ctrl+H", "Sostituisci", self.mostra_sostituisci),
                ("F3", 0, "F3", "Occorrenza successiva", self.trova_avanti),
                ("F3", S, "Maiusc+F3", "Occorrenza precedente",
                 self.trova_indietro),
                ("g", C, "Ctrl+G", "Occorrenza successiva", self.trova_avanti),
                ("g", C | S, "Ctrl+Maiusc+G", "Occorrenza precedente",
                 self.trova_indietro),
                ("i", C, "Ctrl+I", "Vai a riga", self.dialogo_vai_a_riga),
                ("l", C, "Ctrl+L", "Vai a riga", self.dialogo_vai_a_riga),
            ]),
            ("Vista", [
                ("plus", C, "Ctrl++", "Ingrandisci il testo",
                 lambda: self.zoom(1)),
                ("equal", C, "Ctrl+=", "Ingrandisci il testo",
                 lambda: self.zoom(1)),
                ("minus", C, "Ctrl+-", "Rimpicciolisci il testo",
                 lambda: self.zoom(-1)),
                ("0", C, "Ctrl+0", "Dimensione originale",
                 lambda: self.zoom(0)),
                ("Page_Down", C, "Ctrl+PagGiu", "Scheda successiva",
                 lambda: self.cambia_scheda(1)),
                ("Page_Up", C, "Ctrl+PagSu", "Scheda precedente",
                 lambda: self.cambia_scheda(-1)),
                ("F11", 0, "F11", "Schermo intero", self.schermo_intero),
                ("h", C | S, "Ctrl+Maiusc+H", "Questo elenco",
                 self.mostra_scorciatoie),
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
        # Alt+1..9 salta direttamente alla scheda n
        for n in range(1, 10):
            gruppo.connect(Gdk.keyval_from_name(str(n)),
                           Gdk.ModifierType.MOD1_MASK, Gtk.AccelFlags.VISIBLE,
                           lambda *_a, n=n: (self.note.set_current_page(n - 1),
                                             True)[1])

    def _tasti(self, _w, ev):
        if ev.keyval == Gdk.KEY_Escape and \
                self.trova_rivelatore.get_reveal_child():
            self.nascondi_trova()
            return True
        return False

    def mostra_scorciatoie(self):
        """Finestra di aiuto: usa Gtk.ShortcutsWindow se c'e', altrimenti un
        semplice elenco (la ShortcutsWindow esiste solo da GTK 3.20)."""
        try:
            self._shortcuts_window().show_all()
            return
        except Exception:                           # noqa: BLE001
            pass
        dlg = Gtk.Dialog(title="Scorciatoie da tastiera", transient_for=self,
                         modal=True)
        dlg.add_button("Chiudi", Gtk.ResponseType.CLOSE)
        dlg.set_default_size(520, 560)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(12)
        for titolo, voci in self._elenco_scorciatoie():
            t = Gtk.Label(); t.set_xalign(0)
            t.set_markup("<b>%s</b>" % GLib.markup_escape_text(titolo))
            box.pack_start(t, False, False, 6)
            griglia = Gtk.Grid(column_spacing=18, row_spacing=3)
            visti = set()
            r = 0
            for _k, _m, testo, desc, _cb in voci:
                if desc in visti:
                    continue                        # stessa azione, altro tasto
                visti.add(desc)
                a = Gtk.Label(label=testo); a.set_xalign(1)
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

    def _shortcuts_window(self):
        win = Gtk.ShortcutsWindow(transient_for=self, modal=True)
        sezione = Gtk.ShortcutsSection(section_name="vesper-editor",
                                       visible=True, max_height=12)
        for titolo, voci in self._elenco_scorciatoie():
            gruppo = Gtk.ShortcutsGroup(title=titolo, visible=True)
            visti = set()
            for tasto, mod, _testo, desc, _cb in voci:
                if desc in visti:
                    continue
                visti.add(desc)
                pezzi = []
                if mod & Gdk.ModifierType.CONTROL_MASK:
                    pezzi.append("<ctrl>")
                if mod & Gdk.ModifierType.SHIFT_MASK:
                    pezzi.append("<shift>")
                if mod & Gdk.ModifierType.MOD1_MASK:
                    pezzi.append("<alt>")
                scorc = Gtk.ShortcutsShortcut(
                    title=desc, accelerator="".join(pezzi) + tasto,
                    visible=True)
                gruppo.add(scorc)
            sezione.add(gruppo)
        win.add(sezione)
        return win

    # --- gestione delle schede -------------------------------------------
    def corrente(self) -> Documento | None:
        p = self.note.get_current_page()
        return self.note.get_nth_page(p) if p >= 0 else None

    def nuovo(self, percorso=None):
        doc = Documento(self, percorso)
        doc.applica_conf(self.conf, self.schema)
        n = self.note.append_page(doc, doc.tab)
        self.note.set_tab_reorderable(doc, True)
        self.note.show_all()
        self.note.set_current_page(n)
        doc.vista.grab_focus()
        self.note.set_show_tabs(self.note.get_n_pages() > 1)
        return doc

    def apri(self, percorso: str, in_coda=False):
        percorso = os.path.abspath(os.path.expanduser(percorso))
        for i in range(self.note.get_n_pages()):
            doc = self.note.get_nth_page(i)
            if doc.percorso == percorso:            # gia' aperto: ci salto
                self.note.set_current_page(i)
                return doc
        if not os.path.exists(percorso):            # nome nuovo: scheda vuota
            doc = self.nuovo()
            doc.percorso = percorso
            doc._etichetta(doc.nome())
            doc.rileva_linguaggio()
            self.aggiorna_titolo()
            return doc
        vuota = self.corrente()
        riuso = (not in_coda and vuota is not None and vuota.percorso is None
                 and not vuota.buffer.get_modified()
                 and vuota.buffer.get_char_count() == 0)
        doc = vuota if riuso else self.nuovo()
        if not doc.carica(percorso):
            if not riuso:
                self.chiudi_documento(doc, forza=True)
            return None
        doc.applica_conf(self.conf, self.schema)
        self.aggiorna_titolo()
        self.aggiorna_stato()
        return doc

    def chiudi_corrente(self):
        doc = self.corrente()
        if doc:
            self.chiudi_documento(doc)

    def chiudi_documento(self, doc, forza=False):
        if not forza and doc.buffer.get_modified():
            risposta = self._chiedi_salvataggio(doc)
            if risposta == "annulla":
                return False
            if risposta == "salva" and not self._salva_documento(doc):
                return False
        self.note.remove_page(self.note.page_num(doc))
        doc.destroy()
        if self.note.get_n_pages() == 0:
            self.nuovo()
        self.note.set_show_tabs(self.note.get_n_pages() > 1)
        self.aggiorna_titolo()
        return True

    def cambia_scheda(self, passo):
        n = self.note.get_n_pages()
        if n:
            self.note.set_current_page((self.note.get_current_page() + passo) % n)

    def _cambio_scheda(self, _nb, _pag, _num):
        GLib.idle_add(self.aggiorna_titolo)
        GLib.idle_add(self.aggiorna_stato)

    def _chiedi_salvataggio(self, doc) -> str:
        dlg = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.NONE,
            text="Salvare le modifiche a «%s»?" % doc.nome())
        dlg.format_secondary_text("Se non salvi, le modifiche vanno perse.")
        dlg.add_button("Chiudi senza salvare", 1)
        dlg.add_button("Annulla", 2)
        b = dlg.add_button("Salva", 3)
        b.get_style_context().add_class("suggested-action")
        dlg.set_default_response(3)
        r = dlg.run()
        dlg.destroy()
        return {1: "scarta", 3: "salva"}.get(r, "annulla")

    def esci(self):
        for i in reversed(range(self.note.get_n_pages())):
            doc = self.note.get_nth_page(i)
            if doc.buffer.get_modified():
                self.note.set_current_page(i)
                r = self._chiedi_salvataggio(doc)
                if r == "annulla":
                    return False
                if r == "salva" and not self._salva_documento(doc):
                    return False
        w, h = self.get_size()
        self.conf["larghezza"], self.conf["altezza"] = w, h
        salva_conf(self.conf)
        Gtk.main_quit()
        return True

    # --- file -------------------------------------------------------------
    def apri_dialogo(self):
        dlg = Gtk.FileChooserDialog(title="Apri", transient_for=self,
                                    action=Gtk.FileChooserAction.OPEN)
        dlg.add_buttons("Annulla", Gtk.ResponseType.CANCEL,
                        "Apri", Gtk.ResponseType.ACCEPT)
        dlg.set_select_multiple(True)
        doc = self.corrente()
        if doc and doc.percorso:
            dlg.set_current_folder(os.path.dirname(doc.percorso))
        f = Gtk.FileFilter(); f.set_name("File di testo")
        f.add_mime_type("text/*"); f.add_pattern("*")
        dlg.add_filter(f)
        if dlg.run() == Gtk.ResponseType.ACCEPT:
            for nome in dlg.get_filenames():
                self.apri(nome, in_coda=True)
        dlg.destroy()

    def salva(self):
        doc = self.corrente()
        return self._salva_documento(doc) if doc else False

    def _salva_documento(self, doc) -> bool:
        if not doc.percorso:
            return self._salva_come_documento(doc)
        if doc.cambiato_fuori():
            dlg = Gtk.MessageDialog(
                transient_for=self, modal=True,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK_CANCEL,
                text="Il file è cambiato sul disco dopo l'apertura")
            dlg.format_secondary_text(
                "Salvando sovrascrivi le modifiche fatte da altri programmi.")
            r = dlg.run(); dlg.destroy()
            if r != Gtk.ResponseType.OK:
                return False
        ok = doc.salva()
        if ok:
            self.aggiorna_titolo()
            self.nota("Salvato: %s" % doc.percorso)
        return ok

    def salva_come(self):
        doc = self.corrente()
        return self._salva_come_documento(doc) if doc else False

    def _salva_come_documento(self, doc) -> bool:
        dlg = Gtk.FileChooserDialog(title="Salva come", transient_for=self,
                                    action=Gtk.FileChooserAction.SAVE)
        dlg.add_buttons("Annulla", Gtk.ResponseType.CANCEL,
                        "Salva", Gtk.ResponseType.ACCEPT)
        dlg.set_do_overwrite_confirmation(True)
        if doc.percorso:
            dlg.set_current_folder(os.path.dirname(doc.percorso))
            dlg.set_current_name(doc.nome())
        else:
            dlg.set_current_folder(GLib.get_home_dir())
            dlg.set_current_name("senza-nome.txt")
        ok = False
        if dlg.run() == Gtk.ResponseType.ACCEPT:
            ok = doc.salva(dlg.get_filename())
        dlg.destroy()
        if ok:
            doc.applica_conf(self.conf, self.schema)
            self.aggiorna_titolo()
            self.aggiorna_stato()
        return ok

    def ricarica(self):
        doc = self.corrente()
        if not doc or not doc.percorso:
            return
        if doc.buffer.get_modified():
            dlg = Gtk.MessageDialog(
                transient_for=self, modal=True,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.OK_CANCEL,
                text="Ricaricare «%s» dal disco?" % doc.nome())
            dlg.format_secondary_text("Le modifiche non salvate vanno perse.")
            r = dlg.run(); dlg.destroy()
            if r != Gtk.ResponseType.OK:
                return
        riga = self._riga_cursore(doc)
        doc.carica(doc.percorso)
        self.vai_a_riga(riga)
        self.aggiorna_stato()

    def _controlla_file_esterni(self, *_a):
        """Al rientro nella finestra avvisa se il file è cambiato fuori."""
        doc = self.corrente()
        if not doc or doc.avvisato_esterno or not doc.cambiato_fuori():
            return False
        doc.avvisato_esterno = True
        if not doc.buffer.get_modified():
            riga = self._riga_cursore(doc)
            doc.carica(doc.percorso)
            self.vai_a_riga(riga)
            self.nota("«%s» è cambiato sul disco: ricaricato" % doc.nome())
        else:
            self.nota("«%s» è cambiato sul disco (hai modifiche non salvate)"
                      % doc.nome())
        return False

    def stampa(self):
        doc = self.corrente()
        if not doc:
            return
        comp = GtkSource.PrintCompositor.new_from_view(doc.vista)
        comp.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        comp.set_highlight_syntax(True)
        comp.set_print_line_numbers(1 if self.conf["numeri_riga"] else 0)
        comp.set_header_format(True, doc.nome(), None, "%d/%m/%Y")
        comp.set_print_header(True)
        comp.set_footer_format(True, None, "Pagina %N di %Q", None)
        comp.set_print_footer(True)
        op = Gtk.PrintOperation()
        op.set_job_name(doc.nome())

        def impagina(_op, ctx):
            fatto = comp.paginate(ctx)
            if fatto:
                op.set_n_pages(comp.get_n_pages())
            return fatto

        op.connect("paginate", impagina)
        op.connect("draw-page",
                   lambda _o, ctx, n: comp.draw_page(ctx, n))
        try:
            op.run(Gtk.PrintOperationAction.PRINT_DIALOG, self)
        except Exception as e:                      # noqa: BLE001
            self.avviso("Stampa non riuscita", str(e))

    # --- modifica ---------------------------------------------------------
    def annulla(self):
        doc = self.corrente()
        if doc and doc.buffer.can_undo():
            doc.buffer.undo()

    def ripeti(self):
        doc = self.corrente()
        if doc and doc.buffer.can_redo():
            doc.buffer.redo()

    def _righe_selezionate(self, buf):
        """(inizio riga, fine riga) che coprono la selezione o il cursore."""
        a, b = buf.get_selection_bounds() or (None, None)
        if a is None:
            a = b = buf.get_iter_at_mark(buf.get_insert())
        elif b.starts_line() and b.get_line() > a.get_line():
            b.backward_char()      # la selezione finisce dove inizia la riga
        inizio = buf.get_iter_at_line(a.get_line())
        fine = buf.get_iter_at_line(b.get_line())
        if not fine.ends_line():
            fine.forward_to_line_end()
        return inizio, fine

    def duplica_riga(self):
        doc = self.corrente()
        if not doc:
            return
        buf = doc.buffer
        inizio, fine = self._righe_selezionate(buf)
        testo = buf.get_text(inizio, fine, True)
        buf.begin_user_action()
        buf.insert(fine, "\n" + testo)
        buf.end_user_action()

    def elimina_riga(self):
        doc = self.corrente()
        if not doc:
            return
        buf = doc.buffer
        inizio, fine = self._righe_selezionate(buf)
        if not fine.forward_char():                 # ultima riga del file
            pass
        buf.begin_user_action()
        buf.delete(inizio, fine)
        buf.end_user_action()

    def sposta_riga(self, direzione: int):
        doc = self.corrente()
        if not doc:
            return
        buf = doc.buffer
        inizio, fine = self._righe_selezionate(buf)
        prima_riga = inizio.get_line()
        ultima_riga = fine.get_line()
        ultima_file = buf.get_line_count() - 1
        if (direzione < 0 and prima_riga == 0) or \
           (direzione > 0 and ultima_riga >= ultima_file):
            return
        colonna = buf.get_iter_at_mark(buf.get_insert()).get_line_offset()
        testo = buf.get_text(inizio, fine, True)
        taglio_fine = fine.copy()
        if not taglio_fine.forward_char():          # blocco in fondo al file
            taglio_fine = fine
            inizio.backward_char()
            testo = "\n" + testo
        buf.begin_user_action()
        buf.delete(inizio, taglio_fine)
        dest_riga = prima_riga + direzione
        if testo.startswith("\n"):
            dest = buf.get_iter_at_line(max(0, dest_riga))
            dest.forward_to_line_end()
            buf.insert(dest, testo)
            nuova = dest_riga
        else:
            dest = buf.get_iter_at_line(max(0, dest_riga))
            buf.insert(dest, testo + "\n")
            nuova = dest_riga
        it = buf.get_iter_at_line(nuova)
        it.set_line_offset(min(colonna, max(0, it.get_chars_in_line() - 1)))
        buf.place_cursor(it)
        buf.end_user_action()
        doc.vista.scroll_mark_onscreen(buf.get_insert())

    def commenta(self):
        """Commenta/decommenta le righe scelte usando il segno del linguaggio."""
        doc = self.corrente()
        if not doc:
            return
        lang = doc.buffer.get_language()
        segno = None
        if lang is not None:
            segno = (lang.get_metadata("line-comment-start") or "").strip()
        if not segno:
            segno = "#"
        buf = doc.buffer
        inizio, fine = self._righe_selezionate(buf)
        prima, ultima = inizio.get_line(), fine.get_line()
        righe = [buf.get_text(buf.get_iter_at_line(n),
                              self._fine_riga(buf, n), True)
                 for n in range(prima, ultima + 1)]
        piene = [r for r in righe if r.strip()]
        commentate = piene and all(r.lstrip().startswith(segno) for r in piene)
        buf.begin_user_action()
        for n in range(prima, ultima + 1):
            testo = buf.get_text(buf.get_iter_at_line(n),
                                 self._fine_riga(buf, n), True)
            if not testo.strip():
                continue
            rientro = len(testo) - len(testo.lstrip())
            it = buf.get_iter_at_line(n)
            it.forward_chars(rientro)
            if commentate:
                fine_segno = it.copy()
                fine_segno.forward_chars(len(segno))
                if buf.get_text(it, fine_segno, True) == segno:
                    dopo = fine_segno.copy()
                    dopo.forward_char()
                    if buf.get_text(fine_segno, dopo, True) == " ":
                        fine_segno = dopo
                    buf.delete(it, fine_segno)
            else:
                buf.insert(it, segno + " ")
        buf.end_user_action()

    @staticmethod
    def _fine_riga(buf, n):
        it = buf.get_iter_at_line(n)
        if not it.ends_line():
            it.forward_to_line_end()
        return it

    # --- ricerca ----------------------------------------------------------
    def mostra_trova(self, con_sostituisci=False):
        doc = self.corrente()
        if doc:
            a, b = doc.buffer.get_selection_bounds() or (None, None)
            if a is not None and a.get_line() == b.get_line():
                self.e_trova.set_text(doc.buffer.get_text(a, b, True))
        self.riga_sost.set_visible(con_sostituisci)
        self.trova_rivelatore.set_reveal_child(True)
        self.e_trova.grab_focus()
        self.e_trova.select_region(0, -1)
        self._aggiorna_ricerca()

    def mostra_sostituisci(self):
        self.mostra_trova(con_sostituisci=True)

    def nascondi_trova(self):
        self.trova_rivelatore.set_reveal_child(False)
        doc = self.corrente()
        if doc:
            doc.ricerca.set_highlight(False)
            doc.vista.grab_focus()

    def _aggiorna_ricerca(self):
        doc = self.corrente()
        if not doc:
            return
        testo = self.e_trova.get_text()
        cfg = doc.ricerca_cfg
        cfg.set_case_sensitive(self.chk_maiuscole.get_active())
        cfg.set_at_word_boundaries(self.chk_parola.get_active())
        cfg.set_regex_enabled(self.chk_regex.get_active())
        cfg.set_search_text(testo or None)
        doc.ricerca.set_highlight(bool(testo))
        ctx = self.box_trova.get_style_context()
        GLib.timeout_add(120, self._conta_occorrenze, doc, ctx)

    def _conta_occorrenze(self, doc, ctx):
        if doc is not self.corrente():
            return False
        n = doc.ricerca.get_occurrences_count()
        testo = self.e_trova.get_text()
        if not testo:
            self.lbl_occorrenze.set_text("")
            ctx.remove_class("vesper-nulla")
        elif n < 0:
            self.lbl_occorrenze.set_text("...")     # conteggio in corso
        else:
            self.lbl_occorrenze.set_text("%d risultati" % n if n != 1
                                         else "1 risultato")
            (ctx.add_class if n == 0 else ctx.remove_class)("vesper-nulla")
        return False

    def _cerca(self, avanti=True):
        doc = self.corrente()
        if not doc or not self.e_trova.get_text():
            return
        buf = doc.buffer
        sel = buf.get_selection_bounds()
        if sel:
            partenza = sel[1] if avanti else sel[0]
        else:
            partenza = buf.get_iter_at_mark(buf.get_insert())
        trovato = _cerca_da(doc.ricerca, partenza, avanti)
        if trovato is None:
            self.nota("Nessuna occorrenza di «%s»" % self.e_trova.get_text())
            return
        a, b = trovato
        buf.select_range(a, b)
        doc.vista.scroll_to_iter(a, 0.15, False, 0, 0)

    def trova_avanti(self):
        if not self.trova_rivelatore.get_reveal_child():
            self.mostra_trova()
            return
        self._cerca(True)

    def trova_indietro(self):
        if not self.trova_rivelatore.get_reveal_child():
            self.mostra_trova()
            return
        self._cerca(False)

    def sostituisci(self):
        doc = self.corrente()
        if not doc or not self.e_trova.get_text():
            return
        sel = doc.buffer.get_selection_bounds()
        nuovo = self.e_sost.get_text()
        if sel:
            try:
                _sostituisci_uno(doc.ricerca, sel[0], sel[1], nuovo)
            except Exception:                       # noqa: BLE001
                pass
        self._cerca(True)

    def sostituisci_tutto(self):
        doc = self.corrente()
        if not doc or not self.e_trova.get_text():
            return
        try:
            n = doc.ricerca.replace_all(self.e_sost.get_text(), -1)
        except Exception as e:                      # noqa: BLE001
            self.avviso("Sostituzione non riuscita", str(e))
            return
        self.nota("%d sostituzioni" % n)

    # --- navigazione ------------------------------------------------------
    def _riga_cursore(self, doc) -> int:
        it = doc.buffer.get_iter_at_mark(doc.buffer.get_insert())
        return it.get_line() + 1

    def vai_a_riga(self, riga: int):
        doc = self.corrente()
        if not doc or riga < 1:
            return False
        it = doc.buffer.get_iter_at_line(min(riga - 1,
                                             doc.buffer.get_line_count() - 1))
        doc.buffer.place_cursor(it)
        doc.vista.scroll_to_iter(it, 0.25, False, 0, 0)
        doc.vista.grab_focus()
        return False

    def dialogo_vai_a_riga(self):
        doc = self.corrente()
        if not doc:
            return
        dlg = Gtk.Dialog(title="Vai a riga", transient_for=self, modal=True)
        dlg.add_buttons("Annulla", Gtk.ResponseType.CANCEL,
                        "Vai", Gtk.ResponseType.ACCEPT)
        dlg.set_default_response(Gtk.ResponseType.ACCEPT)
        spin = Gtk.SpinButton.new_with_range(1, doc.buffer.get_line_count(), 1)
        spin.set_value(self._riga_cursore(doc))
        spin.set_activates_default(True)
        box = dlg.get_content_area()
        box.set_border_width(12); box.set_spacing(8)
        lab = Gtk.Label(label="Riga (1 - %d):" % doc.buffer.get_line_count())
        lab.set_xalign(0)
        box.pack_start(lab, False, False, 0)
        box.pack_start(spin, False, False, 0)
        dlg.show_all()
        if dlg.run() == Gtk.ResponseType.ACCEPT:
            self.vai_a_riga(int(spin.get_value()))
        dlg.destroy()

    # --- aspetto e impostazioni ------------------------------------------
    def applica_conf(self):
        self.schema = _schema_colore(_chiaro())
        for i in range(self.note.get_n_pages()):
            self.note.get_nth_page(i).applica_conf(self.conf, self.schema)

    def imposta_tab(self, n: int):
        self.conf["larghezza_tab"] = n
        salva_conf(self.conf)
        self.applica_conf()

    def zoom(self, verso: int):
        fd = Pango.FontDescription(self.conf["font"])
        base = Pango.FontDescription(DEFAULTS["font"]).get_size() / Pango.SCALE
        punti = fd.get_size() / Pango.SCALE or base
        if verso == 0:
            punti = base
        else:
            punti = max(6, min(48, punti + verso))
        fd.set_size(int(punti * Pango.SCALE))
        self.conf["font"] = fd.to_string()
        salva_conf(self.conf)
        for i in range(self.note.get_n_pages()):
            self.note.get_nth_page(i).applica_font(self.conf["font"])
        self.nota("Carattere: %.0f pt" % punti)

    def dialogo_font(self):
        dlg = Gtk.FontChooserDialog(title="Carattere dell'editor",
                                    transient_for=self)
        dlg.set_font(self.conf["font"])
        try:
            dlg.set_filter_func(
                lambda famiglia, _faccia: famiglia.is_monospace())
        except Exception:                           # noqa: BLE001
            pass
        if dlg.run() == Gtk.ResponseType.OK:
            self.conf["font"] = dlg.get_font()
            salva_conf(self.conf)
            for i in range(self.note.get_n_pages()):
                self.note.get_nth_page(i).applica_font(self.conf["font"])
        dlg.destroy()

    def dialogo_linguaggio(self):
        doc = self.corrente()
        if not doc:
            return
        lm = GtkSource.LanguageManager.get_default()
        lingue = sorted(
            (lm.get_language(i) for i in (lm.get_language_ids() or [])),
            key=lambda l: (l.get_section() or "", l.get_name() or ""))
        dlg = Gtk.Dialog(title="Linguaggio", transient_for=self, modal=True)
        dlg.add_buttons("Annulla", Gtk.ResponseType.CANCEL,
                        "Applica", Gtk.ResponseType.ACCEPT)
        dlg.set_default_size(360, 460)
        store = Gtk.ListStore(str, str)
        store.append(["Testo semplice", ""])
        for l in lingue:
            store.append(["%s - %s" % (l.get_section(), l.get_name()),
                          l.get_id()])
        tree = Gtk.TreeView(model=store, headers_visible=False)
        tree.append_column(Gtk.TreeViewColumn("", Gtk.CellRendererText(),
                                              text=0))
        attuale = doc.buffer.get_language()
        for i, riga in enumerate(store):
            if riga[1] == (attuale.get_id() if attuale else ""):
                tree.get_selection().select_path(Gtk.TreePath.new_from_indices([i]))
                tree.scroll_to_cell(Gtk.TreePath.new_from_indices([i]),
                                    None, True, 0.4, 0)
                break
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.add(tree)
        dlg.get_content_area().pack_start(sw, True, True, 0)
        tree.connect("row-activated",
                     lambda *_a: dlg.response(Gtk.ResponseType.ACCEPT))
        dlg.show_all()
        if dlg.run() == Gtk.ResponseType.ACCEPT:
            model, it = tree.get_selection().get_selected()
            if it:
                ident = model[it][1]
                doc.buffer.set_language(lm.get_language(ident) if ident else None)
                self.aggiorna_stato()
        dlg.destroy()

    def schermo_intero(self):
        if self.get_window() and (self.get_window().get_state()
                                  & Gdk.WindowState.FULLSCREEN):
            self.unfullscreen()
        else:
            self.fullscreen()

    # --- barre e messaggi -------------------------------------------------
    def aggiorna_titolo(self):
        doc = self.corrente()
        self.set_title(("%s - %s" % (doc.titolo(), APP_NAME)) if doc
                       else APP_NAME)
        return False

    def aggiorna_stato(self):
        doc = self.corrente()
        if not doc:
            return False
        buf = doc.buffer
        it = buf.get_iter_at_mark(buf.get_insert())
        pezzi = ["Riga %d, colonna %d" % (it.get_line() + 1,
                                          it.get_line_offset() + 1)]
        sel = buf.get_selection_bounds()
        if sel:
            n = sel[1].get_offset() - sel[0].get_offset()
            pezzi.append("%d caratteri scelti" % n)
        self.lbl_pos.set_text("   ".join(pezzi))
        lang = buf.get_language()
        self.lbl_lingua.set_text(lang.get_name() if lang else "Testo semplice")
        self.lbl_info.set_text("%s   %d righe   %s"
                               % (doc.codifica.upper(), buf.get_line_count(),
                                  "modificato" if buf.get_modified() else "salvato"))
        self.aggiorna_titolo()
        return False

    def nota(self, testo: str):
        """Messaggio breve nella barra di stato (torna da solo allo stato)."""
        self.lbl_info.set_text(testo)
        GLib.timeout_add_seconds(4, self.aggiorna_stato)

    def avviso(self, titolo: str, corpo: str = ""):
        dlg = Gtk.MessageDialog(transient_for=self, modal=True,
                                message_type=Gtk.MessageType.ERROR,
                                buttons=Gtk.ButtonsType.CLOSE, text=titolo)
        if corpo:
            dlg.format_secondary_text(corpo)
        dlg.run()
        dlg.destroy()

    def _trascinati(self, _w, _ctx, _x, _y, dati, _info, ora):
        for uri in (dati.get_uris() or []):
            percorso = Gio.File.new_for_uri(uri).get_path()
            if percorso:
                self.apri(percorso, in_coda=True)
        Gtk.drag_finish(_ctx, True, False, ora)


# ---------------------------------------------------------------------------
def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    if argv and argv[0] in ("-h", "--help", "aiuto"):
        print("uso: vesper-editor [+RIGA] [FILE...]\n"
              "  +RIGA   posiziona il cursore su quella riga del primo file\n"
              "Scorciatoie: Ctrl+Maiusc+H dentro il programma.")
        return 0
    riga = None
    file_da_aprire = []
    for a in argv:
        if a.startswith("+") and a[1:].isdigit():
            riga = int(a[1:])
        else:
            file_da_aprire.append(a)
    GtkSource.init() if hasattr(GtkSource, "init") else None
    win = Editor(file_da_aprire, riga)
    win.connect("destroy", lambda _w: Gtk.main_quit())
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
