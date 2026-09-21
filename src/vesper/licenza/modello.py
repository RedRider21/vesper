# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Formato, firma e verifica delle licenze commerciali di Vesper.

Vesper è AGPL: chi rispetta il copyleft non ha bisogno di nulla di tutto
questo. Le licenze servono a chi acquista la licenza commerciale alternativa,
tipicamente perché integra Vesper in un prodotto proprietario, e servono a
tenere il conto delle installazioni concordate.

Una licenza è un file di testo con dentro un JSON:

    {"licenza": {...}, "chiave": "<id>", "firma": "<base64>"}

La firma è Ed25519 sul JSON **canonico** del blocco `licenza` (chiavi
ordinate, separatori compatti, UTF-8): due programmi diversi firmano e
verificano lo stesso byte per byte. La chiave privata resta offline, sulla
macchina di chi emette; il cliente riceve solo il file firmato.

Cosa questo impianto può e non può fare: verifica che una licenza sia
autentica, intestata e non scaduta. NON impedisce a un cliente di modificare
il proprio software — è AGPL, il codice ce l'ha — ma renderebbe l'eventuale
manomissione un atto deliberato e dimostrabile, che è ciò che serve davanti
a un contratto.

**Niente rete, per scelta.** Non esiste attivazione online, né telemetria, né
controlli periodici verso un server: la verifica è tutta locale e il conteggio
passa da file che il cliente consegna. Un desktop non deve dipendere da un
server per funzionare, e un fornitore non deve sapere quando i suoi clienti
accendono il computer.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import socket
from datetime import date, datetime
from pathlib import Path

from vesper import paths
from vesper.licenza import ed25519

PRODOTTO = "vesper"

# Che cosa certifica una licenza. Il formato firmato è sempre lo stesso: cambia
# il tipo e i campi che ne dipendono.
#   postazioni  numero di installazioni concordate (OEM, integratori): si
#               contano, e l'eccedenza fa scattare il true-up
#   servizi     contratto di assistenza: livello, servizi inclusi, scadenza.
#               Non si conta niente — è un attestato, non un contatore
#   sito        uso illimitato dentro un perimetro (una sede, una società)
TIPI = ("postazioni", "servizi", "sito")
TIPO_PREDEFINITO = "postazioni"

# Chiavi pubbliche riconosciute: id -> chiave (hex). L'id sono i primi 16
# caratteri esadecimali dello sha256 della chiave pubblica. `vesper-licgen
# chiavi` stampa la riga da incollare qui dopo aver generato la coppia.
CHIAVI_FIDATE: dict[str, str] = {
    # Chiave di firma di Daniele Deplano (RedRider21), generata il 2026-09-21.
    # La privata sta offline: senza di lei non si emettono licenze valide.
    "ee2daa4883ef5c91": "a370b5e6d57430b366a0420add2417e76caf2ddd48cc3bee1e470d1914969aa6",
    # Chiave COMUNE, generata il 2026-09-21: firma i contratti che coprono più
    # prodotti insieme (Vesper dentro lo stesso accordo di un altro prodotto).
    # Sta qui fin d'ora, prima che serva: aggiungerla dopo vorrebbe dire
    # aggiornare le installazioni già consegnate. La privata è offline, nel
    # registro comune (~/licenze/comune/).
    "b744338c0fcb620e": "44e8e6dc3dbe303d1c2bf340c4228a47ce326c206de03f0cc0e70855d03a70cf",
    # "0123456789abcdef": "…64 caratteri esadecimali…",
}

# Dove sta la licenza installata.
FILE_LICENZA = paths.config("licenza.json")


# --- serializzazione canonica ----------------------------------------------
def canonico(blocco: dict) -> bytes:
    """Il byte esatto su cui si firma e si verifica."""
    return json.dumps(blocco, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def id_chiave(pubblica: bytes) -> str:
    return hashlib.sha256(pubblica).hexdigest()[:16]


# --- emissione (lato titolare) ---------------------------------------------
def emetti(dati: dict, seme_privato: bytes) -> dict:
    """Costruisce una licenza firmata. `dati` è il blocco `licenza`."""
    pub = ed25519.chiave_pubblica(seme_privato)
    f = ed25519.firma(canonico(dati), seme_privato)
    return {
        "licenza": dati,
        "chiave": id_chiave(pub),
        "firma": base64.b64encode(f).decode("ascii"),
    }


# --- verifica (lato cliente) -----------------------------------------------
class Esito:
    """Risultato della verifica: valida o no, e perché."""

    def __init__(self, valida: bool, motivo: str, dati: dict | None = None):
        self.valida = valida
        self.motivo = motivo
        self.dati = dati or {}

    def __bool__(self) -> bool:
        return self.valida

    def __repr__(self) -> str:
        return "<Esito %s: %s>" % ("valida" if self.valida else "non valida",
                                   self.motivo)


def verifica(documento: dict, chiavi: dict[str, str] | None = None,
             oggi: date | None = None) -> Esito:
    """Controlla firma, chiave e scadenza di una licenza."""
    chiavi = CHIAVI_FIDATE if chiavi is None else chiavi
    if not isinstance(documento, dict) or "licenza" not in documento:
        return Esito(False, "file di licenza illeggibile")
    dati = documento.get("licenza") or {}
    id_k = documento.get("chiave", "")
    pub_hex = chiavi.get(id_k)
    if not pub_hex:
        return Esito(False, "firmata con una chiave che non conosco (%s)" % id_k,
                     dati)
    try:
        f = base64.b64decode(documento.get("firma", ""), validate=True)
        pub = bytes.fromhex(pub_hex)
    except (ValueError, TypeError):
        return Esito(False, "firma o chiave malformate", dati)
    if not ed25519.verifica(canonico(dati), f, pub):
        return Esito(False, "firma non valida: il file è stato modificato", dati)
    if not copre(dati, PRODOTTO):
        coperti = ", ".join(prodotti(dati)) or "?"
        return Esito(False, "licenza di un altro prodotto (%s)" % coperti, dati)

    scad = dati.get("scadenza")
    if scad:
        try:
            giorno = date.fromisoformat(scad)
        except ValueError:
            return Esito(False, "data di scadenza illeggibile (%s)" % scad, dati)
        if (oggi or date.today()) > giorno:
            return Esito(False, "scaduta il %s" % scad, dati)
    return Esito(True, "valida", dati)


def prodotti(dati: dict) -> list[str]:
    """I prodotti coperti. Le licenze vecchie hanno il solo campo `prodotto`:
    una licenza emessa prima del multi-prodotto deve restare valida."""
    elenco = dati.get("prodotti")
    if isinstance(elenco, list) and elenco:
        return [str(x) for x in elenco]
    uno = dati.get("prodotto")
    return [str(uno)] if uno else []


def copre(dati: dict, prodotto: str) -> bool:
    return prodotto in prodotti(dati)


def tipo(dati: dict) -> str:
    t = dati.get("tipo") or TIPO_PREDEFINITO
    return t if t in TIPI else TIPO_PREDEFINITO


def conta_installazioni(dati: dict) -> bool:
    """True se per questa licenza ha senso contare le installazioni.

    Per un contratto di servizi non ne ha: si vende assistenza, non copie.
    """
    return tipo(dati) == "postazioni"


def carica(percorso: Path | None = None) -> dict | None:
    try:
        return json.loads((percorso or FILE_LICENZA).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def installa(documento: dict) -> Path:
    paths.ensure_config()
    FILE_LICENZA.write_text(json.dumps(documento, indent=1, ensure_ascii=False)
                            + "\n", encoding="utf-8")
    return FILE_LICENZA


# --- identità dell'installazione -------------------------------------------
def id_installazione() -> str:
    """Identificativo stabile e pseudonimo di QUESTA installazione.

    È l'hash del machine-id (o, se manca, di un identificativo generato una
    volta sola e conservato con la configurazione). Non contiene nulla di
    personale e non si può risalire alla macchina: serve solo a non contare
    due volte lo stesso computer.
    """
    # Macchine clonate (VM copiate da un'immagine) condividono il machine-id
    # e verrebbero contate come una sola: chi si trova in quel caso rigenera
    # il machine-id, oppure imposta VESPER_ID_INSTALLAZIONE. Il contratto deve
    # dire come si contano i cloni: è la voce su cui nascono i contenziosi.
    forzato = os.environ.get("VESPER_ID_INSTALLAZIONE", "").strip()
    if forzato:
        return hashlib.sha256(("vesper:" + forzato).encode("utf-8")).hexdigest()[:32]

    sorgente = ""
    for f in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            sorgente = Path(f).read_text(encoding="utf-8").strip()
            if sorgente:
                break
        except OSError:
            continue
    if not sorgente:
        proprio = paths.config("id-installazione")
        try:
            sorgente = proprio.read_text(encoding="utf-8").strip()
        except OSError:
            sorgente = ""
        if not sorgente:
            sorgente = base64.b32encode(os.urandom(20)).decode("ascii")
            paths.ensure_config()
            try:
                proprio.write_text(sorgente + "\n", encoding="utf-8")
            except OSError:
                pass
    return hashlib.sha256(("vesper:" + sorgente).encode("utf-8")).hexdigest()[:32]


# --- rapporto per il conteggio ---------------------------------------------
def rapporto(documento: dict, nome_host: bool = False) -> dict:
    """Rapporto di QUESTA installazione, sigillato col segreto della licenza.

    Il segreto sta nella licenza, quindi sta anche sul computer del cliente:
    il sigillo prova che il rapporto viene da un'installazione con licenza
    valida e che non è stato ritoccato dopo, non che il cliente sia sincero.
    Quello lo garantisce il contratto, non la crittografia.
    """
    dati = documento.get("licenza") or {}
    corpo = {
        "prodotto": PRODOTTO,
        "licenza": dati.get("id", ""),
        "cliente": dati.get("cliente", ""),
        "installazione": id_installazione(),
        "generato": datetime.now().astimezone().isoformat(timespec="seconds"),
        "versione": _versione(),
    }
    if nome_host:
        corpo["host"] = socket.gethostname()
    segreto = dati.get("segreto", "")
    if segreto:
        corpo_b = canonico(corpo)
        sigillo = hmac.new(segreto.encode("utf-8"), corpo_b,
                           hashlib.sha256).hexdigest()
    else:
        sigillo = ""
    return {"rapporto": corpo, "sigillo": sigillo}


def verifica_rapporto(doc: dict, segreto: str) -> bool:
    """Controlla il sigillo di un rapporto (lo usa chi emette le licenze)."""
    corpo = doc.get("rapporto") or {}
    atteso = hmac.new(segreto.encode("utf-8"), canonico(corpo),
                      hashlib.sha256).hexdigest()
    return hmac.compare_digest(atteso, doc.get("sigillo", ""))


def unisci_rapporti(rapporti: list[dict]) -> dict:
    """Fonde i rapporti di più macchine in uno solo, senza doppioni.

    Serve al cliente che non manda dati in rete: raccoglie i rapporti dai
    suoi computer, li unisce e invia un unico file.
    """
    viste: dict[str, dict] = {}
    licenza = cliente = ""
    for doc in rapporti:
        corpo = doc.get("rapporto") or {}
        ident = corpo.get("installazione")
        if not ident:
            continue
        licenza = licenza or corpo.get("licenza", "")
        cliente = cliente or corpo.get("cliente", "")
        prec = viste.get(ident)
        if prec is None or corpo.get("generato", "") > prec.get("generato", ""):
            viste[ident] = corpo
    return {
        "prodotto": PRODOTTO,
        "licenza": licenza,
        "cliente": cliente,
        "generato": datetime.now().astimezone().isoformat(timespec="seconds"),
        "installazioni": sorted(viste.values(),
                                key=lambda c: c.get("installazione", "")),
        "conteggio": len(viste),
    }


def _versione() -> str:
    try:
        from vesper import __version__
        return __version__
    except Exception:                                # noqa: BLE001
        return "?"
