# Vesper — piano di lavoro

Scaffold creato il 2026-08-16. Sviluppo in sessione dedicata.

## Fasi

1. **Porting core** — copiare da `../NexusSec-OS/overlay/usr/local/lib/nxs_cc`
   e `nxs_profiles`, rinominare `nxs_* → vesper.*`, scollegare i percorsi
   NexusSec (`/usr/local/share/nexussec/`, `/etc/sec_os/`) in favore di
   `~/.config/vesper/` + `/usr/share/vesper/`. Risultato: pannello + Centro di
   Controllo + profili funzionanti come DE generico.

   > **Il port del pannello DEVE includere queste migliorie (2026-08-19), già
   > presenti nella sorgente di riferimento `nxs_cc/panel.py`:**
   > 1. **Multi-monitor** — `run()` crea **una barra per monitor** (`Panel(i)`
   >    per ogni `Gdk.Screen.get_n_monitors()`); `_place()` usa l'indice
   >    monitor invece del solo primario; ricostruzione su `monitors-changed`/
   >    `size-changed`. Così barra **e menu** compaiono anche sullo schermo
   >    esterno (il menu si apre sul monitor dove si clicca). NB: i `GLib.timeout`
   >    dei callback ritornano `self._alive` per auto-cancellarsi quando la barra
   >    viene distrutta (hotplug). In Vesper NON serve `panelcfg` di NexusSec:
   >    usare i propri percorsi.
   > 2. **Orologio con regolazione ora/data/fuso** — il popup del calendario ha
   >    spin HH:MM + combo fuso (`COMMON_TZ`) con "Imposta", che chiama un helper
   >    privilegiato (in NexusSec `nxs-datetime`, via `doas`; in Vesper l'analogo
   >    `vesper-datetime` con `pkexec`/`doas`). Dopo il set: `time.tzset()` +
   >    ridisegno orologio. Richiede `tzdata` (zoneinfo) tra i depends.
   > 3. **Monitor risorse (multiload)** — applet `LoadMonitor` (`Gtk.EventBox` +
   >    3 `Gtk.DrawingArea` Cairo) con mini-grafici **CPU/RAM/Rete** letti da
   >    `/proc` (nessuna dipendenza extra oltre `py3-cairo`); clic → Monitor
   >    risorse del Centro di Controllo. Rete auto-scalata sul picco.

2. **vesper-files (finestra)** — file manager GTK3:
   - viste icone/lista (`Gtk.IconView` / `Gtk.TreeView`);
   - navigazione con cronologia, barra percorso, tab;
   - operazioni file async via `Gio` (copia/sposta/elimina con progress);
   - cestino freedesktop (`~/.local/share/Trash`);
   - segnalibri (`~/.config/gtk-3.0/bookmarks`), luoghi (home, dispositivi);
   - apri-con via MIME/`.desktop`, proprietà, permessi;
   - thumbnail (`GdkPixbuf`, cache in `~/.cache/thumbnails`).

3. **vesper-files (desktop)** — `--desktop`: finestra root `Gdk.WindowTypeHint.DESKTOP`,
   disegna sfondo (modalità stretch/fill/center) + icone del desktop
   (`~/Scrivania`/`~/Desktop`) con drag, selezione, menu contestuale. Sostituisce
   `pcmanfm --desktop` e `pcmanfm --set-wallpaper`.

   > **PROTOTIPO VALIDATO** (`filemanager/desktop.py`, 2026-08-17). Architettura
   > decisa dopo prove fallite: **NON** Overlay+Fixed né `Gtk.Layout` (occlusione
   > tra GdkWindow → sfondo nero; draw inaffidabile). Soluzione = **un unico
   > `Gtk.DrawingArea`** che disegna in **Cairo** wallpaper + icone; le icone sono
   > DATI (`IconItem`), hit-test e drag a mano, `queue_draw()` per il repaint
   > (come libfm ma senza il bug "icona invisibile finché non clicchi").
   > Ottiene: **posizionamento libero**, **niente auto-riallineamento**, posizioni
   > persistenti (`~/.config/vesper/desktop-items.json`), toggle "Allinea
   > automaticamente". Screenshot di prova in `docs/proto/`.
   > **Dipendenza runtime**: `py3-cairo` (pycairo) oltre a gtk3/pygobject3/pango/
   > gdk-pixbuf. Da completare: modalità finestra, thumbnail, monitor cartelle,
   > multi-monitor, wallpaper fit/center.

4. **vesper-session** — script/eseguibile che lancia Openbox e i componenti in
   ordine: `vesper-files --desktop` (sfondo+icone) → `vesper-panel` →
   applica profilo (accent+CSS). Entry `.desktop` in `/usr/share/xsessions/`
   così i display manager lo elencano.

5. **Packaging Alpine** — `packaging/alpine/`: APKBUILD per
   `vesper-session`/`vesper-panel`/`vesper-settings`/`vesper-files`. Poi anche
   pacchetti per altre distro (deb/rpm) se serve. Verificare che i depends
   **non** includano più pcmanfm.

## Integrazione con NexusSec OS

Quando Vesper è maturo, NexusSec può **adottarlo** al posto dell'attuale mix
`nxs_cc` + pcmanfm: un solo DE Python coerente, più leggero. Fino ad allora la
distro resta com'è (pcmanfm incluso).

## Decisioni prese

- Nome: **Vesper** (alternative scartate: Lumen, Nyx).
- File manager proprio in Python, **due modalità dallo stesso codice** (finestra
  + desktop), per **eliminare pcmanfm**.
- GTK3 (non GTK4), Openbox come WM, stile flat scuro con accent cyan.
