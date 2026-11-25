#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
#
# Collaudo della sessione Vesper: parte DENTRO il container (lo lancia
# tools/collaudo.sh). Schermo virtuale Xvfb, nessuna rete, home temporanea,
# progetto montato in sola lettura su /vesper, esiti e schermate in /out.
#
# Ogni controllo scrive una riga "OK|KO|--  <nome>  <dettaglio>" in
# /out/esito.txt; l'host le legge e decide l'esito finale.
set -u
export HOME=/home/prova USER=prova XDG_RUNTIME_DIR=/tmp/xdg
export PATH=/vesper/bin:/usr/local/bin:/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1
export NO_AT_BRIDGE=1
mkdir -p "$XDG_RUNTIME_DIR" /out/schermate; chmod 700 "$XDG_RUNTIME_DIR"
CONF=$HOME/.config/vesper; CACHE=$HOME/.cache/vesper
ESITO=/out/esito.txt; : > "$ESITO"
W=1280; H=800

ok() { printf 'OK  %s  %s\n' "$1" "${2:-}" >> "$ESITO"; }
ko() { printf 'KO  %s  %s\n' "$1" "${2:-}" >> "$ESITO"; }
na() { printf '--  %s  %s\n' "$1" "${2:-}" >> "$ESITO"; }   # non applicabile
check() {   # check <nome> <dettaglio-se-ko> <comando...>
  n=$1; d=$2; shift 2
  if "$@" >/dev/null 2>&1; then ok "$n"; else ko "$n" "$d"; fi
}
foto() { import -window root "/out/schermate/$1.png" 2>/dev/null || true; }
# python con l'ambiente dei comandi (pacchetto vesper, dati) e il marcatore di
# sessione, come i processi figli della sessione vera
# (percorsi espliciti: env.sh si orienta da $0, che qui non e' un comando)
vpy() { ( cd /tmp && PYTHONPATH=/vesper/src VESPER_DATA_DIRS=/vesper/data \
          VESPER_SESSION=1 python3 -c "$1" ); }

# preparazione: Openbox come gestore (marco non c'e'), lingua inglese per
# verificare che passi a tutta la sessione
mkdir -p "$CONF"
echo openbox > "$CONF/wm"
echo en > "$CONF/lang"

Xvfb :9 -screen 0 ${W}x${H}x24 -nolisten tcp >/dev/null 2>&1 &
export DISPLAY=:9
i=0; while [ ! -S /tmp/.X11-unix/X9 ] && [ $i -lt 50 ]; do sleep 0.1; i=$((i+1)); done

dbus-run-session -- vesper-session >/out/sessione-stdout.log 2>&1 &
SESS=$!

# I comandi che seguono si comportano come se partissero DALLA sessione (dal
# Centro di Controllo o dal selettore): fuori dalla sessione Vesper,
# giustamente, non ricarica Openbox e il collaudo non vedrebbe i cambi.
export VESPER_SESSION=1 VESPER_RC_XML="$CONF/openbox-rc.xml"

# --- funzioni di osservazione ----------------------------------------------
barra() {   # 0 se la barra (finestra larga quanto lo schermo, bassa) c'e'
  wmctrl -lG 2>/dev/null | awk -v w=$W '$5==w && $6>=20 && $6<=80 {f=1} END{exit !f}'
}
desktop() { wmctrl -l 2>/dev/null | grep -q ' desktop$'; }
attendi() { # attendi <secondi> <comando...>
  t=$(( $1 * 10 )); shift
  while [ $t -gt 0 ]; do "$@" && return 0; sleep 0.1; t=$((t-1)); done
  return 1
}
env_sessione() {  # variabile <nome> dall'ambiente di openbox (figlio della sessione)
  p=$(cat "$CACHE/wm.pid" 2>/dev/null) || return 1
  tr '\0' '\n' < "/proc/$p/environ" 2>/dev/null | sed -n "s/^$1=//p"
}
# conta per quanti decimi di secondo la barra manca durante un'azione
buchi_barra() {
  "$@" >/dev/null 2>&1 &
  pa=$!; assenze=0; t=0
  while [ $t -lt 60 ]; do
    barra || assenze=$((assenze+1))
    sleep 0.1; t=$((t+1))
  done
  wait $pa 2>/dev/null
  echo $assenze
}

# --- 1. avvio ---------------------------------------------------------------
if attendi 25 barra; then ok "avvio: barra presente"; else ko "avvio: barra presente" "nessuna barra dopo 25 s"; fi
if attendi 10 desktop; then ok "avvio: desktop (sfondo e icone)"; else ko "avvio: desktop (sfondo e icone)" "finestra desktop assente"; fi
sleep 2; foto 01-avvio
check "avvio: processo di sessione vivo" "vesper-session non gira" kill -0 $SESS
p=$(cat "$CACHE/wm.pid" 2>/dev/null)
if [ -n "$p" ] && tr '\0' ' ' < /proc/$p/cmdline | grep -q -- "--config-file $CONF/openbox-rc.xml"; then
  ok "openbox: parte col rc.xml di Vesper"
else ko "openbox: parte col rc.xml di Vesper" "cmdline: $(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null)"; fi

# --- 2. menu del gestore finestre --------------------------------------------
f=$(sed -n 's#.*<file>\(.*\)</file>.*#\1#p' "$CONF/openbox-rc.xml" | head -1)
case "$f" in
  /*) [ -f "$f" ] && ok "menu openbox: percorso assoluto ed esistente" || ko "menu openbox: percorso assoluto ed esistente" "$f manca" ;;
  *) ko "menu openbox: percorso assoluto ed esistente" "relativo: $f" ;;
esac
if grep -q 'Unable to find a valid menu' "$CACHE/session.log" /out/sessione-stdout.log 2>/dev/null; then
  ko "menu openbox: caricato" "Openbox non trova il menu"
else ok "menu openbox: caricato"; fi

# --- 2b. icone del menu (da NexusSec) ---------------------------------------
n_ic=$(grep -c "icon=\"$CACHE/menu-icons/" "$CONF/openbox-menu.xml" 2>/dev/null)
[ "${n_ic:-0}" -ge 15 ] && ok "menu openbox: icone con il percorso vero ($n_ic)" \
  || ko "menu openbox: icone con il percorso vero" "trovate ${n_ic:-0}"
grep -q '@ICONE@' "$CONF/openbox-menu.xml" && ko "menu openbox: segnaposto tradotto" "@ICONE@ rimasto" \
  || ok "menu openbox: segnaposto tradotto"
mancanti=$(grep -o "icon=\"[^\"]*\"" "$CONF/openbox-menu.xml" | cut -d'"' -f2 | while read -r f; do [ -f "$f" ] || echo "$f"; done | wc -l)
[ "$mancanti" -eq 0 ] && ok "menu openbox: tutti i file delle icone esistono" \
  || ko "menu openbox: tutti i file delle icone esistono" "$mancanti mancanti"

# --- 3. lingua della sessione ---------------------------------------------------
[ "$(env_sessione LANGUAGE)" = en ] && ok "lingua: LANGUAGE passa alla sessione" \
  || ko "lingua: LANGUAGE passa alla sessione" "LANGUAGE='$(env_sessione LANGUAGE)'"
grep -q 'label="Tools"' "$CONF/openbox-menu.xml" 2>/dev/null && ok "lingua: menu openbox in inglese" \
  || ko "lingua: menu openbox in inglese" "openbox-menu.xml non e' quello inglese"

# --- 4. prompt ---------------------------------------------------------------
pc=$(env_sessione PROMPT_COMMAND); sh_rc=$(env_sessione VESPER_SHRC)
if [ -n "$pc" ] && [ -r "$sh_rc" ]; then
  ok "prompt: PROMPT_COMMAND esportato dalla sessione"
  echo default > "$CONF/prompt"
  ps1=$(VESPER_SESSION=1 VESPER_SHRC="$sh_rc" PROMPT_COMMAND="$pc" PS1=ORIG \
        bash --norc -ic "eval \"\$PROMPT_COMMAND\"; printf %s \"\$PS1\"" 2>/dev/null)
  case "$ps1" in *38\;2\;*) ok "prompt: stile Vesper applicato" ;; *) ko "prompt: stile Vesper applicato" "PS1='$ps1'" ;; esac
  echo system > "$CONF/prompt"
  ps1=$(VESPER_SESSION=1 VESPER_SHRC="$sh_rc" PROMPT_COMMAND="$pc" PS1=ORIG \
        bash --norc -ic "eval \"\$PROMPT_COMMAND\"; printf %s \"\$PS1\"" 2>/dev/null)
  [ "$ps1" = ORIG ] && ok "prompt: stile system lascia il prompt intatto" \
    || ko "prompt: stile system lascia il prompt intatto" "PS1='$ps1'"
else
  ko "prompt: PROMPT_COMMAND esportato dalla sessione" "PROMPT_COMMAND='$pc' VESPER_SHRC='$sh_rc'"
fi

# --- 5. cambio preset (e barra che non sparisce) --------------------------------
n=$(buchi_barra vesper-profile set lime)
grep -qi 'b8ff3b' "$CONF/accent.css" 2>/dev/null && ok "preset: accento applicato (lime)" \
  || ko "preset: accento applicato (lime)" "accent.css non aggiornato"
grep -q '<name>Vesper-Core-lime</name>' "$CONF/openbox-rc.xml" && ok "preset: tema finestre coordinato" \
  || ko "preset: tema finestre coordinato" "$(grep -o '<name>Vesper-[^<]*' "$CONF/openbox-rc.xml" | head -1)"
if [ "$n" -eq 0 ]; then ok "preset: la barra non sparisce"; else ko "preset: la barra non sparisce" "assente per ~$((n*100)) ms"; fi
attendi 10 barra && ok "preset: barra presente dopo il cambio" || ko "preset: barra presente dopo il cambio" "barra non tornata"
sleep 1; foto 02-preset-lime

# --- 5b. cambio preset dal SELETTORE (come il pulsante "Applica"), con
# passaggio a interfaccia chiara: la barra deve restare e cambiare colore
crop_barra() { import -window root -crop ${W}x40+0+$((H-40)) "$1" 2>/dev/null; }
crop_barra /tmp/barra-prima.png
n=$(buchi_barra vpy 'from vesper.profiles import model as m; m.activate_preset("bianco")')
if [ "$n" -eq 0 ]; then ok "selettore: la barra non sparisce (preset bianco)"; else ko "selettore: la barra non sparisce (preset bianco)" "assente per ~$((n*100)) ms"; fi
sleep 1; crop_barra /tmp/barra-dopo.png
d=$(compare -metric AE /tmp/barra-prima.png /tmp/barra-dopo.png /dev/null 2>&1 | cut -d' ' -f1 | cut -d. -f1)
if [ "${d:-0}" -gt 1000 ] 2>/dev/null; then ok "selettore: la barra si ricolora a caldo"
else ko "selettore: la barra si ricolora a caldo" "pixel diversi: ${d:-?}"; fi
foto 02b-preset-bianco
vesper-profile set lime >/dev/null 2>&1; sleep 1

# icone del menu nel colore del preset (lime)
grep -qi 'fill="#b8ff3b"' "$CACHE/menu-icons/terminal.svg" 2>/dev/null \
  && ok "menu openbox: icone nel colore del preset" \
  || ko "menu openbox: icone nel colore del preset" "$(grep -o 'fill="#[0-9a-fA-F]*"' "$CACHE/menu-icons/terminal.svg" | head -1)"

# --- 6. famiglia macOS scuro -----------------------------------------------------
vesper-profile theme mac-scuro >/dev/null 2>&1
grep -q '<name>Vesper-Mac-Scuro-lime</name>' "$CONF/openbox-rc.xml" && ok "temi: macOS scuro nel colore del preset" \
  || ko "temi: macOS scuro nel colore del preset" "$(grep -o '<name>Vesper-[^<]*' "$CONF/openbox-rc.xml" | head -1)"
grep -q '<titleLayout>CIMLN</titleLayout>' "$CONF/openbox-rc.xml" && ok "temi: pulsanti a sinistra" \
  || ko "temi: pulsanti a sinistra" "$(grep -o '<titleLayout>[^<]*' "$CONF/openbox-rc.xml")"

# menu del tasto destro sul desktop, aperto e fotografato
sleep 3   # Openbox ricaricato dal cambio di preset, grafici aggiornati
xdotool mousemove 300 300 click 3; sleep 1.2; foto 02c-menu-tasto-destro
xdotool key Escape; sleep 0.4

# --- 7. una finestra si apre davvero (Centro di Controllo) --------------------
prima=$(wmctrl -l | wc -l)
vesper-control-center >/dev/null 2>&1 &
if attendi 20 sh -c "[ \$(wmctrl -l | wc -l) -gt $prima ]"; then
  ok "finestre: il Centro di Controllo si apre"
else ko "finestre: il Centro di Controllo si apre" "nessuna finestra nuova in 20 s"; fi
sleep 2; foto 03-centro-controllo
# chiude le finestre normali (non barra, non desktop), per id
wmctrl -lG | awk -v w=$W '$NF!="desktop" && !($5==w && $6<=80) {print $1}' |
  while read -r id; do wmctrl -i -c "$id"; done
sleep 1

# --- 8. skin coordinata e "vince l'ultima scelta" -------------------------------
# come fa il Centro di Controllo quando si sceglie una skin (con Coordina)
crop_barra /tmp/barra-prima.png
n=$(buchi_barra vpy 'from vesper import paneltheme as p
from vesper.profiles import model as m
p.set_theme("amber"); m.coordina_con_skin("amber")')
if [ "$n" -eq 0 ]; then ok "skin: la barra non sparisce"; else ko "skin: la barra non sparisce" "assente per ~$((n*100)) ms"; fi
attendi 10 barra && ok "skin: barra presente dopo il cambio" || ko "skin: barra presente dopo il cambio" "barra non tornata"
sleep 1; crop_barra /tmp/barra-dopo.png
d=$(compare -metric AE /tmp/barra-prima.png /tmp/barra-dopo.png /dev/null 2>&1 | cut -d' ' -f1 | cut -d. -f1)
if [ "${d:-0}" -gt 1000 ] 2>/dev/null; then ok "skin: la barra si ricolora a caldo"
else ko "skin: la barra si ricolora a caldo" "pixel diversi: ${d:-?}"; fi
sleep 1; foto 04-skin-ambra
[ "$(cat "$CONF/skin-coord" 2>/dev/null)" = ambra ] && ok "skin: coordinata col preset piu' vicino (ambra)" \
  || ko "skin: coordinata col preset piu' vicino (ambra)" "skin-coord='$(cat "$CONF/skin-coord" 2>/dev/null)'"
vesper-profile set cyan >/dev/null 2>&1
[ ! -s "$CONF/skin-coord" ] && ok "skin: scegliere un preset annulla la coordinazione" \
  || ko "skin: scegliere un preset annulla la coordinazione" "skin-coord rimasto"
sleep 2; foto 05-preset-cyan

# --- 9. picom: mai con la configurazione dell'utente ---------------------------
for pp in $(pgrep -x picom); do
  if tr '\0' ' ' < /proc/$pp/cmdline | grep -q -- "--config $HOME/.config/vesper/\|--config /vesper/data/"; then
    ok "picom: con la configurazione di Vesper"
  else ko "picom: con la configurazione di Vesper" "$(tr '\0' ' ' < /proc/$pp/cmdline)"; fi
done
pgrep -x picom >/dev/null || na "picom: non avviato" "nessuna scheda video vera o tema senza compositor"

# --- 9b. energia ------------------------------------------------------------
if attendi 10 sh -c "[ -s $CACHE/power.pid ] && kill -0 \$(cat $CACHE/power.pid) 2>/dev/null"; then
  ok "energia: vesper-power attivo"
else ko "energia: vesper-power attivo" "power.pid assente o processo morto"; fi
vesper-power >/dev/null 2>&1
[ "$(pgrep -f 'vesper[.]power' | wc -l)" -le 1 ] && ok "energia: una sola istanza" \
  || ko "energia: una sola istanza" "$(pgrep -f 'vesper[.]power' | wc -l) processi"
vesper-power --stato 2>/dev/null | grep -q '^battery_action=' && ok "energia: --stato" \
  || ko "energia: --stato" "uscita inattesa"

# blocco schermo forzato (come prima della sospensione), con una password
vpy 'from vesper.screensaver import secret; secret.set_password("collaudo")' >/dev/null 2>&1
prima=$(wmctrl -l | wc -l)
vesper-screensaver --blocca >/dev/null 2>&1 &
if attendi 10 sh -c "[ \$(wmctrl -l | wc -l) -gt $prima ] || pgrep -f 'vesper[.]screensaver' >/dev/null"; then
  ok "blocco: vesper-screensaver --blocca si apre"
else ko "blocco: vesper-screensaver --blocca si apre" "nessun salvaschermo"; fi
sleep 2; foto 06-blocco
vesper-screensaver --blocca >/dev/null 2>&1; sleep 1
[ "$(pgrep -f 'vesper[.]screensaver' | wc -l)" -eq 1 ] && ok "blocco: niente secondo salvaschermo" \
  || ko "blocco: niente secondo salvaschermo" "$(pgrep -f 'vesper[.]screensaver' | wc -l) processi"
p=$(cat "$CACHE/screensaver.pid" 2>/dev/null); [ -n "$p" ] && kill "$p" 2>/dev/null; sleep 0.5

# schede nuove del Centro di Controllo: si aprono senza errori
for vista in energia supporti; do
  prima=$(wmctrl -l | wc -l)
  vesper-control-center $vista >/dev/null 2>&1 &
  if attendi 20 sh -c "[ \$(wmctrl -l | wc -l) -gt $prima ]"; then ok "centro di controllo: scheda $vista"
  else ko "centro di controllo: scheda $vista" "non si apre"; fi
  sleep 1.5; foto 07-$vista
  wmctrl -lG | awk -v w=$W '$NF!="desktop" && !($5==w && $6<=80) {print $1}' |
    while read -r id; do wmctrl -i -c "$id"; done
  sleep 1
done

# --- 10. log senza errori Python ---------------------------------------------
if grep -q 'Traceback' "$CACHE/session.log" /out/sessione-stdout.log "$CACHE"/*.log 2>/dev/null; then
  ko "log: nessun errore Python" "Traceback nel log (vedi /out)"
else ok "log: nessun errore Python"; fi

# --- 11. uscita dalla sessione --------------------------------------------------
vesper-session --logout >/dev/null 2>&1
if attendi 15 sh -c "! kill -0 $SESS 2>/dev/null"; then ok "uscita: vesper-session --logout chiude la sessione"
else ko "uscita: vesper-session --logout chiude la sessione" "sessione ancora viva dopo 15 s"; fi
grep -q 'sessione Vesper terminata' "$CACHE/session.log" && ok "uscita: ripristino eseguito" \
  || ko "uscita: ripristino eseguito" "manca la riga di fine sessione"

cp "$CACHE"/*.log /out/ 2>/dev/null
exit 0
