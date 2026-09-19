# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Modello dati dei dischi - logica PURA, senza GTK.

Separato apposta dalla GUI: questo modulo si importa tal quale in Vesper come
barra laterale "Dispositivi" del file manager, senza trascinarsi dietro GTK.

REGOLA FORENSIC della distro: qui dentro non si monta e non si scrive NULLA.
L'enumerazione e' sola lettura. Il montaggio vive in mount.py ed e' sempre
esplicito (mai automatico), con "ro" come default.

Usa solo strumenti di base, presenti ovunque: lsblk, findmnt, blkid,
cryptsetup, parted. Nessun udisks2, nessun gvfs, nessuna dipendenza nuova.
"""
import json
import shutil
import subprocess

# Colonne chieste a lsblk. Tenute al minimo compatibile: le versioni recenti di
# util-linux hanno sostituito MOUNTPOINT con MOUNTPOINTS (lista), quindi se la
# prima chiamata fallisce si ripiega su un set ridotto.
_COLS = "NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINT,RM,RO,MODEL,TRAN,PARTLABEL"
_COLS_FALLBACK = "NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINT,RM,RO"

# Filesystem che sappiamo montare (informativo: serve alla GUI per dire perche'
# un montaggio non e' possibile invece di fallire in silenzio).
_MOUNTABILI = {
    "ext2", "ext3", "ext4", "vfat", "exfat", "ntfs", "ntfs3", "iso9660",
    "udf", "xfs", "btrfs", "f2fs", "squashfs", "hfsplus", "msdos",
}


def _run(args, timeout=15):
    """Esegue un comando e ne restituisce lo stdout (stringa vuota se fallisce).
    Non solleva mai: l'assenza di un tool non deve rompere l'enumerazione."""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def have(prog):
    return shutil.which(prog) is not None


def human(n):
    """Dimensione leggibile all'italiana (virgola decimale): 476,9 G."""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "-"
    for unit in ("B", "K", "M", "G", "T", "P"):
        if n < 1024 or unit == "P":
            if unit == "B":
                return "%d B" % int(n)
            return ("%.1f %s" % (n, unit)).replace(".", ",")
        n /= 1024.0
    return "-"


class Node:
    """Un dispositivo a blocchi: disco, partizione o volume LUKS aperto."""

    def __init__(self, raw, parent=None):
        self.name = raw.get("name") or ""
        self.path = raw.get("path") or ("/dev/%s" % self.name)
        self.type = raw.get("type") or ""
        self.fstype = raw.get("fstype") or ""
        self.label = raw.get("label") or raw.get("partlabel") or ""
        self.uuid = raw.get("uuid") or ""
        self.model = (raw.get("model") or "").strip()
        self.tran = raw.get("tran") or ""
        self.parent = parent
        self.children = []

        # size: intero (con -b) ma alcune versioni lo danno come stringa.
        try:
            self.size = int(raw.get("size") or 0)
        except (TypeError, ValueError):
            self.size = 0

        # mountpoint: MOUNTPOINT (stringa) oppure MOUNTPOINTS (lista).
        mp = raw.get("mountpoint")
        if not mp:
            mps = raw.get("mountpoints") or []
            mp = next((m for m in mps if m), None)
        self.mountpoint = mp or ""

        self.removable = str(raw.get("rm", "")).lower() in ("1", "true")
        self.readonly = str(raw.get("ro", "")).lower() in ("1", "true")

    # --- comodita' per la GUI -------------------------------------------
    @property
    def is_disk(self):
        return self.type == "disk"

    @property
    def is_partition(self):
        return self.type in ("part", "crypt", "lvm")

    @property
    def mounted(self):
        return bool(self.mountpoint)

    @property
    def is_luks(self):
        return self.fstype in ("crypto_LUKS", "crypto_luks")

    @property
    def is_swap(self):
        return self.fstype == "swap"

    @property
    def mountable(self):
        """Vero se ha senso proporre il montaggio (fs riconosciuto e non swap)."""
        return bool(self.fstype) and self.fstype in _MOUNTABILI

    @property
    def descrizione(self):
        """Etichetta breve per l'elenco."""
        if self.is_disk:
            base = self.model or self.name
            if self.tran:
                base = "%s (%s)" % (base, self.tran.upper())
            return base
        parti = []
        if self.fstype:
            parti.append(self.fstype)
        if self.label:
            parti.append(self.label)
        return "  ".join(parti) if parti else "(nessun filesystem)"

    def __repr__(self):
        return "<Node %s %s %s>" % (self.path, self.type, human(self.size))


def _walk(raw, parent=None):
    n = Node(raw, parent)
    for c in raw.get("children") or []:
        n.children.append(_walk(c, n))
    return n


def list_devices(include_loop=False):
    """Albero dei dispositivi a blocchi. SOLA LETTURA: non monta nulla.

    include_loop: normalmente i loop device (il modloop della live, gli
    squashfs) sono rumore e vengono esclusi.
    """
    out = _run(["lsblk", "-J", "-b", "-o", _COLS])
    if not out:
        out = _run(["lsblk", "-J", "-b", "-o", _COLS_FALLBACK])
    if not out:
        return []
    try:
        data = json.loads(out)
    except ValueError:
        return []

    nodi = []
    for raw in data.get("blockdevices") or []:
        n = _walk(raw)
        if not include_loop and n.type in ("loop", "rom") and not n.children:
            # rom senza figli = lettore CD vuoto; loop = squashfs interni.
            if n.type == "loop":
                continue
        nodi.append(n)
    return nodi


def flatten(nodi):
    """Appiattisce l'albero in una lista (disco seguito dai suoi figli)."""
    fuori = []

    def _f(n):
        fuori.append(n)
        for c in n.children:
            _f(c)

    for n in nodi:
        _f(n)
    return fuori


def find(nodi, path):
    for n in flatten(nodi):
        if n.path == path:
            return n
    return None


# --- informazioni aggiuntive (tutte in sola lettura) ---------------------

def smart(path):
    """Stato SMART del disco: dict con 'stato' e 'ore', oppure None.

    Richiede smartmontools. Su USB spesso non e' interrogabile: in quel caso
    si restituisce None e la GUI semplicemente non mostra la riga.
    """
    if not have("smartctl"):
        return None
    out = _run(["smartctl", "-H", "-A", path], timeout=20)
    if not out:
        return None
    stato, ore = None, None
    for riga in out.splitlines():
        r = riga.strip()
        if "overall-health" in r:
            stato = r.rsplit(":", 1)[-1].strip()
        elif "SMART Health Status" in r:
            stato = r.rsplit(":", 1)[-1].strip()
        elif "Power_On_Hours" in r:
            campi = r.split()
            if campi:
                try:
                    ore = int(campi[-1].split()[0])
                except (ValueError, IndexError):
                    pass
    if stato is None and ore is None:
        return None
    return {"stato": stato or "sconosciuto", "ore": ore}


def uso(mountpoint):
    """Spazio usato/libero di un filesystem montato: (usato, totale) in byte."""
    if not mountpoint:
        return None
    try:
        import os
        st = os.statvfs(mountpoint)
    except OSError:
        return None
    tot = st.f_blocks * st.f_frsize
    lib = st.f_bavail * st.f_frsize
    return (tot - lib, tot)


def protetto_in_scrittura(path):
    """Vero se il device e' in sola lettura a livello di BLOCCO (blockdev --getro).

    E' la vera protezione forense: agisce sotto al filesystem, quindi nessun
    montaggio puo' scrivere, nemmeno per sbaglio.
    """
    out = _run(["blockdev", "--getro", path])
    return out.strip() == "1"
