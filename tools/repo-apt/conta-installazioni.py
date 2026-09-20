#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Quante macchine si aggiornano con il token di ciascun cliente.

Legge i log di accesso del server che ospita il repository APT (formato
`combined` di nginx e Apache) e conta, per ogni token, quanti indirizzi
distinti hanno scaricato gli indici o i pacchetti.

    tools/repo-apt/conta-installazioni.py /var/log/nginx/vesper-repo.access.log
    tools/repo-apt/conta-installazioni.py --giorni 30 --clienti clienti.json log*

`clienti.json` associa i token ai nomi e alle postazioni concordate:

    {"3f9a…": {"cliente": "Acme S.p.A.", "postazioni": 50}}

**Che valore ha questo numero.** Un indirizzo IP non è una macchina: dietro un
NAT aziendale cento computer escono con lo stesso indirizzo, e un portatile ne
cambia diversi in una settimana. Questo conteggio quindi **sottostima** in
azienda e sovrastima con gli indirizzi dinamici: serve come segnale, non come
prova. Il conteggio che fa fede è quello dei rapporti firmati
(`vesper-licenza --rapporto`, poi `vesper-licgen.py conta`), che identificano
la macchina e non l'indirizzo. Se i due numeri divergono molto, è lì che si
guarda.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 1.2.3.4 - - [21/Sep/2026:10:11:12 +0200] "GET /t/<token>/dists/... HTTP/1.1" 200 ...
RIGA = re.compile(
    r'^(?P<ip>\S+)\s+\S+\s+(?P<utente>\S+)\s+\[(?P<quando>[^\]]+)\]\s+'
    r'"(?P<metodo>\w+)\s+(?P<url>\S+)[^"]*"\s+(?P<stato>\d{3})')
# il token può stare nel percorso (/t/<token>/…) o essere l'utente di basic auth
TOKEN_URL = re.compile(r"/t/([A-Za-z0-9_-]{8,})/")


def _quando(testo: str):
    try:
        return datetime.strptime(testo, "%d/%b/%Y:%H:%M:%S %z")
    except ValueError:
        return None


def analizza(file: list[str], giorni: int) -> dict:
    limite = datetime.now(timezone.utc) - timedelta(days=giorni) if giorni else None
    per_token: dict[str, dict] = defaultdict(
        lambda: {"indirizzi": set(), "richieste": 0, "pacchetti": 0,
                 "prima": None, "ultima": None})
    for nome in file:
        try:
            testo = Path(nome).read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            print("salto %s (%s)" % (nome, e), file=sys.stderr)
            continue
        for riga in testo.splitlines():
            m = RIGA.match(riga)
            if not m or not m.group("stato").startswith("2"):
                continue
            quando = _quando(m.group("quando"))
            if limite and quando and quando < limite:
                continue
            url = m.group("url")
            t = TOKEN_URL.search(url)
            token = t.group(1) if t else m.group("utente")
            if token in ("-", ""):
                continue
            d = per_token[token]
            d["indirizzi"].add(m.group("ip"))
            d["richieste"] += 1
            if url.endswith(".deb"):
                d["pacchetti"] += 1
            if quando:
                d["prima"] = min(d["prima"] or quando, quando)
                d["ultima"] = max(d["ultima"] or quando, quando)
    return per_token


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("log", nargs="+", help="file di log del server")
    ap.add_argument("--giorni", type=int, default=30,
                    help="finestra da considerare (0 = tutto)")
    ap.add_argument("--clienti", help="JSON che associa token a cliente e postazioni")
    args = ap.parse_args(argv)

    clienti = {}
    if args.clienti:
        try:
            clienti = json.loads(Path(args.clienti).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print("non leggo %s (%s)" % (args.clienti, e), file=sys.stderr)

    dati = analizza(args.log, args.giorni)
    if not dati:
        print("nessun accesso con token negli ultimi %d giorni" % args.giorni)
        return 0

    print("Ultimi %s giorni\n" % (args.giorni or "tutti i"))
    print("%-20s %-26s %8s %8s %9s" %
          ("token", "cliente", "indiriz.", "pacch.", "concordate"))
    allarmi = []
    for token, d in sorted(dati.items(),
                           key=lambda kv: -len(kv[1]["indirizzi"])):
        info = clienti.get(token, {})
        nome = info.get("cliente", "(token non associato)")
        quante = info.get("postazioni")
        print("%-20s %-26s %8d %8d %9s"
              % (token[:20], nome[:26], len(d["indirizzi"]), d["pacchetti"],
                 quante if quante is not None else "-"))
        if quante and len(d["indirizzi"]) > quante:
            allarmi.append((nome, len(d["indirizzi"]), quante))

    if allarmi:
        print("\nDa guardare:")
        for nome, visti, quante in allarmi:
            print("  %s: %d indirizzi distinti contro %d postazioni concordate."
                  % (nome, visti, quante))
        print("  Un indirizzo non è una macchina: chiedere il rapporto firmato")
        print("  (vesper-licenza --rapporto) prima di trarre conclusioni.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
