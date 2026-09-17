# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""CLI dei preset di aspetto (comando `vesper-profile`).

    vesper-profile                 selettore grafico
    vesper-profile list            elenca i preset (* = attivo)
    vesper-profile get             stampa il preset attivo
    vesper-profile set <id>        applica un preset
    vesper-profile apply           riapplica il preset corrente (avvio sessione)
    vesper-profile style [stile]   stile finestre: flat | vetro | telaio | aero
    vesper-profile theme [fam]     famiglia tema finestre: core | retro | cards
                                   (oppure raw:<NomeTema> per un tema fisso)

Nessuna dipendenza GTK: si può usare da terminale e dagli script di sessione.
"""
from __future__ import annotations

import sys

from . import model


def _list(_args) -> int:
    cur = model.current_preset()
    for key, d in model.presets().items():
        mark = "*" if key == cur else " "
        print("%s %-10s %-14s %-9s %s" % (mark, key, d.get("name", key),
                                          d.get("accent", ""), d.get("desc", "")))
    return 0


def _get(_args) -> int:
    key = model.current_preset()
    d = model.preset_data(key)
    print("%s\t%s\t%s" % (key, d.get("name", key), d.get("accent", "")))
    return 0


def _set(args) -> int:
    if not args:
        print("uso: vesper-profile set <id>  (vedi: vesper-profile list)",
              file=sys.stderr)
        return 2
    key = args[0]
    if key not in model.presets():
        print("preset sconosciuto: %s" % key, file=sys.stderr)
        return 1
    ok = model.activate_preset(key)
    d = model.preset_data(key)
    wp = model.wallpaper_path(key)
    print("[+] preset: %s  accent: %s  sfondo: %s"
          % (d.get("name", key), d.get("accent", ""), wp.name if wp else "-"))
    return 0 if ok else 1


def _apply(_args) -> int:
    d = model.apply_current()
    key = model.current_preset()
    print("[+] preset: %s  accent: %s" % (d.get("name", key), model.accent(key)))
    return 0


def _style(args) -> int:
    if not args:
        print(model.get_window_style())
        print("disponibili:", " ".join(model.WINDOW_STYLES))
        return 0
    if args[0] not in model.WINDOW_STYLES:
        print("stile sconosciuto: %s (usa: %s)"
              % (args[0], " ".join(model.WINDOW_STYLES)), file=sys.stderr)
        return 1
    model.set_window_style(args[0])
    print("[+] stile finestre:", args[0])
    return 0


def _theme(args) -> int:
    if not args:
        print(model.theme_family())
        print("disponibili:", " ".join(model.THEME_FAMILIES), "oppure raw:<NomeTema>")
        return 0
    fam = args[0]
    if fam not in model.THEME_FAMILIES and not fam.startswith("raw:"):
        print("famiglia sconosciuta: %s" % fam, file=sys.stderr)
        return 1
    model.set_theme_family(fam)
    print("[+] tema finestre:", model.resolve_ob_theme())
    return 0


def _gui(args) -> int:
    """Selettore grafico (import qui: la CLI resta usabile senza GTK)."""
    from .selector import run
    return run(args)


COMANDI = {
    "list": _list, "ls": _list, "get": _get, "set": _set, "apply": _apply,
    "style": _style, "theme": _theme, "gui": _gui,
}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return _gui([])
    cmd, args = argv[0], argv[1:]
    fn = COMANDI.get(cmd)
    if fn is None:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    return fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
