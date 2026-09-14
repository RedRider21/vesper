# Vesper — piano di porting dal desktop di NexusSec OS

> Documento di **handoff**: contiene tutto il necessario per portare in Vesper —
> in una sessione dedicata — il lavoro desktop già maturato in **NexusSec OS**,
> **senza riferimenti a NexusSec** (Vesper è un DE generico e autonomo).
> Ultimo aggiornamento: 2026-09-14.

## 0. Stato
- Vesper oggi = **scaffold** (1 commit reale). Di concreto solo
  `src/vesper/filemanager/desktop.py` (modalità desktop del file manager).
- Il **desktop è maturo in NexusSec** e va **portato** qui (rinominato e
  scollegato dalla distro). Il porting **NON è ancora iniziato**.

## 1. Sorgente di verità (dove sta il codice da portare)
Repo `../NexusSec-OS/` (branch `master`):
- `overlay/usr/local/lib/nxs_cc/` — pannello + Centro di Controllo + CSS/tema:
  - `common.py` (725 righe) — CSS/tema, `apply_css()`, `panel_window()` (con
    ScrolledWindow), helper `icon_button`, centratura multi-monitor.
  - `panel.py` (2833) — pannello inferiore: menu+ricerca, tasklist, orologio+fuso,
    monitor risorse (Cairo), tray, applet.
  - `views.py` (3540) — viste del Centro di Controllo.
  - `main.py` (319) — dispatch argomenti → viste; `paneltheme.py`, `panelcfg.py`,
    `launcherd.py` (launcher "caldo"), `bootsplash.py` (splash).
- `overlay/usr/local/lib/nxs_profiles/` — `model.py` (917), `selector.py` (231),
  `cli.py` (182), `isolation.py` (766, **NON portare**, è l'arsenale).
- `overlay/usr/local/bin/nxs-*` — launcher/utility (vedi §3).
- `overlay/home/nexus/.config/openbox/` (rc.xml, menu.xml, autostart),
  `.themes/` (temi Openbox + CSS finestre + sfondi), `.xinitrc`, `.profile`.

## 2. Cosa PORTARE (generico) vs ESCLUDERE (NexusSec-specifico)

### PORTARE (fa parte del DE generico)
- **Core**: `common.py` (CSS/tema), `panel.py` (pannello), le viste di `views.py`
  **generiche**, `main.py`, `launcherd.py`, `bootsplash.py`, `paneltheme.py`,
  `panelcfg.py`.
- **Profili come PRESET di aspetto** (accent + sfondo + tema icone/finestre):
  da `model.py`/`selector.py` tenere SOLO il meccanismo accent/sfondo/temi
  (NIENTE meta-pacchetti `sec-profile-*`, niente `apk add` dei profili).
- **Applet pannello generiche**: audio, luminosità, batteria, Bluetooth, WiFi,
  schermi, orologio/calendario+fuso, monitor risorse, **notifiche**, tasklist.
- **Utility desktop** (vedi §3): sessione/logout, greeter, night-light, appunti,
  editor scorciatoie, screenshot, blocco schermo, datetime.
- **Aspetto coordinato**: temi finestre (Core/Retro/Cards) + prompt terminale.
- **i18n** (`nxs_i18n` → `vesper.i18n`).
- **File manager** `vesper-files` (già iniziato).

### ESCLUDERE (è la distro di sicurezza, non un DE)
- **Arsenale tool**: `isolation.py`, `cli.py` (nxs-tool), `repo.json`,
  `kali_catalog.json`, i profili di **sicurezza** `sec-profile-*`.
- **Sicurezza/anonimato**: `nxs-firewall`, `nxs-tor`, `nxs-anon`, `nxs-macspoof`,
  `nxs-panic`, `nxs-metadata`, `nxs-harden`, `nxs-writeblock`, dischi forensic.
- **HORUS** (`nxs-horus`) e il resto OSINT/forense.
- **Persistenza/installazione distro**: `nxs-persist`, `nxs-install`,
  `nxs-unlock-data`, LUKS NXSDATA, apkovl/genapkovl, mkimage, aports.
- **greeter/auth**: il **concetto** greeter si porta (vedi §3), ma con auth
  generica (PAM se disponibile, o `vesper-chkpwd` setuid come su NexusSec).

## 3. Feature desktop "realizzate finora" — da portare (con note)
| NexusSec (sorgente) | Vesper (destinazione) | Note / gotcha |
|---|---|---|
| `nxs-session` | `vesper-session` | dialogo logout/lock/reboot/shutdown; icone azioni |
| `nxs-greeter` | `vesper-greeter` | GTK, logo esagonale (Cairo), card a tema, mostra/nascondi pw, **sfondo disegnato con Cairo (Overlay+DrawingArea)** — NON usare CSS background-image su window (in GTK3 non dipinge). Serve `DISPLAY` (guardia con messaggio). |
| `nxs-authcheck` + `aports/nxs-chkpwd` (C setuid) | `vesper-chkpwd` | Alpine non usa PAM → verifica shadow con crypt via ctypes/C. **Setuid deve stare in `/usr/bin`** (abuild vieta /usr/local). Su distro con PAM valutare `pam`/`unix_chkpwd`. Password SEMPRE da STDIN, mai argv. |
| `nxs-nightlight` | `vesper-nightlight` | **usare gamma `xrandr`** (on/off/toggle/restore). L'overlay traslucido è stato SCARTATO: in VM senza compositore diventa opaco e copre lo schermo. |
| `nxs-clipboard` | `vesper-clipboard` | daemon + popup finestra-lista con **refresh live**; NON `Gtk.Menu.popup_at_pointer` (dà GTK-CRITICAL da terminale). |
| `nxs-keys` + editor in `views.open_hotkeys` | `vesper-keys` + vista | editor scorciatoie rc.xml **text-based** (preserva commenti), cattura combinazione, applica con `openbox --reconfigure`. |
| dunst + `dunstrc` + autostart | idem | demone notifiche; feedback install → in Vesper NON c'è install-on-demand, quindi le notifiche restano per app generiche. |
| `acpid` + `/etc/acpi/nxs-handler.sh` | `vesper` power mgmt | coperchio→lock, accensione→shutdown, batteria scarica (sysfs nel pannello). |
| gate greeter al boot: `.profile` (loop startx) + autostart (dopo splash) + flag | equivalente Vesper | flag `~/.config/vesper/greeter.on` o via un `vesper-session`/DM. Su distro generica valutare integrazione con un vero DM o con la sessione xinit. |

## 4. Regole di rename / decoupling (applicare ovunque)
- Codice: `nxs_cc` → `vesper` (pacchetto), `nxs_profiles` → `vesper.profiles`,
  `nxs_i18n` → `vesper.i18n`.
- Comandi: `nxs-*` → `vesper-*` (aggiornare menu.xml, autostart, rc.xml, chiamate
  interne, e i path assoluti tipo `/usr/local/bin/...` → path Vesper).
- Percorsi dati: `/usr/local/share/nexussec/` → `/usr/share/vesper/`;
  `/etc/sec_os/` e `~/.config/nxs/` → `~/.config/vesper/`; sfondi/temi sotto
  `/usr/share/vesper/` o `~/.local/share/vesper/`.
- Branding: rimuovere nome/logo/marchi **NexusSec**; la **palette** si può tenere
  ma rinominata (Vesper = stella della sera, accent cyan di default).
- Rimuovere gli import "morbidi" verso `nxs_profiles.model` legati all'arsenale;
  tenere solo model degli aspetti (accent/sfondo/tema).
- **Niente** riferimenti a NexusSec nei testi/commenti (richiesta esplicita utente).

## 5. Piano a fasi (ordine consigliato)
1. **common** (`vesper.common`: CSS/tema, apply_css, panel_window, icon_button).
2. **profiles-as-presets** (accent/sfondo/temi finestre + prompt), senza sicurezza.
3. **panel** (`vesper-panel`): menu+ricerca, tasklist, orologio+fuso, monitor
   risorse, multi-monitor; applet generiche (audio/brightness/battery/bt/wifi/
   screens/notifiche/clipboard/nightlight). Rimuovere l'applet "scudo" sicurezza.
4. **control center** (`vesper-settings`): aspetto, sfondo, schermi, audio, BT,
   mouse, tastiera, autostart, **editor scorciatoie**. Rimuovere: sicurezza/
   harden/firewall/utenti/persist/pacchetti-apk/profili-sicurezza/HORUS.
5. **utility** (§3): session, greeter(+chkpwd), nightlight, clipboard, keys,
   screenshot, screensaver, datetime; notifiche (dunst) + power (acpid).
6. **session**: `.xinitrc`/`.profile` equivalenti, voce `/usr/share/xsessions/`,
   loop logout→greeter.
7. **file manager** finestra (completare `vesper-files`).
8. **packaging** (APKBUILD Alpine + poi deb/rpm) e MIME/app predefinite.

## 6. Servizi da DE generico ANCORA da implementare (non presenti in NexusSec)
(vedi anche `confronto-desktop.md`)
1. **Demone notifiche**: c'è dunst (ok).
2. **Agente PolicyKit** (prompt grafici privilegi) — **manca**.
3. **Settings/XSettings daemon** (tema GTK/cursore/DPI/HiDPI) — **manca**.
4. **Power management** completo (oltre lid/power base) — parziale.
5. **Automount rimovibili** (udisks2) opzionale — **manca** (NexusSec lo evita
   apposta; su Vesper generico ha senso offrirlo).

## 7. Gotcha tecnici ereditati (NON re-derivare)
- **GTK3, non GTK4**: niente `text-transform`/`letter-spacing` nel CSS (eccezione
  → crash di `apply_css`). Uppercase in Python.
- **.pyc stale**: non impacchettare `__pycache__`; con mtime azzerati Python
  esegue bytecode vecchio. Il packaging deve eliminarli.
- **Riavvio pannello**: `pkill -f` da una shell il cui argv contiene il pattern si
  autouccide → usare pkill diretto + launcher con argv "pulito".
- **rc.xml Openbox** deve restare il default COMPLETO (sezione `<mouse>`),
  altrimenti finestre non gestibili.
- **Setuid**: i pacchetti apk NON possono installare in `/usr/local` → `/usr/bin`.
- **greeter background**: Cairo (Overlay+DrawingArea), non CSS.
- **nightlight**: gamma xrandr (overlay opaco in VM).

## 8. Come riprendere in una sessione dedicata
Aprire una sessione nella cartella `vesper/`, leggere QUESTO file +
`docs/design.md` + `docs/confronto-desktop.md`. Il codice sorgente da cui copiare
è in `../NexusSec-OS/overlay/usr/local/`. Procedere per fasi (§5), committando a
ogni passo (regola: commit locale a ogni modifica), **senza** riferimenti a NexusSec.
