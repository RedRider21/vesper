# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Dove va la memoria: quanto occupa Vesper e quanto il resto del sistema.

Si misura il **PSS** (Proportional Set Size), non l'RSS: le librerie condivise
— e GTK è grossa — compaiono nell'RSS di OGNI processo che le usa, quindi
sommare gli RSS gonfia il totale. Il PSS assegna a ogni processo la sua quota
e la somma torna con la memoria davvero occupata.

Il dato che mostra il pannello ("RAM %") è 1 - MemAvailable/MemTotal, cioè la
memoria NON disponibile per nuovi programmi: comprende tutto il sistema (X,
servizi, tmpfs), non solo Vesper. Questo comando spacca quel numero.
"""
from __future__ import annotations

import os
import sys

MIB = 1024.0


def _meminfo() -> dict[str, float]:
    d = {}
    try:
        with open("/proc/meminfo") as f:
            for riga in f:
                chiave, _, resto = riga.partition(":")
                try:
                    d[chiave] = float(resto.split()[0])      # kB
                except (IndexError, ValueError):
                    pass
    except OSError:
        pass
    return d


def pss_vesper() -> float:
    """Memoria (PSS, in kB) dei soli processi del desktop.

    Si legge prima la cmdline (file piccolo) e si apre smaps_rollup solo per i
    processi che ci interessano: sul pannello gira ogni tanto, deve costare
    poco.
    """
    tot = 0.0
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open("/proc/%s/cmdline" % pid, "rb") as f:
                cmd = f.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
            if not cmd or not _e_di_vesper(cmd):
                continue
            with open("/proc/%s/smaps_rollup" % pid) as f:
                for riga in f:
                    if riga.startswith("Pss:"):
                        tot += float(riga.split()[1])
                        break
        except (OSError, ValueError, IndexError):
            continue
    return tot


def _processi() -> list[tuple[float, int, str]]:
    """[(pss_kb, pid, cmdline)] per i processi leggibili."""
    out = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            pss = 0.0
            with open("/proc/%s/smaps_rollup" % pid) as f:
                for riga in f:
                    if riga.startswith("Pss:"):
                        pss = float(riga.split()[1])
                        break
            with open("/proc/%s/cmdline" % pid, "rb") as f:
                cmd = f.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
        except (OSError, ValueError, IndexError):
            continue                                  # processo finito o non nostro
        if pss > 0 and cmd:
            out.append((pss, int(pid), cmd))
    return out


def _e_di_vesper(cmd: str) -> bool:
    """True se il processo è del desktop. Si guarda il COMANDO, non l'intera
    riga: altrimenti basta lavorare in una cartella chiamata vesper/ perché
    una shell qualunque finisca nel conto."""
    pezzi = cmd.split()
    if not pezzi:
        return False
    exe = os.path.basename(pezzi[0])
    if exe in ("openbox", "marco", "metacity", "picom", "dunst"):
        return True
    if exe.startswith("vesper-"):
        return True
    if "-m" in pezzi:                                  # python3 -m vesper.panel
        i = pezzi.index("-m")
        if i + 1 < len(pezzi) and pezzi[i + 1].startswith("vesper"):
            return True
    return any(os.path.basename(p).startswith("vesper-") for p in pezzi[1:3])


def _riga(etichetta: str, kb: float, tot_kb: float) -> str:
    quota = (100.0 * kb / tot_kb) if tot_kb else 0.0
    return "  %-34s %8.1f MiB  %5.1f%%" % (etichetta, kb / MIB, quota)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    tutto = "--tutto" in argv or "--all" in argv

    mi = _meminfo()
    totale = mi.get("MemTotal", 0.0)
    disp = mi.get("MemAvailable", mi.get("MemFree", 0.0))
    usata = totale - disp
    cache = mi.get("Cached", 0.0) + mi.get("Buffers", 0.0)
    shmem = mi.get("Shmem", 0.0)                       # tmpfs e memoria condivisa
    slab = mi.get("Slab", 0.0)                         # strutture del kernel

    proc = _processi()
    nostri = [p for p in proc if _e_di_vesper(p[2])]
    altri = [p for p in proc if not _e_di_vesper(p[2])]
    pss_nostri = sum(p[0] for p in nostri)
    pss_altri = sum(p[0] for p in altri)

    print("Memoria della macchina")
    print("  totale %.1f MiB   non disponibile %.1f MiB (%.0f%%)   libera per i "
          "programmi %.1f MiB"
          % (totale / MIB, usata / MIB,
             (100.0 * usata / totale) if totale else 0.0, disp / MIB))
    print("  (il pannello mostra la stessa percentuale: è tutto il sistema, non "
          "solo Vesper)")
    print()
    print("Di cosa è fatta")
    print(_riga("desktop Vesper (%d processi)" % len(nostri), pss_nostri, totale))
    print(_riga("altri programmi (%d processi)" % len(altri), pss_altri, totale))
    print(_riga("cache dei file (si libera da sé)", cache, totale))
    print(_riga("tmpfs e memoria condivisa", shmem, totale))
    print(_riga("strutture del kernel (slab)", slab, totale))
    print()
    print("Processi di Vesper (PSS: quota propria, librerie condivise divise)")
    for pss, pid, cmd in sorted(nostri, reverse=True):
        print("  %8.1f MiB  %-7d %s" % (pss / MIB, pid, cmd[:58]))
    print("  %8.1f MiB  TOTALE" % (pss_nostri / MIB))

    if tutto:
        print()
        print("Altri processi, dal più grosso")
        for pss, pid, cmd in sorted(altri, reverse=True)[:25]:
            print("  %8.1f MiB  %-7d %s" % (pss / MIB, pid, cmd[:58]))
    else:
        print()
        print("I primi consumatori fuori da Vesper")
        for pss, pid, cmd in sorted(altri, reverse=True)[:5]:
            print("  %8.1f MiB  %-7d %s" % (pss / MIB, pid, cmd[:58]))
        print("  (elenco completo: vesper-ram --tutto)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
