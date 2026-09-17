#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
#
# Installa Vesper come un qualsiasi ambiente desktop: dopo l'installazione
# compare fra le sessioni del display manager (voce "Vesper" al login).
#
#   ./install.sh                      installa in /usr/local (serve root)
#   ./install.sh --prefix=/usr        installa in /usr (pacchetti distro)
#   ./install.sh --user               installa in ~/.local (senza root)
#   ./install.sh --uninstall          disinstalla (stesso prefisso)
#   DESTDIR=/tmp/pkg ./install.sh     installa in una radice finta (packaging)
#
# Cosa mette dove:
#   <prefisso>/bin/vesper-*                 comandi
#   <prefisso>/lib/vesper/vesper/           pacchetto Python
#   <prefisso>/lib/vesper/env.sh            risolutore percorsi dei comandi
#   <prefisso>/share/vesper/                sfondi, skin, preset, temi, skel
#   <prefisso>/share/icons/hicolor/         marchio
#   <prefisso>/share/xsessions/vesper.desktop   voce di sessione (login)
#   <prefisso>/share/applications/*.desktop     app nel menu
set -eu

PREFIX=/usr/local
DESTDIR="${DESTDIR:-}"
ACTION=install
SRC=$(cd "$(dirname "$0")" && pwd)

for arg in "$@"; do
  case "$arg" in
    --prefix=*) PREFIX="${arg#--prefix=}" ;;
    --user) PREFIX="${XDG_DATA_HOME:-$HOME/.local}" ;;
    --uninstall|--remove) ACTION=uninstall ;;
    -h|--help) sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "argomento non riconosciuto: $arg (usa --help)" >&2; exit 2 ;;
  esac
done

# --user: i comandi vanno in ~/.local/bin, che dev'essere nel PATH
BIN="$DESTDIR$PREFIX/bin"
LIB="$DESTDIR$PREFIX/lib/vesper"
SHARE="$DESTDIR$PREFIX/share/vesper"
ICONS="$DESTDIR$PREFIX/share/icons/hicolor"
XSESS="$DESTDIR$PREFIX/share/xsessions"
APPS="$DESTDIR$PREFIX/share/applications"

COMANDI="vesper-session vesper-panel vesper-panel-restart vesper-control-center
         vesper-files vesper-profile vesper-logout vesper-shutdown
         vesper-autostart vesper-terminal vesper-wallpaper vesper-lang
         vesper-audio vesper-audio-unmute vesper-battery vesper-bluetooth
         vesper-brightness vesper-clipboard vesper-datetime vesper-keys
         vesper-netinfo vesper-nightlight vesper-screens vesper-screenshot
         vesper-wifi"

if [ "$ACTION" = uninstall ]; then
  echo "Disinstallo Vesper da $PREFIX"
  for c in $COMANDI; do rm -f "$BIN/$c"; done
  rm -rf "$LIB" "$SHARE"
  rm -f "$XSESS/vesper.desktop"
  rm -f "$APPS/vesper-control-center.desktop" "$APPS/vesper-files.desktop" \
        "$APPS/vesper-profile.desktop"
  rm -f "$ICONS/scalable/apps/vesper-logo.svg" \
        "$ICONS/scalable/apps/vesper-logo-symbolic.svg"
  command -v gtk-update-icon-cache >/dev/null 2>&1 && \
    gtk-update-icon-cache -q -f -t "$ICONS" 2>/dev/null || true
  echo "Fatto. La configurazione in ~/.config/vesper NON è stata toccata."
  exit 0
fi

# --- controlli preliminari -------------------------------------------------
[ -d "$SRC/src/vesper" ] || { echo "install.sh: sorgenti non trovati in $SRC" >&2; exit 1; }
if [ -z "$DESTDIR" ] && [ ! -w "$(dirname "$PREFIX")" ] && [ "$(id -u)" != 0 ]; then
  echo "Per installare in $PREFIX servono i privilegi di root." >&2
  echo "Usa:  sudo ./install.sh        oppure  ./install.sh --user" >&2
  exit 1
fi

echo "Installo Vesper in $PREFIX${DESTDIR:+ (radice: $DESTDIR)}"
mkdir -p "$BIN" "$LIB" "$SHARE" "$ICONS/scalable/apps" "$XSESS" "$APPS"

# --- pacchetto Python ------------------------------------------------------
# Senza __pycache__: bytecode vecchio con mtime azzerati farebbe eseguire
# codice superato (gotcha noto del packaging).
rm -rf "$LIB/vesper"
(cd "$SRC/src" && find vesper -name '__pycache__' -prune -o -type f -print | \
  while read -r f; do
    mkdir -p "$LIB/$(dirname "$f")"
    cp "$f" "$LIB/$f"
  done)
cp "$SRC/bin/env.sh" "$LIB/env.sh"

# --- comandi ---------------------------------------------------------------
for c in $COMANDI; do
  if [ -f "$SRC/bin/$c" ]; then
    cp "$SRC/bin/$c" "$BIN/$c"
    chmod 755 "$BIN/$c"
  else
    echo "  (assente, salto: $c)"
  fi
done

# --- dati ------------------------------------------------------------------
for d in backgrounds panel-themes themes skel; do
  [ -d "$SRC/data/$d" ] || continue
  rm -rf "$SHARE/$d"
  mkdir -p "$SHARE/$d"
  (cd "$SRC/data/$d" && find . -type f -print | while read -r f; do
      mkdir -p "$SHARE/$d/$(dirname "$f")"; cp "$f" "$SHARE/$d/$f"; done)
done
[ -f "$SRC/data/presets.json" ] && cp "$SRC/data/presets.json" "$SHARE/presets.json"

# --- icone, sessione, voci di menu ----------------------------------------
cp "$SRC/data/icons/hicolor/scalable/apps/vesper-logo.svg" "$ICONS/scalable/apps/"
cp "$SRC/data/icons/hicolor/scalable/apps/vesper-logo-symbolic.svg" "$ICONS/scalable/apps/"
cp "$SRC/data/xsessions/vesper.desktop" "$XSESS/vesper.desktop"
cp "$SRC/data/applications/"*.desktop "$APPS/"

command -v gtk-update-icon-cache >/dev/null 2>&1 && \
  gtk-update-icon-cache -q -f -t "$DESTDIR$PREFIX/share/icons/hicolor" 2>/dev/null || true
command -v update-desktop-database >/dev/null 2>&1 && \
  update-desktop-database -q "$APPS" 2>/dev/null || true

# --- riepilogo e dipendenze mancanti --------------------------------------
echo
echo "Installato. Al prossimo login scegli la sessione \"Vesper\"."
echo
MANCANTI=""
for dep in openbox python3 wmctrl xrandr; do
  command -v "$dep" >/dev/null 2>&1 || MANCANTI="$MANCANTI $dep"
done
"${VESPER_PY:-python3}" - <<'PY' 2>/dev/null || MANCANTI="$MANCANTI python3-gi/pygobject"
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: F401
import cairo  # noqa: F401
PY
if [ -n "$MANCANTI" ]; then
  echo "ATTENZIONE - componenti richiesti non trovati:$MANCANTI"
  echo "  Debian/Ubuntu: apt install openbox python3-gi python3-gi-cairo gir1.2-gtk-3.0 wmctrl x11-xserver-utils"
  echo "  Fedora:        dnf install openbox python3-gobject python3-cairo wmctrl xrandr"
  echo "  Arch:          pacman -S openbox python-gobject python-cairo wmctrl xorg-xrandr"
  echo "  Alpine:        apk add openbox py3-gobject3 py3-cairo wmctrl xrandr"
fi
if [ "$PREFIX" = "${XDG_DATA_HOME:-$HOME/.local}" ]; then
  echo
  echo "Installazione utente: assicurati che $PREFIX/bin sia nel PATH."
  echo "La voce di sessione è in $PREFIX/share/xsessions: alcuni display"
  echo "manager leggono solo /usr/share/xsessions (allora installa con sudo)."
fi
