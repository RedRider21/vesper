# Vesper — stato del porting

> Il porting del desktop è **fatto**. Questo documento tiene il conto di cosa è
> stato portato, cosa è stato volutamente lasciato fuori e cosa manca ancora
> per stare alla pari con gli altri ambienti desktop.
> Ultimo aggiornamento: 2026-09-19.

## 1. Fatto

| Fase | Contenuto | Dove |
|---|---|---|
| 1. Core | percorsi, CSS/tema, accent e skin a caldo, skin del pannello | `src/vesper/{paths,common,paneltheme,panelcfg}.py` |
| 2. Preset | preset di aspetto (accento, sfondo, icone, stile finestre), 14 colori, marchio nuovo, 14 sfondi | `src/vesper/profiles/`, `data/`, `tools/make-wallpapers.py` |
| 3. Pannello | barra multi-monitor, applet, menu applicazioni per categorie, i18n | `src/vesper/panel/`, `src/vesper/i18n/` |
| 4. Utility e sessione | 28 comandi `vesper-*`, avvio sessione, autostart XDG, installazione | `bin/`, `install.sh`, `data/skel/` |
| 5. File manager | finestra (schede, viste, operazioni async, cestino) e desktop (sfondo + icone) | `src/vesper/filemanager/` |
| 6. Centro di Controllo | 19 viste native + salvaschermo con blocco schermo | `src/vesper/control_center/`, `src/vesper/screensaver/` |
| 7. Aspetto coordinato | icone del colore del preset, temi finestre Retro/Cards per ogni preset, 1977 e Arc inclusi | `tools/make-openbox-themes.py`, `data/themes/` |
| 8. Distribuzione | `.deb` pulito secondo lintian, tarball, PKGBUILD, spec RPM, APKBUILD | `tools/make-deb.sh`, `packaging/` |

## 2. Lasciato fuori di proposito

Roba della distribuzione di origine, non di un ambiente desktop: arsenale di
strumenti e relativo catalogo, profili di sicurezza, firewall, Tor/anonimato,
MAC spoofing, panico/wipe, write-blocker forense, gestione pacchetti apk,
gestione utenti, hardening, dischi e casi forensi, OSINT, assistente IA,
persistenza e installazione della distro, splash di avvio, demone
"launcher caldo".

## 3. Ancora da fare

1. **Schermata di login (greeter)** — c'era nella sorgente ma legata a
   `chkpwd` setuid e ad Alpine. Su una distro qualunque conviene appoggiarsi
   al display manager, oppure portare il greeter con autenticazione PAM.
2. **Demone notifiche proprio** — oggi Vesper avvia quello che trova (dunst,
   mako, xfce4-notifyd). Un demone nostro darebbe notifiche a tema.
3. **Agente PolicyKit proprio** — stessa logica: oggi si avvia quello
   installato, se c'è.
4. **Daemon XSettings** — propagazione di tema, cursore e DPI/HiDPI alle app
   che non rileggono `settings.ini`.
5. **Power management completo** — coperchio, sospensione, batteria scarica
   (oggi c'è l'applet batteria e l'avviso di batteria scarica).
6. **Automount dei dispositivi rimovibili** (udisks2) nel file manager.
7. **Pagine di manuale** per i comandi `vesper-*` (l'unico avviso che lintian
   segnala sul pacchetto).
8. **Set di icone proprio** — oggi si usano quelli del sistema, scelti per
   colore. Un tema icone originale sarebbe il passo successivo.

## 4. Gotcha già risolti (non re-derivare)

Sono elencati in [`../CLAUDE.md`](../CLAUDE.md): riavvio del pannello senza
auto-suicidio, `rc.xml` completo, `.pyc` stantii, provider CSS per-widget,
viste a elenco bianche, `settings.ini` senza `[Settings]`, lanciatori
`.desktop` rifiutati da GLib, sfondo del salvaschermo in Cairo, luce blu con
gamma xrandr.
