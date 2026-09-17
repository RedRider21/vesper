# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""i18n minimale e senza dipendenze per Vesper (it/en/fr/es/de).

La lingua attiva sta in ~/.config/vesper/lang (override con VESPER_LANG).
Le stringhe sono in strings/<lang>.json (dizionari piatti chiave -> testo). t()
risolve con catena di fallback: lingua scelta -> inglese -> italiano -> chiave,
cosi' una chiave non ancora tradotta non rompe mai l'interfaccia. Condiviso da
pannello, Centro di Controllo e script (via `vesper-lang`).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

LANGS = ("it", "en", "fr", "es", "de")
LANG_NAMES = {
    "it": "Italiano", "en": "English", "fr": "Français",
    "es": "Español", "de": "Deutsch",
}
DEFAULT = "it"

_DIR = Path(__file__).resolve().parent / "strings"
_cache: dict[str, dict] = {}
_active: str | None = None


def _conf_path() -> str:
    from vesper import paths
    return str(paths.config("lang"))


def current_lang() -> str:
    """Lingua attiva (memoizzata): VESPER_LANG, poi il file, poi il default."""
    global _active
    if _active:
        return _active
    lang = os.environ.get("VESPER_LANG", "").strip().lower()
    if lang not in LANGS:
        try:
            lang = Path(_conf_path()).read_text(encoding="utf-8").strip().lower()
        except OSError:
            lang = ""
    _active = lang if lang in LANGS else DEFAULT
    return _active


def set_lang(code: str) -> bool:
    """Salva la lingua scelta; ritorna True se valida."""
    code = (code or "").strip().lower()
    if code not in LANGS:
        return False
    p = Path(_conf_path())
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(code + "\n", encoding="utf-8")
    global _active
    _active = code
    _cache.clear()
    return True


def _load(lang: str) -> dict:
    if lang in _cache:
        return _cache[lang]
    try:
        d = json.loads((_DIR / (lang + ".json")).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    _cache[lang] = d
    return d


def t(key: str, **kw) -> str:
    """Traduce la chiave nella lingua attiva (con fallback). kw = interpolazione."""
    s = None
    for lang in (current_lang(), "en", "it"):
        d = _load(lang)
        if key in d:
            s = d[key]
            break
    if s is None:
        s = key
    if kw:
        try:
            s = s.format(**kw)
        except (KeyError, IndexError, ValueError):
            pass
    return s
