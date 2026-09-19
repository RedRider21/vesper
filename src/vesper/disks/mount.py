# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Montaggio dischi: l'unico punto in cui Vesper tocca un disco.

Scelte di comportamento:

  1. NIENTE automount: ogni montaggio nasce da un clic dell'utente. Chi vuole
     il montaggio automatico dei supporti rimovibili installa udisks2 e il suo
     agente; Vesper non lo fa di nascosto.
  2. In LETTURA E SCRITTURA di default (mount_rw), come ci si aspetta da un
     desktop quando si collega una chiavetta. Resta `mount_ro()` per montare
     in SOLA LETTURA quando serve davvero.
  3. Opzioni sempre attive: `nosuid` e `nodev`, perché un disco altrui non deve
     poter portare binari setuid o nodi di device.

Elevazione: si passa da doas/sudo/pkexec, il primo disponibile.
"""
import os
import re
import shutil
import subprocess

try:
    from vesper.i18n import t as _t
except Exception:                # noqa: BLE001
    def _t(key, **kw):           # fallback: non rompe mai i messaggi
        return key

# Radice dei punti di montaggio creati da noi. Sotto /media (non /mnt) per non
# pestare i piedi a chi monta a mano.
RADICE = "/media/vesper"

# nosuid,nodev: difese minime su un disco che arriva da fuori. Niente noatime
# (serviva a non alterare i tempi di accesso di un reperto: qui non è il caso).
_OPZIONI_BASE = "nosuid,nodev"
_SICURO = re.compile(r"^[A-Za-z0-9._-]+$")


def _priv(args, input_text=None, timeout=60):
    """Esegue un comando da root via doas. Ritorna (ok, output)."""
    if os.geteuid() != 0:
        for elevatore in ("doas", "sudo", "pkexec"):
            if shutil.which(elevatore):
                args = [elevatore] + args
                break
    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           input=input_text, timeout=timeout)
        return (r.returncode == 0, (r.stdout + r.stderr).strip())
    except (OSError, subprocess.SubprocessError) as e:
        return (False, str(e))


def _nome_punto(node):
    """Nome della cartella di mount: etichetta se pulita, altrimenti il device.

    L'etichetta arriva dal disco ALTRUI: va trattata come non fidata, quindi
    accettiamo solo caratteri innocui (niente '/', niente '..').
    """
    cand = (node.label or "").strip()
    if not cand or not _SICURO.match(cand):
        cand = node.name
    return cand


def punto_di_mount(node):
    return os.path.join(RADICE, _nome_punto(node))


def mount_ro(node):
    """Monta in SOLA LETTURA. Ritorna (ok, messaggio)."""
    return _monta(node, scrittura=False)


def mount_rw(node):
    """Monta in lettura e scrittura: è il modo normale su un desktop."""
    return _monta(node, scrittura=True)


def _monta(node, scrittura):
    if node.mounted:
        return (True, _t("mnt.already_mounted") % node.mountpoint)
    if node.is_swap:
        return (False, _t("mnt.swap"))
    if not node.fstype:
        return (False, _t("mnt.no_fs") % node.path)

    punto = punto_di_mount(node)
    # Collisione: due partizioni con la STESSA etichetta (es. due NTFS "Windows")
    # mapperebbero sulla stessa cartella e la seconda si monterebbe SOPRA la
    # prima, nascondendola. Se il punto e' gia' un mountpoint attivo, ripiego
    # sul nome del device (sempre univoco).
    if os.path.ismount(punto):
        punto = os.path.join(RADICE, node.name)
    ok, msg = _priv(["mkdir", "-p", punto])
    if not ok:
        return (False, _t("mnt.mkdir_fail") % (punto, msg))

    opz = ("rw," if scrittura else "ro,") + _OPZIONI_BASE
    ok, msg = _priv(["mount", "-o", opz, node.path, punto])
    if ok:
        return (True, punto)

    # ntfs: se il kernel non ha ntfs3, ci pensa ntfs-3g (FUSE). Riproviamo
    # esplicitamente cosi' l'errore che mostriamo e' quello vero.
    if node.fstype in ("ntfs", "ntfs3") and shutil.which("ntfs-3g"):
        ok2, msg2 = _priv(["ntfs-3g", "-o", opz, node.path, punto])
        if ok2:
            return (True, punto)
        msg = msg2 or msg
    _priv(["rmdir", punto])
    return (False, msg or _t("mnt.mount_fail"))


def smonta(node):
    """Smonta. Rimuove anche la cartella se l'avevamo creata noi."""
    if not node.mounted:
        return (True, _t("mnt.not_mounted"))
    ok, msg = _priv(["umount", node.mountpoint])
    if not ok:
        return (False, msg or _t("mnt.umount_fail"))
    if node.mountpoint.startswith(RADICE + "/"):
        _priv(["rmdir", node.mountpoint])
    return (True, _t("mnt.unmounted"))


def write_protect(path, attiva):
    """Protezione in scrittura a livello di BLOCCO (`blockdev --setro`).

    Agisce sotto al filesystem: con questa attiva nessun montaggio, nemmeno in
    scrittura, riesce a modificare il dispositivo. Utile quando si vuole essere
    certi di non toccare il contenuto di un disco altrui.
    """
    flag = "--setro" if attiva else "--setrw"
    ok, msg = _priv(["blockdev", flag, path])
    return (ok, msg or (_t("mnt.protected") if attiva else _t("mnt.prot_removed")))


def luks_apri(path, nome, passphrase):
    """Apre un volume LUKS. In SOLA LETTURA (--readonly), coerente col resto.

    La passphrase passa da STDIN, mai negli argomenti: in argv sarebbe visibile
    a chiunque con un 'ps' (stessa regola di vesper-users e del PSK WiFi).
    """
    if not _SICURO.match(nome or ""):
        return (False, _t("mnt.bad_volname"))
    return _priv(["cryptsetup", "open", "--readonly", "--key-file=-", path, nome],
                 input_text=passphrase)


def luks_chiudi(nome):
    if not _SICURO.match(nome or ""):
        return (False, _t("mnt.bad_volname"))
    return _priv(["cryptsetup", "close", nome])
