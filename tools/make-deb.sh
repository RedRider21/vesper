#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
#
# Costruisce il pacchetto .deb di Vesper (Debian, Ubuntu, Linux Mint).
# Usa lo STESSO install.sh dell'installazione manuale, montato su una radice
# finta con DESTDIR: quello che finisce nel pacchetto è esattamente ciò che
# installerebbe lo script, senza duplicare la lista dei file.
#
#   ./tools/make-deb.sh                 -> packaging/vesper_<ver>_all.deb
#   ./tools/make-deb.sh --out /tmp      cambia la cartella di destinazione
#
# Il pacchetto è "all" (architettura indipendente): dentro c'è solo Python,
# dati e script di shell.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT="$ROOT/packaging"
for a in "$@"; do
  case "$a" in
    --out) shift; OUT="${1:-$OUT}" ;;
    --out=*) OUT="${a#--out=}" ;;
  esac
done

command -v dpkg-deb >/dev/null 2>&1 || {
  echo "serve dpkg-deb (pacchetto dpkg)" >&2; exit 1; }

VER=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/src/vesper/__init__.py")
[ -n "$VER" ] || VER=0.1.0
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

echo "Vesper $VER: preparo l'albero del pacchetto..."
DESTDIR="$STAGE" sh "$ROOT/install.sh" --prefix=/usr >/dev/null

# Il bytecode lo genera il postinst sulla macchina di destinazione: nel
# pacchetto NON deve finirci (sarebbe legato alla versione di Python di chi
# costruisce, e i .pyc stantii fanno eseguire codice vecchio).
find "$STAGE" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find "$STAGE" -name '*.pyc' -delete 2>/dev/null || true
# Cache generate: le rifà il postinst sulla macchina dell'utente, nel
# pacchetto non ci vanno (Debian le considera un errore).
rm -f "$STAGE/usr/share/applications/mimeinfo.cache" \
      "$STAGE/usr/share/icons/hicolor/icon-theme.cache" 2>/dev/null || true

INSTALLED=$(du -sk "$STAGE/usr" | cut -f1)

mkdir -p "$STAGE/DEBIAN"
cat > "$STAGE/DEBIAN/control" <<EOF
Package: vesper
Version: $VER
Section: x11
Priority: optional
Architecture: all
Maintainer: Daniele Deplano <deplano.d@gmail.com>
Installed-Size: $INSTALLED
Depends: openbox | marco | metacity, python3 (>= 3.8), python3-gi, python3-gi-cairo, gir1.2-gtk-3.0, gir1.2-gdkpixbuf-2.0, gir1.2-gtksource-4, wmctrl, x11-xserver-utils
Recommends: marco | metacity, mint-themes, dunst, xautolock, lxappearance, brightnessctl, xdg-user-dirs, fonts-dejavu-core,
 gir1.2-gst-plugins-base-1.0, gstreamer1.0-plugins-good, gstreamer1.0-plugins-bad, gstreamer1.0-libav, gstreamer1.0-pulseaudio
Suggests: picom, bluez, bluez-tools, policykit-1-gnome, alsa-utils, maim, xclip
Description: ambiente desktop leggero in Python + GTK3 su Openbox
 Vesper è un ambiente desktop completo e leggero: pannello con menu delle
 applicazioni e applet, Centro di Controllo con 19 pannelli di impostazioni,
 file manager proprio (finestra e desktop con sfondo e icone), salvaschermo
 con blocco schermo e preset di aspetto che cambiano insieme colore
 d'accento, sfondo, set di icone e tema delle finestre.
 .
 Dopo l'installazione compare fra le sessioni del gestore di accesso: si
 sceglie "Vesper" al login.
EOF

cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
# Bytecode compilato QUI, sulla macchina di destinazione.
if command -v py3compile >/dev/null 2>&1; then
    py3compile -q /usr/lib/vesper 2>/dev/null || true
elif command -v python3 >/dev/null 2>&1; then
    python3 -m compileall -q /usr/lib/vesper >/dev/null 2>&1 || true
fi
command -v gtk-update-icon-cache >/dev/null 2>&1 && \
    gtk-update-icon-cache -q -f -t /usr/share/icons/hicolor 2>/dev/null || true
command -v update-desktop-database >/dev/null 2>&1 && \
    update-desktop-database -q /usr/share/applications 2>/dev/null || true
exit 0
EOF

cat > "$STAGE/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
# Via il bytecode generato dal postinst (non è nel pacchetto, quindi dpkg non
# lo rimuoverebbe da solo e lascerebbe cartelle orfane).
if command -v py3clean >/dev/null 2>&1; then
    py3clean /usr/lib/vesper 2>/dev/null || true
else
    find /usr/lib/vesper -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
fi
exit 0
EOF

cat > "$STAGE/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    rm -rf /usr/lib/vesper 2>/dev/null || true
    command -v gtk-update-icon-cache >/dev/null 2>&1 && \
        gtk-update-icon-cache -q -f -t /usr/share/icons/hicolor 2>/dev/null || true
fi
exit 0
EOF
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/prerm" "$STAGE/DEBIAN/postrm"

# Licenza e changelog dove se li aspetta Debian
mkdir -p "$STAGE/usr/share/doc/vesper"
cp "$ROOT/README.md" "$STAGE/usr/share/doc/vesper/README.md" 2>/dev/null || true
[ -f "$ROOT/data/themes/ATTRIBUZIONI.md" ] && \
  cp "$ROOT/data/themes/ATTRIBUZIONI.md" "$STAGE/usr/share/doc/vesper/ATTRIBUZIONI-temi.md"
# changelog: Debian lo vuole, compresso
printf 'vesper (%s) unstable; urgency=low\n\n  * Versione %s.\n\n -- %s  %s\n' \
  "$VER" "$VER" "Daniele Deplano <deplano.d@gmail.com>" "$(date -R)" \
  | gzip -9n > "$STAGE/usr/share/doc/vesper/changelog.gz"

cat > "$STAGE/usr/share/doc/vesper/copyright" <<'EOF'
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: vesper

Files: *
Copyright: 2026 Daniele Deplano (RedRider21)
License: AGPL-3.0-or-later

Files: usr/share/themes/1977-*
Copyright: Thayer Williams <thayerw@gmail.com>
License: vedi l'intestazione di ogni themerc

Files: usr/share/themes/Vesper-Arc-* usr/share/themes/Vesper-Cards-*
Copyright: the-zero885 (Lubuntu Arc-Round Openbox), horst3180 (Arc)
License: GPL-3
EOF
find "$STAGE/usr/share/doc" -type d -exec chmod 755 {} +
find "$STAGE/usr/share/doc" -type f -exec chmod 644 {} +

mkdir -p "$OUT"
DEB="$OUT/vesper_${VER}_all.deb"
# --root-owner-group: dentro il pacchetto tutto risulta di root:root anche
# costruendo da utente normale.
dpkg-deb --root-owner-group --build "$STAGE" "$DEB" >/dev/null
echo "pacchetto: $DEB"
command -v lintian >/dev/null 2>&1 && lintian --no-tag-display-limit "$DEB" 2>&1 | head -20 || true
