# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Gestione energia della sessione Vesper (servizio `vesper-power`).

Cosa fa (tutto regolabile in ~/.config/vesper/power.conf o dal Centro di
Controllo -> Energia):
  - BLOCCA LO SCHERMO PRIMA DELLA SOSPENSIONE: prende da logind un inibitore
    "delay" sul sonno; quando arriva PrepareForSleep avvia
    `vesper-screensaver --blocca` e solo dopo rilascia l'inibitore, cosi' al
    risveglio lo schermo e' gia' bloccato. Serve una password di sblocco
    (Centro di Controllo -> Salvaschermo).
  - SPEGNE LO SCHERMO dopo N minuti di inattivita' (DPMS via xset).
  - SOSPENDE dopo N minuti di inattivita' (facoltativo, spento di serie).
  - BATTERIA CRITICA: sotto la soglia, in scarica, avvisa e dopo un minuto
    sospende / iberna / spegne (o niente).
Coperchio e tasto di accensione restano a logind (impostazioni di sistema).

Isolamento: gira SOLO dentro la sessione Vesper (paths.sessione_vesper), una
istanza per volta, e si chiude da se' quando la sessione finisce. Parla solo
con logind (bus di sistema) e col display della sessione.

    vesper-power              avvia il servizio (lo fa vesper-session)
    vesper-power --ricarica   rilegge power.conf (SIGHUP al servizio)
    vesper-power --stato      stato e impostazioni
    vesper-power --stop       ferma il servizio
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os
import signal
import subprocess
import sys
from pathlib import Path

from vesper import paths

CONF = paths.config("power.conf")
PIDFILE = paths.cache("power.pid")
SYSFS = Path(os.environ.get("VESPER_POWER_SYSFS", "/sys/class/power_supply"))

DEFAULT = {
    "lock_on_sleep": "1",       # blocca lo schermo prima della sospensione
    "screen_off": "10",         # minuti di inattivita' prima di spegnere lo schermo (0 = mai)
    "idle_suspend": "0",        # minuti di inattivita' prima di sospendere (0 = mai)
    "battery_critical": "5",    # percentuale critica
    "battery_action": "suspend",  # suspend | hibernate | poweroff | nothing
}
AZIONI = ("suspend", "hibernate", "poweroff", "nothing")
_METODO = {"suspend": "Suspend", "hibernate": "Hibernate", "poweroff": "PowerOff"}


def _t(chiave: str, ripiego: str) -> str:
    try:
        from vesper.i18n import t
        v = t(chiave)
        return ripiego if v == chiave else v
    except Exception:                    # noqa: BLE001
        return ripiego


# ------------------------------------------------------------ configurazione
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
    righe = ["# Energia di Vesper (Centro di Controllo -> Energia)"]
    righe += ["%s=%s" % (k, cfg.get(k, v)) for k, v in DEFAULT.items()]
    tmp = CONF.with_name(CONF.name + ".tmp")
    tmp.write_text("\n".join(righe) + "\n")
    os.replace(str(tmp), str(CONF))


def _int(cfg: dict, k: str) -> int:
    try:
        return max(0, int(cfg.get(k, DEFAULT[k])))
    except ValueError:
        return int(DEFAULT[k])


# ------------------------------------------------------------ batteria
def battery() -> tuple[int, str] | None:
    """(percentuale, stato) della prima batteria, o None se non ce n'e'."""
    try:
        voci = sorted(SYSFS.iterdir())
    except OSError:
        return None
    for d in voci:
        try:
            if (d / "type").read_text().strip() != "Battery":
                continue
            cap = int((d / "capacity").read_text().strip())
            st = (d / "status").read_text().strip()
            return cap, st
        except (OSError, ValueError):
            continue
    return None


# ------------------------------------------------------------ inattivita' (X)
class _XSSInfo(ctypes.Structure):
    _fields_ = [("window", ctypes.c_ulong), ("state", ctypes.c_int),
                ("kind", ctypes.c_int), ("til_or_since", ctypes.c_ulong),
                ("idle", ctypes.c_ulong), ("eventMask", ctypes.c_ulong)]


class Idle:
    """Millisecondi di inattivita' dall'estensione MIT-SCREEN-SAVER di X.
    Se libXss manca, idle() ritorna None e la sospensione per inattivita' resta
    spenta (lo spegnimento schermo lo fa comunque X col DPMS)."""

    def __init__(self):
        self.ok = False
        try:
            self.x11 = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
            self.xss = ctypes.CDLL(ctypes.util.find_library("Xss") or "libXss.so.1")
            self.x11.XOpenDisplay.restype = ctypes.c_void_p
            self.x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            self.x11.XDefaultRootWindow.restype = ctypes.c_ulong
            self.x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
            self.xss.XScreenSaverAllocInfo.restype = ctypes.POINTER(_XSSInfo)
            self.xss.XScreenSaverQueryInfo.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(_XSSInfo)]
            self.dpy = self.x11.XOpenDisplay(None)
            if self.dpy:
                self.info = self.xss.XScreenSaverAllocInfo()
                self.ok = True
        except (OSError, AttributeError):
            self.ok = False

    def idle(self) -> int | None:
        if not self.ok:
            return None
        root = self.x11.XDefaultRootWindow(self.dpy)
        if not self.xss.XScreenSaverQueryInfo(self.dpy, root, self.info):
            return None
        return int(self.info.contents.idle)


# ------------------------------------------------------------ DPMS
def apply_dpms(minuti: int) -> None:
    """Spegnimento dello schermo dopo `minuti` (0 = mai). Solo nella sessione
    Vesper: fuori, il display e' quello di un altro desktop."""
    if not paths.sessione_vesper():
        return
    try:
        if minuti > 0:
            s = str(minuti * 60)
            subprocess.run(["xset", "dpms", s, s, s], timeout=5)
            subprocess.run(["xset", "+dpms"], timeout=5)
        else:
            subprocess.run(["xset", "-dpms"], timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass


# ------------------------------------------------------------ servizio
class Servizio:
    def __init__(self):
        from gi.repository import GLib, Gio
        self.GLib, self.Gio = GLib, Gio
        self.loop = GLib.MainLoop()
        self.cfg = read_conf()
        self.fd_inib = -1
        self.idle = Idle()
        self.sospeso_per_idle = False
        self.critico_dal = 0          # istante del primo avviso di batteria critica
        try:
            self.bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        except Exception:                # noqa: BLE001
            self.bus = None
        self.sess_pid = self._pid_sessione()

    # --- logind ------------------------------------------------------------
    def _logind(self, metodo, args=None, tipo=None, fd=False):
        if self.bus is None:
            return None
        GLib, Gio = self.GLib, self.Gio
        try:
            if fd:
                ris, lista = self.bus.call_with_unix_fd_list_sync(
                    "org.freedesktop.login1", "/org/freedesktop/login1",
                    "org.freedesktop.login1.Manager", metodo, args,
                    GLib.VariantType(tipo) if tipo else None,
                    Gio.DBusCallFlags.NONE, -1, None, None)
                return lista.get(ris.unpack()[0])
            return self.bus.call_sync(
                "org.freedesktop.login1", "/org/freedesktop/login1",
                "org.freedesktop.login1.Manager", metodo, args,
                GLib.VariantType(tipo) if tipo else None,
                Gio.DBusCallFlags.NONE, -1, None)
        except Exception as e:           # noqa: BLE001
            print("vesper-power: logind %s: %s" % (metodo, e), file=sys.stderr)
            return None

    def prendi_inibitore(self):
        if self.fd_inib >= 0 or self.cfg.get("lock_on_sleep") != "1":
            return
        fd = self._logind("Inhibit", self.GLib.Variant("(ssss)", (
            "sleep", "Vesper",
            _t("pw.inhibit_why", "Blocco dello schermo prima della sospensione"),
            "delay")), "(h)", fd=True)
        if fd is not None and fd >= 0:
            self.fd_inib = fd

    def lascia_inibitore(self):
        if self.fd_inib >= 0:
            try:
                os.close(self.fd_inib)
            except OSError:
                pass
            self.fd_inib = -1

    def _prima_del_sonno(self, _c, _s, _p, _i, _n, params):
        verso_il_sonno = params.unpack()[0]
        if verso_il_sonno:
            if self.cfg.get("lock_on_sleep") == "1":
                try:
                    from vesper.screensaver import secret
                    if secret.has_password():
                        subprocess.Popen(["vesper-screensaver", "--blocca"],
                                         stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL,
                                         start_new_session=True)
                except Exception:        # noqa: BLE001
                    pass
            # un attimo perche' la finestra di blocco sia a schermo, poi via
            self.GLib.timeout_add(900, lambda: (self.lascia_inibitore(), False)[1])
        else:
            self.sospeso_per_idle = False
            self.prendi_inibitore()          # pronto per la prossima volta

    def esegui(self, azione: str) -> None:
        metodo = _METODO.get(azione)
        if metodo:
            self._logind(metodo, self.GLib.Variant("(b)", (False,)))

    # --- controlli periodici ---------------------------------------------------
    @staticmethod
    def _pid_sessione() -> int:
        try:
            return int(paths.SESSION_PID.read_text().split()[0])
        except (OSError, ValueError, IndexError):
            return 0

    def _sessione_viva(self) -> bool:
        return not self.sess_pid or os.path.isdir("/proc/%d" % self.sess_pid)

    def _notifica(self, titolo, testo, urgente=True):
        try:
            subprocess.Popen(["notify-send", "-a", "Vesper", "-i", "battery-caution",
                              "-u", "critical" if urgente else "normal",
                              titolo, testo],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass

    def controlla(self):
        if not self._sessione_viva():
            self.loop.quit()
            return False
        # sospensione per inattivita'
        lim = _int(self.cfg, "idle_suspend")
        ms = self.idle.idle() if lim else None
        if lim and ms is not None and ms >= lim * 60000 and not self.sospeso_per_idle:
            self.sospeso_per_idle = True     # una volta; si azzera al risveglio
            self.esegui("suspend")
        elif ms is not None and ms < 60000:
            self.sospeso_per_idle = False
        # batteria critica
        b = battery()
        soglia = _int(self.cfg, "battery_critical")
        azione = self.cfg.get("battery_action", "suspend")
        if b and b[1] == "Discharging" and b[0] <= soglia and azione in AZIONI:
            ora = self.GLib.get_monotonic_time() // 1000000
            if not self.critico_dal:
                self.critico_dal = ora
                nomi = {"suspend": _t("pw.act_suspend", "sospensione"),
                        "hibernate": _t("pw.act_hibernate", "ibernazione"),
                        "poweroff": _t("pw.act_poweroff", "spegnimento"),
                        "nothing": ""}
                testo = (_t("pw.crit_body", "Batteria al %d%%: collega l'alimentatore.") % b[0])
                if azione != "nothing":
                    testo += " " + (_t("pw.crit_then", "Tra un minuto: %s.") % nomi[azione])
                self._notifica(_t("pw.crit_title", "Batteria quasi scarica"), testo)
            elif ora - self.critico_dal >= 60 and azione != "nothing":
                self.critico_dal = ora + 600   # non riprovare per 10 minuti
                self.esegui(azione)
        elif b and b[1] != "Discharging":
            self.critico_dal = 0
        return True

    def ricarica(self, *_a):
        self.cfg = read_conf()
        apply_dpms(_int(self.cfg, "screen_off"))
        if self.cfg.get("lock_on_sleep") == "1":
            self.prendi_inibitore()
        else:
            self.lascia_inibitore()
        return True

    def avvia(self):
        GLib = self.GLib
        if self.bus is not None:
            self.bus.signal_subscribe(
                "org.freedesktop.login1", "org.freedesktop.login1.Manager",
                "PrepareForSleep", "/org/freedesktop/login1", None,
                self.Gio.DBusSignalFlags.NONE, self._prima_del_sonno)
        self.ricarica()
        GLib.timeout_add_seconds(30, self.controlla)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGHUP, self.ricarica)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM,
                             lambda: (self.loop.quit(), False)[1])
        self.loop.run()
        self.lascia_inibitore()


# ------------------------------------------------------------ istanza unica
def _pid_attivo() -> int:
    try:
        pid = int(PIDFILE.read_text().strip())
        with open("/proc/%d/cmdline" % pid, "rb") as f:
            if b"vesper.power" in f.read():
                return pid
    except (OSError, ValueError):
        pass
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    pid = _pid_attivo()
    if argv[:1] == ["--ricarica"]:
        if pid:
            os.kill(pid, signal.SIGHUP)
        return 0
    if argv[:1] == ["--stop"]:
        if pid:
            os.kill(pid, signal.SIGTERM)
        return 0
    if argv[:1] == ["--stato"]:
        cfg = read_conf()
        print("servizio: %s" % ("attivo (pid %d)" % pid if pid else "fermo"))
        for k in DEFAULT:
            print("%s=%s" % (k, cfg[k]))
        b = battery()
        print("batteria: %s" % ("%d%% %s" % b if b else "nessuna"))
        return 0
    if argv:
        print(__doc__, file=sys.stderr)
        return 2
    if not paths.sessione_vesper():
        print("vesper-power: gira solo dentro la sessione Vesper", file=sys.stderr)
        return 1
    if pid:
        return 0                          # gia' attivo
    paths.ensure_cache()
    PIDFILE.write_text(str(os.getpid()) + "\n")
    try:
        Servizio().avvia()
    finally:
        try:
            if PIDFILE.read_text().strip() == str(os.getpid()):
                PIDFILE.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
