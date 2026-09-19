# Temi finestre inclusi in Vesper

## 1977-* (9 colori)

Set di temi Openbox minimalisti di **Thayer Williams** (cinderwick.ca).
Inclusi così come sono, con l'intestazione originale dentro ogni `themerc`.
Sono la base della famiglia "Retro" generata da `tools/make-openbox-themes.py`.

## Vesper-Arc-Dark / Vesper-Arc-Light

Adattati da **Lubuntu Arc-Round Openbox** di *the-zero885* (licenza GPL-3), a
sua volta ispirato al tema GTK **Arc** di *horst3180*. Hanno i pulsanti tondi
in stile macOS. L'attribuzione originale è conservata nei rispettivi `themerc`.

## Vesper-Core

Tema proprio di Vesper: scuro, con l'accento del preset attivo.

## Vesper-Retro-<preset> e Vesper-Cards-<preset>

Generati da `tools/make-openbox-themes.py` a partire dai template in
`tools/openbox-templates/`, uno per ogni colore dei preset:

- **Retro**: flat chiaro, derivato dal look di 1977.
- **Cards**: stile macOS/iOS — barra scura, tre pulsanti a sfera a sinistra
  (rosso/giallo/verde) col simbolo scavato dentro, angoli arrotondati (serve
  picom, che Vesper accende da solo quando la famiglia è Cards). Le maschere
  dei pulsanti derivano dalla geometria di Arc-Round (GPL-3).
