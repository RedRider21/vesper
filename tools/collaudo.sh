#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
#
# collaudo.sh - collaudo automatico di Vesper, da lanciare prima di ogni release.
#
#   tools/collaudo.sh            controlli statici + sessione vera nel container
#   tools/collaudo.sh --statico  solo i controlli statici (veloce, niente container)
#   tools/collaudo.sh --popup [preset[:skin] ...]   foto dei popup della barra
#
# 1. Controlli statici sull'host: traduzioni (check-i18n), sintassi di tutti i
#    .py e degli script sh, segnaposto rimasti nei temi generati, file privati
#    che non devono finire nei pacchetti.
# 2. Sessione vera in un container (immagine di prova, nessuna rete), su uno
#    schermo virtuale Xvfb: avvio, barra, desktop, menu di Openbox, lingua,
#    prompt, cambio di preset (anche: la barra non deve sparire), temi macOS,
#    apertura di una finestra, skin coordinata, picom, log, uscita.
#    Vedi tools/collaudo/dentro.sh.
#
# Isolamento: progetto montato in SOLA LETTURA, home temporanea in
# $XDG_RUNTIME_DIR/vesper-collaudo (cancellata a ogni giro), nessun display
# dell'utente (Xvfb dentro il container), nessuna rete.
# Esito: 0 se tutto OK, 1 se qualcosa fallisce. Schermate e log in
# $XDG_RUNTIME_DIR/vesper-collaudo/out.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMG="${VESPER_PROVA_IMG:-localhost/nxs-prova}"
BASE="${XDG_RUNTIME_DIR:-/tmp}/vesper-collaudo"
KO=0
riga() { printf '%s  %s\n' "$1" "$2"; [ "$1" = KO ] && KO=1; return 0; }

echo "== controlli statici"
out=$(python3 "$ROOT/tools/check-i18n.py" 2>&1 | tail -1)
case "$out" in *" 0 problemi, 0 orfane"*) riga OK "traduzioni: $out" ;; *) riga KO "traduzioni: $out" ;; esac

err=0
for f in $(cd "$ROOT" && git ls-files '*.py'); do
  python3 -c 'import ast,sys; ast.parse(open(sys.argv[1]).read(), sys.argv[1])' "$ROOT/$f" 2>/dev/null \
    || { riga KO "sintassi Python: $f"; err=1; }
done
[ $err = 0 ] && riga OK "sintassi Python di tutti i .py"

err=0
for f in "$ROOT"/bin/* "$ROOT"/tools/*.sh "$ROOT"/tools/collaudo/*.sh "$ROOT"/install.sh; do
  head -1 "$f" | grep -q '^#!/bin/sh' || continue
  sh -n "$f" 2>/dev/null || { riga KO "sintassi sh: ${f#$ROOT/}"; err=1; }
done
[ $err = 0 ] && riga OK "sintassi degli script sh"

if grep -rlE '@[A-Z_]+@' "$ROOT/data/themes" >/dev/null 2>&1; then
  riga KO "temi: segnaposto non sostituiti ($(grep -rlE '@[A-Z_]+@' "$ROOT/data/themes" | head -1))"
else riga OK "temi: nessun segnaposto rimasto"; fi

if (cd "$ROOT" && git ls-files | grep -qE '^docs/privato/|^Appunti'); then
  riga KO "file privati tracciati da git (docs/privato, appunti)"
else riga OK "nessun file privato tracciato da git"; fi

# campionario dei popup della barra, da guardare a occhio
if [ "${1:-}" = "--popup" ]; then
  shift
  [ $# -gt 0 ] || set -- cyan bianco cyan:light ambra:amber
  rm -rf "$BASE"; mkdir -p "$BASE/out"
  podman run --rm --network none --user "$(id -u):$(id -g)" --userns=keep-id \
    --shm-size=256m --security-opt seccomp=unconfined --security-opt label=disable \
    -v "$ROOT:/vesper:ro" -v "$BASE/out:/out" \
    "$IMG" timeout 600 sh /vesper/tools/collaudo/popup.sh "$@" >"$BASE/out/popup.log" 2>&1
  ls "$BASE"/out/popup-*.png 2>/dev/null
  exit 0
fi
[ "${1:-}" = "--statico" ] && { [ $KO = 0 ] && echo "ESITO: OK" || echo "ESITO: KO"; exit $KO; }

echo "== sessione nel container ($IMG)"
if ! command -v podman >/dev/null || ! podman image exists "$IMG"; then
  riga KO "container: podman o immagine $IMG non disponibili (VESPER_PROVA_IMG)"
  echo "ESITO: KO"; exit 1
fi
rm -rf "$BASE"; mkdir -p "$BASE/home" "$BASE/out"
podman run --rm --network none --user "$(id -u):$(id -g)" --userns=keep-id \
  --shm-size=256m --security-opt seccomp=unconfined --security-opt label=disable \
  -e LANG="${LANG:-it_IT.UTF-8}" \
  -v "$ROOT:/vesper:ro" -v "$BASE/home:/home/prova" -v "$BASE/out:/out" \
  "$IMG" timeout 300 sh /vesper/tools/collaudo/dentro.sh >"$BASE/out/collaudo.log" 2>&1
if [ ! -s "$BASE/out/esito.txt" ]; then
  riga KO "il collaudo nel container non ha prodotto esiti (vedi $BASE/out/collaudo.log)"
else
  while IFS= read -r l; do
    s=${l%%  *}; r=${l#*  }
    riga "$s" "$r"
  done < "$BASE/out/esito.txt"
fi
echo "schermate e log: $BASE/out"
[ $KO = 0 ] && echo "ESITO: OK" || echo "ESITO: KO"
exit $KO
