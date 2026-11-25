# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Montaggio automatico dei supporti rimovibili (chiavette, dischi USB, SD).

Gira dentro il servizio di sessione `vesper-power` (un processo solo, niente
memoria in piu') e passa SOLO da udisks2, come MATE e Cinnamon:
  - si montano solo i filesystem che udisks segna come "da montare in
    automatico" (Block.HintAuto) e non da ignorare o di sistema, collegati
    DOPO l'avvio della sessione; mai i dischi interni, mai quelli gia' montati;
  - punto di montaggio e opzioni li decide udisks (/media/<utente>/<nome>,
    nosuid,nodev); per i supporti rimovibili dell'utente attivo non chiede
    password (politica di udisks2);
  - le chiavette CIFRATE non si aprono da sole: un avviso rimanda a Dischi;
  - niente di nascosto: una notifica a ogni montaggio e, se attivo,
    il file manager si apre sulla cartella.
Impostazioni in ~/.config/vesper/automount.conf (enabled, open); Centro di
Controllo -> Supporti rimovibili.
"""
from __future__ import annotations

import os
import subprocess
import sys

from vesper import paths

CONF = paths.config("automount.conf")
DEFAULT = {"enabled": "1", "open": "1"}
_UD = "org.freedesktop.UDisks2"
_BLOCK = "org.freedesktop.UDisks2.Block"
_FS = "org.freedesktop.UDisks2.Filesystem"
_CRYPT = "org.freedesktop.UDisks2.Encrypted"


def _t(chiave: str, ripiego: str) -> str:
    try:
        from vesper.i18n import t
        v = t(chiave)
        return ripiego if v == chiave else v
    except Exception:                    # noqa: BLE001
        return ripiego


def read_conf() -> dict:
    cfg = dict(DEFAULT)
    try:
        for riga in CONF.read_text().splitlines():
            if "=" in riga and not riga.lstrip().startswith("#"):
                k, v = riga.split("=", 1)
                if k.strip() in DEFAULT:
                    cfg[k.strip()] = v.strip()
    except OSError:
        pass
    return cfg


def write_conf(cfg: dict) -> None:
    paths.ensure_config()
    righe = ["# Supporti rimovibili (Centro di Controllo -> Supporti rimovibili)"]
    righe += ["%s=%s" % (k, cfg.get(k, v)) for k, v in DEFAULT.items()]
    tmp = CONF.with_name(CONF.name + ".tmp")
    tmp.write_text("\n".join(righe) + "\n")
    os.replace(str(tmp), str(CONF))


def _bytes_str(v) -> str:
    """Le stringhe di udisks arrivano come array di byte chiusi da \\0."""
    if isinstance(v, (bytes, bytearray)):
        return bytes(v).rstrip(b"\0").decode(errors="replace")
    if isinstance(v, list):
        return bytes(v).rstrip(b"\0").decode(errors="replace")
    return str(v or "")


def decidi(block: dict, ha_fs: bool, ha_crypt: bool) -> str:
    """Cosa fare di un dispositivo appena comparso, dalle proprieta' del suo
    Block: "monta", "cifrato" (avvisa soltanto) oppure "" (ignora).
    Logica pura, senza D-Bus: si prova anche senza udisks."""
    if not block.get("HintAuto", False):
        return ""                         # udisks dice: non montarlo da solo
    if block.get("HintIgnore", False) or block.get("HintSystem", True):
        return ""                         # da ignorare, o disco di sistema
    if ha_crypt or block.get("IdUsage") == "crypto":
        return "cifrato"
    if not ha_fs or block.get("IdUsage") != "filesystem":
        return ""
    return "monta"


class Automount:
    """Ascolta udisks2 sul bus di sistema e monta i supporti nuovi."""

    def __init__(self, bus, GLib, Gio):
        self.bus, self.GLib, self.Gio = bus, GLib, Gio
        self.cfg = read_conf()
        self.visti = set()                # oggetti gia' gestiti
        self.sub = None

    def avvia(self) -> None:
        if self.bus is None:
            return
        self.sub = self.bus.signal_subscribe(
            _UD, "org.freedesktop.DBus.ObjectManager", "InterfacesAdded",
            "/org/freedesktop/UDisks2", None,
            self.Gio.DBusSignalFlags.NONE, self._aggiunto)

    def ricarica(self) -> None:
        self.cfg = read_conf()

    def _props(self, path: str, iface: str) -> dict:
        try:
            r = self.bus.call_sync(_UD, path, "org.freedesktop.DBus.Properties",
                                   "GetAll", self.GLib.Variant("(s)", (iface,)),
                                   self.GLib.VariantType("(a{sv})"),
                                   self.Gio.DBusCallFlags.NONE, 5000, None)
            return r.unpack()[0]
        except Exception:                # noqa: BLE001
            return {}

    def _aggiunto(self, _c, _s, _p, _i, _n, params):
        if self.cfg.get("enabled") != "1":
            return
        path, ifaces = params.unpack()
        if not path.startswith("/org/freedesktop/UDisks2/block_devices/"):
            return
        if _FS not in ifaces and _CRYPT not in ifaces:
            return
        # un attimo: le proprieta' (etichetta, tipo) arrivano subito dopo
        self.GLib.timeout_add(800, lambda: (self._gestisci(path), False)[1])

    def _gestisci(self, path: str) -> None:
        if path in self.visti:
            return
        block = self._props(path, _BLOCK)
        fs = self._props(path, _FS)
        azione = decidi(block, bool(fs),
                        bool(self._props(path, _CRYPT)))
        nome = block.get("IdLabel") or _bytes_str(block.get("PreferredDevice")) \
            or path.rsplit("/", 1)[-1]
        if azione == "cifrato":
            self.visti.add(path)
            self._notifica(_t("am.crypt_title", "Supporto cifrato collegato"),
                           _t("am.crypt_body", "%s è cifrato: aprilo da Dischi.") % nome)
            return
        if azione != "monta":
            return
        if any(fs.get("MountPoints") or []):
            return                        # l'ha gia' montato qualcun altro
        self.visti.add(path)
        try:
            r = self.bus.call_sync(_UD, path, _FS, "Mount",
                                   self.GLib.Variant("(a{sv})", ({},)),
                                   self.GLib.VariantType("(s)"),
                                   self.Gio.DBusCallFlags.NONE, 30000, None)
            dove = r.unpack()[0]
        except Exception as e:           # noqa: BLE001
            self.visti.discard(path)
            print("vesper-power: montaggio %s: %s" % (path, e), file=sys.stderr)
            self._notifica(_t("am.fail_title", "Supporto non montato"),
                           _t("am.fail_body", "%s non si può montare: provalo da Dischi.") % nome)
            return
        self._notifica(_t("am.ok_title", "Supporto collegato"),
                       _t("am.ok_body", "%s è pronto in %s") % (nome, dove))
        if self.cfg.get("open") == "1":
            try:
                subprocess.Popen(["vesper-files", dove], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
            except OSError:
                pass

    @staticmethod
    def _notifica(titolo, testo, urgente=False):
        try:
            subprocess.Popen(["notify-send", "-a", "Vesper", "-i", "drive-removable-media",
                              "-u", "normal" if not urgente else "critical",
                              titolo, testo],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass
