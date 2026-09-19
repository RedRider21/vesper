# Vesper — istruzioni per Claude

Ambiente desktop (DE) leggero in **Python + GTK3** su **Openbox**, installabile
come qualsiasi altro DE (voce di sessione nel display manager).

## Lingua e stile

- Contenuti user-visible (README, menu, log, messaggi) e commenti nei sorgenti
  in **italiano** con accenti corretti. Commenti informali.
- UI **flat**, niente emoji nei file salvo richiesta. Palette di base:
  `#050a14` sfondo, `#0a1a26` pannello, `#00e5ff` accento, `#c8f5ff` testo,
  `#5a8a9a` tenue, `#1a3a52` bordi, `#ff5a8a` allarme. L'accento lo decide il
  **preset** attivo.
- **GTK3, NON GTK4**: niente `text-transform`, `letter-spacing` nel CSS — non
  esistono in GTK3 e fanno sollevare eccezione a `Gtk.CssProvider.load_from_data`.
  Per il maiuscolo usare `.upper()` in Python. `apply_css()` avvolge il load in
  try/except (difensivo).
- Prefisso unico `vesper-` sia per le classi CSS sia per i nomi dei comandi.

## Architettura

```
vesper/
├── bin/                    comandi vesper-* + env.sh (risolve percorsi)
├── src/vesper/
│   ├── paths.py            TUTTI i percorsi (config/cache/dati) passano da qui
│   ├── common.py           CSS/tema, apply_css, accent e skin a caldo, helper
│   ├── paneltheme.py       skin colore del pannello
│   ├── panelcfg.py         posizione/altezza barra, margini rc.xml, desktop virtuali
│   ├── desktopentry.py     parser .desktop (senza GTK) + autostart XDG
│   ├── i18n/               it/en/fr/es/de
│   ├── panel/              pannello: barra, applet, menu applicazioni
│   ├── control_center/     Centro di Controllo: main.py (tessere) + views.py
│   ├── filemanager/        window.py (finestra) + desktop.py (sfondo e icone)
│   ├── profiles/           preset di aspetto: model.py, cli.py, selector.py
│   └── screensaver/        salvaschermo + blocco schermo
├── data/                   sfondi, skin, preset.json, temi, icone, skel, .desktop
├── tools/                  generatori (sfondi+preset, skin del pannello)
└── install.sh              installazione come DE (prefix/user/DESTDIR/uninstall)
```

## Regole che valgono sempre

- **Percorsi**: mai percorsi assoluti sparsi. Si chiede a `vesper.paths`
  (`config()`, `cache()`, `find_data()`, `data_dirs()`). Le variabili
  `VESPER_CONFIG_HOME` e `VESPER_DATA_DIRS` spostano tutto: servono per provare
  su una copia isolata senza toccare la configurazione vera.
- **Comandi**: ogni script in `bin/` include `env.sh`, che trova pacchetto
  Python, dati e interprete partendo da dove è installato.
- **Openbox**: Vesper usa il PROPRIO `~/.config/vesper/openbox-rc.xml` e lo
  passa con `--config-file`. Non si tocca `~/.config/openbox` dell'utente.
- **Niente dipendenze pesanti**: minimale, estetico, a basso consumo. Niente
  GTK4, niente pcmanfm, niente componenti di altri DE.
- **Distro-agnostico**: nome sistema da `/etc/os-release`, pacchetti con
  apk/dpkg/rpm/pacman, privilegi con doas/sudo/pkexec, terminale scelto da
  `vesper-terminal`, spegnimento via logind con ripieghi.

## Gotcha da NON re-derivare

- **Riavvio del pannello**: `pkill -f` da una shell il cui argv contiene il
  pattern si autouccide. Si usa `vesper-panel-restart`, che cerca
  `vesper[.]panel` (le parentesi quadre non compaiono nella cmdline del regex).
- **rc.xml** deve restare il default COMPLETO (sezione `<mouse>`), altrimenti
  le finestre non si spostano né si chiudono.
- **`.pyc` stale**: non impacchettare `__pycache__` (l'installatore lo esclude).
- **Provider CSS su widget**: in GTK3 valgono solo per QUEL widget, non per i
  figli (vedi la barretta d'accento nelle schede dei preset).
- **Viste a icone/elenco**: senza regole CSS esplicite GTK usa il colore "base"
  bianco e le liste appaiono candide dentro finestre scure.
- **Icone del desktop**: i `.desktop` si avviano senza dialogo di conferma; se
  il programma di `Exec` non è installato GLib rifiuta il file, quindi si legge
  con il parser nostro e si spiega il problema al clic.
- **Sfondo del greeter/finestre a schermo intero**: disegnare in Cairo, non con
  `background-image` CSS (in GTK3 su window non dipinge).
- **Luce blu**: gamma via `xrandr`. L'overlay traslucido è stato SCARTATO: in VM
  senza compositore diventa opaco e copre lo schermo.

## Come si prova senza rompere niente

- X annidato: `Xephyr :7 -screen 1280x800 -ac &` e poi `DISPLAY=:7 ...`.
  Avviare Xephyr e il comando nello STESSO comando di shell (altrimenti Xephyr
  muore con la shell).
- Configurazione isolata: `VESPER_CONFIG_HOME=/tmp/prova-conf` +
  `VESPER_DATA_DIRS=$PWD/data`. **Mai** provare su `~/.config/vesper` reale.
- Attenzione: `vesper-audio-unmute` agisce sul mixer VERO della macchina, e
  `vesper-screens`/`vesper-nightlight` su xrandr reale. In prova vanno tenuti
  fuori dal PATH.
- **gsettings/dconf ignorano HOME**: scrivono SEMPRE nella configurazione
  della sessione reale, attraverso il bus di sessione. `set_wm_theme()` le usa
  per il tema di marco/metacity: in prova si esporta `VESPER_NO_GSETTINGS=1`,
  altrimenti si cambiano tema e pulsanti del desktop vero dell'utente
  (successo: tema marco e button-layout modificati e poi ripristinati a mano).
- Chiudere sempre le finestre Xephyr a fine prova (`pkill Xephyr`).
- Commit locale a ogni modifica; nei messaggi niente riferimenti a Claude.
