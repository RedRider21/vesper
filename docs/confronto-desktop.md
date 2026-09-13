# Vesper — punto della situazione e confronto con gli altri Desktop Environment

> Documento di riferimento (2026-09-13). Riassume lo stato di Vesper e cosa
> manca per essere un DE generico competitivo (XFCE / MATE / LXQt / Cinnamon).
> Consultabile in sessioni future. Sorgente maturo del desktop: `../NexusSec-OS/`.

## Stato attuale di Vesper: *scaffold*

- Un solo commit (scaffold iniziale).
- Di concreto c'è **solo `src/vesper/filemanager/desktop.py`** (~357 righe):
  modalità **desktop** del file manager (sfondo + icone in Cairo, architettura
  validata — un unico `Gtk.DrawingArea`, icone come dati, hit-test/drag a mano,
  posizioni persistenti in `~/.config/vesper/desktop-items.json`).
- Tutto il resto è `__init__.py` **vuoto**: `panel/`, `control_center/`,
  `profiles/`, `session/`, `common.py`, la **modalità-finestra** del file
  manager; nessun APKBUILD.

**Buona notizia:** il "cervello" (pannello, Centro di Controllo, profili) è
**già maturo in NexusSec** (`nxs_cc/`, `nxs_profiles/`). Per Vesper va **portato
e scollegato** dalla distro (`nxs_* → vesper.*`, percorsi in `~/.config/vesper/`
+ `/usr/share/vesper/`), non reinventato.

## Confronto con un DE completo

Legenda: ✅ presente · ⏳ da portare da NexusSec (esiste già lì) · ⚠️ parziale ·
❌ mancante.

| Area | Negli altri DE | Stato Vesper |
|---|---|---|
| Pannello (menu+ricerca, tasklist, orologio, tray, monitor risorse, multi-monitor) | ✅ | ⏳ da portare (completo in NexusSec) |
| Centro di Controllo (aspetto, rete, audio, BT, mouse/tastiera, autostart, pacchetti) | ✅ | ⏳ da portare (ricco in NexusSec) |
| Profili "look" dinamici (accent/sfondo/icone al volo) | ➖ raro | ✅ feature distintiva (da portare) |
| File manager — finestra (tab, thumbnail, copia async, cestino, apri-con) | ✅ | ❌ non iniziato |
| File manager — desktop (sfondo + icone) | ✅ | ⚠️ prototipo validato (manca thumbnail, monitor cartelle, multi-monitor, fit/center) |
| Voce sessione in `/usr/share/xsessions` (login da display manager) | ✅ | ❌ da fare |
| **Demone notifiche** (`org.freedesktop.Notifications`) | ✅ | ❌ manca |
| **Agente PolicyKit** (prompt grafici per privilegi) | ✅ | ❌ manca |
| **Settings/XSettings daemon** (tema GTK, cursore, DPI/HiDPI) | ✅ | ❌ manca |
| **Power management** (coperchio, sospensione, batteria scarica) | ✅ | ⚠️ solo applet batteria |
| **Automount rimovibili** (udisks2/gvfs) | ✅ | ❌ (in NexusSec assente per scelta forense; su DE generico va offerto opzionale) |
| Screenshot / lock-screensaver / config schermi | ✅ | ⏳ da portare (nxs-screenshot/screensaver/screens) |
| Multilingua (i18n) | spesso parziale | ✅ punto di forza (it/en/fr/es/de) |
| Packaging installabile (apk/deb/rpm) + MIME/app predefinite | ✅ | ❌ da fare |

## Cosa manca davvero — priorità

1. **Portare il core**: pannello + Centro di Controllo + profili (il grosso, ma è
   porting, non invenzione). Il port del pannello deve includere le migliorie già
   in `nxs_cc/panel.py`: multi-monitor (una barra per schermo), orologio con
   regolazione ora/fuso, monitor risorse CPU/RAM/Rete (Cairo).
2. **Finire `vesper-files` (finestra)**: viste icone/lista, tab, copia/sposta
   async (`Gio`), cestino freedesktop, segnalibri, apri-con MIME, thumbnail.
3. **Demone notifiche** freedesktop — atteso da qualsiasi DE (oggi assente anche
   in NexusSec: `notify-send` è un no-op senza demone).
4. **Agente PolicyKit** — indispensabile su una distro "normale" per i prompt
   grafici di privilegio (in NexusSec bastava `doas` nopass; fuori no).
5. **Settings/XSettings daemon** — propagazione tema GTK/cursore/DPI (HiDPI).
6. **Power management** completo (coperchio/sospensione/batteria) — senza logind
   serve un approccio via `acpid`/handler.
7. **Automount opzionale** (udisks2) nel file manager — su Vesper generico ha
   senso, a differenza della modalità forense di NexusSec.
8. **Sessione**: voce `.desktop` in `xsessions`, logout/lock/shutdown, autostart XDG.
9. **Packaging** (APKBUILD + poi deb/rpm) e app/MIME predefinite.

## Sintesi

Vesper **non è indietro come idee** (profili dinamici e i18n sono sopra la media
dei DE leggeri), ma è **indietro come implementazione** (scaffold). I buchi
funzionali veri rispetto agli altri DE sono i **servizi di sistema** che NexusSec
dava per scontati nel contesto live: **notifiche, PolicyKit, settings-daemon,
power-management, automount opzionale**.

## Strategia concordata (2026-09-13)

Il desktop si **matura in NexusSec** (dove ha un ambiente reale in cui girare e
si collauda). **Vesper raccoglie**: ogni feature desktop aggiunta a NexusSec
(es. il blocco "Privacy e anonimato" nel Centro di Controllo) sarà ereditata dal
porting. I 5 servizi da DE generico restano lavoro specifico di Vesper, da
affrontare quando lo attiveremo. Primo passo quando si riprende: **porting del
core** (pannello + CC + profili) per far *partire* davvero il DE.
