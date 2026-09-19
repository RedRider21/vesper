#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
#
# Archivio dei sorgenti: è quello che si scarica dalle release e da cui
# partono tutte le ricette (deb, PKGBUILD, spec, APKBUILD) e l'installazione
# manuale con ./install.sh.
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT="${1:-$ROOT/packaging}"
VER=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/src/vesper/__init__.py")
[ -n "$VER" ] || VER=0.1.0
NAME="vesper-$VER"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE/$NAME" "$OUT"
# Solo ciò che serve a installare e a ricostruire: niente .git, niente cache.
for item in bin data src tools install.sh README.md CLAUDE.md docs packaging LICENSE; do
  [ -e "$ROOT/$item" ] && cp -r "$ROOT/$item" "$STAGE/$NAME/"
done
find "$STAGE/$NAME" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find "$STAGE/$NAME" -name '*.pyc' -delete 2>/dev/null || true
# fuori gli artefatti già costruiti: nell'archivio dei sorgenti non servono
rm -f "$STAGE/$NAME/packaging"/*.deb "$STAGE/$NAME/packaging"/*.tar.gz \
      "$STAGE/$NAME/packaging"/*.sha256 "$STAGE/$NAME/packaging"/*.rpm \
      "$STAGE/$NAME/packaging"/*.apk 2>/dev/null || true

tar -C "$STAGE" -czf "$OUT/$NAME.tar.gz" "$NAME"
( cd "$OUT" && sha256sum "$NAME.tar.gz" > "$NAME.tar.gz.sha256" )
echo "archivio: $OUT/$NAME.tar.gz"
cat "$OUT/$NAME.tar.gz.sha256"
