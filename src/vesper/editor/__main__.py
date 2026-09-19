# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Avvio dell'editor: vesper-editor [file1 file2 ...] [+RIGA]."""
import sys

from vesper.editor.app import main

if __name__ == "__main__":
    main(sys.argv[1:])
