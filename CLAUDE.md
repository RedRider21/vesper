# Vesper — istruzioni per Claude

Ambiente desktop (DE) leggero in **Python + GTK3** su **Openbox**, installabile
come MATE/XFCE/KDE. Estratto e reso autonomo dalla parte desktop di **NexusSec
OS** (progetto sorgente: `../NexusSec-OS/`).

## Lingua e stile

- Contenuti user-visible (README, menu, log, messaggi) e commenti nei sorgenti
  in **italiano** con accenti corretti. Commenti informali.
- UI **flat**, niente emoji nei file salvo richiesta. Palette (ereditata da
  NexusSec, cambiabile dal profilo): `#050a14` sfondo, `#0a1a26` pannello,
  `#00e5ff` accent, `#c8f5ff` testo, `#5a8a9a` tenue, `#1a3a52` bordi,
  `#ff5a8a` allarme.
- **GTK3, NON GTK4** (vincolo ereditato): niente `text-transform`,
  `letter-spacing` nel CSS — non esistono in GTK3 e fanno sollevare eccezione a
  `Gtk.CssProvider.load_from_data`. Per il maiuscolo usare `.upper()` in Python.
  `apply_css()` avvolge il load in try/except (difensivo).

## Architettura

```
vesper/
├── src/vesper/
│   ├── common.py          # CSS/tema condiviso (porting di nxs_cc.common)
│   ├── panel/             # pannello: menu ricerca, categorie, orologio, tray
│   ├── control_center/    # vesper-settings: aspetto, profili, sfondo, accent
│   ├── filemanager/       # vesper-files: FM Python (finestra + modalità desktop)
│   ├── profiles/          # profili dinamici (accent/sfondo/icone)
│   └── session/           # vesper-session: avvio Openbox + componenti + autostart
├── data/{themes,icons}/   # temi Openbox/GTK, set di icone per profilo
├── packaging/alpine/      # APKBUILD: vesper-session/panel/settings/files
└── docs/design.md         # piano di lavoro e design del file manager
```

## Da dove partire (porting)

Sorgenti di riferimento in `../NexusSec-OS/overlay/usr/local/lib/`:

- `nxs_cc/` → `panel.py` (pannello + menu), `common.py` (CSS/tema),
  `selector.py`/`views.py`/`panelcfg.py`. **Da rinominare** in `vesper.*` e
  **scollegare** dai percorsi di NexusSec (`/usr/local/share/nexussec/`,
  `/etc/sec_os/`) usando percorsi/env propri di Vesper.
- `nxs_profiles/` → `model.py` (stato profilo attivo, accent, sfondo),
  `selector.py`, `cli.py`. In Vesper i "profili" sono **temi/preset del DE**
  (non i profili di sicurezza della distro): mantenere il meccanismo
  accent+sfondo+icone, togliere l'aggancio ai meta-pacchetti `sec-profile-*`.

## File manager (vesper-files) — il pezzo nuovo

Clone **funzionale** di pcmanfm in GTK3, **un solo codice, due modalità**:

- **Finestra**: navigazione cartelle, tab, vista icone/lista, taglia/copia/
  incolla, rinomina, cestino (freedesktop Trash spec), segnalibri
  (`~/.config/gtk-3.0/bookmarks`), apri-con (`.desktop`/MIME), proprietà.
- **Desktop** (`vesper-files --desktop`): finestra root senza decorazioni che
  disegna **sfondo** (assorbe `pcmanfm --set-wallpaper`) + **icone del desktop**
  (contenuto di `~/Scrivania`/`~/Desktop`). Sostituisce `pcmanfm --desktop`.

Obiettivo: **rimuovere pcmanfm** dai depends → DE più leggero, zero dipendenze
esterne per file/desktop. Base tecnica consigliata: `Gio`/`GLib` per I/O e
monitor delle cartelle, `GdkPixbuf` per thumbnail, `Gtk.IconView`/`Gtk.TreeView`
per le viste.

## Gotcha ereditati da NexusSec (NON re-derivare)

- **Riavvio pannello**: non fare `pkill -f nxs_cc.panel` da una shell il cui
  argv contiene quel pattern (si autouccide). `pkill` diretto + launcher il cui
  argv non contiene il pattern.
- **Icone desktop che chiedono "eseguire?"**: con pcmanfm serviva
  `~/.config/libfm/libfm.conf` `quick_exec=1`. In `vesper-files` gestirlo nel
  nostro codice (lanciare i `.desktop` fidati senza dialogo).
- **rc.xml Openbox** deve restare il default COMPLETO (sezione `<mouse>`),
  altrimenti le finestre non si spostano/chiudono. Personalizzare solo
  theme/margins/keybind.

## Cosa NON fare

- Non introdurre dipendenze pesanti: Vesper deve restare **minimale, estetico,
  a basso consumo**. Niente GTK4, niente pcmanfm, niente componenti di altri DE.
- Non agganciare Vesper alla logica di sicurezza di NexusSec: è un DE generico.
