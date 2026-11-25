#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
#
# prova-xephyr.sh - il desktop Vesper in una FINESTRA (Xephyr), senza
# installarlo e senza toccare il desktop vero.
#
# La sessione gira in un container (Openbox, picom, GTK3) e disegna nella
# finestra Xephyr. Isolamento:
#   - il codice arriva dalla cartella del progetto in SOLA LETTURA;
#   - la home di prova e' una cartella temporanea ($XDG_RUNTIME_DIR), mai la
#     home vera: niente ~/.config/vesper, gsettings o dconf dell'utente;
#   - D-Bus di sessione proprio (dbus-run-session dentro il container);
#   - Xephyr si chiude per PID, mai per nome.
#
#   tools/prova-xephyr.sh              avvia (home nuova, come al primo accesso)
#   tools/prova-xephyr.sh --tieni      avvia conservando la home di prova
#   tools/prova-xephyr.sh --stop       chiude finestra e container
#   VESPER_PROVA_SIZE=1600x900 tools/prova-xephyr.sh
#   VESPER_PROVA_TEMA=mac|mac-scuro|core|retro|cards   famiglia finestre iniziale
#   VESPER_PROVA_IMG=...               immagine container (predefinita: quella
#                                      di prova di NexusSec, se c'e')
#
# Angoli arrotondati: in produzione Vesper avvia picom solo con una scheda
# video vera (backend GLX). Qui la home di prova riceve un picom.conf
# personale (~/.config/vesper/picom.conf) col backend software xrender, solo
# per vedere l'effetto: nelle VM quel backend puo' dare finestre bianche.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DISP="${VESPER_PROVA_DISPLAY:-:7}"
N="${DISP#:}"
SIZE="${VESPER_PROVA_SIZE:-1366x768}"
TEMA="${VESPER_PROVA_TEMA:-mac-scuro}"
CNAME=vesper-prova
IMG="${VESPER_PROVA_IMG:-localhost/nxs-prova}"
BASE="${XDG_RUNTIME_DIR:-/tmp}/vesper-prova"
HOMEP="$BASE/home"
XPID="$BASE/xephyr.pid"

ferma() {
  podman rm -f "$CNAME" >/dev/null 2>&1 || true
  if [ -f "$XPID" ]; then
    p=$(cat "$XPID" 2>/dev/null || echo "")
    # solo se quel PID e' ancora il NOSTRO Xephyr (PID riciclati)
    if [ -n "$p" ] && grep -qa "Xephyr" "/proc/$p/cmdline" 2>/dev/null; then
      kill "$p" 2>/dev/null || true
    fi
    rm -f "$XPID"
  fi
}

case "${1:-}" in
  --stop) ferma; echo "prova chiusa"; exit 0 ;;
esac

command -v Xephyr >/dev/null || { echo "manca Xephyr (pacchetto xserver-xephyr)"; exit 1; }
command -v podman >/dev/null || { echo "manca podman"; exit 1; }
if ! podman image exists "$IMG"; then
  echo "immagine $IMG assente: indica la tua con VESPER_PROVA_IMG"
  echo "(serve Alpine con openbox picom gtk+3.0 py3-gobject3 py3-cairo"
  echo " gtksourceview4 wmctrl xdotool xrandr feh dbus font-dejavu adwaita-icon-theme)"
  exit 1
fi
if [ -S "/tmp/.X11-unix/X$N" ] && [ ! -f "$XPID" ]; then
  echo "il display $DISP e' gia' occupato: scegline un altro con VESPER_PROVA_DISPLAY"
  exit 1
fi

ferma
mkdir -p "$BASE"
if [ "${1:-}" != "--tieni" ] || [ ! -d "$HOMEP" ]; then
  rm -rf "$HOMEP"
  mkdir -p "$HOMEP/.config/vesper"
  echo "openbox" > "$HOMEP/.config/vesper/wm"
  echo "$TEMA" > "$HOMEP/.config/vesper/theme"
  sed -e 's/backend = "glx";/backend = "xrender";/' -e 's/^vsync = true;/vsync = false;/' \
      -e 's/^blur-background = true;/blur-background = false;/' \
      "$ROOT/data/picom.conf" > "$HOMEP/.config/vesper/picom.conf"
fi

setsid Xephyr "$DISP" -screen "$SIZE" -resizeable -ac -no-host-grab \
  -title "Vesper (prova in finestra)" </dev/null >/dev/null 2>&1 &
echo $! > "$XPID"
i=0; while [ ! -S "/tmp/.X11-unix/X$N" ] && [ $i -lt 50 ]; do sleep 0.1; i=$((i+1)); done

# seccomp=unconfined: gdk-pixbuf recente isola il caricamento delle immagini
# in una sandbox bwrap che il filtro predefinito di podman blocca.
podman run -d --rm --name "$CNAME" --user "$(id -u):$(id -g)" --userns=keep-id \
  --network none --shm-size=256m \
  --security-opt seccomp=unconfined --security-opt label=disable \
  -e DISPLAY="$DISP" -e HOME=/home/prova -e USER=prova -e LANG="${LANG:-it_IT.UTF-8}" \
  -e XDG_RUNTIME_DIR=/tmp/xdg -e NO_AT_BRIDGE=1 -e PYTHONDONTWRITEBYTECODE=1 \
  -e VESPER_PICOM_FORZA=1 -e PATH=/vesper/bin:/usr/local/bin:/usr/bin:/bin \
  -v /tmp/.X11-unix:/tmp/.X11-unix -v /etc/localtime:/etc/localtime:ro \
  -v "$ROOT:/vesper:ro" \
  -v "$HOMEP:/home/prova" \
  "$IMG" sh -c '
    mkdir -p /tmp/xdg; chmod 700 /tmp/xdg
    setxkbmap it 2>/dev/null
    exec dbus-run-session -- /vesper/bin/vesper-session' >/dev/null

echo "Vesper in prova nella finestra Xephyr ($DISP, $SIZE), finestre: $TEMA."
echo "Log della sessione: $HOMEP/.cache/vesper/session.log"
echo "Chiudi con: tools/prova-xephyr.sh --stop"
