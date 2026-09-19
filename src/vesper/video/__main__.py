# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Avvio del visualizzatore video: vesper-video [file1 file2 ...]."""
import sys

from vesper.video.app import main

if __name__ == "__main__":
    main(sys.argv[1:])
