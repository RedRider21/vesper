# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
#
# Ambiente comune dei comandi di Vesper: NON si esegue, si include.
# Trova il pacchetto Python e l'interprete a partire da dove è installato
# questo file, così gli stessi comandi funzionano se Vesper sta in /usr, in
# /usr/local, in un prefisso qualunque, o se lo si avvia dal repo dei
# sorgenti (senza installare nulla).
#
# Uso, in testa a ogni comando vesper-*:
#   _self=$(readlink -f "$0" 2>/dev/null || echo "$0"); _d=$(dirname "$_self")
#   for _e in "$_d/env.sh" "$(dirname "$_d")/lib/vesper/env.sh" \
#             /usr/local/lib/vesper/env.sh /usr/lib/vesper/env.sh; do
#     [ -r "$_e" ] && { . "$_e"; break; }
#   done

# --- pacchetto Python (la cartella che CONTIENE vesper/) ---
# Questo file può stare in due posti: $PREFIX/lib/vesper/env.sh (installato) o
# bin/env.sh (repo dei sorgenti). Proviamo le due letture senza indovinare.
_vesper_env_self=$(readlink -f "${_e:-$0}" 2>/dev/null || echo "${_e:-$0}")
_vesper_env_dir=$(dirname "$_vesper_env_self")       # .../lib/vesper oppure .../bin
_vesper_up1=$(dirname "$_vesper_env_dir")            # .../lib        oppure il prefisso/repo
_vesper_up2=$(dirname "$_vesper_up1")                # il prefisso, se siamo in lib/vesper

for _d in "$_vesper_env_dir" \
          "$_vesper_up1/lib/vesper" "$_vesper_up2/lib/vesper" \
          "$_vesper_up1/src" \
          /usr/local/lib/vesper /usr/lib/vesper; do
  if [ -d "$_d/vesper" ]; then
    VESPER_LIB=$(cd "$_d" && pwd)
    break
  fi
done

if [ -n "${VESPER_LIB:-}" ]; then
  # Il nostro percorso davanti: se il sistema ha una copia più vecchia, vince
  # quella che sta accanto ai comandi in esecuzione.
  PYTHONPATH="$VESPER_LIB${PYTHONPATH:+:$PYTHONPATH}"
  export PYTHONPATH VESPER_LIB
fi

# --- dati (sfondi, skin, preset, temi) ---
# Cercati accanto al pacchetto: utile con prefissi non standard e dai sorgenti.
if [ -z "${VESPER_DATA_DIRS:-}" ]; then
  for _d in "$_vesper_up1/share/vesper" "$_vesper_up2/share/vesper" \
            "$_vesper_up1/data"; do
    if [ -d "$_d" ]; then
      _dd=$(cd "$_d" && pwd)
      VESPER_DATA_DIRS="${VESPER_DATA_DIRS:+$VESPER_DATA_DIRS:}$_dd"
    fi
  done
  [ -n "${VESPER_DATA_DIRS:-}" ] && export VESPER_DATA_DIRS
fi

# --- interprete ---
for _c in python3 python3.13 python3.12 python3.11 python3.10 python3.9; do
  if command -v "$_c" >/dev/null 2>&1; then VESPER_PY="$_c"; break; fi
done
export VESPER_PY

# GTK_IM_MODULE "simple": senza, un TextView editabile può tentare di caricare
# un modulo input-method assente e far crashare l'app su X minimale.
export GTK_IM_MODULE="${GTK_IM_MODULE:-gtk-im-context-simple}"
# Identificazione del desktop: la leggono le app (OnlyShowIn) e il nostro menu.
export XDG_CURRENT_DESKTOP="${XDG_CURRENT_DESKTOP:-Vesper}"

unset _d _dd _c _vesper_env_self _vesper_env_dir _vesper_up1 _vesper_up2
