# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Registrazione dell'installazione presso il fornitore, quando è prevista.

Regole che questo modulo rispetta, e che vanno rispettate anche nel contratto:

- **Niente di nascosto.** Si contatta la rete solo se la licenza contiene un
  `endpoint`, cioè solo se il contratto lo prevede, e mai nella versione AGPL:
  questo modulo non finisce nel pacchetto pubblico.
- **Niente dati personali.** Si invia l'identificativo pseudonimo della
  macchina (hash del machine-id), il numero di licenza, la versione e la data.
  Nessun nome utente, nessun nome host, nessun indirizzo, nessun contenuto.
  Base giuridica: esecuzione del contratto; minimizzazione by design.
- **Mai bloccante.** Se la rete non c'è o il server non risponde, Vesper
  funziona esattamente come prima: la registrazione riprova più avanti. Un
  desktop che smette di funzionare perché non raggiunge un server è un danno
  per il cliente, non una tutela per il fornitore.
- **Sempre disattivabile.** `VESPER_NO_ATTIVAZIONE=1`, oppure la riga `off` in
  `~/.config/vesper/attivazione`. Chi non può avere telemetria (pubblica
  amministrazione, sanità, difesa) usa `vesper-licenza --rapporto`, che
  produce un file da allegare alla dichiarazione periodica.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

from vesper import paths
from vesper.licenza import modello

SCELTA = paths.config("attivazione")          # "off" per disattivare
ULTIMA = paths.cache("attivazione-ultima")    # data dell'ultimo invio riuscito
OGNI_GIORNI = 7
TIMEOUT = 8


def consentita() -> bool:
    if os.environ.get("VESPER_NO_ATTIVAZIONE") == "1":
        return False
    try:
        return SCELTA.read_text(encoding="utf-8").strip().lower() != "off"
    except OSError:
        return True                                # nessuna scelta = consentita


def _gia_fatta_di_recente() -> bool:
    try:
        quando = datetime.fromisoformat(ULTIMA.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    return (datetime.now(timezone.utc) - quando).days < OGNI_GIORNI


def _segna_fatta() -> None:
    try:
        ULTIMA.parent.mkdir(parents=True, exist_ok=True)
        ULTIMA.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    except OSError:
        pass


def _invia(endpoint: str, corpo: dict) -> tuple[bool, str]:
    dati = json.dumps(corpo).encode("utf-8")
    req = urllib.request.Request(
        endpoint, data=dati, method="POST",
        headers={"Content-Type": "application/json",
                 "User-Agent": "vesper-licenza/%s" % corpo.get("versione", "?")})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return 200 <= r.status < 300, "HTTP %s" % r.status
    except urllib.error.HTTPError as e:
        return False, "HTTP %s" % e.code
    except (urllib.error.URLError, OSError, ValueError) as e:
        return False, str(e)


def attiva_ora(forza: bool = True) -> int:
    """Registra questa installazione. Ritorna 0 se fatto o non necessario."""
    doc = modello.carica()
    if doc is None:
        print("nessuna licenza installata: niente da registrare")
        return 0
    esito = modello.verifica(doc)
    if not esito:
        print("licenza non valida (%s): non registro" % esito.motivo)
        return 1
    endpoint = (esito.dati.get("endpoint") or "").strip()
    if not endpoint:
        print("questa licenza non prevede la registrazione in rete.")
        print("Per il conteggio: vesper-licenza --rapporto")
        return 0
    if not consentita():
        print("registrazione disattivata su questa macchina "
              "(~/.config/vesper/attivazione)")
        return 0
    if not forza and _gia_fatta_di_recente():
        return 0

    corpo = modello.rapporto(doc)["rapporto"]
    ok, dettaglio = _invia(endpoint, corpo)
    if ok:
        _segna_fatta()
        print("installazione registrata presso %s" % endpoint)
        return 0
    print("registrazione non riuscita (%s): riproverò. "
          "Vesper funziona normalmente." % dettaglio)
    return 0                                      # mai un errore bloccante


def attiva_in_silenzio() -> None:
    """Chiamata all'avvio della sessione: non stampa e non blocca mai."""
    try:
        doc = modello.carica()
        if doc is None or not consentita() or _gia_fatta_di_recente():
            return
        esito = modello.verifica(doc)
        endpoint = (esito.dati.get("endpoint") or "").strip()
        if not esito or not endpoint:
            return
        ok, _ = _invia(endpoint, modello.rapporto(doc)["rapporto"])
        if ok:
            _segna_fatta()
    except Exception:                              # noqa: BLE001
        pass                                       # mai disturbare la sessione
