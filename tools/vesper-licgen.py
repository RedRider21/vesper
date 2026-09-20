#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Emissione delle licenze commerciali di Vesper. Strumento del TITOLARE.

Sta in tools/ e non viene installato da nessuna parte: gira sulla macchina di
chi emette le licenze, possibilmente senza rete, e la chiave privata non deve
mai uscire di lì.

    # una volta sola: la coppia di chiavi
    tools/vesper-licgen.py chiavi --out ~/licenze-vesper

    # per ogni cliente
    tools/vesper-licgen.py emetti --chiave ~/licenze-vesper/privata.key \\
        --cliente "Acme S.p.A." --postazioni 50 --mesi 12 \\
        --nota "contratto 2026/017" --out acme.licenza.json

    # controllo di ciò che si è emesso, o di un file ricevuto
    tools/vesper-licgen.py verifica acme.licenza.json

    # conteggio: dai rapporti che manda il cliente
    tools/vesper-licgen.py conta --licenza acme.licenza.json rapporti/*.json

La chiave privata è un file di 32 byte con permessi 600. Perderla significa
non poter più emettere licenze verificabili dalle installazioni esistenti:
copiala su due supporti diversi e tienila offline.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import secrets
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from vesper.licenza import ed25519, modello          # noqa: E402


def _scrivi_privata(percorso: Path, seme: bytes) -> None:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(percorso), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(seme)


def cmd_chiavi(args) -> int:
    out = Path(args.out).expanduser()
    priv = out / "privata.key"
    pub = out / "pubblica.hex"
    if priv.exists():
        print("c'è già una chiave privata in %s: non la sovrascrivo" % priv,
              file=sys.stderr)
        return 1
    seme = secrets.token_bytes(32)
    _scrivi_privata(priv, seme)
    pubblica = ed25519.chiave_pubblica(seme)
    pub.write_text(pubblica.hex() + "\n", encoding="utf-8")
    ident = modello.id_chiave(pubblica)
    print("chiave privata : %s  (permessi 600, tienila offline)" % priv)
    print("chiave pubblica: %s" % pub)
    print("identificativo : %s" % ident)
    print()
    print("Incolla questa riga in CHIAVI_FIDATE, dentro")
    print("src/vesper/licenza/modello.py:")
    print()
    print('    "%s": "%s",' % (ident, pubblica.hex()))
    return 0


def cmd_emetti(args) -> int:
    seme = Path(args.chiave).expanduser().read_bytes()
    if len(seme) != 32:
        print("la chiave privata deve essere di 32 byte", file=sys.stderr)
        return 1
    oggi = date.today()
    scadenza = (oggi + timedelta(days=int(args.mesi * 30.44))).isoformat() \
        if args.mesi else args.scadenza
    dati = {
        "prodotto": modello.PRODOTTO,
        "id": args.id or "VSP-%s-%s" % (oggi.year,
                                        secrets.token_hex(3).upper()),
        "cliente": args.cliente,
        "postazioni": args.postazioni,
        "emessa": oggi.isoformat(),
        "emessa_da": args.emessa_da or getpass.getuser(),
        # Segreto condiviso col cliente: sigilla i rapporti di conteggio.
        "segreto": base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
    }
    if scadenza:
        dati["scadenza"] = scadenza
    if args.nota:
        dati["nota"] = args.nota
    if args.endpoint:
        dati["endpoint"] = args.endpoint

    documento = modello.emetti(dati, seme)
    testo = json.dumps(documento, indent=1, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).write_text(testo, encoding="utf-8")
        print("licenza scritta in %s" % args.out)
    else:
        print(testo)
    print("  id          : %s" % dati["id"])
    print("  cliente     : %s" % dati["cliente"])
    print("  postazioni  : %d" % dati["postazioni"])
    print("  scadenza    : %s" % dati.get("scadenza", "nessuna"))
    return 0


def cmd_verifica(args) -> int:
    doc = json.loads(Path(args.file).read_text(encoding="utf-8"))
    chiavi = None
    if args.pubblica:
        pub = Path(args.pubblica).expanduser().read_text().strip()
        chiavi = {modello.id_chiave(bytes.fromhex(pub)): pub}
    esito = modello.verifica(doc, chiavi=chiavi)
    dati = esito.dati
    print("%s: %s" % (args.file, esito.motivo))
    for campo in ("id", "cliente", "postazioni", "emessa", "scadenza", "nota"):
        if campo in dati:
            print("  %-11s: %s" % (campo, dati[campo]))
    return 0 if esito else 1


def cmd_conta(args) -> int:
    lic = json.loads(Path(args.licenza).read_text(encoding="utf-8"))
    dati = lic.get("licenza") or {}
    segreto = dati.get("segreto", "")
    postazioni = int(dati.get("postazioni") or 0)

    validi, alterati, estranei = [], 0, 0
    for nome in args.rapporti:
        try:
            doc = json.loads(Path(nome).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            print("illeggibile, salto: %s" % nome, file=sys.stderr)
            continue
        # Può essere un rapporto singolo o un file già unito.
        elenco = ([doc] if "rapporto" in doc
                  else [{"rapporto": c, "sigillo": ""}
                        for c in doc.get("installazioni", [])])
        for r in elenco:
            corpo = r.get("rapporto") or {}
            if corpo.get("licenza") != dati.get("id"):
                estranei += 1
                continue
            if r.get("sigillo") and segreto and \
                    not modello.verifica_rapporto(r, segreto):
                alterati += 1
                continue
            validi.append(corpo)

    unico = modello.unisci_rapporti([{"rapporto": c} for c in validi])
    n = unico["conteggio"]
    print("cliente      : %s" % dati.get("cliente", "?"))
    print("licenza      : %s" % dati.get("id", "?"))
    print("dichiarate   : %d postazioni" % postazioni)
    print("contate      : %d installazioni distinte" % n)
    if alterati:
        print("ATTENZIONE   : %d rapporti col sigillo non valido" % alterati)
    if estranei:
        print("nota         : %d rapporti di un'altra licenza, ignorati"
              % estranei)
    if postazioni and n > postazioni:
        print()
        print("ECCEDENZA: %d installazioni oltre le %d concordate."
              % (n - postazioni, postazioni))
        print("Da contratto le eccedenti non sono coperte dalla licenza")
        print("commerciale e ricadono sotto AGPL: è il momento di un true-up.")
    if args.out:
        Path(args.out).write_text(json.dumps(unico, indent=1,
                                             ensure_ascii=False) + "\n",
                                  encoding="utf-8")
        print("\nriepilogo scritto in %s" % args.out)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="vesper-licgen.py",
        description="Emissione e controllo delle licenze commerciali di Vesper")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("chiavi", help="genera la coppia di chiavi (una volta)")
    p.add_argument("--out", required=True, help="cartella dove scriverle")
    p.set_defaults(func=cmd_chiavi)

    p = sub.add_parser("emetti", help="emette una licenza firmata")
    p.add_argument("--chiave", required=True, help="file della chiave privata")
    p.add_argument("--cliente", required=True)
    p.add_argument("--postazioni", type=int, required=True)
    p.add_argument("--mesi", type=int, default=12,
                   help="durata in mesi (0 = nessuna scadenza)")
    p.add_argument("--scadenza", help="data esatta AAAA-MM-GG (alternativa a --mesi)")
    p.add_argument("--id", help="identificativo della licenza (altrimenti generato)")
    p.add_argument("--nota", help="riferimento al contratto")
    p.add_argument("--emessa-da", dest="emessa_da")
    p.add_argument("--endpoint", help="URL di attivazione, se previsto dal contratto")
    p.add_argument("--out", help="file di destinazione")
    p.set_defaults(func=cmd_emetti)

    p = sub.add_parser("verifica", help="controlla un file di licenza")
    p.add_argument("file")
    p.add_argument("--pubblica", help="file con la chiave pubblica in esadecimale")
    p.set_defaults(func=cmd_verifica)

    p = sub.add_parser("conta", help="conta le installazioni dai rapporti")
    p.add_argument("--licenza", required=True)
    p.add_argument("rapporti", nargs="+")
    p.add_argument("--out", help="scrive il riepilogo unito")
    p.set_defaults(func=cmd_conta)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
