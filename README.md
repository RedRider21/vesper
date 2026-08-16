# Vesper

**Vesper** è un ambiente desktop (Desktop Environment) leggero scritto in
**Python + GTK3**, pensato per girare su **Openbox** come window manager e per
installarsi come un qualsiasi DE (MATE, XFCE, KDE, ...).

Nasce estraendo e rendendo autonoma la parte desktop di **NexusSec OS**: il
pannello, il Centro di Controllo e i **profili dinamici** (accent, sfondo e tema
delle icone che cambiano al volo). Vesper li impacchetta come DE riusabile,
scollegato dalla distro.

> "Vesper" = la stella della sera: interfaccia **flat**, scura, con accent
> luminoso (cyan di default, cambiabile dal profilo).

## Componenti

| Pacchetto | Ruolo |
|---|---|
| `vesper-session` | avvio della sessione: Openbox + pannello + file manager (modalità desktop) + autostart |
| `vesper-panel` | pannello inferiore: menu con ricerca, categorie, orologio, tray |
| `vesper-settings` | Centro di Controllo (aspetto, profili, sfondo, accent) |
| `vesper-files` | **file manager proprio in Python** (vedi sotto) |

## File manager (`vesper-files`)

Clone **funzionale** di pcmanfm, in Python/GTK3, in **due modalità dallo stesso
codice**:

1. **Finestra** — gestione file classica (navigazione, tab, taglia/copia/incolla,
   rinomina, cestino, apri-con, segnalibri, vista icone/lista).
2. **Desktop** — assorbe il ruolo di `pcmanfm --desktop`: disegna lo **sfondo**
   e le **icone del desktop**. Così Vesper **elimina del tutto pcmanfm**: nessuna
   dipendenza esterna per file/desktop → DE ancora più leggero.

## Stato

Scaffold iniziale. Sviluppo nella sua sessione dedicata. Vedi
[`docs/design.md`](docs/design.md) per il piano e [`CLAUDE.md`](CLAUDE.md) per
lingua, stile e architettura.

## Origine del codice

Il punto di partenza è `NexusSec-OS/overlay/usr/local/lib/`:
`nxs_cc/` (pannello + Centro di Controllo + CSS/tema) e `nxs_profiles/`
(model/selector/cli dei profili). Vesper li rinomina in `vesper.*`, li rende
indipendenti dalla distro e aggiunge `vesper-files`.
