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
ITEMS="bin data src tools install.sh README.md CLAUDE.md docs packaging
       LICENSE COPYRIGHT THIRD-PARTY.md CLA.md CONTRIBUTING.md"
if git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  # SOLO i file tracciati da git: cio' che e' escluso da .gitignore (docs/privato
  # con le guide commerciali, appunti) non deve MAI finire nell'archivio
  # pubblico. Fino alla 0.7.0 si copiavano le cartelle intere e docs/privato
  # finiva nei tarball delle release.
  # shellcheck disable=SC2086
  git -C "$ROOT" ls-files -z -- $ITEMS | (cd "$ROOT" && xargs -0 cp --parents -t "$STAGE/$NAME/")
else
  for item in $ITEMS; do
    [ -e "$ROOT/$item" ] && cp -r "$ROOT/$item" "$STAGE/$NAME/"
  done
fi
# rete di sicurezza, anche fuori da git
rm -rf "$STAGE/$NAME/docs/privato" "$STAGE/$NAME"/Appunti* 2>/dev/null || true
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
