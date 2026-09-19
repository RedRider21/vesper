# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""vesper-launcherd - il servizio che tiene GTK «caldo».

Un processo residente importa gi/GTK e i moduli del desktop UNA volta sola,
apre il display e gira il suo `Gtk.main()`. Le richieste arrivano su un socket
UNIX sorvegliato dal main loop: la finestra viene creata DENTRO questo
processo, quindi niente nuovo interprete e niente re-import. Su un disco lento
(live, VM, chiavetta) e' la differenza fra «si apre» e «aspetta».

Perche' non con la fork: dopo che GLib/gio hanno avviato i loro thread, il
figlio di una fork si pianta. Si lavora in-process e basta.

Cosa passa di qui: Centro di Controllo (e le sue viste), preset di aspetto,
file manager, dischi. NON l'editor ne' i lettori multimediali: l'editor puo'
avere documenti non salvati e i lettori portano dentro le pipeline native di
GStreamer; se il servizio cadesse, si porterebbe dietro anche loro.

Robustezza:
- chiudere una finestra NON spegne il servizio (si scollega `Gtk.main_quit`);
- ogni apertura e' protetta: una vista che esplode non abbatte il servizio;
- se qualcuno riesce comunque a fermare il main loop, lo si riavvia;
- se il servizio non c'e', i comandi `vesper-*` partono nel modo normale.

Uso:  vesper-launcherd [--prewarm | --no-prewarm]
      vesper-launcherd --stop | --status
"""
import os
import socket
import sys
import time
import traceback
from pathlib import Path

os.environ.setdefault("GTK_IM_MODULE", "gtk-im-context-simple")

import gi                                                    # noqa: E402
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
try:
    gi.require_version("GdkPixbuf", "2.0")
except ValueError:
    pass
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf          # noqa: E402,F401
try:
    from gi.repository import Pango                          # noqa: E402,F401
except Exception:                                            # noqa: BLE001
    pass

from vesper import paths                                     # noqa: E402,F401
from vesper import common                                    # noqa: E402
from vesper.launcher.client import chiedi, socket_path       # noqa: E402

# app -> (modulo da importare, funzione che apre la finestra)
APP_SUPPORTATE = ("cc", "profile", "files", "disks")
# Cosa vale la pena scaldare da soli, appena il servizio e' libero: sono i
# moduli grossi, quelli che all'apertura fanno aspettare.
PREWARM = ("vesper.control_center.views", "vesper.control_center.main",
           "vesper.profiles.selector", "vesper.filemanager.window")


def _log(msg: str) -> None:
    sys.stderr.write("vesper-launcherd: %s\n" % msg)
    sys.stderr.flush()


def _scollega_quit(win) -> None:
    """Toglie `Gtk.main_quit` dai segnali della finestra: qui il main loop e'
    condiviso, chiudere una finestra non deve spegnere il servizio."""
    try:
        win.disconnect_by_func(Gtk.main_quit)
    except Exception:                                        # noqa: BLE001
        pass


def _rileggi_lingua() -> None:
    """Il servizio e' residente e la lingua si puo' cambiare a sessione
    avviata: si azzera la memoria di vesper.i18n cosi' ogni nuova finestra
    rilegge quella attiva."""
    try:
        from vesper import i18n
        for nome in ("_active", "_lang", "_current"):
            if hasattr(i18n, nome):
                setattr(i18n, nome, None)
        for nome in ("_cache", "_strings"):
            cache = getattr(i18n, nome, None)
            if isinstance(cache, dict):
                cache.clear()
    except Exception:                                        # noqa: BLE001
        pass


# ---------------------------------------------------------------- aperture
def _apri_cc(args):
    from vesper.control_center import main as cc
    cc.apply_css()
    viste = getattr(cc, "VIEW_MAP", {})
    if args and args[0] in viste:
        viste[args[0]]()                     # vista singola: si chiude da se'
        return
    win = cc.build_window()
    _scollega_quit(win)
    win.show_all()


def _apri_profile(_args):
    from vesper.profiles import selector
    common.apply_css()
    win = selector.Selector()
    _scollega_quit(win)
    win.show_all()


def _apri_files(args):
    from vesper.filemanager.window import FileWindow
    dove = Path(paths.HOME)
    if args:
        scelto = Path(args[0]).expanduser()
        if scelto.is_dir():
            dove = scelto
        elif scelto.parent.is_dir():
            dove = scelto.parent
    win = FileWindow(dove)
    _scollega_quit(win)
    win.show_all()


def _apri_disks(_args):
    from vesper.disks import view
    win = view.open_disks()                  # apre gia' la finestra
    _scollega_quit(win)


APERTURE = {"cc": _apri_cc, "profile": _apri_profile,
            "files": _apri_files, "disks": _apri_disks}


def _apri(app, args):
    """Apre l'app richiesta (chiamata da idle_add, quindi nel main loop)."""
    _rileggi_lingua()
    inizio = time.monotonic()
    try:
        APERTURE[app](args)
    except Exception:                                        # noqa: BLE001
        traceback.print_exc()
        sys.stderr.flush()
        return False
    # Il tempo finisce nel log: serve a capire se il servizio sta davvero
    # facendo il suo mestiere (la prima apertura paga l'import, le altre no).
    _log("%s aperta in %d ms" % (app, (time.monotonic() - inizio) * 1000))
    return False                             # una volta sola


def _scalda(elenco):
    """Importa un modulo per volta quando il servizio non ha altro da fare."""
    if not elenco:
        return False
    nome = elenco[0]
    try:
        __import__(nome)
    except Exception as e:                                   # noqa: BLE001
        _log("non riesco a scaldare %s (%s)" % (nome, e))
    GLib.idle_add(_scalda, elenco[1:])
    return False


# ---------------------------------------------------------------- socket
def _su_richiesta(fd, _cond, srv):
    try:
        conn, _ = srv.accept()
    except OSError:
        return True
    try:
        dati = conn.recv(4096).decode("utf-8", "replace").strip()
    except OSError:
        dati = ""
    risposta = b"ok\n"
    pezzi = dati.split()
    if not pezzi or pezzi[0] == "ping":
        pass
    elif pezzi[0] == "stop":
        GLib.idle_add(Gtk.main_quit)
    elif pezzi[0] in APERTURE:
        GLib.idle_add(_apri, pezzi[0], pezzi[1:])
    else:
        risposta = b"no\n"
    for azione in (lambda: conn.sendall(risposta), conn.close):
        try:
            azione()
        except OSError:
            pass
    return True                              # continua ad ascoltare


def _in_ascolto() -> bool:
    """C'e' gia' un servizio vivo? (un socket orfano non conta)."""
    return chiedi("ping", timeout=1.0)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    percorso = socket_path()

    if "--status" in argv:
        vivo = _in_ascolto()
        print("in ascolto su %s" % percorso if vivo
              else "non in esecuzione (%s)" % percorso)
        return 0 if vivo else 1
    if "--stop" in argv:
        if not chiedi("stop", timeout=2.0):
            print("vesper-launcherd: non era in esecuzione")
            return 1
        print("vesper-launcherd: fermato")
        return 0
    if "-h" in argv or "--help" in argv:
        print(__doc__.strip())
        return 0

    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        _log("serve una sessione grafica (DISPLAY)")
        return 1
    if _in_ascolto():
        _log("c'e' gia' un servizio in ascolto su %s" % percorso)
        return 0

    try:
        os.unlink(percorso)                  # socket rimasto da una sessione
    except OSError:
        pass
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        srv.bind(percorso)
    except OSError as e:
        _log("non riesco ad ascoltare su %s (%s)" % (percorso, e))
        return 1
    try:
        os.chmod(percorso, 0o600)            # solo l'utente che l'ha avviato
    except OSError:
        pass
    srv.listen(8)
    srv.setblocking(False)
    GLib.io_add_watch(srv.fileno(), GLib.IO_IN, _su_richiesta, srv)

    common.apply_css()                       # tema pronto per la prima finestra
    if "--no-prewarm" not in argv:
        GLib.idle_add(_scalda, list(PREWARM))
    _log("pronto su %s" % percorso)

    # Se qualcosa riesce comunque a fermare il main loop (una finestra che
    # chiama main_quit di suo), lo si riavvia invece di lasciare il servizio
    # sordo. Il contatore evita di girare a vuoto se il display e' sparito.
    tentativi = 0
    while tentativi < 20:
        Gtk.main()
        if Gdk.Display.get_default() is None:
            break
        tentativi += 1
    try:
        os.unlink(percorso)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
