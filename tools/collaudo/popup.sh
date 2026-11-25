#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
#
# Campionario dei popup della barra (Bluetooth, Wi-Fi, audio, calendario,
# schermi, batteria, lingua, menu), DENTRO il container: lo lancia
# `tools/collaudo.sh --popup`. Per ogni variante "preset[:skin]" avvia una
# sessione su Xvfb, apre i popup uno per uno e mette tutte le foto in
# /out/popup-<variante>.png, da guardare a occhio (contrasti, testi leggibili).
set -u
export USER=prova XDG_RUNTIME_DIR=/tmp/xdg PATH=/vesper/bin:/usr/local/bin:/usr/bin:/bin
export PYTHONDONTWRITEBYTECODE=1 NO_AT_BRIDGE=1
mkdir -p "$XDG_RUNTIME_DIR"; chmod 700 "$XDG_RUNTIME_DIR"
W=1280; H=800; N=20

for var in "$@"; do
  preset=${var%%:*}; skin=""; case "$var" in *:*) skin=${var#*:} ;; esac
  export HOME=/tmp/home-$N; CONF=$HOME/.config/vesper
  rm -rf "$HOME"; mkdir -p "$CONF"
  echo openbox > "$CONF/wm"; echo "$preset" > "$CONF/profile"; echo it > "$CONF/lang"
  [ -n "$skin" ] && echo "$skin" > "$CONF/panel-theme"
  Xvfb :$N -screen 0 ${W}x${H}x24 -nolisten tcp >/dev/null 2>&1 & XP=$!
  export DISPLAY=:$N; sleep 1
  dbus-run-session -- vesper-session >/dev/null 2>&1 & SP=$!
  t=0; until wmctrl -lG 2>/dev/null | awk -v w=$W '$5==w && $6<=80 {f=1} END{exit !f}' || [ $t -ge 250 ]; do
    sleep 0.1; t=$((t+1)); done
  sleep 3
  # posizione della barra e delle sue icone: si cercano i pulsanti dal lato
  # destro, in base alla geometria della barra (in basso, alta PH)
  PH=$(wmctrl -lG | awk -v w=$W '$5==w && $6<=80 {print $6; exit}')
  Y=$((H - PH/2))
  dir=/tmp/foto-$N; mkdir -p $dir; i=0
  # x delle icone a destra (1280 px): schermi, wifi, audio, bluetooth, lingua,
  # batteria, orologio; poi il menu a sinistra
  for x in 947 983 1018 1055 1091 1127 1199 26; do
    xdotool mousemove $x $Y click 1; sleep 0.4
    xdotool mousemove 640 60; sleep 1.6        # via il mouse: niente suggerimenti sopra
    i=$((i+1))
    # zona del popup a piena risoluzione: meta' bassa, dal lato dell'icona
    if [ $x -lt 400 ]; then g=760x$((H-200))+0+200; else g=760x$((H-200))+$((W-760))+200; fi
    import -window root -crop $g +repage "$dir/$(printf %02d $i).png"
    xdotool key Escape; sleep 0.3
    # chiude le finestre normali rimaste (es. la scelta della lingua), per id
    wmctrl -lG | awk -v w=$W '$NF!="desktop" && !($5==w && $6<=80) {print $1}' |
      while read -r id; do wmctrl -i -c "$id"; done
    xdotool mousemove 640 300 click 1; sleep 0.6
  done
  out="/out/popup-$preset${skin:+-$skin}.png"
  # due per riga
  set -- "$dir"/*.png; r=0; righe=""
  while [ $# -gt 0 ]; do
    a=$1; shift; b=${1:-}; [ -n "$b" ] && shift
    convert "$a" ${b:+"$b"} -background '#222' -splice 6x0 +append "$dir/riga-$r.png"
    righe="$righe $dir/riga-$r.png"; r=$((r+1))
  done
  convert $righe -background '#222' -splice 0x6 -append "$out"
  vesper-session --logout >/dev/null 2>&1; sleep 2
  kill $SP $XP 2>/dev/null; wait $XP 2>/dev/null
  N=$((N+1))
done
