# Vesper — confronto con gli altri ambienti desktop

> Aggiornato al 2026-09-19, dopo il porting completo. Serve a vedere a colpo
> d'occhio dove Vesper è alla pari e dove no.

Legenda: ✅ c'è · ⚠️ parziale · ❌ manca

| Area | Negli altri DE | Vesper |
|---|---|---|
| Pannello (menu, lista finestre, desktop virtuali, orologio, tray, monitor risorse, multi-monitor) | ✅ | ✅ |
| Menu applicazioni per categorie standard, con ricerca | ✅ | ✅ |
| Centro di Controllo (aspetto, schermi, audio, rete, bluetooth, mouse, tastiera, autostart) | ✅ | ✅ 19 viste |
| Preset di aspetto che cambiano insieme accento, sfondo, icone e finestre | ➖ raro | ✅ tratto distintivo |
| File manager — finestra (schede, viste, copia async, cestino, apri-con, miniature) | ✅ | ✅ |
| File manager — desktop (sfondo + icone) | ✅ | ✅ multi-monitor, posizioni libere |
| Salvaschermo + blocco schermo con password | ✅ | ✅ |
| Voce di sessione nel display manager | ✅ | ✅ |
| Autostart XDG | ✅ | ✅ |
| Multilingua | spesso parziale | ✅ it/en/fr/es/de |
| Pacchetti installabili | ✅ | ✅ deb + ricette Arch/RPM/Alpine |
| Demone notifiche | ✅ proprio | ⚠️ si usa quello installato |
| Agente PolicyKit | ✅ proprio | ⚠️ si usa quello installato |
| Daemon XSettings (tema/cursore/DPI) | ✅ | ❌ |
| Power management (coperchio, sospensione) | ✅ | ⚠️ batteria e avvisi |
| Automount rimovibili | ✅ | ❌ |
| Schermata di login propria | ✅ (GDM/SDDM/LightDM) | ❌ si usa quella della distro |
| Set di icone proprio | ✅ | ⚠️ si usano quelli di sistema, scelti per colore |
| Pagine di manuale | ✅ | ❌ |

## In sintesi

Vesper fa tutto quello che serve per usarlo come desktop quotidiano, ed è
sopra la media dei DE leggeri su due cose: i **preset di aspetto** (un colore
cambia accento, sfondo, icone e decorazione delle finestre insieme) e
l'**i18n** in cinque lingue. Quello che manca sono i **servizi di sistema**
che gli altri DE portano con sé (notifiche, PolicyKit, XSettings, power
management completo, automount) e la schermata di login: per ora Vesper si
appoggia a quelli della distribuzione, il che funziona ma non è "suo".
