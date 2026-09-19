# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Lato client dell'avvio caldo: solo socket, niente GTK.

Tenuto minuscolo di proposito: chi lo importa (o il comando `vesper-launch`)
deve partire in pochi millisecondi, altrimenti il guadagno se ne va.
"""
import os
import socket

NOME_SOCKET = "vesper-launcherd.sock"


# I socket UNIX hanno un limite di lunghezza del percorso (108 byte su Linux,
# meno su altri Unix): oltre, bind() fallisce con "path too long".
MAX_PERCORSO = 100


def _ripiego() -> str:
    return os.path.join("/tmp", "%s-%d" % (NOME_SOCKET, os.getuid()))


def socket_path() -> str:
    """Dove ascolta il servizio. $XDG_RUNTIME_DIR e' per-utente e in tmpfs;
    senza (o se il percorso e' troppo lungo per un socket) si ripiega su /tmp
    col numero dell'utente, cosi' due utenti non si pestano i piedi."""
    forzato = os.environ.get("VESPER_LAUNCHERD_SOCK")
    if forzato:
        return forzato if len(forzato) <= MAX_PERCORSO else _ripiego()
    base = os.environ.get("XDG_RUNTIME_DIR")
    if base and os.path.isdir(base):
        scelto = os.path.join(base, NOME_SOCKET)
        if len(scelto) <= MAX_PERCORSO:
            return scelto
    return _ripiego()


def chiedi(*argomenti, timeout: float = 3.0) -> bool:
    """Chiede al servizio di aprire una finestra. True se ha preso in carico.

    False vuol dire «servizio assente o muto»: chi chiama avvia l'app nel modo
    normale. Mai un'eccezione: l'avvio caldo e' un di piu', non una dipendenza.
    """
    percorso = socket_path()
    if not argomenti or not os.path.exists(percorso):
        return False
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(percorso)
        s.sendall((" ".join(argomenti) + "\n").encode("utf-8"))
        risposta = s.recv(32)
        s.close()
    except OSError:
        return False
    return risposta.strip() == b"ok"
