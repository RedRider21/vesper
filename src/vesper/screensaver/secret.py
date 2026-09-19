# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Gestione della password del salvaschermo (blocco schermo).

La password NON e' salvata in chiaro: si conserva solo un hash PBKDF2-HMAC-SHA256
con salt casuale in ~/.config/vesper/screensaver.secret (permessi 600). Sola
stdlib (hashlib) - nessuna dipendenza extra.

Formato del file: pbkdf2_sha256$<iterazioni>$<salt_hex>$<hash_hex>
"""
import hashlib
import hmac
import os

SECRET = os.path.expanduser("~/.config/vesper/screensaver.secret")
_ITER = 120000


def has_password():
    """True se e' stata impostata una password di sblocco."""
    try:
        return os.path.getsize(SECRET) > 0
    except OSError:
        return False


def set_password(pw):
    """Imposta (o cambia) la password. pw vuota -> rimuove la password."""
    d = os.path.dirname(SECRET)
    os.makedirs(d, exist_ok=True)
    if not pw:
        clear_password()
        return
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, _ITER)
    line = "pbkdf2_sha256$%d$%s$%s" % (_ITER, salt.hex(), dk.hex())
    # scrittura con permessi ristretti (600)
    fd = os.open(SECRET, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(line + "\n")


def clear_password():
    try:
        os.remove(SECRET)
    except OSError:
        pass


def verify(pw):
    """True se pw corrisponde alla password memorizzata."""
    try:
        with open(SECRET) as f:
            stored = f.read().strip()
    except OSError:
        return False
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, int(iters))
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False
