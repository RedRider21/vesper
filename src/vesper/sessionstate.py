# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Stato del desktop PRIMA della sessione Vesper, per poterlo rimettere com'era.

Alcune impostazioni non sono di Vesper: sono dell'UTENTE e le condividono
tutti gli ambienti desktop installati sulla stessa macchina.

- `~/.config/gtk-3.0/settings.ini` e `~/.gtkrc-2.0`: tema e icone di ogni
  applicazione GTK, XFCE e Cinnamon compresi.
- gsettings di marco/metacity (tema delle decorazioni, disposizione dei
  pulsanti, scorciatoie): **gsettings e dconf ignorano HOME**, scrivono
  sempre nella configurazione della sessione reale passando dal bus.

Vesper le tocca perché è un ambiente desktop e deve vestirsi, ma le tocca
solo quando È la sessione attiva (`VESPER_SESSION=1`, che imposta
`vesper-session`) e ne salva prima il valore: all'uscita rimette tutto com'era,
così tornando in XFCE o in Cinnamon l'utente ritrova il suo desktop.

    python3 -m vesper.sessionstate salva       all'avvio della sessione
    python3 -m vesper.sessionstate ripristina  all'uscita
    python3 -m vesper.sessionstate mostra      cosa c'è nel file di stato
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from vesper import paths

# Il file vive nella NOSTRA configurazione: se l'utente disinstalla Vesper e
# cancella ~/.config/vesper, si porta via anche questo.
STATO = paths.config("stato-precedente.json")

# File dell'utente che Vesper riscrive per vestirsi.
FILE_UTENTE = (
    Path.home() / ".config" / "gtk-3.0" / "settings.ini",
    Path.home() / ".gtkrc-2.0",
)

# Chiavi gsettings toccate da Vesper: (schema, chiave).
# marco = MATE, metacity = GNOME storico; le scorciatoie hanno 12 posti fissi.
CHIAVI_GSETTINGS = [
    ("org.mate.interface", "gtk-theme"),
    ("org.mate.interface", "icon-theme"),
    ("org.gnome.desktop.interface", "gtk-theme"),
    ("org.gnome.desktop.interface", "icon-theme"),
    ("org.mate.Marco.general", "theme"),
    ("org.mate.Marco.general", "button-layout"),
    ("org.gnome.desktop.wm.preferences", "theme"),
    ("org.gnome.desktop.wm.preferences", "button-layout"),
    ("org.mate.Marco.keybinding-commands", "command-%d"),
    ("org.mate.Marco.global-keybindings", "run-command-%d"),
]
POSTI_SCORCIATOIE = 12


def _gsettings_get(schema: str, chiave: str) -> str | None:
    if not shutil.which("gsettings"):
        return None
    try:
        r = subprocess.run(["gsettings", "get", schema, chiave],
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def _gsettings_set(schema: str, chiave: str, valore: str) -> bool:
    if not shutil.which("gsettings"):
        return False
    # `gsettings get` restituisce il valore quotato ('Mint-Y'): `set` lo
    # riaccetta così com'è, quindi si rimette esattamente quello che c'era.
    try:
        r = subprocess.run(["gsettings", "set", schema, chiave, valore],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=5)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _chiavi_da_salvare() -> list[tuple[str, str]]:
    fuori = []
    for schema, chiave in CHIAVI_GSETTINGS:
        if "%d" in chiave:
            fuori += [(schema, chiave % n) for n in range(1, POSTI_SCORCIATOIE + 1)]
        else:
            fuori.append((schema, chiave))
    return fuori


def salva(forza: bool = False) -> int:
    """Fotografa lo stato attuale. Non sovrascrive una fotografia già presente:
    se la sessione precedente non è stata chiusa bene, il valore BUONO è
    quello vecchio, non quello lasciato da Vesper."""
    if STATO.exists() and not forza:
        print("vesper-sessionstate: stato già salvato, non lo tocco (%s)" % STATO)
        return 0

    dati: dict = {"file": {}, "gsettings": {}}
    for f in FILE_UTENTE:
        try:
            dati["file"][str(f)] = f.read_text(encoding="utf-8")
        except FileNotFoundError:
            dati["file"][str(f)] = None          # non c'era: andrà rimosso
        except OSError as e:
            print("vesper-sessionstate: non leggo %s (%s)" % (f, e),
                  file=sys.stderr)

    for schema, chiave in _chiavi_da_salvare():
        val = _gsettings_get(schema, chiave)
        if val is not None:
            dati["gsettings"]["%s %s" % (schema, chiave)] = val

    paths.ensure_config()
    try:
        STATO.write_text(json.dumps(dati, indent=1, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    except OSError as e:
        print("vesper-sessionstate: non scrivo %s (%s)" % (STATO, e),
              file=sys.stderr)
        return 1
    print("vesper-sessionstate: salvati %d file e %d valori gsettings"
          % (len(dati["file"]), len(dati["gsettings"])))
    return 0


def ripristina() -> int:
    """Rimette il desktop com'era prima della sessione Vesper."""
    try:
        dati = json.loads(STATO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0                                  # niente da rimettere

    for nome, contenuto in (dati.get("file") or {}).items():
        f = Path(nome)
        try:
            if contenuto is None:
                if f.exists():
                    f.unlink()                    # prima non c'era
            else:
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(contenuto, encoding="utf-8")
        except OSError as e:
            print("vesper-sessionstate: non ripristino %s (%s)" % (f, e),
                  file=sys.stderr)

    for chiave, valore in (dati.get("gsettings") or {}).items():
        schema, _, nome = chiave.partition(" ")
        if schema and nome:
            _gsettings_set(schema, nome, valore)

    try:
        STATO.unlink()
    except OSError:
        pass
    print("vesper-sessionstate: desktop precedente ripristinato")
    return 0


def _gsettings_reset(schema: str, chiave: str) -> bool:
    if not shutil.which("gsettings"):
        return False
    try:
        r = subprocess.run(["gsettings", "reset", schema, chiave],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=5)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def ripara() -> int:
    """Rimette ai valori predefiniti le impostazioni che Vesper tocca.

    Serve a chi ha provato una versione di Vesper che scriveva senza salvare
    prima (fino alla 0.4.1): non c'è una fotografia da cui tornare indietro,
    quindi si fa `gsettings reset`, che riporta ogni chiave al valore della
    distribuzione — su Linux Mint il suo tema e le sue scorciatoie.

    Se una fotografia c'è, si preferisce quella: è il valore esatto di prima.
    """
    if STATO.exists():
        print("vesper-sessionstate: c'è una fotografia dello stato precedente, "
              "uso quella")
        return ripristina()

    fatti = 0
    for schema, chiave in _chiavi_da_salvare():
        if _gsettings_reset(schema, chiave):
            fatti += 1
    print("vesper-sessionstate: riportate ai valori della distribuzione %d "
          "impostazioni" % fatti)

    # Nei file GTK si tolgono SOLO le righe che scrive Vesper: il resto è
    # dell'utente (su XFCE, per esempio, .gtkrc-2.0 include .gtkrc-xfce).
    nostre = ("gtk-theme-name", "gtk-icon-theme-name")
    for f in FILE_UTENTE:
        try:
            righe = f.read_text(encoding="utf-8").splitlines(True)
        except OSError:
            continue
        restano = [r for r in righe
                   if not r.strip().lstrip("#").strip().startswith(nostre)]
        if len(restano) != len(righe):
            try:
                f.write_text("".join(restano), encoding="utf-8")
                print("vesper-sessionstate: tolte %d righe da %s"
                      % (len(righe) - len(restano), f))
            except OSError as e:
                print("vesper-sessionstate: non scrivo %s (%s)" % (f, e),
                      file=sys.stderr)
    print("Rientra nella tua sessione (MATE, XFCE, Cinnamon) per vedere il "
          "risultato.")
    return 0


# Blocco che il Centro di Controllo scriveva in ~/.config/openbox/autostart
_AS_BEGIN = "# >>> Vesper autostart utente (Centro di Controllo)"
_AS_END = "# <<< Vesper autostart utente"


def migra() -> int:
    """Porta via da casa dell'utente ciò che le versioni <= 0.4.1 ci hanno
    lasciato: il blocco di autostart dentro ~/.config/openbox/autostart.

    Il contenuto finisce in ~/.config/vesper/autostart (che è quello che
    Vesper esegue davvero) e il file dell'utente torna come prima.
    """
    vecchio = Path.home() / ".config" / "openbox" / "autostart"
    try:
        righe = vecchio.read_text(encoding="utf-8").splitlines(True)
    except OSError:
        return 0
    dentro, nostre, restano = False, [], []
    for r in righe:
        t = r.strip()
        if t == _AS_BEGIN:
            dentro = True
            continue
        if t == _AS_END:
            dentro = False
            continue
        (nostre if dentro else restano).append(r)
    if not nostre:
        return 0

    nostro = paths.config("autostart")
    paths.ensure_config()
    try:
        prima = nostro.read_text(encoding="utf-8") if nostro.exists() else ""
        if _AS_BEGIN not in prima:
            nostro.write_text(prima + _AS_BEGIN + "\n" + "".join(nostre)
                              + _AS_END + "\n", encoding="utf-8")
        testo = "".join(restano)
        if testo.strip():
            vecchio.write_text(testo, encoding="utf-8")
        else:
            vecchio.unlink()                  # era solo roba nostra
        print("vesper-sessionstate: autostart migrato in %s e tolto da %s"
              % (nostro, vecchio))
    except OSError as e:
        print("vesper-sessionstate: migrazione non riuscita (%s)" % e,
              file=sys.stderr)
        return 1
    return 0


def mostra() -> int:
    try:
        print(STATO.read_text(encoding="utf-8"))
    except OSError:
        print("nessuno stato salvato (%s)" % STATO)
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "mostra"
    if cmd == "salva":
        return salva(forza="--forza" in argv)
    if cmd == "ripristina":
        return ripristina()
    if cmd == "mostra":
        return mostra()
    if cmd == "ripara":
        return ripara()
    if cmd == "migra":
        return migra()
    print("uso: python3 -m vesper.sessionstate "
          "{salva|ripristina|ripara|migra|mostra}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
