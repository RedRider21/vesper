#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
#
# Costruisce un repository APT per i clienti con licenza commerciale.
#
#   tools/repo-apt/crea-repo.sh --repo /srv/vesper-repo --deb pacchetto.deb \
#       [--suite stabile] [--gpg CHIAVE]
#
# Struttura prodotta (quella classica di Debian):
#
#   /srv/vesper-repo/
#     pool/main/v/vesper/vesper_0.5.0_all_commerciale.deb
#     dists/stabile/main/binary-all/Packages{,.gz}
#     dists/stabile/{Release,Release.gpg,InRelease}
#     chiave-pubblica.asc
#
# Ogni cliente riceve un token e una riga da mettere in sources.list.d; il
# server conta da sé quante macchine si aggiornano con quel token (vedi
# conta-installazioni.py). Il conteggio che fa fede resta quello dei rapporti
# firmati di `vesper-licenza --rapporto`: i log del repository servono a
# capire se i numeri dichiarati tornano.
set -eu

REPO=""; DEB=""; SUITE="stabile"; GPGKEY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --repo)  REPO="${2:-}"; shift 2 ;;
    --deb)   DEB="${2:-}"; shift 2 ;;
    --suite) SUITE="${2:-stabile}"; shift 2 ;;
    --gpg)   GPGKEY="${2:-}"; shift 2 ;;
    -h|--help)
      sed -n '5,20p' "$0"; exit 0 ;;
    *) echo "argomento non riconosciuto: $1" >&2; exit 2 ;;
  esac
done
[ -n "$REPO" ] || { echo "manca --repo" >&2; exit 2; }
[ -n "$DEB" ] && [ -f "$DEB" ] || { echo "manca --deb (o il file non c'è)" >&2; exit 2; }

POOL="$REPO/pool/main/v/vesper"
DIST="$REPO/dists/$SUITE/main/binary-all"
mkdir -p "$POOL" "$DIST"
cp "$DEB" "$POOL/"
echo "pacchetto copiato in $POOL"

cd "$REPO"
if command -v apt-ftparchive >/dev/null 2>&1; then
  apt-ftparchive packages pool > "$DIST/Packages"
else
  command -v dpkg-scanpackages >/dev/null 2>&1 || {
    echo "servono apt-utils (apt-ftparchive) oppure dpkg-dev" >&2; exit 1; }
  dpkg-scanpackages --multiversion pool /dev/null > "$DIST/Packages"
fi
gzip -9 -c "$DIST/Packages" > "$DIST/Packages.gz"
echo "indice: $(grep -c '^Package:' "$DIST/Packages") pacchetti"

# Release: senza, apt si rifiuta di usare il repository.
REL="$REPO/dists/$SUITE/Release"
if command -v apt-ftparchive >/dev/null 2>&1; then
  apt-ftparchive \
    -o APT::FTPArchive::Release::Origin=Vesper \
    -o APT::FTPArchive::Release::Label=Vesper \
    -o APT::FTPArchive::Release::Suite="$SUITE" \
    -o APT::FTPArchive::Release::Codename="$SUITE" \
    -o APT::FTPArchive::Release::Architectures=all \
    -o APT::FTPArchive::Release::Components=main \
    release "dists/$SUITE" > "$REL"
else
  {
    echo "Origin: Vesper"; echo "Label: Vesper"; echo "Suite: $SUITE"
    echo "Codename: $SUITE"; echo "Architectures: all"; echo "Components: main"
    echo "Date: $(date -Ru)"
  } > "$REL"
fi

# Firma: apt accetta un repository non firmato solo con [trusted=yes], che è
# una cattiva idea su una rete pubblica.
if [ -n "$GPGKEY" ]; then
  rm -f "$REL.gpg" "$REPO/dists/$SUITE/InRelease"
  gpg --default-key "$GPGKEY" --armor --detach-sign -o "$REL.gpg" "$REL"
  gpg --default-key "$GPGKEY" --clearsign -o "$REPO/dists/$SUITE/InRelease" "$REL"
  gpg --armor --export "$GPGKEY" > "$REPO/chiave-pubblica.asc"
  echo "firmato con $GPGKEY; chiave pubblica in $REPO/chiave-pubblica.asc"
else
  echo "ATTENZIONE: repository non firmato. Genera una chiave e rilancia con"
  echo "  --gpg <ID>   (i client altrimenti devono usare [trusted=yes])"
fi
echo "fatto: $REPO"
