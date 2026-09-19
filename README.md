# Vesper

**Vesper** è un ambiente desktop (Desktop Environment) leggero scritto in
**Python + GTK3**, che gira su **Openbox** come window manager e si installa
come un qualsiasi altro DE: dopo l'installazione compare fra le sessioni del
display manager e si sceglie al login.

> "Vesper" = la stella della sera: interfaccia **flat**, scura, con accento
> luminoso (cyan di default, cambiabile dal preset).

![marchio: stella a quattro punte sopra l'orizzonte](data/icons/hicolor/scalable/apps/vesper-logo.svg)

## Installazione

**Debian, Ubuntu, Linux Mint** — pacchetto `.deb`:

```sh
sudo apt install ./vesper_0.1.0_all.deb     # scarica il .deb dalle release
```

**Da sorgenti, su qualsiasi distribuzione:**

```sh
tar xzf vesper-0.1.0.tar.gz && cd vesper-0.1.0
sudo ./install.sh                 # in /usr/local
sudo ./install.sh --prefix=/usr   # in /usr (come i pacchetti della distro)
./install.sh --user               # in ~/.local, senza root
sudo ./install.sh --uninstall     # rimuove (la configurazione utente resta)
```

Poi si esce dalla sessione e al login si sceglie **Vesper** nell'elenco delle
sessioni.

### Pacchetti

Tutte le ricette partono dallo **stesso `install.sh`** con `DESTDIR`, quindi
l'albero dei file è identico ovunque; cambiano solo i nomi delle dipendenze.

| Formato | Ricetta | Come si costruisce |
|---|---|---|
| `.deb` (Debian/Ubuntu/Mint) | `tools/make-deb.sh` | `./tools/make-deb.sh` |
| sorgenti `.tar.gz` | `tools/make-tarball.sh` | `./tools/make-tarball.sh` |
| Arch/Manjaro | `packaging/arch/PKGBUILD` | `makepkg -si` |
| Fedora/openSUSE | `packaging/rpm/vesper.spec` | `rpmbuild -ba` |
| Alpine | `packaging/alpine/APKBUILD` | `abuild -r` |

### Cosa serve

| Componente | Perché | Debian/Ubuntu |
|---|---|---|
| openbox | window manager | `openbox` |
| python3 + PyGObject + Cairo | tutto il desktop | `python3-gi python3-gi-cairo gir1.2-gtk-3.0` |
| wmctrl | lista finestre e desktop virtuali del pannello | `wmctrl` |
| xrandr | gestione schermi | `x11-xserver-utils` |

Opzionali: `dunst` (notifiche), un agente PolicyKit, `xautolock` (salvaschermo
automatico), `picom` (vetro reale/angoli arrotondati), `brightnessctl`,
`bluez` + `bluez-tools`, `xwallpaper`/`feh` (solo se si usa il pannello di
Vesper sotto un altro desktop). L'installatore segnala cosa manca, con il
comando giusto per Debian/Ubuntu, Fedora, Arch e Alpine.

## Componenti

| Comando | Ruolo |
|---|---|
| `vesper-session` | avvia la sessione: preset, desktop, pannello, servizi, autostart XDG, Openbox |
| `vesper-panel` | pannello: menu applicazioni, lista finestre, desktop virtuali, orologio, applet |
| `vesper-control-center` | Centro di Controllo: 19 viste (aspetto, schermi, audio, rete, ...) |
| `vesper-files` | file manager: finestra **e** desktop (sfondo + icone) |
| `vesper-profile` | preset di aspetto: accento, sfondo, icone, stile finestre |
| `vesper-screensaver` | salvaschermo animato + blocco schermo con password |
| `vesper-logout` | dialogo di fine sessione (blocca/esci/riavvia/spegni) |
| altri `vesper-*` | audio, batteria, bluetooth, luminosità, appunti, data/ora, scorciatoie, lingua, luce blu, schermi, schermate, sfondo, terminale, wifi |

Tutti i comandi trovano da soli il pacchetto Python e i dati a partire da dove
sono installati (`bin/env.sh`): funzionano in `/usr`, `/usr/local`, in un
prefisso qualunque o direttamente dal repo dei sorgenti.

## Preset di aspetto

Un **preset** è un look completo: colore d'accento, sfondo, tema icone e stile
finestre. Cambiandolo si ricolorano **subito** barra, menu, Centro di Controllo
e finestre già aperte — i CSS generati sono sorvegliati e ricaricati a caldo.
Di serie ci sono 14 preset, uno per colore (cyan, acquamarina, verde, lime,
giallo, ambra, arancio, rosso, rosa, magenta, viola, indaco, blu, argento),
ognuno col proprio sfondo.

Gli sfondi si rigenerano con `python3 tools/make-wallpapers.py` (anche a
risoluzioni diverse: `--size 2560x1440`), le skin del pannello con
`python3 tools/make-panel-themes.py`.

## File manager

`vesper-files` è un clone funzionale di pcmanfm in Python/GTK3, **due modalità
dallo stesso codice**:

1. **Finestra** — cronologia e schede, viste icone/elenco, barra dei luoghi
   (cartelle XDG, cestino, segnalibri GTK), copia/taglia/incolla asincroni,
   cestino freedesktop, rinomina, apri-con, proprietà, miniature.
2. **Desktop** (`--desktop`) — disegna **sfondo** e **icone del desktop** con un
   unico canvas Cairo: posizionamento libero senza riallineamenti, selezione
   multipla, multi-monitor, ricarica a caldo dello sfondo.

Così Vesper **non usa pcmanfm**: nessuna dipendenza esterna per file e desktop.

## Configurazione

Tutto sotto `~/.config/vesper/`: preset attivo, accento e stile finestre
generati, sfondo scelto, skin del pannello, layout della barra, posizioni delle
icone del desktop, lingua, e il **proprio** `openbox-rc.xml` (Vesper avvia
Openbox con `--config-file`, quindi non tocca `~/.config/openbox` di chi usa
Openbox per conto suo).

## Dove finiscono i file

Percorsi standard (FHS/XDG), gli stessi su ogni distribuzione:

```
<prefisso>/bin/vesper-*                      comandi
<prefisso>/lib/vesper/                       pacchetto Python + env.sh
<prefisso>/share/vesper/                     sfondi, skin del pannello, preset, skel
<prefisso>/share/themes/                     temi finestre (Openbox + GTK)
<prefisso>/share/icons/hicolor/              marchio
<prefisso>/share/xsessions/vesper.desktop    voce di sessione (login)
<prefisso>/share/applications/               voci di menu
~/.config/vesper/                            configurazione dell'utente
~/.cache/vesper/                             log e roba rigenerabile
```

Permessi: cartelle 755, dati 644, comandi 755; niente setuid, niente file
scrivibili da gruppo o da tutti. La password del blocco schermo è salvata come
hash PBKDF2 in un file 600.

## Stato

Il desktop è funzionante e installabile. Restano da fare: schermata di login
(greeter), demone notifiche proprio, agente PolicyKit proprio, daemon XSettings,
automount dei dispositivi rimovibili, temi icone per preset e pacchetti
nativi (deb/rpm/apk). Vedi [`docs/porting-plan.md`](docs/porting-plan.md).

## Licenza

AGPL-3.0-or-later.
