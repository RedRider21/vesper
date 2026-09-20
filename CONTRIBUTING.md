# Contribuire a Vesper

Grazie per l'interesse. Vesper è un ambiente desktop piccolo e curato: si
accettano volentieri correzioni, traduzioni e funzionalità, purché restino
nello spirito del progetto (leggero, senza dipendenze pesanti, coerente).

## Prima di aprire una pull request: il CLA

Vesper ha una **doppia licenza**: AGPL-3.0-or-later per tutti e, in
alternativa, una licenza commerciale concessa dal titolare. Perché questo
resti possibile, il titolare deve poter concedere in licenza tutto il codice
del progetto — anche il tuo contributo.

Per questo ogni pull request richiede l'accettazione del
**[CLA](CLA.md)**. Non cedi la proprietà del tuo codice: resti l'autore e puoi
continuare a usarlo come vuoi.

Si accetta così, nel testo della pull request:

```
Accetto il CLA di Vesper (CLA.md) — Nome Cognome <email> — GitHub: @utente
```

e firmando i commit con `git commit -s`.

Senza CLA una pull request non può essere unita, per quanto buona sia: non è
diffidenza, è l'unico modo di tenere in piedi il modello di licenza.

## Come si lavora

- **Lingua**: interfaccia, documentazione e commenti in **italiano**, con gli
  accenti giusti. I nomi di variabili e funzioni seguono lo stile del file in
  cui scrivi.
- **Traduzioni**: ogni stringa visibile passa da `vesper.i18n.t()` e va scritta
  in tutte e cinque le lingue (`src/vesper/i18n/strings/*.json`). Prima di
  aprire la PR, `tools/check-i18n.py` deve dire **0 problemi**.
- **Isolamento**: Vesper scrive solo dentro `~/.config/vesper`,
  `~/.cache/vesper` e `~/.local/share/vesper`. Le impostazioni condivise con
  gli altri desktop si toccano solo dentro la sessione Vesper e vanno
  fotografate per poterle rimettere (vedi `src/vesper/sessionstate.py`).
- **GTK3, non GTK4**; niente dipendenze pesanti; niente componenti di altri
  ambienti desktop.
- **Prove**: si prova in un X annidato (`Xephyr`) con configurazione isolata
  (`VESPER_CONFIG_HOME`), mai sulla propria sessione. Le note stanno in
  `CLAUDE.md`, che vale come guida allo sviluppo.

## Segnalare un problema

Apri una issue dicendo: distribuzione e versione, versione di Vesper
(`vesper-profile --version` o il pacchetto installato), gestore finestre in
uso (`vesper-wm`), e cosa ti aspettavi. Per i problemi di sessione allega
`~/.cache/vesper/session.log`.

## Licenza dei contributi

Inviando un contributo accetti che sia distribuito sotto AGPL-3.0-or-later e,
alle condizioni del [CLA](CLA.md), anche sotto la licenza commerciale del
titolare.
