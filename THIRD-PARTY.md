# Componenti di terze parti

Vesper è codice originale (AGPL-3.0-or-later, vedi [`COPYRIGHT`](COPYRIGHT)),
ma gira su componenti di terzi e include alcuni temi che NON sono suoi. Qui c'è
l'elenco, con la provenienza e la licenza di ognuno.

## Richiesti a runtime (non inclusi: li installa la distribuzione)

| Componente | Ruolo | Licenza |
|---|---|---|
| Openbox | window manager | GPL-2.0-or-later |
| GTK3 | libreria grafica | LGPL-2.1-or-later |
| Python 3 + PyGObject + pycairo | linguaggio e binding | PSF-2.0 / LGPL-2.1+ / LGPL-2.1+ |
| wmctrl | lista finestre e desktop virtuali | GPL-2.0-or-later |
| xrandr | gestione schermi | MIT |

Opzionali (notifiche, salvaschermo automatico, composizione, ecc.): dunst,
xautolock, picom, lxappearance, brightnessctl, bluez, alsa-utils, maim, xclip —
ognuno con la propria licenza.

## Temi finestre inclusi in `data/themes/`

| Tema | Autore / origine | Licenza |
|---|---|---|
| `1977-*` (9 colori) | Thayer Williams (cinderwick.ca) | vedi l'intestazione di ogni `themerc` |
| `Vesper-Arc-Dark`, `Vesper-Arc-Light` | adattati da Lubuntu Arc-Round Openbox di *the-zero885*, ispirato al tema Arc di *horst3180* | GPL-3.0 |
| `Vesper-Cards-*` | template originale di Vesper; la geometria dei pulsanti a sfera deriva da Arc-Round | GPL-3.0 |
| `Vesper-Retro-*` | template originale di Vesper, nel solco dell'estetica di 1977 | AGPL-3.0-or-later |
| `Vesper-Core` | originale di Vesper | AGPL-3.0-or-later |

Le attribuzioni originali sono conservate dentro i rispettivi file `themerc`.

## Set di icone

Vesper **non include** set di icone: usa quelli installati sul sistema. Ogni
preset indica i temi del proprio colore (le varianti Mint-Y / Mint-L / Mint-X,
Papirus, Adwaita…) e viene usato il primo disponibile. Quei temi restano dei
rispettivi autori e distribuiti con le loro licenze.
