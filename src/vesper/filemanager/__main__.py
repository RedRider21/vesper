# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Avvio del file manager: `python3 -m vesper.filemanager` (vesper-files).

    vesper-files [CARTELLA ...]   finestra di gestione file
    vesper-files --desktop        sfondo e icone del desktop
"""
import sys


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--desktop" in argv:
        from .desktop import main as desktop_main
        argv.remove("--desktop")
        return desktop_main(argv)
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    from .window import main as window_main
    return window_main(argv)


raise SystemExit(main())
