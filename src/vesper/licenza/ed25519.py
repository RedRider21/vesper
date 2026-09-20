# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Ed25519 (RFC 8032) in puro Python: firma e verifica, zero dipendenze.

Serve a verificare le licenze commerciali sul computer del cliente. Si usa
un'implementazione propria e non `cryptography` o PyNaCl perché Vesper non
vuole dipendenze pesanti e la verifica deve funzionare ovunque, anche su
un'installazione minimale.

Non è codice a tempo costante: va benissimo per verificare una firma su una
licenza (dati pubblici), NON per operazioni su segreti in un contesto dove
conti la resistenza ai side channel. La chiave privata sta offline, sulla
macchina di chi emette le licenze, e non tocca mai il cliente.

Correttezza verificata con i vettori di prova dell'RFC 8032 (§7.1):
`python3 -m vesper.licenza.ed25519` li esegue.
"""
from __future__ import annotations

import hashlib

# --- parametri della curva (RFC 8032, §5.1) ---------------------------------
P = 2 ** 255 - 19
L = 2 ** 252 + 27742317777372353535851937790883648493
D = (-121665 * pow(121666, P - 2, P)) % P
I = pow(2, (P - 1) // 4, P)                       # radice quadrata di -1
BY = 4 * pow(5, P - 2, P) % P


def _sha512(b: bytes) -> bytes:
    return hashlib.sha512(b).digest()


def _inv(x: int) -> int:
    return pow(x, P - 2, P)


def _x_da_y(y: int, segno: int) -> int:
    """Ricostruisce x dalla y del punto compresso."""
    yy = y * y % P
    u = (yy - 1) % P
    v = (D * yy + 1) % P
    xx = u * _inv(v) % P
    x = pow(xx, (P + 3) // 8, P)
    if (x * x - xx) % P != 0:
        x = x * I % P
    if (x * x - xx) % P != 0:
        raise ValueError("punto non sulla curva")
    if x % 2 != segno:
        x = P - x
    return x


# I punti si tengono in coordinate estese (X, Y, Z, T): niente inversioni
# modulari a ogni somma, che renderebbero la verifica lentissima.
def _somma(a, b):
    ax, ay, az, at = a
    bx, by, bz, bt = b
    A = (ay - ax) * (by - bx) % P
    B = (ay + ax) * (by + bx) % P
    C = 2 * at * bt * D % P
    dd = 2 * az * bz % P
    E = B - A
    F = dd - C
    G = dd + C
    H = B + A
    return (E * F % P, G * H % P, F * G % P, E * H % P)


def _doppio(a):
    return _somma(a, a)


def _moltiplica(punto, scalare: int):
    risultato = (0, 1, 1, 0)                       # elemento neutro
    while scalare > 0:
        if scalare & 1:
            risultato = _somma(risultato, punto)
        punto = _doppio(punto)
        scalare >>= 1
    return risultato


def _base():
    by = BY
    bx = _x_da_y(by, 0)
    return (bx, by, 1, bx * by % P)


def _comprimi(punto) -> bytes:
    x, y, z, _t = punto
    zi = _inv(z)
    x = x * zi % P
    y = y * zi % P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decomprimi(dati: bytes):
    if len(dati) != 32:
        raise ValueError("punto di 32 byte atteso")
    n = int.from_bytes(dati, "little")
    y = n & ((1 << 255) - 1)
    segno = n >> 255
    if y >= P:
        raise ValueError("coordinata y fuori campo")
    x = _x_da_y(y, segno)
    return (x, y, 1, x * y % P)


def _uguali(a, b) -> bool:
    ax, ay, az, _ = a
    bx, by, bz, _ = b
    return (ax * bz - bx * az) % P == 0 and (ay * bz - by * az) % P == 0


def _chiarifica(seme: bytes) -> tuple[int, bytes]:
    h = _sha512(seme)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8                            # azzera i 3 bit bassi
    a |= 1 << 254                                  # e impone il bit alto
    return a, h[32:]


def chiave_pubblica(seme: bytes) -> bytes:
    """Chiave pubblica (32 byte) dal seme privato (32 byte)."""
    if len(seme) != 32:
        raise ValueError("il seme privato è di 32 byte")
    a, _ = _chiarifica(seme)
    return _comprimi(_moltiplica(_base(), a))


def firma(messaggio: bytes, seme: bytes) -> bytes:
    """Firma di 64 byte del messaggio, con il seme privato."""
    a, prefisso = _chiarifica(seme)
    pub = _comprimi(_moltiplica(_base(), a))
    r = int.from_bytes(_sha512(prefisso + messaggio), "little") % L
    R = _comprimi(_moltiplica(_base(), r))
    k = int.from_bytes(_sha512(R + pub + messaggio), "little") % L
    S = (r + k * a) % L
    return R + int.to_bytes(S, 32, "little")


def verifica(messaggio: bytes, firma_: bytes, pubblica: bytes) -> bool:
    """True se la firma è valida per quel messaggio e quella chiave."""
    try:
        if len(firma_) != 64 or len(pubblica) != 32:
            return False
        R = _decomprimi(firma_[:32])
        A = _decomprimi(pubblica)
        S = int.from_bytes(firma_[32:], "little")
        if S >= L:
            return False                           # firma non canonica
        k = int.from_bytes(_sha512(firma_[:32] + pubblica + messaggio),
                           "little") % L
        sinistra = _moltiplica(_base(), S)
        destra = _somma(R, _moltiplica(A, k))
        return _uguali(sinistra, destra)
    except (ValueError, TypeError):
        return False


# --- prove (RFC 8032 §7.1) --------------------------------------------------
_VETTORI = [
    # (seme, chiave pubblica attesa, messaggio, firma attesa) in esadecimale
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
     "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
     "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
     "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
     "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
     "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
     "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac"
     "18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
]


def _prova() -> int:
    errori = 0
    for seme_hex, pub_hex, msg_hex, firma_hex in _VETTORI:
        seme = bytes.fromhex(seme_hex)
        msg = bytes.fromhex(msg_hex)
        pub = chiave_pubblica(seme)
        if pub != bytes.fromhex(pub_hex):
            print("chiave pubblica sbagliata per %s..." % seme_hex[:16])
            errori += 1
            continue
        f = firma(msg, seme)
        if f != bytes.fromhex(firma_hex):
            print("firma sbagliata per %s..." % seme_hex[:16])
            errori += 1
            continue
        if not verifica(msg, f, pub):
            print("la firma appena fatta non si verifica")
            errori += 1
            continue
        guasta = bytearray(f)
        guasta[0] ^= 1
        if verifica(msg, bytes(guasta), pub):
            print("una firma alterata risulta valida!")
            errori += 1
    print("Ed25519: %d vettori RFC 8032, %d errori" % (len(_VETTORI), errori))
    return 1 if errori else 0


if __name__ == "__main__":
    raise SystemExit(_prova())
