#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Controllo delle traduzioni: chiavi mancanti, orfane e segnaposto sbagliati.

Gira senza GTK: legge i sorgenti con una regex, quindi si puo' lanciare ovunque.

    tools/check-i18n.py            tutto
    tools/check-i18n.py ed. iv.    solo le chiavi con quei prefissi
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
SRC = RADICE / "src" / "vesper"
STR = SRC / "i18n" / "strings"
LINGUE = ("it", "en", "fr", "es", "de")
BASE = "it"                                  # lingua di riferimento

# t("chiave"), _t("chiave"), i18n.t('chiave'), label("chiave", "ripiego")
RX_USO = re.compile(
    r"""\b(?:_?t|label|label_for)\(\s*["']([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)["']""")
# negli script shell: vesper_t <chiave> 'ripiego'
RX_SHELL = re.compile(r"""\bvesper_t\s+([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)""")
ESTENSIONI = {"xml", "json", "py", "log", "sh", "txt", "png", "svg", "css",
              "desktop", "conf", "ini", "wav", "gz", "deb"}
# chiave scritta tale e quale in una tabella, fuori da una chiamata a t()
RX_LETTERALE = re.compile(r"""["']((?:app|appcat|cc|cb|dk|ed|fm|iv|k|lang|menu|mnt|
    pl|pn|pr|rc|sel|session|ss|tray|v|vd)\.[a-z0-9_]+(?:\.[a-z0-9_]+)*)["']""", re.X)
# chiavi composte a runtime: t("appcat." + nome), t("k." + tasto)
RX_PREFISSO = re.compile(
    r"""\(\s*["']([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)*\.)["']\s*\+""")
RX_SEGNA = re.compile(r"%(?:[-+ #0]*\d*(?:\.\d+)?[sdifgxX%]|[NQ])|\{[a-z_]+\}")


def sorgenti():
    """Sorgenti da scandire: il pacchetto Python e i comandi bin/ (che sono
    script Python senza estensione: anche loro traducono)."""
    for f in sorted(SRC.rglob("*.py")):
        if "__pycache__" not in f.parts:
            yield f
    for f in sorted((RADICE / "bin").glob("vesper-*")):
        if f.is_file():                      # shell e Python: traducono entrambi
            yield f


def chiavi_usate() -> tuple[dict[str, list[str]], set[str]]:
    usi: dict[str, list[str]] = {}
    prefissi: set[str] = set()
    for f in sorgenti():
        testo = f.read_text(encoding="utf-8")
        for k in RX_USO.findall(testo):
            usi.setdefault(k, []).append(str(f.relative_to(RADICE)))
        prefissi.update(RX_PREFISSO.findall(testo))
        for k in RX_SHELL.findall(testo):
            usi.setdefault(k, []).append(str(f.relative_to(RADICE)))
        # chiavi passate a una funzione da una tabella (vesper-logout) o
        # composte altrove: se la chiave compare tale e quale, e' usata
        for k in RX_LETTERALE.findall(testo):
            if k.rsplit(".", 1)[1] in ESTENSIONI:      # "rc.xml" e' un file
                continue
            usi.setdefault(k, []).append(str(f.relative_to(RADICE)))
    return usi, prefissi


def main(prefissi: list[str]) -> int:
    def interessa(k: str) -> bool:
        return not prefissi or any(k.startswith(p) for p in prefissi)

    ling = {l: json.loads((STR / (l + ".json")).read_text(encoding="utf-8"))
            for l in LINGUE}
    usi, dinamici = chiavi_usate()
    problemi = 0

    mancanti = sorted(k for k in usi if interessa(k) and k not in ling[BASE])
    for k in mancanti:
        print("MANCA in %s.json: %s   (%s)" % (BASE, k, usi[k][0]))
    problemi += len(mancanti)

    orfane = sorted(k for k in ling[BASE] if interessa(k) and k not in usi
                    and not any(k.startswith(p) for p in dinamici))
    for k in orfane:
        print("orfana (nessun sorgente la usa): %s" % k)

    for lingua in LINGUE:
        if lingua == BASE:
            continue
        for k, testo in sorted(ling[BASE].items()):
            if not interessa(k):
                continue
            altro = ling[lingua].get(k)
            if altro is None:
                print("MANCA in %s.json: %s" % (lingua, k))
                problemi += 1
                continue
            a, b = sorted(RX_SEGNA.findall(testo)), sorted(RX_SEGNA.findall(altro))
            if a != b:
                print("SEGNAPOSTO diversi %s [%s]: %s <-> %s"
                      % (k, lingua, a, b))
                problemi += 1

    n = len([k for k in ling[BASE] if interessa(k)])
    print("%d chiavi controllate, %d problemi, %d orfane" %
          (n, problemi, len(orfane)))
    return 1 if problemi else 0


if __name__ == "__main__":
    sys.exit(main([a for a in sys.argv[1:]]))
