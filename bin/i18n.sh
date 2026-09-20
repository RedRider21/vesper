# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
#
# Traduzione dei messaggi degli script. NON si esegue, si include:
#
#   vesper_t() { printf '%s\n' "${2:-$1}"; }          # ripiego: italiano
#   for _i in "$_d/i18n.sh" "$(dirname "$_d")/lib/vesper/i18n.sh" \
#             /usr/local/lib/vesper/i18n.sh /usr/lib/vesper/i18n.sh; do
#     [ -r "$_i" ] && { . "$_i"; break; }
#   done
#
# Poi:  echo "$(vesper_t cli.tizio.usage 'uso: ...')" >&2
#
# La chiave si cerca in src/vesper/i18n/strings/<lingua>.json; il secondo
# argomento è il testo italiano, che si usa se il pacchetto Python non c'è
# (così un messaggio d'errore non sparisce mai) o se la chiave manca.

vesper_t() {
  _vt_py="${VESPER_PY:-}"
  if [ -z "$_vt_py" ]; then
    for _vt_c in python3 python3.13 python3.12 python3.11 python3.10; do
      command -v "$_vt_c" >/dev/null 2>&1 && { _vt_py="$_vt_c"; break; }
    done
  fi
  _vt_out=""
  if [ -n "$_vt_py" ]; then
    _vt_out=$("$_vt_py" -c 'import sys
try:
    from vesper.i18n import t
except Exception:
    raise SystemExit
s = t(sys.argv[1])
if s != sys.argv[1]:
    sys.stdout.write(s)' "$1" 2>/dev/null) || _vt_out=""
  fi
  [ -n "$_vt_out" ] || _vt_out="${2:-$1}"
  printf '%s\n' "$_vt_out"
  unset _vt_out _vt_py _vt_c
}
