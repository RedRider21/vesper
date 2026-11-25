#!/usr/bin/env python3
"""Genera le SKIN colore del pannello di Vesper (barra + menu + popup).

Ogni skin e' un file CSS statico in
  data/panel-themes/<id>.css
che sovrascrive SOLO le classi del pannello (.vesper-panel*, .vesper-popup,
menu, .vesper-menu-strip). Vengono caricate a priorita' piu' alta dell'accent
del preset, quindi una skin a palette FISSA rende la barra indipendente dal
preset di aspetto. La skin speciale "profile" NON e' un file: assenza di skin =
base + accent del preset.

Uso:  python3 tools/make-panel-themes.py     (rigenera i .css)
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "panel-themes")

# id -> palette. Chiavi colore:
#   bg   sfondo barra            pop  sfondo popup/menu
#   border bordi/separatori      text testo principale
#   dim  testo tenue             accent colore d'accento (icone, menu, attivo)
#   on_accent testo su fondo accent (pager attivo)
#   strip (3 stop del gradiente della banda verticale del menu)  brand testo banda
THEMES = {
    "hud": {
        "name": "HUD Cyan (fisso)",
        "bg": "#0a1a26", "pop": "#0a1a26", "border": "#1a3a52",
        "text": "#c8f5ff", "dim": "#5a8a9a", "accent": "#00e5ff",
        "on_accent": "#050a14",
        "strip": ("#03070f", "#00334a", "#00e5ff"), "brand": "#eafcff",
    },
    "dark": {
        "name": "Grigio scuro",
        "bg": "#1e1e1e", "pop": "#252525", "border": "#3a3a3a",
        "text": "#e6e6e6", "dim": "#8a8a8a", "accent": "#7aa2f7",
        "on_accent": "#0b0b0b",
        "strip": ("#161616", "#2a2a2a", "#7aa2f7"), "brand": "#ffffff",
    },
    "light": {
        "name": "Chiaro",
        "bg": "#f2f2f2", "pop": "#ffffff", "border": "#cfcfcf",
        "text": "#222222", "dim": "#6a6a6a", "accent": "#1a73e8",
        "on_accent": "#ffffff",
        "strip": ("#e6e6e6", "#c9d9f5", "#1a73e8"), "brand": "#0b3d91",
    },
    "nord": {
        "name": "Nord",
        "bg": "#2e3440", "pop": "#3b4252", "border": "#4c566a",
        "text": "#eceff4", "dim": "#81a1c1", "accent": "#88c0d0",
        "on_accent": "#2e3440",
        "strip": ("#2b303b", "#3b4252", "#88c0d0"), "brand": "#eceff4",
    },
    "solarized": {
        "name": "Solarized Dark",
        "bg": "#002b36", "pop": "#073642", "border": "#586e75",
        "text": "#eee8d5", "dim": "#93a1a1", "accent": "#2aa198",
        "on_accent": "#002b36",
        "strip": ("#00212b", "#073642", "#2aa198"), "brand": "#fdf6e3",
    },
    "matrix": {
        "name": "Terminal Green",
        "bg": "#000000", "pop": "#071a07", "border": "#0f3f0f",
        "text": "#33ff66", "dim": "#1f8f3f", "accent": "#33ff66",
        "on_accent": "#001100",
        "strip": ("#000000", "#052905", "#33ff66"), "brand": "#99ffaa",
    },
    "amber": {
        "name": "Retro Amber",
        "bg": "#140d00", "pop": "#1c1400", "border": "#4a3600",
        "text": "#ffb000", "dim": "#a06f00", "accent": "#ffb000",
        "on_accent": "#140d00",
        "strip": ("#0a0700", "#2a1e00", "#ffb000"), "brand": "#ffd27f",
    },
    "contrast": {
        "name": "Alto contrasto",
        "bg": "#000000", "pop": "#000000", "border": "#ffffff",
        "text": "#ffffff", "dim": "#cccccc", "accent": "#ffff00",
        "on_accent": "#000000",
        "strip": ("#000000", "#333300", "#ffff00"), "brand": "#ffff00",
    },
    "black": {
        "name": "Nero",
        "bg": "#000000", "pop": "#0a0a0a", "border": "#2e2e2e",
        "text": "#eaeaea", "dim": "#8a8a8a", "accent": "#ffffff",
        "on_accent": "#000000",
        "strip": ("#000000", "#0e0e0e", "#ffffff"), "brand": "#ffffff",
    },
    "white": {
        "name": "Bianco",
        "bg": "#ffffff", "pop": "#ffffff", "border": "#d4d4d4",
        "text": "#1a1a1a", "dim": "#707070", "accent": "#111111",
        "on_accent": "#ffffff",
        "strip": ("#e8e8e8", "#f3f3f3", "#111111"), "brand": "#111111",
    },
}

TEMPLATE = """\
/* name: {name} */
/* Vesper - skin colore pannello (auto-generato da tools/make-panel-themes.py).
   Palette FISSA: ignora l'accent del preset. NON modificare a mano. */
.vesper-panel {{ background-color:{bg}; border-top:1px solid {border}; }}
.vesper-panel.vesper-panel-top {{ border-top:none; border-bottom:1px solid {border}; }}
.vesper-panel button {{ color:{text}; }}
.vesper-panel button:hover {{ background-color:{hover}; border-color:{border}; }}
.vesper-panel button:active {{ background-color:{active}; }}
.vesper-panel button image {{ color:{accent}; }}
.vesper-panel button.vesper-icon:hover image {{ color:{text}; }}
.vesper-panel button.vesper-menu {{ color:{accent}; }}
.vesper-panel button.vesper-menu image {{ color:{accent}; }}
.vesper-panel button.vesper-launcher image {{ color:{accent}; }}
.vesper-panel button.vesper-task {{ color:{dim}; }}
.vesper-panel button.vesper-task:hover {{ color:{text}; }}
.vesper-panel button.vesper-task-active {{ color:{accent}; background-color:{hover}; border-color:{border}; }}
.vesper-panel button.vesper-pager-btn {{ color:{dim}; border-color:{border}; }}
.vesper-panel button.vesper-pager-btn:hover {{ color:{text}; }}
.vesper-panel button.vesper-pager-active {{ color:{on_accent}; background-color:{accent}; border-color:{accent}; }}
.vesper-panel label.vesper-clock {{ color:{text}; }}
.vesper-panel label.vesper-clock-date {{ color:{dim}; }}
.vesper-panel separator {{ background-color:{border}; }}
.vesper-popup, .vesper-popup.background {{ background-color:{pop}; border:1px solid {border}; }}
menu, .menu, menu.background {{ background-color:{pop}; color:{text}; border:1px solid {border}; }}
menu menuitem {{ color:{text}; }}
menu menuitem:hover {{ background-color:{hover}; }}
popover.vesper-startmenu, popover.vesper-startmenu.background {{ background-color:{pop}; border:1px solid {border}; }}
popover.vesper-startmenu > arrow {{ background-color:{strip1}; border:1px solid {border}; }}
.vesper-menu-strip {{ background-image: linear-gradient(to top, {strip0}, {strip1} 45%, {strip2}); border-right:1px solid {border}; }}
.vesper-menu-strip label.brand {{ color:{brand}; }}
.vesper-menu-strip label.brand-sub {{ color:{brand}; }}
.vesper-startmenu-list button.vesper-menu-item {{ color:{text}; }}
/* Colore del TESTO di TUTTE le voci menu (lista E footer esci/riavvia/spegni):
   il CSS base forza le label a un colore chiaro (button.vesper-menu-item label),
   che sulla skin "Chiaro" sparirebbe sul fondo bianco. Sovrascriviamo con lo
   stesso selettore (stessa specificita', ma priorita' skin piu' alta). */
button.vesper-menu-item label {{ color:{text}; }}
.vesper-startmenu-list button.vesper-menu-item:hover {{ background-color:{hover}; }}
.vesper-startmenu-list button.vesper-menu-item:hover label {{ color:{accent}; }}
/* TUTTE le icone del menu start seguono la skin (righe app, categorie,
   e il FOOTER esci/riavvia/spegni). NB: il menu e' una Gtk.Window (classe
   .vesper-popup) col contenuto in .vesper-startmenu, NON un elemento <popover>:
   quindi i selettori DEVONO essere per-CLASSE (element-agnostici), altrimenti
   il footer e altre parti restano col colore dell'accent del profilo. */
.vesper-startmenu button image,
.vesper-startmenu-list button image,
.vesper-startmenu-footer button image,
.vesper-popup button image {{ color:{accent}; }}
.vesper-startmenu-list label {{ color:{text}; }}
button.vesper-menu-cat, label.vesper-menu-cat {{ color:{dim}; }}
button.vesper-menu-cat:hover {{ color:{accent}; border-left-color:{accent}; }}
button.vesper-app-item {{ color:{text}; }}
button.vesper-app-item:hover {{ background-color:{hover}; }}
button.vesper-app-item:hover label {{ color:{accent}; }}
entry.vesper-menu-search {{ background-color:{pop}; color:{text}; border:1px solid {border}; }}
entry.vesper-menu-search image {{ color:{dim}; }}
entry.vesper-menu-search:focus {{ border-color:{accent}; }}
/* --- CONTENUTO dei POPUP dei widget del pannello (wifi/audio/batteria/
   bluetooth/calendario/schermi) --- Questi popup sono finestre
   .vesper-popup: il loro TESTO usa i colori del tema SCURO base (label chiare,
   valori chiari, accenti ciano) che sulle skin CHIARE spariscono. Qui lo
   adeguiamo alla palette della skin. NB: le voci del menu start (anch'esse in
   .vesper-popup) hanno regole piu' specifiche che restano valide. */
.vesper-popup {{ color:{text}; }}
.vesper-popup label {{ color:{text}; }}
.vesper-popup .vesper-val {{ color:{text}; }}
.vesper-popup .vesper-key, .vesper-popup .vesper-card-title, .vesper-popup .vesper-eyebrow {{ color:{accent}; }}
.vesper-popup .vesper-headerbar label.title {{ color:{accent}; }}
.vesper-popup .vesper-headerbar label.subtitle {{ color:{dim}; }}
.vesper-popup .vesper-dt-row label {{ color:{dim}; }}
.vesper-popup calendar {{ color:{text}; }}
.vesper-popup calendar.header, .vesper-popup calendar.button,
.vesper-popup calendar.highlight {{ color:{accent}; }}
.vesper-popup calendar:indeterminate {{ color:{dim}; }}
"""


def _rgba(hexcol, alpha):
    h = hexcol.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return "rgba(%d,%d,%d,%.2f)" % (r, g, b, alpha)


# COORDINAZIONE (da NexusSec): la skin colora anche l'INTERNO di tutte le
# finestre di Vesper (Centro di Controllo, sessione, popup Wi-Fi/Bluetooth/
# audio, ...), non solo barra e menu. Stesse classi del CSS base
# (vesper/common.py), a priorita' piu' alta.
CONTENUTO = """
/* --- interno delle finestre di Vesper (coordinazione) ---
   Tutto e' limitato a window:not(.vesper-panel): la barra e il suo menu hanno le
   loro regole sopra (in GTK3 la priorita' del foglio vince sulla specificita',
   una regola generica qui coprirebbe i colori della barra). */
window:not(.vesper-panel), dialog {{ background-color:{win}; color:{text}; }}
window:not(.vesper-panel) .vesper-headerbar {{ background-color:{bg}; color:{text}; border-bottom:1px solid {accent}; }}
window:not(.vesper-panel) .vesper-headerbar label.title {{ color:{accent}; }}
window:not(.vesper-panel) .vesper-headerbar label.subtitle {{ color:{dim}; }}
window:not(.vesper-panel) .vesper-footer {{ background-color:{win}; color:{dim}; border-top:1px solid {border}; }}
window:not(.vesper-panel) .vesper-section {{ color:{accent}; border-bottom:1px solid {border}; }}
window:not(.vesper-panel) .vesper-key, window:not(.vesper-panel) .vesper-card-title, window:not(.vesper-panel) frame > label {{ color:{accent}; }}
window:not(.vesper-panel) .vesper-val, window:not(.vesper-panel) radiobutton, window:not(.vesper-panel) checkbutton, window:not(.vesper-panel) combobox {{ color:{text}; }}
window:not(.vesper-panel) .vesper-tile, window:not(.vesper-panel) .vesper-card {{ background-color:{card}; color:{text}; border:1px solid {border}; }}
window:not(.vesper-panel) .vesper-tile label {{ color:{text}; }}
window:not(.vesper-panel) .vesper-tile:hover {{ background-color:{hover}; border-color:{accent}; }}
window:not(.vesper-panel) .vesper-tile-badge {{ background-color:{hover}; }}
window:not(.vesper-panel) .vesper-tile-badge image, window:not(.vesper-panel) spinner {{ color:{accent}; }}
window:not(.vesper-panel) textview, window:not(.vesper-panel) textview text, window:not(.vesper-panel) treeview {{ background-color:{card}; color:{text}; caret-color:{accent}; }}
window:not(.vesper-panel) treeview:selected {{ background-color:{active}; color:{text}; }}
window:not(.vesper-panel) treeview header button {{ background-color:{bg}; color:{accent}; border-bottom:1px solid {border}; }}
window:not(.vesper-panel) button {{ background-color:{card}; color:{text}; border:1px solid {border}; }}
window:not(.vesper-panel) button:hover {{ background-color:{hover}; border-color:{accent}; }}
window:not(.vesper-panel) button:active, window:not(.vesper-panel) button:checked {{ background-color:{accent}; color:{on_accent}; }}
window:not(.vesper-panel) button.vesper-primary {{ background-color:{active}; border-color:{accent}; color:{accent}; }}
window:not(.vesper-panel) button.vesper-menu-item {{ background-color:transparent; border-color:transparent; }}
window:not(.vesper-panel) button.vesper-menu-item:hover {{ background-color:{hover}; }}
window:not(.vesper-panel) entry {{ background-color:{card}; color:{text}; border:1px solid {border}; caret-color:{accent}; }}
window:not(.vesper-panel) entry:focus {{ border-color:{accent}; }}
window:not(.vesper-panel) progressbar > trough, window:not(.vesper-panel) switch {{ background-color:{card}; border:1px solid {border}; }}
window:not(.vesper-panel) progressbar > trough > progress, window:not(.vesper-panel) levelbar block.filled, window:not(.vesper-panel) switch:checked slider {{ background-color:{accent}; }}
window:not(.vesper-panel) switch:checked {{ background-color:{active}; border-color:{accent}; }}
window:not(.vesper-panel) switch slider {{ background-color:{dim}; }}
window:not(.vesper-panel) notebook header {{ background-color:{bg}; }}
window:not(.vesper-panel) notebook tab {{ color:{dim}; }}
window:not(.vesper-panel) notebook tab:checked {{ color:{accent}; background-color:{card}; box-shadow: inset 0 -2px {accent}; }}
window:not(.vesper-panel) frame > border {{ border:1px solid {border}; }}
/* Le ETICHETTE dentro pulsanti, caselle e menu hanno una regola propria nel
   CSS di base: senza dichiararle qui vince quella (ereditare dal genitore
   conta meno) e con una skin chiara su un preset scuro il testo restava
   chiaro su chiaro (pulsanti OK/Annulla, menu a tendina). */
window:not(.vesper-panel) label {{ color:{text}; }}
window:not(.vesper-panel) button label, window:not(.vesper-panel) combobox button, window:not(.vesper-panel) combobox cellview {{ color:{text}; }}
window:not(.vesper-panel) button:active label, window:not(.vesper-panel) button:checked label {{ color:{on_accent}; }}
window:not(.vesper-panel) spinbutton, window:not(.vesper-panel) spinbutton entry {{ background-color:{card}; color:{text}; caret-color:{accent}; }}
window:not(.vesper-panel) spinbutton button {{ background-color:{card}; color:{text}; border-color:{border}; }}
window:not(.vesper-panel) menu, window:not(.vesper-panel) .menu {{ background-color:{pop}; color:{text}; border:1px solid {border}; }}
window:not(.vesper-panel) menuitem label {{ color:{text}; }}
window:not(.vesper-panel) menuitem:hover {{ background-color:{hover}; }}
/* calendario (popup dell'orologio, impostazioni data/ora) */
window:not(.vesper-panel) calendar {{ background-color:{card}; color:{text}; border:1px solid {border}; }}
window:not(.vesper-panel) calendar.header {{ background-color:{bg}; color:{accent}; border:none; }}
window:not(.vesper-panel) calendar.button {{ color:{accent}; }}
window:not(.vesper-panel) calendar.highlight {{ color:{accent}; }}
window:not(.vesper-panel) calendar:indeterminate {{ color:{dim}; }}
window:not(.vesper-panel) calendar:selected {{ background-color:{accent}; color:{on_accent}; }}
"""


def _anche_dialoghi(css):
    """Ogni selettore 'window:not(.vesper-panel) X' vale anche per 'dialog X':
    in GTK3 le Gtk.Dialog hanno come nome CSS "dialog", non "window", e
    restavano fuori (finestra della lingua: testo chiaro su chiaro)."""
    out = []
    for riga in css.splitlines():
        if "{{" in riga and "window:not(.vesper-panel)" in riga.split("{{", 1)[0]:
            sel, resto = riga.split("{{", 1)
            parti = [x.strip() for x in sel.split(",") if x.strip()]
            extra = ["dialog" + x[len("window:not(.vesper-panel)"):]
                     for x in parti if x.startswith("window:not(.vesper-panel)")]
            extra = [x for x in extra if x != "dialog" and x not in parti]
            riga = ", ".join(parti + extra) + " {{" + resto
        out.append(riga)
    return "\n".join(out)


def _luce(hexcol):
    h = hexcol.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def main():
    os.makedirs(OUT, exist_ok=True)
    for tid, p in THEMES.items():
        chiara = _luce(p["bg"]) > 0.5
        win = p.get("win") or p["bg"]
        card = p.get("card") or p["pop"]
        css = (TEMPLATE + _anche_dialoghi(CONTENUTO) + "/* tono: %s */\n" % ("chiaro" if chiara else "scuro")).format(
            win=win, card=card,
            name=p["name"], bg=p["bg"], pop=p["pop"], border=p["border"],
            text=p["text"], dim=p["dim"], accent=p["accent"],
            on_accent=p["on_accent"], brand=p["brand"],
            hover=_rgba(p["accent"], 0.14), active=_rgba(p["accent"], 0.24),
            strip0=p["strip"][0], strip1=p["strip"][1], strip2=p["strip"][2],
        )
        with open(os.path.join(OUT, tid + ".css"), "w") as f:
            f.write(css)
        print("generato", tid + ".css", "(" + p["name"] + ")")
    print("skin in", os.path.normpath(OUT))


if __name__ == "__main__":
    main()
