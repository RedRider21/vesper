# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""`vesper-licenza`: la licenza commerciale vista dal cliente.

Vesper resta AGPL per tutti: questo comando serve solo a chi ha una licenza
commerciale e deve dimostrare, a sé e al fornitore, quante installazioni ha
in uso.

    vesper-licenza                    stato della licenza installata
    vesper-licenza --installa FILE    installa una licenza ricevuta
    vesper-licenza --id               identificativo di questa installazione
    vesper-licenza --rapporto         rapporto sigillato di QUESTA macchina
    vesper-licenza --unisci F...      unisce i rapporti di più macchine
    vesper-licenza --attiva           registra l'installazione (se prevista)

Il rapporto non contiene nulla di personale: identificativo pseudonimo della
macchina (hash del machine-id), numero di licenza, data e versione. Il nome
del computer si aggiunge solo con `--host`, se serve al cliente per
riconoscere le proprie macchine.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from vesper.licenza import modello


def _stampa_stato() -> int:
    doc = modello.carica()
    if doc is None:
        print("Nessuna licenza commerciale installata.")
        print("Vesper è comunque utilizzabile secondo l'AGPL-3.0-or-later,")
        print("che è la licenza con cui viene distribuito.")
        return 0
    esito = modello.verifica(doc)
    dati = esito.dati
    print("Licenza  : %s" % dati.get("id", "?"))
    print("Cliente  : %s" % dati.get("cliente", "?"))
    print("Postazioni concordate: %s" % dati.get("postazioni", "?"))
    print("Emessa   : %s" % dati.get("emessa", "?"))
    print("Scadenza : %s" % dati.get("scadenza", "nessuna"))
    if dati.get("nota"):
        print("Nota     : %s" % dati["nota"])
    print("Stato    : %s" % esito.motivo.upper())
    print("Questa installazione: %s" % modello.id_installazione())
    return 0 if esito else 1


def _installa(percorso: str) -> int:
    try:
        doc = json.loads(Path(percorso).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print("non riesco a leggere %s (%s)" % (percorso, e), file=sys.stderr)
        return 1
    esito = modello.verifica(doc)
    if not esito:
        print("licenza rifiutata: %s" % esito.motivo, file=sys.stderr)
        return 1
    dove = modello.installa(doc)
    print("licenza di %s installata in %s"
          % (esito.dati.get("cliente", "?"), dove))
    return 0


def _rapporto(host: bool, out: str | None) -> int:
    doc = modello.carica()
    if doc is None:
        print("nessuna licenza installata: niente da dichiarare",
              file=sys.stderr)
        return 1
    r = modello.rapporto(doc, nome_host=host)
    testo = json.dumps(r, indent=1, ensure_ascii=False) + "\n"
    if out:
        Path(out).write_text(testo, encoding="utf-8")
        print("rapporto scritto in %s" % out)
    else:
        print(testo, end="")
    return 0


def _unisci(file: list[str], out: str | None) -> int:
    rapporti = []
    for nome in file:
        try:
            rapporti.append(json.loads(Path(nome).read_text(encoding="utf-8")))
        except (OSError, ValueError):
            print("illeggibile, salto: %s" % nome, file=sys.stderr)
    unito = modello.unisci_rapporti(rapporti)
    testo = json.dumps(unito, indent=1, ensure_ascii=False) + "\n"
    if out:
        Path(out).write_text(testo, encoding="utf-8")
        print("%d installazioni distinte, riepilogo in %s"
              % (unito["conteggio"], out))
    else:
        print(testo, end="")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    host = "--host" in argv
    if host:
        argv.remove("--host")
    out = None
    if "--out" in argv:
        i = argv.index("--out")
        out = argv[i + 1] if i + 1 < len(argv) else None
        del argv[i:i + 2]

    if not argv or argv[0] in ("--stato", "stato"):
        return _stampa_stato()
    cmd = argv[0]
    if cmd in ("-h", "--help", "aiuto"):
        print(__doc__.strip())
        return 0
    if cmd == "--id":
        print(modello.id_installazione())
        return 0
    if cmd == "--installa":
        if len(argv) < 2:
            print("uso: vesper-licenza --installa FILE", file=sys.stderr)
            return 2
        return _installa(argv[1])
    if cmd in ("--rapporto", "--report"):
        return _rapporto(host, out)
    if cmd == "--unisci":
        if len(argv) < 2:
            print("uso: vesper-licenza --unisci FILE [FILE...]", file=sys.stderr)
            return 2
        return _unisci(argv[1:], out)
    if cmd == "--attiva":
        from vesper.licenza import attivazione
        return attivazione.attiva_ora()
    print("uso: vesper-licenza [--stato|--installa FILE|--id|--rapporto|"
          "--unisci FILE...|--attiva]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
