# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Modalita' testuale di vesper-disks: usata da vesper-install e dal terminale.

Sta qui e non nella GUI perche' vesper-install e' uno script di shell e non puo'
(ne' deve) tirarsi dietro GTK. Stessa logica di model.py, altra vestizione.
"""
from __future__ import annotations

import subprocess
import sys

from vesper.disks import model


def _spazio_libero(disco):
    """Blocchi di spazio NON allocato su un disco, via parted.

    Ritorna [(inizio, fine, dimensione)] come stringhe cosi' come le riporta
    parted (con l'unita'), piu' la dimensione in byte per l'ordinamento.
    """
    try:
        r = subprocess.run(["parted", "-s", "-m", disco, "unit", "B", "print", "free"],
                           capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode != 0:
        return []
    liberi = []
    for riga in r.stdout.splitlines():
        campi = riga.strip().rstrip(";").split(":")
        # formato: numero:inizio:fine:dimensione:fs:nome:flag
        if len(campi) >= 5 and campi[4] == "free":
            try:
                ini = int(campi[1].rstrip("B"))
                fin = int(campi[2].rstrip("B"))
                dim = int(campi[3].rstrip("B"))
            except ValueError:
                continue
            # sotto i 2 GiB non ha senso proporlo come destinazione
            if dim >= 2 * 1024 ** 3:
                liberi.append((ini, fin, dim))
    return liberi


def elenco(mostra_liberi=False):
    """Stampa l'elenco leggibile di dischi e partizioni."""
    nodi = model.list_devices()
    if not nodi:
        print("  (nessun disco rilevato)")
        return 1
    for d in nodi:
        if d.type != "disk":
            continue
        # zram = RAM compressa usata come swap, non un disco su cui installare.
        if d.name.startswith("zram"):
            continue
        prot = "  [PROTETTO IN SCRITTURA]" if model.protetto_in_scrittura(d.path) else ""
        print("  %-14s %10s  %s%s" % (d.path, model.human(d.size), d.descrizione, prot))
        for p in model.flatten([d])[1:]:
            mp = ("  ->  %s" % p.mountpoint) if p.mounted else ""
            print("     %-12s %10s  %-10s %-16s%s"
                  % (p.path, model.human(p.size), p.fstype or "(nessuno)",
                     p.label or "", mp))
        if mostra_liberi:
            for ini, _fin, dim in _spazio_libero(d.path):
                print("     %-12s %10s  %s"
                      % ("(libero)", model.human(dim), "spazio non allocato a %s" % model.human(ini)))
    return 0


def elenco_partizioni_installabili():
    """Righe 'percorso<TAB>dimensione<TAB>fs<TAB>etichetta<TAB>montato' delle
    partizioni che possono ospitare un'installazione. Escluse: EFI, swap,
    quelle montate e quelle del supporto da cui stiamo girando."""
    fuori = []
    for n in model.flatten(model.list_devices()):
        if not n.is_partition or n.is_swap:
            continue
        # Senza filesystem non e' una destinazione sensata (es. la "Microsoft
        # reserved partition" da 16 MB: niente fs, troppo piccola per installarci).
        if not n.fstype:
            continue
        # Sotto i 2 GiB e' inutilizzabile come radice (stessa soglia dello spazio
        # libero): non la proponiamo.
        if n.size and n.size < 2 * 1024 ** 3:
            continue
        if n.fstype in ("vfat",) and (n.label or "").upper() in ("SYSTEM", "EFI", "ESP"):
            continue
        if n.mountpoint in ("/", "/boot", "/boot/efi"):
            continue
        fuori.append("%s\t%s\t%s\t%s\t%s"
                     % (n.path, model.human(n.size), n.fstype or "-",
                        n.label or "-", n.mountpoint or "-"))
    return fuori


def spazio_libero_righe(disco):
    """Righe 'inizio<TAB>fine<TAB>dimensione-leggibile' dello spazio libero."""
    return ["%d\t%d\t%s" % (i, f, model.human(d)) for i, f, d in _spazio_libero(disco)]


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    cmd = argv[0] if argv else "--lista"
    if cmd in ("--lista", "--list", "lista"):
        return elenco(mostra_liberi=False)
    if cmd in ("--lista-completa", "--full"):
        return elenco(mostra_liberi=True)
    if cmd in ("--partizioni",):
        for r in elenco_partizioni_installabili():
            print(r)
        return 0
    if cmd in ("--liberi",) and len(argv) > 1:
        for r in spazio_libero_righe(argv[1]):
            print(r)
        return 0
    print("uso: vesper-disks [--lista|--lista-completa|--partizioni|--liberi DISCO]",
          file=sys.stderr)
    return 2
