# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Avvio del salvaschermo: `python3 -m vesper.screensaver [stile]`."""
import sys

from vesper.screensaver.app import main

raise SystemExit(main(sys.argv[1:]))
