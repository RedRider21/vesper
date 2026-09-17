# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Voci .desktop (freedesktop): lettura, scansione, avvio.

Modulo SENZA dipendenze GTK: lo usano il menu del pannello, l'autostart della
sessione e il file manager (apri-con). Una sola implementazione del parser,
così le tre cose sono d'accordo su cosa sia "un'applicazione installata".
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess

try:
    from vesper.i18n import current_lang as _current_lang
    LANG = _current_lang()
except Exception:                 # noqa: BLE001
    LANG = "it"

# Ambienti desktop con cui ci identifichiamo per OnlyShowIn/NotShowIn: Vesper e
# Openbox (molte voci pensate per un desktop minimale usano quest'ultimo).
ENVS = {"VESPER", "OPENBOX"}

_FIELD_RE = re.compile(r'%[fFuUdDnNickvm]')


def _parse_exec(exec_str):
    """Exec di un .desktop -> argv, togliendo i codici di campo freedesktop
    (%f %F %u %U %i %c %k ...) che non si passano al lancio diretto."""
    cleaned = _FIELD_RE.sub("", exec_str).strip()
    try:
        return shlex.split(cleaned)
    except ValueError:
        return cleaned.split()


def _read_desktop(path):
    """Parsa la sola sezione [Desktop Entry] di un file .desktop -> dict."""
    entry = {}
    in_main = False
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.rstrip("\n")
                if line.startswith("["):
                    in_main = (line.strip() == "[Desktop Entry]")
                    continue
                if not in_main or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                entry[k.strip()] = v.strip()
    except OSError:
        return None
    return entry


def scan_desktop_apps():
    """App installate (freedesktop): scansiona ~/.local/share/applications e le
    directory di $XDG_DATA_DIRS (default /usr/local/share:/usr/share). Salta le
    voci NoDisplay/Hidden e i non-Application. Le dir utente vincono su quelle di
    sistema (dedup per nome-file). Ritorna lista ordinata per nome."""
    home = os.path.expanduser("~")
    xdg_data_home = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local/share")
    dirs = [os.path.join(xdg_data_home, "applications")]
    xdg_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    dirs += [os.path.join(d, "applications") for d in xdg_dirs.split(":") if d]

    seen_files = set()
    apps = {}
    for d in dirs:
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for fn in names:
            if not fn.endswith(".desktop") or fn in seen_files:
                continue
            seen_files.add(fn)                      # dir utente (prima) ha priorita'
            e = _read_desktop(os.path.join(d, fn))
            if not e or e.get("Type") != "Application" or not e.get("Exec"):
                continue
            if e.get("NoDisplay", "").lower() == "true":
                continue
            if e.get("Hidden", "").lower() == "true":
                continue
            argv = _parse_exec(e["Exec"])
            if not argv:
                continue
            # OnlyShowIn/NotShowIn: rispettiamo la scelta dell'app. Vesper si
            # presenta come "Vesper" in XDG_CURRENT_DESKTOP; accettiamo anche
            # le voci pensate per un DE generico basato su Openbox.
            envs = {"VESPER", "OPENBOX"}
            only = {v.strip().upper() for v in
                    (e.get("OnlyShowIn") or "").split(";") if v.strip()}
            nots = {v.strip().upper() for v in
                    (e.get("NotShowIn") or "").split(";") if v.strip()}
            if only and not (only & envs):
                continue
            if nots & envs:
                continue
            # Nome nella lingua dell'interfaccia, se il .desktop la ha
            # (prima era fissato all'italiano: le altre lingue perdevano le
            # traduzioni fornite dalle app).
            name = (e.get("Name[%s]" % LANG) or e.get("Name")
                    or fn[:-8])
            apps[name] = {
                "name": name,
                "argv": argv,
                "icon": e.get("Icon", "application-x-executable"),
                "terminal": e.get("Terminal", "").lower() == "true",
                # Categories serve a raggruppare le voci nel menu (vedi
                # app_category): senza, tutto finirebbe in "Altre".
                "categories": e.get("Categories", ""),
                "comment": e.get("Comment[it]") or e.get("Comment", ""),
            }
    return sorted(apps.values(), key=lambda a: a["name"].lower())



def launch(app: dict, terminal_cmd: str = "vesper-terminal") -> None:
    """Avvia una voce .desktop. Se chiede il terminale, lo apre tramite
    `vesper-terminal`, che sceglie l'emulatore disponibile sulla macchina."""
    argv = app["argv"]
    if app.get("terminal"):
        argv = [terminal_cmd, "-e"] + argv
    try:
        subprocess.Popen(argv, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass


def autostart_entries() -> list[dict]:
    """Voci di avvio automatico XDG: ~/.config/autostart e $XDG_CONFIG_DIRS
    (default /etc/xdg). Le voci utente vincono su quelle di sistema (dedup per
    nome-file), come vuole la specifica. Rispetta Hidden, OnlyShowIn/NotShowIn
    e TryExec."""
    home = os.path.expanduser("~")
    conf_home = os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
    dirs = [os.path.join(conf_home, "autostart")]
    conf_dirs = os.environ.get("XDG_CONFIG_DIRS") or "/etc/xdg"
    dirs += [os.path.join(d, "autostart") for d in conf_dirs.split(":") if d]

    seen, out = set(), []
    for d in dirs:
        try:
            names = sorted(os.listdir(d))
        except OSError:
            continue
        for fn in names:
            if not fn.endswith(".desktop") or fn in seen:
                continue
            seen.add(fn)
            e = _read_desktop(os.path.join(d, fn))
            if not e or not e.get("Exec"):
                continue
            if e.get("Hidden", "").lower() == "true":
                continue
            only = {v.strip().upper() for v in
                    (e.get("OnlyShowIn") or "").split(";") if v.strip()}
            nots = {v.strip().upper() for v in
                    (e.get("NotShowIn") or "").split(";") if v.strip()}
            if (only and not (only & ENVS)) or (nots & ENVS):
                continue
            tryexec = e.get("TryExec")
            if tryexec and not _have(tryexec):
                continue
            argv = _parse_exec(e["Exec"])
            if not argv:
                continue
            out.append({
                "name": e.get("Name[%s]" % LANG) or e.get("Name") or fn[:-8],
                "argv": argv,
                "terminal": e.get("Terminal", "").lower() == "true",
                "file": fn,
            })
    return out


def _have(prog: str) -> bool:
    """TryExec: programma presente (percorso assoluto o nel PATH)."""
    if prog.startswith("/"):
        return os.access(prog, os.X_OK)
    for d in (os.environ.get("PATH") or "/usr/bin:/bin").split(":"):
        if d and os.access(os.path.join(d, prog), os.X_OK):
            return True
    return False
