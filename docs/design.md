# Vesper — piano di lavoro

Scaffold creato il 2026-08-16. Sviluppo in sessione dedicata.

## Fasi

1. **Porting core** — copiare da `../NexusSec-OS/overlay/usr/local/lib/nxs_cc`
   e `nxs_profiles`, rinominare `nxs_* → vesper.*`, scollegare i percorsi
   NexusSec (`/usr/local/share/nexussec/`, `/etc/sec_os/`) in favore di
   `~/.config/vesper/` + `/usr/share/vesper/`. Risultato: pannello + Centro di
   Controllo + profili funzionanti come DE generico.

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
