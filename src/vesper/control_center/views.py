# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Viste GTK native del Centro di Controllo di Vesper.

Ogni funzione open_* costruisce e mostra una finestra con una vera
interfaccia grafica (niente dump testuali ne terminali esterni, salvo
dove un programma dedicato e' gia' una GUI: lxappearance).
"""
from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import threading
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Pango  # noqa: E402
import cairo  # noqa: E402  (py3-cairo, gia' dipendenza)

from vesper.common import (
    HOME, have, run_bg, run_capture, info_dialog, panel_window, read_file,
    icon_button, COL_ACCENT, COL_ALERT,
)
from vesper import panelcfg

try:
    from vesper.i18n import t as _t          # traduzioni (it/en/fr/es/de)
except Exception:                         # noqa: BLE001
    def _t(key, **kw):                    # fallback: non rompe la UI
        return key


# ---------------------------------------------------------------------------
# Letture di sistema
# ---------------------------------------------------------------------------
def _meminfo() -> tuple[int, int]:
    """Ritorna (used_kb, total_kb)."""
    total = avail = 0
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                total = int(line.split()[1])
            elif line.startswith("MemAvailable:"):
                avail = int(line.split()[1])
    except OSError:
        pass
    return max(total - avail, 0), total


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return _t("v.cpu_unknown")


def _cpu_count() -> int:
    return os.cpu_count() or 1


def _read_cpu_times() -> tuple[int, int]:
    """Ritorna (idle, total) dalla prima riga di /proc/stat."""
    try:
        parts = Path("/proc/stat").read_text().splitlines()[0].split()[1:]
        nums = [int(x) for x in parts]
        idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
        return idle, sum(nums)
    except (OSError, ValueError, IndexError):
        return 0, 0


def _distro_name() -> str:
    """Nome del sistema da /etc/os-release (PRETTY_NAME), come fanno tutti gli
    strumenti di sistema: Vesper gira su qualunque distribuzione."""
    try:
        for ln in Path("/etc/os-release").read_text().splitlines():
            if ln.startswith("PRETTY_NAME="):
                return ln.split("=", 1)[1].strip().strip('"')
        for ln in Path("/etc/os-release").read_text().splitlines():
            if ln.startswith("NAME="):
                return ln.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return run_capture(["uname", "-o"]) or "?"


def _pkg_count() -> str:
    """Numero di pacchetti installati, col gestore presente sulla macchina."""
    for cmd in ("apk info 2>/dev/null | wc -l",
                "dpkg-query -f '.\n' -W 2>/dev/null | wc -l",
                "rpm -qa 2>/dev/null | wc -l",
                "pacman -Qq 2>/dev/null | wc -l"):
        out = run_capture(["sh", "-c", cmd]).strip()
        if out.isdigit() and int(out) > 0:
            return out
    return "?"


def _human(kb: int) -> str:
    mb = kb / 1024
    if mb >= 1024:
        return f"{mb/1024:.1f} GB"
    return f"{mb:.0f} MB"


def _human_bps(n: float) -> str:
    """Byte/s -> stringa (B/s, K/s, M/s, G/s)."""
    for unit in ("B", "K", "M", "G"):
        if n < 1024 or unit == "G":
            return f"{n:.0f} {unit}/s"
        n /= 1024.0
    return f"{n:.0f} G/s"


def _human_bytes(n: float) -> str:
    """Byte -> stringa (B/KB/MB/GB/TB) per lo spazio dei filesystem."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} TB"


_DISK_RE = re.compile(r'^(sd[a-z]+|vd[a-z]+|hd[a-z]+|xvd[a-z]+|nvme\d+n\d+|mmcblk\d+)$')


def _read_net_total() -> float:
    """Byte totali rx+tx su tutte le interfacce (esclusa lo)."""
    tot = 0.0
    try:
        with open("/proc/net/dev") as f:
            for line in f.readlines()[2:]:
                iface, _, data = line.partition(":")
                if iface.strip() == "lo":
                    continue
                cols = data.split()
                tot += float(cols[0]) + float(cols[8])
    except (OSError, ValueError, IndexError):
        pass
    return tot


def _read_disk_total() -> float:
    """Byte totali letti+scritti sui dischi fisici interi (da /proc/diskstats)."""
    sectors = 0.0
    try:
        with open("/proc/diskstats") as f:
            for line in f:
                p = line.split()
                if len(p) < 11 or not _DISK_RE.match(p[2]):
                    continue
                sectors += float(p[5]) + float(p[9])
    except (OSError, ValueError, IndexError):
        pass
    return sectors * 512.0


# ---------------------------------------------------------------------------
# Info sistema
# ---------------------------------------------------------------------------
def open_sysinfo(_btn=None):
    win, body = panel_window(_t("v.sysinfo.title"), 560, 480)

    grid = Gtk.Grid(column_spacing=18, row_spacing=8)
    body.pack_start(grid, False, False, 0)

    def row(r, key, val):
        k = Gtk.Label(label=key)
        k.set_xalign(0)
        k.get_style_context().add_class("vesper-key")
        v = Gtk.Label(label=val)
        v.set_xalign(0)
        v.set_selectable(True)
        v.get_style_context().add_class("vesper-val")
        v.set_line_wrap(True)
        grid.attach(k, 0, r, 1, 1)
        grid.attach(v, 1, r, 1, 1)
        return v

    uname = run_capture(["uname", "-r"]) or "?"
    arch = run_capture(["uname", "-m"]) or "?"
    row(0, _t("v.host"), socket.gethostname())
    row(1, _t("v.user"), os.getenv("USER", "?"))
    row(2, _t("v.system"), _distro_name())
    row(3, _t("v.kernel"), uname)
    row(4, _t("v.arch"), arch)
    row(5, _t("v.cpu"), f"{_cpu_model()}  ({_cpu_count()} core)")
    up = row(6, _t("v.uptime"), run_capture(["uptime", "-p"]) or run_capture(["uptime"]))

    # RAM
    body.pack_start(Gtk.Separator(), False, False, 6)
    ram_lbl = Gtk.Label(); ram_lbl.set_xalign(0)
    ram_lbl.get_style_context().add_class("vesper-key")
    ram_bar = Gtk.ProgressBar(); ram_bar.set_show_text(True)
    body.pack_start(ram_lbl, False, False, 0)
    body.pack_start(ram_bar, False, False, 0)

    # Disco /
    disk_lbl = Gtk.Label(); disk_lbl.set_xalign(0)
    disk_lbl.get_style_context().add_class("vesper-key")
    disk_bar = Gtk.ProgressBar(); disk_bar.set_show_text(True)
    body.pack_start(disk_lbl, False, False, 0)
    body.pack_start(disk_bar, False, False, 0)

    # Pacchetti installati (qualunque gestore)
    tcz = row(7, _t("v.pkgs"), _pkg_count())

    def refresh(*_a):
        used, total = _meminfo()
        if total:
            frac = used / total
            ram_bar.set_fraction(frac)
            ram_bar.set_text(f"{_human(used)} / {_human(total)}  ({frac*100:.0f}%)")
        ram_lbl.set_text(_t("v.ram"))
        try:
            du = shutil.disk_usage("/")
            frac = du.used / du.total if du.total else 0
            disk_bar.set_fraction(frac)
            disk_bar.set_text(f"{du.used//(1024**2)} MB / {du.total//(1024**2)} MB  ({frac*100:.0f}%)")
        except OSError:
            disk_bar.set_text(_t("v.na"))
        disk_lbl.set_text(_t("v.disk_root"))
        up.set_text(run_capture(["uptime", "-p"]) or run_capture(["uptime"]))

    refresh()

    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    btn_r = Gtk.Button(label=_t("v.refresh"))
    btn_r.connect("clicked", refresh)
    btn_c = Gtk.Button(label=_t("v.close"))
    btn_c.connect("clicked", lambda _b: win.destroy())
    bar.pack_start(btn_r, False, False, 0)
    bar.pack_end(btn_c, False, False, 0)
    body.pack_end(bar, False, False, 0)

    win.show_all()


# ---------------------------------------------------------------------------
# Monitor risorse (live, nativo)
# ---------------------------------------------------------------------------
GRAPH_N = 60


class _Graph(Gtk.DrawingArea):
    """Grafico a scorrimento (linea + area riempita + griglia), stile Monitor di
    sistema MATE. hist tiene 0..1 (CPU/RAM) o byte/s grezzi (Rete/Disco: autoscale)."""
    def __init__(self, rgb, autoscale=False):
        super().__init__()
        self.rgb = rgb
        self.autoscale = autoscale
        self.hist = [0.0] * GRAPH_N
        self.set_size_request(-1, 68)
        self.connect("draw", self._draw)

    def push(self, v):
        self.hist.append(v if v > 0 else 0.0)
        del self.hist[0]
        self.queue_draw()

    def _draw(self, _w, cr):
        w = self.get_allocated_width(); h = self.get_allocated_height()
        r, g, b = self.rgb
        cr.set_source_rgba(0.02, 0.06, 0.10, 1.0)
        cr.rectangle(0, 0, w, h); cr.fill()
        cr.set_source_rgba(0.10, 0.23, 0.32, 0.55); cr.set_line_width(1)
        for i in range(1, 4):
            y = round(h * i / 4.0) + 0.5
            cr.move_to(0, y); cr.line_to(w, y); cr.stroke()
        if self.autoscale:
            peak = max(self.hist); peak = peak if peak > 1 else 1.0
            vals = [min(1.0, v / peak) for v in self.hist]
        else:
            vals = [min(1.0, v) for v in self.hist]
        n = len(vals)
        if n >= 2:
            step = w / (n - 1); pad = 2
            def yv(v):
                return h - pad - v * (h - 2 * pad)
            cr.move_to(0, h)
            for i, v in enumerate(vals):
                cr.line_to(i * step, yv(v))
            cr.line_to((n - 1) * step, h); cr.close_path()
            grad = cairo.LinearGradient(0, 0, 0, h)
            grad.add_color_stop_rgba(0, r, g, b, 0.42)
            grad.add_color_stop_rgba(1, r, g, b, 0.04)
            cr.set_source(grad); cr.fill()
            cr.set_source_rgba(r, g, b, 0.95); cr.set_line_width(1.6)
            cr.set_line_join(cairo.LINE_JOIN_ROUND)
            for i, v in enumerate(vals):
                (cr.move_to if i == 0 else cr.line_to)(i * step, yv(v))
            cr.stroke()
        cr.set_source_rgba(0.10, 0.23, 0.32, 0.9); cr.set_line_width(1)
        cr.rectangle(0.5, 0.5, w - 1, h - 1); cr.stroke()


def _filesystems():
    """Filesystem montati REALI: (device, mount, tipo, tot, usato, libero)."""
    pseudo = {"proc", "sysfs", "devtmpfs", "devpts", "cgroup", "cgroup2",
              "mqueue", "debugfs", "tracefs", "securityfs", "pstore", "bpf",
              "configfs", "fusectl", "hugetlbfs", "autofs", "binfmt_misc",
              "ramfs", "efivarfs"}
    seen = set(); rows = []
    try:
        with open("/proc/mounts") as f:
            lines = f.readlines()
    except OSError:
        return rows
    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        dev, mnt, fstype = parts[0], parts[1], parts[2]
        if fstype in pseudo or mnt in seen:
            continue
        seen.add(mnt)
        mnt_dec = mnt.replace("\\040", " ")
        try:
            st = os.statvfs(mnt)
        except OSError:
            continue
        total = st.f_blocks * st.f_frsize
        if total == 0:
            continue
        used = (st.f_blocks - st.f_bfree) * st.f_frsize
        free = st.f_bavail * st.f_frsize
        rows.append((dev, mnt_dec, fstype, total, used, free))
    return rows


def open_monitor(_btn=None):
    win, body = panel_window(_t("v.monitor.title"), 540, 600)
    nb = Gtk.Notebook()
    body.pack_start(nb, True, True, 0)

    # ===== Scheda RISORSE: grafici a scorrimento =====
    res = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    res.set_border_width(8)
    nb.append_page(res, Gtk.Label(label=_t("v.resources")))

    def make_graph(title, rgb, autoscale=False):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        card.get_style_context().add_class("vesper-card")
        hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        t = Gtk.Label(label=title); t.set_xalign(0)
        t.get_style_context().add_class("vesper-card-title")
        val = Gtk.Label(); val.set_xalign(1)
        val.get_style_context().add_class("vesper-val")
        hdr.pack_start(t, True, True, 0)
        hdr.pack_end(val, False, False, 0)
        gr = _Graph(rgb, autoscale)
        card.pack_start(hdr, False, False, 0)
        card.pack_start(gr, False, False, 0)
        res.pack_start(card, False, False, 0)
        return gr, val

    cpu_g, cpu_v = make_graph(_t("v.cpu"), (0.00, 0.898, 1.00))
    ram_g, ram_v = make_graph(_t("v.ram"), (0.40, 0.95, 0.65))
    net_g, net_v = make_graph(_t("v.net_rxtx"), (1.00, 0.72, 0.25), True)
    disk_g, disk_v = make_graph(_t("v.disk_rw"), (0.66, 0.55, 1.00), True)

    # --- Pannellino _t("v.loadavg_plain") ---
    ncpu = max(1, _cpu_count())
    load_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    load_card.get_style_context().add_class("vesper-card")
    lc_title = Gtk.Label(); lc_title.set_xalign(0)
    lc_title.get_style_context().add_class("vesper-card-title")
    lc_title.set_text(_t("v.loadavg") % ncpu)
    load_card.pack_start(lc_title, False, False, 0)

    load_bars = {}
    lgrid = Gtk.Grid(column_spacing=10, row_spacing=4)
    for i, name in enumerate((_t("v.1min"), _t("v.5min"), _t("v.15min"))):
        kl = Gtk.Label(label=name); kl.set_xalign(0)
        kl.get_style_context().add_class("vesper-val")
        pb = Gtk.ProgressBar(); pb.set_show_text(True); pb.set_hexpand(True)
        lgrid.attach(kl, 0, i, 1, 1)
        lgrid.attach(pb, 1, i, 1, 1)
        load_bars[i] = pb
    load_card.pack_start(lgrid, False, False, 0)
    load_extra = Gtk.Label(); load_extra.set_xalign(0)
    load_extra.get_style_context().add_class("vesper-val")
    load_card.pack_start(load_extra, False, False, 0)
    res.pack_start(load_card, False, False, 2)

    state = {"idle": 0, "total": 0}
    state["idle"], state["total"] = _read_cpu_times()
    state["net"] = _read_net_total()
    state["disk"] = _read_disk_total()

    def tick():
        idle, total = _read_cpu_times()
        di = idle - state["idle"]; dt = total - state["total"]
        state["idle"], state["total"] = idle, total
        cpu = min(max((1 - di / dt) if dt > 0 else 0, 0), 1)
        cpu_g.push(cpu); cpu_v.set_text(f"{cpu*100:.0f}%")

        used, tot = _meminfo()
        frac = used / tot if tot else 0
        ram_g.push(frac)
        ram_v.set_text(f"{_human(used)} / {_human(tot)}  ({frac*100:.0f}%)")

        ncur = _read_net_total()
        nrate = max(0.0, ncur - state["net"]); state["net"] = ncur
        net_g.push(nrate); net_v.set_text(_human_bps(nrate))

        dcur = _read_disk_total()
        drate = max(0.0, dcur - state["disk"]); state["disk"] = dcur
        disk_g.push(drate); disk_v.set_text(_human_bps(drate))

        try:
            la = os.getloadavg()
            for i in range(3):
                frac = min(1.0, la[i] / ncpu)
                load_bars[i].set_fraction(frac)
                load_bars[i].set_text("%.2f  (%.0f%%)" % (la[i], frac * 100))
                ctx = load_bars[i].get_style_context()
                ctx.remove_class("vesper-warn"); ctx.remove_class("vesper-alert")
                if frac >= 1.0:
                    ctx.add_class("vesper-alert")
                elif frac >= 0.7:
                    ctx.add_class("vesper-warn")
            try:
                nproc = sum(1 for p in os.listdir("/proc") if p.isdigit())
                load_extra.set_text(_t("v.procs") % nproc)
            except OSError:
                pass
        except OSError:
            pass
        return True

    # ===== Scheda FILE SYSTEM: spazio dischi/partizioni =====
    fs_scroll = Gtk.ScrolledWindow()
    fs_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    fs_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    fs_box.set_border_width(8)
    fs_scroll.add(fs_box)
    nb.append_page(fs_scroll, Gtk.Label(label=_t("v.fs")))

    def refresh_fs():
        for c in fs_box.get_children():
            fs_box.remove(c)
        rows = _filesystems()
        if not rows:
            lbl = Gtk.Label(label=_t("v.nofs")); lbl.set_xalign(0)
            fs_box.pack_start(lbl, False, False, 0)
        for dev, mnt, fstype, total, used, free in rows:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            card.get_style_context().add_class("vesper-card")
            top = Gtk.Label(); top.set_xalign(0)
            top.set_markup("<b>%s</b>  <small>%s · %s</small>" % (
                GLib.markup_escape_text(mnt),
                GLib.markup_escape_text(dev), GLib.markup_escape_text(fstype)))
            card.pack_start(top, False, False, 0)
            frac = used / total if total else 0
            bar = Gtk.ProgressBar(); bar.set_fraction(min(1.0, frac))
            bar.set_show_text(True)
            bar.set_text(_t("v.disk_free") % (
                _human_bytes(used), _human_bytes(total), frac * 100,
                _human_bytes(free)))
            ctx = bar.get_style_context()
            if frac >= 0.9:
                ctx.add_class("vesper-alert")
            elif frac >= 0.75:
                ctx.add_class("vesper-warn")
            card.pack_start(bar, False, False, 0)
            fs_box.pack_start(card, False, False, 0)
        fs_box.show_all()

    # ===== Scheda SISTEMA: informazioni statiche + RAM/uptime live =====
    sys_scroll = Gtk.ScrolledWindow()
    sys_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    sys_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    sys_box.set_border_width(8)
    sys_scroll.add(sys_box)
    nb.append_page(sys_scroll, Gtk.Label(label=_t("v.system")))

    sgrid = Gtk.Grid(column_spacing=18, row_spacing=6)
    sys_box.pack_start(sgrid, False, False, 0)

    def srow(r, key, val):
        k = Gtk.Label(label=key); k.set_xalign(0)
        k.get_style_context().add_class("vesper-key")
        v = Gtk.Label(label=val); v.set_xalign(0); v.set_selectable(True)
        v.set_line_wrap(True); v.get_style_context().add_class("vesper-val")
        sgrid.attach(k, 0, r, 1, 1); sgrid.attach(v, 1, r, 1, 1)
        return v

    srow(0, _t("v.host"), socket.gethostname())
    srow(1, _t("v.user"), os.getenv("USER", "?"))
    srow(2, _t("v.system"), _distro_name())
    srow(3, _t("v.kernel"), run_capture(["uname", "-r"]) or "?")
    srow(4, _t("v.arch"), run_capture(["uname", "-m"]) or "?")
    srow(5, _t("v.cpu"), "%s  (%d core)" % (_cpu_model(), _cpu_count()))
    sys_up = srow(6, _t("v.uptime"),
                  run_capture(["uptime", "-p"]) or run_capture(["uptime"]))
    srow(7, _t("v.pkgs"), _pkg_count())

    sys_box.pack_start(Gtk.Separator(), False, False, 4)
    sys_ram_lbl = Gtk.Label(label=_t("v.ram")); sys_ram_lbl.set_xalign(0)
    sys_ram_lbl.get_style_context().add_class("vesper-key")
    sys_ram_bar = Gtk.ProgressBar(); sys_ram_bar.set_show_text(True)
    sys_box.pack_start(sys_ram_lbl, False, False, 0)
    sys_box.pack_start(sys_ram_bar, False, False, 0)
    sys_disk_lbl = Gtk.Label(label=_t("v.disk_root")); sys_disk_lbl.set_xalign(0)
    sys_disk_lbl.get_style_context().add_class("vesper-key")
    sys_disk_bar = Gtk.ProgressBar(); sys_disk_bar.set_show_text(True)
    sys_box.pack_start(sys_disk_lbl, False, False, 0)
    sys_box.pack_start(sys_disk_bar, False, False, 0)

    def refresh_sys():
        used, total = _meminfo()
        if total:
            frac = used / total
            sys_ram_bar.set_fraction(frac)
            sys_ram_bar.set_text("%s / %s  (%.0f%%)" % (
                _human(used), _human(total), frac * 100))
        try:
            du = shutil.disk_usage("/")
            frac = du.used / du.total if du.total else 0
            sys_disk_bar.set_fraction(frac)
            sys_disk_bar.set_text("%s / %s  (%.0f%%)" % (
                _human_bytes(du.used), _human_bytes(du.total), frac * 100))
        except OSError:
            sys_disk_bar.set_text(_t("v.na"))
        sys_up.set_text(run_capture(["uptime", "-p"]) or run_capture(["uptime"]))
        return True

    refresh_sys()
    refresh_fs()
    tick()
    src3 = GLib.timeout_add_seconds(5, refresh_sys)
    src1 = GLib.timeout_add_seconds(1, tick)
    src2 = GLib.timeout_add_seconds(5, lambda: (refresh_fs(), True)[1])
    win.connect("destroy", lambda *_a: (GLib.source_remove(src1),
                                        GLib.source_remove(src2),
                                        GLib.source_remove(src3)))

    btn_c = Gtk.Button(label=_t("v.close"))
    btn_c.connect("clicked", lambda _b: win.destroy())
    bbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    bbox.pack_end(btn_c, False, False, 0)
    body.pack_end(bbox, False, False, 0)

    win.show_all()


# ---------------------------------------------------------------------------
# Rete
# ---------------------------------------------------------------------------
def _parse_interfaces() -> list[tuple[str, str, str]]:
    """Ritorna lista (interfaccia, ipv4, stato)."""
    out = run_capture(["ip", "-o", "-4", "addr", "show"])
    rows: dict[str, list[str]] = {}
    if out:
        for line in out.splitlines():
            m = re.match(r"\d+:\s+(\S+)\s+inet\s+(\S+)", line)
            if m:
                rows.setdefault(m.group(1), []).append(m.group(2))
    # stato up/down
    res = []
    for iface, ips in rows.items():
        state_out = run_capture(["sh", "-c", f"cat /sys/class/net/{iface}/operstate 2>/dev/null"])
        res.append((iface, ", ".join(ips), state_out or "?"))
    if not res:
        # fallback ifconfig
        ic = run_capture(["ifconfig"])
        cur = None
        for line in ic.splitlines():
            if line and not line[0].isspace():
                cur = line.split()[0].rstrip(":")
            m = re.search(r"inet (?:addr:)?(\S+)", line)
            if m and cur:
                res.append((cur, m.group(1), "?"))
    return res


def _net_ifaces() -> list[str]:
    """Interfacce di rete configurabili (esclusa loopback)."""
    names = []
    base = Path("/sys/class/net")
    if base.is_dir():
        for p in sorted(base.iterdir()):
            if p.name != "lo":
                names.append(p.name)
    return names


def _valid_ipv4(s: str) -> bool:
    parts = s.split(".")
    if len(parts) != 4:
        return False
    for p in parts:
        if not p.isdigit() or not 0 <= int(p) <= 255:
            return False
    return True


def open_network(_btn=None):
    win, body = panel_window(_t("v.network"), 600, 560)

    store = Gtk.ListStore(str, str, str)
    tree = Gtk.TreeView(model=store)
    for i, title in enumerate((_t("v.col_iface"), _t("v.col_ipv4"), _t("v.col_state"))):
        col = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=i)
        col.set_expand(i == 1)
        tree.append_column(col)
    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    sw.set_min_content_height(120)
    sw.add(tree)
    body.pack_start(sw, True, True, 0)

    def refresh(*_a):
        store.clear()
        for r in _parse_interfaces():
            store.append(list(r))
        if not len(store):
            store.append((_t("v.none_paren"), "-", "-"))

    refresh()

    # --- Configurazione interfaccia -------------------------------------
    frame = Gtk.Frame(label=_t("v.config"))
    grid = Gtk.Grid(row_spacing=8, column_spacing=8)
    grid.set_margin_top(8); grid.set_margin_bottom(8)
    grid.set_margin_start(8); grid.set_margin_end(8)
    frame.add(grid)

    grid.attach(Gtk.Label(label=_t("v.iface"), xalign=0), 0, 0, 1, 1)
    cb_if = Gtk.ComboBoxText()
    for name in _net_ifaces() or ["eth0"]:
        cb_if.append_text(name)
    cb_if.set_active(0)
    grid.attach(cb_if, 1, 0, 2, 1)

    rb_dhcp = Gtk.RadioButton.new_with_label_from_widget(None, _t("v.auto_dhcp"))
    rb_static = Gtk.RadioButton.new_with_label_from_widget(rb_dhcp, _t("v.static"))
    grid.attach(rb_dhcp, 0, 1, 3, 1)
    grid.attach(rb_static, 0, 2, 3, 1)

    def mk_row(label, row, placeholder):
        grid.attach(Gtk.Label(label=label, xalign=0), 0, row, 1, 1)
        e = Gtk.Entry()
        e.set_placeholder_text(placeholder)
        grid.attach(e, 1, row, 2, 1)
        return e

    e_ip = mk_row(_t("v.ip_label"), 3, "es. 192.168.1.50")
    e_mask = mk_row(_t("v.mask_label"), 4, "es. 255.255.255.0")
    e_gw = mk_row(_t("v.gw_label"), 5, "es. 192.168.1.1")
    e_dns = mk_row(_t("v.dns_label"), 6, "es. 1.1.1.1")

    def on_mode(*_a):
        static = rb_static.get_active()
        for e in (e_ip, e_mask, e_gw, e_dns):
            e.set_sensitive(static)

    rb_dhcp.connect("toggled", on_mode)
    on_mode()
    body.pack_start(frame, False, False, 0)

    ping_lbl = Gtk.Label(label=_t("v.conn_untested"))
    ping_lbl.set_xalign(0)
    ping_lbl.get_style_context().add_class("vesper-val")
    body.pack_start(ping_lbl, False, False, 0)

    spinner = Gtk.Spinner()

    def set_status(txt):
        ping_lbl.set_text(txt)
        return False

    def do_ping(_b):
        spinner.start()
        ping_lbl.set_text(_t("v.testing"))

        def worker():
            out = run_capture(["ping", "-c", "2", "-W", "2", "1.1.1.1"], timeout=8)
            ok = "0% packet loss" in out or " 0% packet" in out
            m = re.search(r"min/avg/max\S*\s*=\s*[\d.]+/([\d.]+)", out)
            avg = f"  (avg {m.group(1)} ms)" if m else ""
            txt = (_t("v.conn_ok") + avg) if ok else _t("v.conn_none")
            GLib.idle_add(finish, txt)

        def finish(txt):
            spinner.stop()
            ping_lbl.set_text(_t("v.net.conn") + " " + txt)
            return False

        threading.Thread(target=worker, daemon=True).start()

    def do_apply(_b):
        iface = cb_if.get_active_text()
        if not iface:
            info_dialog(_t("v.network"), _t("v.no_iface_sel"), level="warn", parent=win)
            return
        if rb_static.get_active():
            ip = e_ip.get_text().strip()
            mask = e_mask.get_text().strip() or "255.255.255.0"
            gw = e_gw.get_text().strip()
            dns = e_dns.get_text().strip()
            if not _valid_ipv4(ip):
                info_dialog(_t("v.network"), _t("v.ip_invalid"), level="warn", parent=win)
                return
            if not _valid_ipv4(mask):
                info_dialog(_t("v.network"), _t("v.mask_invalid"), level="warn", parent=win)
                return
            if gw and not _valid_ipv4(gw):
                info_dialog(_t("v.network"), _t("v.gw_invalid"), level="warn", parent=win)
                return
            if dns and not _valid_ipv4(dns):
                info_dialog(_t("v.network"), _t("v.dns_invalid"), level="warn", parent=win)
                return
            script = (
                f"pkill -f 'udhcpc.*{iface}' 2>/dev/null; "
                f"ifconfig {iface} {ip} netmask {mask} up && "
                f"{{ [ -n '{gw}' ] && {{ route del default 2>/dev/null; route add default gw {gw}; }}; }}; "
                f"{{ [ -n '{dns}' ] && echo 'nameserver {dns}' > /etc/resolv.conf; }}; true"
            )
            descr = f"IP statico {ip}/{mask} su {iface}"
        else:
            script = (
                f"pkill -f 'udhcpc.*{iface}' 2>/dev/null; "
                f"ifconfig {iface} up; "
                f"udhcpc -b -i {iface} -t 8 -T 2 2>&1"
            )
            descr = f"DHCP su {iface}"

        spinner.start()
        ping_lbl.set_text(_t("v.net.applying") % descr)

        def worker():
            out = run_capture(["sudo", "sh", "-c", script], timeout=25)
            def finish():
                spinner.stop()
                refresh()
                ping_lbl.set_text(_t("v.net.applied") % descr)
                if out:
                    print("[rete] " + out, flush=True)
                return False
            GLib.idle_add(finish)

        threading.Thread(target=worker, daemon=True).start()

    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    b_apply = icon_button(_t("v.apply"), "emblem-ok", primary=True)
    b_apply.connect("clicked", do_apply)
    b_ping = icon_button(_t("v.test_conn"), "network-transmit-receive")
    b_ping.connect("clicked", do_ping)
    b_ref = icon_button(_t("v.refresh"), "view-refresh")
    b_ref.connect("clicked", refresh)
    b_close = icon_button(_t("v.close"), "window-close")
    b_close.connect("clicked", lambda _b: win.destroy())
    bar.pack_start(b_apply, False, False, 0)
    bar.pack_start(b_ping, False, False, 0)
    bar.pack_start(spinner, False, False, 0)
    bar.pack_start(b_ref, False, False, 0)
    bar.pack_end(b_close, False, False, 0)
    body.pack_end(bar, False, False, 0)

    win.show_all()


# ---------------------------------------------------------------------------
# Privilegi (doas / sudo / pkexec)
# ---------------------------------------------------------------------------
def _priv():
    """Comando per privilegi: doas, sudo o pkexec, il primo disponibile."""
    import shutil
    if shutil.which("doas"):
        return ["doas"]
    if shutil.which("sudo"):
        return ["sudo"]
    return []




# Nomi GDK dei soli modificatori: premerli da soli non fa una scorciatoia.
_OB_MOD_SKIP = ("Control_L", "Control_R", "Alt_L", "Alt_R", "Shift_L",
                "Shift_R", "Super_L", "Super_R", "Meta_L", "Meta_R",
                "ISO_Level3_Shift", "Caps_Lock", "Num_Lock")


def _ob_key_from_event(ev):
    """Da un evento tastiera GDK alla stringa in sintassi Openbox ('W-n',
    'C-A-t'). None se e' premuto solo un modificatore. La sintassi Openbox e'
    quella "ufficiale" di Vesper: con marco la traduce vesper-keys."""
    name = Gdk.keyval_name(ev.keyval)
    if name in _OB_MOD_SKIP:
        return None
    m = ev.state
    parts = []
    if m & Gdk.ModifierType.CONTROL_MASK:
        parts.append("C")
    if m & Gdk.ModifierType.MOD1_MASK:                 # Alt
        parts.append("A")
    if m & Gdk.ModifierType.SHIFT_MASK:
        parts.append("S")
    if (m & Gdk.ModifierType.SUPER_MASK) or (m & Gdk.ModifierType.MOD4_MASK):
        parts.append("W")                              # Super / tasto Windows
    if len(name) == 1 and name.isalpha():
        name = name.lower()                            # 'S-n', non 'S-N'
    return "-".join(parts + [name])


def _capture_key(parent):
    """Dialogo «premi la combinazione» -> stringa Openbox o None."""
    dlg = Gtk.Dialog(title=_t("v.new_combo"), transient_for=parent, modal=True)
    dlg.add_button(_t("v.cancel"), Gtk.ResponseType.CANCEL)
    lab = Gtk.Label(label=_t("v.press_combo"))
    lab.set_line_wrap(True)
    lab.set_margin_top(24); lab.set_margin_bottom(24)
    lab.set_margin_start(28); lab.set_margin_end(28)
    dlg.get_content_area().add(lab)
    res = {"key": None}

    def on_key(_w, ev):
        if ev.keyval == Gdk.KEY_Escape:
            dlg.response(Gtk.ResponseType.CANCEL)
            return True
        k = _ob_key_from_event(ev)
        if k:
            res["key"] = k
            dlg.response(Gtk.ResponseType.OK)
        return True
    dlg.connect("key-press-event", on_key)
    dlg.show_all()
    dlg.run()
    dlg.destroy()
    return res["key"]


def _ask_text(parent, title, initial=""):
    """Dialogo con una sola riga di testo -> il testo, o None se si annulla."""
    dlg = Gtk.Dialog(title=title, transient_for=parent, modal=True)
    dlg.add_button(_t("v.cancel"), Gtk.ResponseType.CANCEL)
    dlg.add_button(_t("v.ok"), Gtk.ResponseType.OK)
    ent = Gtk.Entry(); ent.set_text(initial); ent.set_activates_default(True)
    ent.set_width_chars(40)
    ent.set_margin_top(14); ent.set_margin_bottom(14)
    ent.set_margin_start(16); ent.set_margin_end(16)
    dlg.get_content_area().add(ent)
    dlg.set_default_response(Gtk.ResponseType.OK)
    dlg.show_all()
    resp = dlg.run()
    txt = ent.get_text().strip()
    dlg.destroy()
    return txt if resp == Gtk.ResponseType.OK and txt else None


def open_hotkeys(_btn=None):
    win, body = panel_window(_t("v.hotkeys.title"), 620, 560)

    dove = run_capture(["vesper-keys", "backend"], timeout=6).strip()
    intro = Gtk.Label(label=_t("v.hk_intro") + (("\n" + dove) if dove else ""))
    intro.set_xalign(0); intro.set_line_wrap(True)
    intro.get_style_context().add_class("vesper-val")
    body.pack_start(intro, False, False, 0)

    store = Gtk.ListStore(str, str)                    # tasto, comando
    tree = Gtk.TreeView(model=store)
    tree.set_headers_visible(True)
    c0 = Gtk.TreeViewColumn(_t("v.col_key"), Gtk.CellRendererText(), text=0)
    c0.set_min_width(180)
    tree.append_column(c0)
    rend = Gtk.CellRendererText(); rend.set_property("editable", True)
    c1 = Gtk.TreeViewColumn(_t("v.col_command"), rend, text=1)
    c1.set_expand(True)
    tree.append_column(c1)
    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    sw.add(tree)
    body.pack_start(sw, True, True, 0)

    def keys(*args):
        subprocess.run(["vesper-keys", *args],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def refresh():
        store.clear()
        for line in run_capture(["vesper-keys", "list"], timeout=8).splitlines():
            if "\t" in line:
                k, c = line.split("\t", 1)
                store.append([k, c])

    def _selected():
        model, it = tree.get_selection().get_selected()
        return (model, it) if it else (None, None)

    def on_cmd_edited(_r, path, new_text):
        new_text = new_text.strip()
        if not new_text:
            return
        k = store[path][0]
        keys("set", k, k, new_text)
        refresh()
    rend.connect("edited", on_cmd_edited)

    def on_add(_b):
        k = _capture_key(win)
        if not k:
            return
        cmd = _ask_text(win, _t("v.cmd_for") % k)
        if not cmd:
            return
        keys("add", k, cmd)
        refresh()

    def on_rekey(_b):
        model, it = _selected()
        if not it:
            return
        oldk = model[it][0]; cmd = model[it][1]
        newk = _capture_key(win)
        if not newk or newk == oldk:
            return
        keys("set", oldk, newk, cmd)
        refresh()

    def on_remove(_b):
        model, it = _selected()
        if not it:
            return
        keys("remove", model[it][0])
        refresh()

    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    b_add = icon_button(_t("v.add"), "list-add-symbolic", primary=True)
    b_add.connect("clicked", on_add)
    b_re = icon_button(_t("v.change_key"), "input-keyboard-symbolic")
    b_re.connect("clicked", on_rekey)
    b_rm = icon_button(_t("v.remove"), "list-remove-symbolic")
    b_rm.connect("clicked", on_remove)
    b_close = icon_button(_t("v.close"), "window-close")
    b_close.connect("clicked", lambda _b: win.destroy())
    bar.pack_start(b_add, False, False, 0)
    bar.pack_start(b_re, False, False, 0)
    bar.pack_start(b_rm, False, False, 0)
    bar.pack_end(b_close, False, False, 0)
    body.pack_end(bar, False, False, 0)

    refresh()
    win.show_all()


# ---------------------------------------------------------------------------
# Pannello inferiore (vesper-panel) - gestione
# ---------------------------------------------------------------------------
def _panel_running() -> bool:
    out = run_capture(["pgrep", "-f", "vesper.panel"])
    return bool(out.strip())


def _panel_start():
    subprocess.Popen(["sh", "-c", "vesper-panel >/tmp/vesper-panel.log 2>&1 &"])


def _panel_stop():
    subprocess.Popen(["pkill", "-f", "vesper.panel"])


def _panel_restart():
    # pkill DIRETTO (si auto-esclude) + launcher il cui argv NON contiene
    # "vesper.panel" (altrimenti pkill -f ucciderebbe la shell del rilancio).
    subprocess.run(["pkill", "-f", "vesper.panel"])
    subprocess.Popen(["sh", "-c", "sleep 0.4; exec vesper-panel"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


def _zram_stato() -> dict:
    """Stato della zram, chiesto a vesper-zram (che sa leggere /sys)."""
    import json as _json
    try:
        return _json.loads(run_capture(["vesper-zram", "status", "--json"],
                                       timeout=8) or "{}")
    except ValueError:
        return {}


def _gb(kb: float) -> str:
    if kb >= 1024 * 1024:
        return "%.1f GB" % (kb / 1024 / 1024)
    return "%.0f MB" % (kb / 1024)


def open_zram(_btn=None):
    """Swap compresso in RAM: stato e accensione, sempre su richiesta."""
    win, body = panel_window(_t("v.zram.title"), 620, 540)

    intro = Gtk.Label(label=_t("v.zram.intro"))
    intro.set_xalign(0); intro.set_line_wrap(True)
    intro.get_style_context().add_class("vesper-val")
    body.pack_start(intro, False, False, 0)

    griglia = Gtk.Grid(column_spacing=16, row_spacing=6)
    body.pack_start(griglia, False, False, 6)
    valori = {}
    for riga, (chiave, etichetta) in enumerate((
            ("ram", _t("v.zram.ram")),
            ("zram", _t("v.zram.device")),
            ("dentro", _t("v.zram.inside")),
            ("swap", _t("v.zram.swap")),
            ("conf", _t("v.zram.config")),
            ("consiglio", _t("v.zram.advice")))):
        k = Gtk.Label(label=etichetta); k.set_xalign(0)
        k.get_style_context().add_class("vesper-key")
        v = Gtk.Label(label="-"); v.set_xalign(0); v.set_line_wrap(True)
        v.get_style_context().add_class("vesper-val")
        griglia.attach(k, 0, riga, 1, 1)
        griglia.attach(v, 1, riga, 1, 1)
        valori[chiave] = v

    avviso = Gtk.Label(label="")
    avviso.set_xalign(0); avviso.set_line_wrap(True)
    avviso.get_style_context().add_class("vesper-warn")
    body.pack_start(avviso, False, False, 0)

    # --- scelte per l'accensione ---
    scelte = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    scelte.pack_start(Gtk.Label(label=_t("v.zram.size")), False, False, 0)
    quota = Gtk.SpinButton.new_with_range(10, 200, 5)
    quota.set_value(50)
    scelte.pack_start(quota, False, False, 0)
    scelte.pack_start(Gtk.Label(label=_t("v.zram.algo")), False, False, 0)
    algo = Gtk.ComboBoxText()
    for nome in ("zstd", "lz4", "lzo-rle", "lzo"):
        algo.append_text(nome)
    algo.set_active(0)
    scelte.pack_start(algo, False, False, 0)
    body.pack_start(scelte, False, False, 0)

    stato_msg = Gtk.Label(label="")
    stato_msg.set_xalign(0); stato_msg.set_line_wrap(True)
    stato_msg.get_style_context().add_class("vesper-val")
    body.pack_start(stato_msg, False, False, 0)

    b_on = icon_button(_t("v.zram.enable"), "media-playback-start-symbolic",
                       primary=True)
    b_off = icon_button(_t("v.zram.disable"), "media-playback-stop-symbolic")

    def aggiorna():
        s = _zram_stato()
        attiva = bool(s.get("attiva"))
        valori["ram"].set_text(_gb(s.get("ram_kb", 0)))
        dev = s.get("dispositivi") or []
        if dev:
            d = dev[0]
            valori["zram"].set_text(
                _t("v.zram.dev_line")
                % (d["dispositivo"], _gb(d["disksize"] / 1024), d["algoritmo"],
                   s.get("quota_ram", 0)))
            if d.get("originale", 0) > 1024 * 1024:
                valori["dentro"].set_text(
                    _t("v.zram.ratio") % (_gb(d["originale"] / 1024),
                                          _gb(d["usato_ram"] / 1024),
                                          d.get("rapporto", 0)))
            else:
                valori["dentro"].set_text(_t("v.zram.empty"))
        else:
            valori["zram"].set_text(_t("v.zram.absent"))
            valori["dentro"].set_text("-")
        valori["swap"].set_text("%s (%s %s)"
                                % (_gb(s.get("swap_totale_kb", 0)),
                                   _t("v.zram.used"),
                                   _gb(s.get("swap_usato_kb", 0))))
        valori["conf"].set_text(s.get("config") or _t("v.zram.noconfig"))
        valori["consiglio"].set_text(s.get("consiglio", "-"))
        conflitti = s.get("conflitti") or []
        if conflitti:
            avviso.set_text(_t("v.zram.conflict")
                            % ", ".join(c["servizio"] for c in conflitti))
        else:
            avviso.set_text("")
        b_on.set_sensitive(not attiva)
        b_off.set_sensitive(attiva)
        if dev:
            quota.set_value(max(10, min(200, int(s.get("quota_ram") or 50))))
        return False

    def lavora(argomenti, messaggio):
        stato_msg.set_text(messaggio)

        def worker():
            r = subprocess.run(["vesper-zram", *argomenti],
                               capture_output=True, text=True)
            uscita = (r.stdout + r.stderr).strip().splitlines()

            def fine():
                stato_msg.set_text(uscita[-1] if uscita else "")
                aggiorna()
                return False
            GLib.idle_add(fine)
        threading.Thread(target=worker, daemon=True).start()

    def on_on(_b):
        # L'accensione tocca la configurazione di sistema: si chiede conferma,
        # e i privilegi li chiede vesper-zram (doas/sudo/pkexec).
        d = Gtk.MessageDialog(transient_for=win, modal=True,
                              message_type=Gtk.MessageType.QUESTION,
                              buttons=Gtk.ButtonsType.OK_CANCEL,
                              text=_t("v.zram.confirm_q"))
        d.format_secondary_text(_t("v.zram.confirm_body")
                                % (int(quota.get_value()),
                                   algo.get_active_text() or "zstd"))
        r = d.run(); d.destroy()
        if r == Gtk.ResponseType.OK:
            lavora(["enable", str(int(quota.get_value())),
                    "--algo", algo.get_active_text() or "zstd"],
                   _t("v.zram.working"))

    def on_off(_b):
        lavora(["disable"], _t("v.zram.working"))

    b_on.connect("clicked", on_on)
    b_off.connect("clicked", on_off)
    barra = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    barra.pack_start(b_on, False, False, 0)
    barra.pack_start(b_off, False, False, 0)
    b_ref = icon_button(_t("v.refresh"), "view-refresh-symbolic")
    b_ref.connect("clicked", lambda _b: aggiorna())
    barra.pack_start(b_ref, False, False, 0)
    b_close = icon_button(_t("v.close"), "window-close")
    b_close.connect("clicked", lambda _b: win.destroy())
    barra.pack_end(b_close, False, False, 0)
    body.pack_end(barra, False, False, 0)

    aggiorna()
    win.show_all()


def open_statusbar(_btn=None):
    win, body = panel_window(_t("v.panel.bottom"), 540, 680)

    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    card.get_style_context().add_class("vesper-card")
    title = Gtk.Label(label=_t("v.panel.mate"))
    title.set_xalign(0)
    title.get_style_context().add_class("vesper-card-title")
    card.pack_start(title, False, False, 0)
    desc = Gtk.Label(label=(
        _t("v.panel_intro")))
    desc.set_xalign(0)
    desc.get_style_context().add_class("vesper-val")
    card.pack_start(desc, False, False, 0)
    body.pack_start(card, False, False, 0)

    # Posizione (basso / alto)
    frame_pos = Gtk.Frame(label=_t("v.position"))
    pbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    pbox.set_margin_top(8); pbox.set_margin_bottom(8)
    pbox.set_margin_start(10); pbox.set_margin_end(10)
    rb_bottom = Gtk.RadioButton.new_with_label_from_widget(None, _t("v.bottom"))
    rb_top = Gtk.RadioButton.new_with_label_from_widget(rb_bottom, _t("v.top"))
    if panelcfg.get_position() == "top":
        rb_top.set_active(True)
    pbox.pack_start(rb_bottom, False, False, 0)
    pbox.pack_start(rb_top, False, False, 0)
    b_applypos = Gtk.Button(label=_t("v.apply_pos"))
    b_applypos.get_style_context().add_class("vesper-primary")

    def apply_pos(_b):
        pos = "top" if rb_top.get_active() else "bottom"
        panelcfg.move_panel(pos)
        info_dialog(_t("v.panel_moved"),
                    _t("v.pos_applied")
                    % (_t("v.top_low") if pos == "top" else _t("v.bottom_low")), parent=win)
    b_applypos.connect("clicked", apply_pos)
    pbox.pack_end(b_applypos, False, False, 0)
    frame_pos.add(pbox)
    body.pack_start(frame_pos, False, False, 0)

    # Dimensioni: altezza barra + grandezza icone
    frame_dim = Gtk.Frame(label=_t("v.sizes"))
    dbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    dbox.set_margin_top(8); dbox.set_margin_bottom(8)
    dbox.set_margin_start(10); dbox.set_margin_end(10)

    r_h = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    l_h = Gtk.Label(label=_t("v.bar_height")); l_h.set_xalign(0)
    r_h.pack_start(l_h, True, True, 0)
    spin_h = Gtk.SpinButton.new_with_range(panelcfg.MIN_HEIGHT,
                                           panelcfg.MAX_HEIGHT, 1)
    spin_h.set_value(panelcfg.get_height())
    r_h.pack_end(spin_h, False, False, 0)
    dbox.pack_start(r_h, False, False, 0)

    r_i = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    l_i = Gtk.Label(label=_t("v.icon_size")); l_i.set_xalign(0)
    r_i.pack_start(l_i, True, True, 0)
    spin_i = Gtk.SpinButton.new_with_range(panelcfg.MIN_ICON_PX,
                                           panelcfg.MAX_ICON_PX, 1)
    spin_i.set_value(panelcfg.get_icon_px())
    r_i.pack_end(spin_i, False, False, 0)
    dbox.pack_start(r_i, False, False, 0)

    b_applydim = Gtk.Button(label=_t("v.apply_sizes"))
    b_applydim.get_style_context().add_class("vesper-primary")

    def apply_dim(_b):
        panelcfg.apply_layout(height=int(spin_h.get_value()),
                              icon_px=int(spin_i.get_value()))
        info_dialog(_t("v.bar_updated"),
                    _t("v.size_applied"), parent=win)
    b_applydim.connect("clicked", apply_dim)
    row_bd = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    row_bd.pack_end(b_applydim, False, False, 0)
    dbox.pack_start(row_bd, False, False, 0)
    frame_dim.add(dbox)
    body.pack_start(frame_dim, False, False, 0)

    # Desktop virtuali (workspaces)
    frame_ws = Gtk.Frame(label=_t("v.vdesktops"))
    wbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    wbox.set_margin_top(8); wbox.set_margin_bottom(8)
    wbox.set_margin_start(10); wbox.set_margin_end(10)
    l_ws = Gtk.Label(label=_t("v.ndesktops")); l_ws.set_xalign(0)
    wbox.pack_start(l_ws, True, True, 0)
    spin_ws = Gtk.SpinButton.new_with_range(panelcfg.MIN_DESKTOPS,
                                            panelcfg.MAX_DESKTOPS, 1)
    spin_ws.set_value(panelcfg.get_desktops())
    wbox.pack_start(spin_ws, False, False, 0)
    b_applyws = Gtk.Button(label=_t("v.apply"))
    b_applyws.get_style_context().add_class("vesper-primary")

    def apply_ws(_b):
        panelcfg.set_desktops(int(spin_ws.get_value()))
        info_dialog(_t("v.desktops_updated"),
                    _t("v.vdesk_info")
                    % int(spin_ws.get_value()), parent=win)
    b_applyws.connect("clicked", apply_ws)
    wbox.pack_end(b_applyws, False, False, 0)
    frame_ws.add(wbox)
    body.pack_start(frame_ws, False, False, 0)

    # Stato
    state = Gtk.Label()
    state.set_xalign(0)

    def refresh_state():
        running = _panel_running()
        state.set_markup(
            _t("v.state_running") % COL_ACCENT
            if running else
            _t("v.state_off") % COL_ALERT)
    refresh_state()
    body.pack_start(state, False, False, 4)

    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    b_restart = Gtk.Button(label=_t("v.restart_panel"))
    b_restart.get_style_context().add_class("vesper-primary")

    def do_restart(_b):
        _panel_restart()
        GLib.timeout_add(700, lambda: (refresh_state(), False)[1])
    b_restart.connect("clicked", do_restart)

    b_start = Gtk.Button(label=_t("v.start"))
    b_start.connect("clicked", lambda _b: (_panel_start(),
                    GLib.timeout_add(700, lambda: (refresh_state(), False)[1])))
    b_stop = Gtk.Button(label=_t("v.stop"))
    b_stop.connect("clicked", lambda _b: (_panel_stop(),
                   GLib.timeout_add(700, lambda: (refresh_state(), False)[1])))
    b_close = Gtk.Button(label=_t("v.close"))
    b_close.connect("clicked", lambda _b: win.destroy())
    bar.pack_start(b_restart, False, False, 0)
    bar.pack_start(b_start, False, False, 0)
    bar.pack_start(b_stop, False, False, 0)
    bar.pack_end(b_close, False, False, 0)
    body.pack_end(bar, False, False, 0)

    win.show_all()


# ---------------------------------------------------------------------------
# Openbox: temi finestra e menu tasto destro
# ---------------------------------------------------------------------------
RC_XML = HOME / ".config/openbox/rc.xml"
MENU_XML = HOME / ".config/openbox/menu.xml"
THEME_DIRS = [
    HOME / ".themes",
    HOME / ".local/share/themes",
    Path("/usr/local/share/themes"),
    Path("/usr/share/themes"),
]


def _ob_list_themes() -> list[str]:
    """Nomi dei temi Openbox installati (cartelle con openbox-3/themerc)."""
    found = set()
    for d in THEME_DIRS:
        try:
            for sub in d.iterdir():
                if (sub / "openbox-3" / "themerc").is_file():
                    found.add(sub.name)
        except OSError:
            pass
    return sorted(found)


def _ob_current_theme() -> str:
    try:
        m = re.search(r"<theme>.*?<name>([^<]+)</name>", RC_XML.read_text(),
                      re.DOTALL)
        if m:
            return m.group(1).strip()
    except OSError:
        pass
    return ""


def _ob_set_theme(name: str):
    try:
        txt = RC_XML.read_text()
    except OSError:
        return
    txt = re.sub(r"(<theme>.*?<name>)[^<]*(</name>)",
                 r"\g<1>" + name + r"\g<2>", txt, count=1, flags=re.DOTALL)
    RC_XML.write_text(txt)
    panelcfg.openbox_reconfigure()


def open_openbox_theme(_btn=None):
    print("[cc] ob-theme: start", flush=True)
    win, body = panel_window(_t("v.obtheme.title"), 480, 460)
    print("[cc] ob-theme: finestra creata", flush=True)

    lab = Gtk.Label(label=_t("v.obtheme_intro"))
    lab.set_xalign(0)
    lab.get_style_context().add_class("vesper-val")
    body.pack_start(lab, False, False, 0)

    store = Gtk.ListStore(str)
    tree = Gtk.TreeView(model=store)
    tree.set_headers_visible(False)
    col = Gtk.TreeViewColumn(_t("v.theme_col"), Gtk.CellRendererText(), text=0)
    tree.append_column(col)
    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    sw.add(tree)
    body.pack_start(sw, True, True, 0)

    def reload_store():
        cur = _ob_current_theme()
        store.clear()
        for t in _ob_list_themes():
            store.append([t + (_t("v.current_paren") if t == cur else "")])
    reload_store()

    def selected_theme():
        model, it = tree.get_selection().get_selected()
        if it is None:
            return None
        return model[it][0].split("   ")[0].strip()

    def apply(_w=None, *_a):
        name = selected_theme()
        if not name:
            return
        _ob_set_theme(name)
        reload_store()
        info_dialog(_t("v.theme_applied"), _t("v.ob_theme_set") % name, parent=win)

    tree.connect("row-activated", apply)

    # --- installazione tema da archivio (tar.gz/xz/bz2, .obt, .zip) -----------
    def _safe_extract(arch, dest):
        import tarfile
        import zipfile
        if arch.lower().endswith(".zip"):
            with zipfile.ZipFile(arch) as z:
                for m in z.namelist():
                    if m.startswith("/") or ".." in m.split("/"):
                        raise ValueError(_t("v.unsafe_path"))
                z.extractall(dest)
        else:
            with tarfile.open(arch) as t:
                try:
                    t.extractall(dest, filter="data")   # Python >= 3.12
                except TypeError:
                    for m in t.getmembers():
                        if m.name.startswith("/") or ".." in m.name.split("/"):
                            raise ValueError(_t("v.unsafe_path"))
                    t.extractall(dest)

    def install_theme(_b=None):
        dlg = Gtk.FileChooserDialog(
            title=_t("v.install_ob_theme"), transient_for=win,
            action=Gtk.FileChooserAction.OPEN)
        dlg.add_button(_t("v.cancel"), Gtk.ResponseType.CANCEL)
        dlg.add_button(_t("v.install"), Gtk.ResponseType.OK)
        flt = Gtk.FileFilter(); flt.set_name(_t("v.theme_archives"))
        for pat in ("*.tar.gz", "*.tgz", "*.tar.xz", "*.tar.bz2", "*.obt", "*.zip"):
            flt.add_pattern(pat)
        dlg.add_filter(flt)
        arch = dlg.get_filename() if dlg.run() == Gtk.ResponseType.OK else None
        dlg.destroy()
        if not arch:
            return
        import tempfile
        tmp = tempfile.mkdtemp(prefix="vesper-theme-")
        try:
            _safe_extract(arch, tmp)
            # trova la cartella del tema (quella che contiene openbox-3/themerc)
            root = None
            for dp, _dn, fn in os.walk(tmp):
                if os.path.basename(dp) == "openbox-3" and "themerc" in fn:
                    root = os.path.dirname(dp)
                    break
            if not root:
                info_dialog(_t("v.not_ob_theme"),
                            _t("v.archive_no_themerc"),
                            parent=win)
                return
            name = os.path.basename(root)
            themes_dir = os.path.expanduser("~/.themes")
            os.makedirs(themes_dir, exist_ok=True)
            dest = os.path.join(themes_dir, name)
            if os.path.exists(dest):
                shutil.rmtree(dest, ignore_errors=True)
            shutil.move(root, dest)
            reload_store()
            info_dialog(_t("v.theme_installed"),
                        _t("v.theme_installed_pick") % name,
                        parent=win)
        except Exception as e:                       # noqa: BLE001
            info_dialog(_t("v.install_failed"), str(e), parent=win)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def delete_theme(_b=None):
        name = selected_theme()
        if not name:
            return
        if name == "Vesper-Core":
            info_dialog(_t("v.not_removable"),
                        _t("v.core_default"),
                        parent=win)
            return
        # eliminabile solo dalle cartelle utente (non i temi di sistema)
        target = None
        for d in (HOME / ".themes", HOME / ".local/share/themes"):
            p = d / name
            if (p / "openbox-3" / "themerc").is_file():
                target = p
                break
        if target is None:
            info_dialog(_t("v.system_theme"),
                        _t("v.theme_sys_noremove") % name, parent=win)
            return
        conf = Gtk.MessageDialog(
            transient_for=win, modal=True, message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=_t("v.delete_theme_q") % name)
        do = conf.run() == Gtk.ResponseType.OK
        conf.destroy()
        if not do:
            return
        try:
            if _ob_current_theme() == name:
                _ob_set_theme("Vesper-Core")   # torna al default se era attivo
            shutil.rmtree(target, ignore_errors=True)
            reload_store()
        except Exception as e:                       # noqa: BLE001
            info_dialog(_t("v.remove_failed"), str(e), parent=win)

    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    b_apply = Gtk.Button(label=_t("v.apply"))
    b_apply.get_style_context().add_class("vesper-primary")
    b_apply.connect("clicked", apply)
    bar.pack_start(b_apply, False, False, 0)
    b_inst = Gtk.Button(label=_t("v.install_theme"))
    b_inst.connect("clicked", install_theme)
    bar.pack_start(b_inst, False, False, 0)
    b_del = Gtk.Button(label=_t("v.delete"))
    b_del.connect("clicked", delete_theme)
    bar.pack_start(b_del, False, False, 0)
    if have("obconf"):
        b_adv = Gtk.Button(label=_t("v.advanced_obconf"))
        b_adv.connect("clicked", lambda _b: run_bg(["obconf"]))
        bar.pack_start(b_adv, False, False, 0)
    b_close = Gtk.Button(label=_t("v.close"))
    b_close.connect("clicked", lambda _b: win.destroy())
    bar.pack_end(b_close, False, False, 0)
    body.pack_end(bar, False, False, 0)

    print("[cc] ob-theme: prima di show_all", flush=True)
    win.show_all()
    print("[cc] ob-theme: show_all OK", flush=True)


def open_menu_editor(_btn=None):
    # Versione autonoma e strumentata (i print con flush localizzano un
    # eventuale crash nativo in /tmp/vesper-cc.log).
    print("[cc] menu-editor: start", flush=True)
    win, body = panel_window(_t("v.menu.title"), 760, 560)
    print("[cc] menu-editor: finestra creata", flush=True)
    tv = Gtk.TextView()
    tv.set_monospace(True)
    tv.set_left_margin(8)
    tv.set_top_margin(6)
    txt = read_file(MENU_XML)
    print("[cc] menu-editor: letto menu.xml (%d bytes)" % len(txt), flush=True)
    tv.get_buffer().set_text(txt)
    print("[cc] menu-editor: buffer impostato", flush=True)
    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    sw.add(tv)
    body.pack_start(sw, True, True, 0)

    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    b_save = Gtk.Button(label=_t("v.menu.save_reload"))
    b_save.get_style_context().add_class("vesper-primary")

    def save(_b):
        try:
            buf = tv.get_buffer()
            s, e = buf.get_bounds()
            MENU_XML.write_text(buf.get_text(s, e, False))
            panelcfg.openbox_reconfigure()
            info_dialog(_t("v.saved"), _t("v.menu_updated"),
                        parent=win)
        except Exception as err:                       # noqa: BLE001
            info_dialog(_t("v.error"), str(err), level="error", parent=win)

    b_save.connect("clicked", save)
    b_close = Gtk.Button(label=_t("v.close"))
    b_close.connect("clicked", lambda _b: win.destroy())
    bar.pack_start(b_save, False, False, 0)
    bar.pack_end(b_close, False, False, 0)
    body.pack_end(bar, False, False, 0)

    print("[cc] menu-editor: prima di show_all", flush=True)
    win.show_all()
    print("[cc] menu-editor: show_all OK", flush=True)


# ---------------------------------------------------------------------------
# Editor di testo (autostart, rc.xml)
# ---------------------------------------------------------------------------
def open_text_editor(title: str, path: Path, on_save=None):
    win, body = panel_window(title, 760, 560)
    tv = Gtk.TextView()
    tv.set_monospace(True)
    tv.set_left_margin(8); tv.set_top_margin(6)
    tv.get_buffer().set_text(read_file(path))
    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    sw.add(tv)
    body.pack_start(sw, True, True, 0)

    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    b_save = Gtk.Button(label=_t("v.save"))
    b_save.get_style_context().add_class("vesper-primary")

    def save(_b):
        buf = tv.get_buffer()
        s, e = buf.get_bounds()
        try:
            Path(path).write_text(buf.get_text(s, e, False))
            if on_save is not None:
                on_save()
            info_dialog(_t("v.saved"), f"Scritto: {path}", parent=win)
        except OSError as err:
            info_dialog(_t("v.error"), str(err), level="error", parent=win)

    b_save.connect("clicked", save)
    b_close = Gtk.Button(label=_t("v.close"))
    b_close.connect("clicked", lambda _b: win.destroy())
    bar.pack_start(b_save, False, False, 0)
    bar.pack_end(b_close, False, False, 0)
    body.pack_end(bar, False, False, 0)
    win.show_all()


AUTOSTART = HOME / ".config/openbox/autostart"
_AS_BEGIN = "# >>> Vesper autostart utente (Centro di Controllo)"
_AS_END = "# <<< Vesper autostart utente"


def _autostart_read_user():
    """Legge le voci utente nel blocco delimitato: lista di (abilitato, cmd)."""
    entries = []
    try:
        lines = AUTOSTART.read_text().splitlines()
    except OSError:
        return entries
    inside = False
    for ln in lines:
        s = ln.strip()
        if s == _AS_BEGIN:
            inside = True
            continue
        if s == _AS_END:
            break
        if not inside or not s:
            continue
        enabled = True
        cmd = s
        if cmd.startswith("#"):
            enabled = False
            cmd = cmd.lstrip("#").strip()
        if cmd.endswith("&"):
            cmd = cmd[:-1].strip()
        if cmd:
            entries.append((enabled, cmd))
    return entries


def _autostart_write_user(entries):
    """Riscrive SOLO il blocco utente, preservando il resto dell'autostart."""
    block = [_AS_BEGIN]
    for enabled, cmd in entries:
        cmd = cmd.strip()
        if not cmd:
            continue
        line = "%s &" % cmd
        block.append(line if enabled else "# " + line)
    block.append(_AS_END)
    block_txt = "\n".join(block)

    try:
        txt = AUTOSTART.read_text()
    except OSError:
        txt = "#!/bin/sh\n"
    if _AS_BEGIN in txt and _AS_END in txt:
        pat = re.compile(re.escape(_AS_BEGIN) + r".*?" + re.escape(_AS_END),
                         re.DOTALL)
        txt = pat.sub(block_txt, txt, count=1)
    else:
        if not txt.endswith("\n"):
            txt += "\n"
        txt += "\n" + block_txt + "\n"
    AUTOSTART.write_text(txt)


def open_autostart(_btn=None):
    print("[cc] autostart: start", flush=True)
    win, body = panel_window(_t("v.autostart.title"), 660, 480)

    intro = Gtk.Label(label=(
        _t("v.autostart_intro")))
    intro.set_xalign(0)
    intro.set_line_wrap(True)
    intro.get_style_context().add_class("vesper-val")
    body.pack_start(intro, False, False, 0)

    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    listbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    listbox.set_margin_top(4)
    sw.add(listbox)
    body.pack_start(sw, True, True, 0)

    rows = []

    def add_row(enabled=True, cmd=""):
        rb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        chk = Gtk.CheckButton()
        chk.set_active(enabled)
        chk.set_tooltip_text(_t("v.autostart.enabled"))
        ent = Gtk.Entry()
        ent.set_text(cmd)
        ent.set_hexpand(True)
        ent.set_placeholder_text(_t("v.autostart.cmd_ph"))
        rm = Gtk.Button(label="−")     # segno meno
        rm.set_tooltip_text(_t("v.autostart.remove_row"))
        rb.pack_start(chk, False, False, 0)
        rb.pack_start(ent, True, True, 0)
        rb.pack_start(rm, False, False, 0)
        listbox.pack_start(rb, False, False, 0)
        entry = {"chk": chk, "ent": ent, "box": rb}

        def remove(_b):
            listbox.remove(rb)
            if entry in rows:
                rows.remove(entry)
        rm.connect("clicked", remove)
        rows.append(entry)
        rb.show_all()

    for en, cmd in _autostart_read_user():
        add_row(en, cmd)
    if not rows:
        add_row(True, "")

    bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    b_add = Gtk.Button(label=_t("v.add"))
    b_add.connect("clicked", lambda _b: add_row(True, ""))
    b_save = Gtk.Button(label=_t("v.save"))
    b_save.get_style_context().add_class("vesper-primary")

    def save(_b):
        ents = [(r["chk"].get_active(), r["ent"].get_text().strip())
                for r in rows if r["ent"].get_text().strip()]
        try:
            _autostart_write_user(ents)
            info_dialog(_t("v.saved"),
                        _t("v.autostart_saved")
                        % AUTOSTART, parent=win)
        except OSError as e:
            info_dialog(_t("v.error"), str(e), level="error", parent=win)

    b_save.connect("clicked", save)
    b_raw = Gtk.Button(label=_t("v.autostart.edit_raw"))
    b_raw.connect("clicked",
                  lambda _b: open_text_editor(_t("v.autostart_advanced"), AUTOSTART))
    b_close = Gtk.Button(label=_t("v.close"))
    b_close.connect("clicked", lambda _b: win.destroy())
    bar.pack_start(b_add, False, False, 0)
    bar.pack_start(b_save, False, False, 0)
    bar.pack_start(b_raw, False, False, 0)
    bar.pack_end(b_close, False, False, 0)
    body.pack_end(bar, False, False, 0)

    print("[cc] autostart: prima di show_all", flush=True)
    win.show_all()
    print("[cc] autostart: show_all OK", flush=True)


# ---------------------------------------------------------------------------
# Log di sistema (viewer a schede)
# ---------------------------------------------------------------------------
def open_logs(_btn=None):
    win, body = panel_window(_t("v.logs.title"), 820, 560)
    nb = Gtk.Notebook()
    body.pack_start(nb, True, True, 0)
    sources = [
        ("autostart", "/tmp/vesper-autostart.log"),
        ("pannello", "/tmp/vesper-panel.log"),
        ("Xorg", os.path.expanduser("~/.local/share/xorg/Xorg.0.log")),
        ("boot", "/var/log/vesper-boot.log"),
    ]
    for label, path in sources:
        sw = Gtk.ScrolledWindow()
        tv = Gtk.TextView()
        tv.set_editable(False); tv.set_monospace(True); tv.set_left_margin(6)
        tv.get_buffer().set_text(read_file(path))
        sw.add(tv)
        nb.append_page(sw, Gtk.Label(label=label))
    win.show_all()


# ---------------------------------------------------------------------------
# Aspetto: tema GTK (lxappearance) e wallpaper
# ---------------------------------------------------------------------------
def _gtk_themes() -> list[str]:
    """Temi GTK installati (cartelle con gtk-3.0/gtk.css o gtk-2.0/gtkrc)."""
    seen, out = set(), []
    for d in (HOME / ".themes", HOME / ".local" / "share" / "themes",
              Path("/usr/share/themes"), Path("/usr/local/share/themes")):
        try:
            entries = sorted(d.iterdir())
        except OSError:
            continue
        for e in entries:
            if e.name in seen:
                continue
            if (e / "gtk-3.0" / "gtk.css").is_file() or (e / "gtk-2.0" / "gtkrc").is_file():
                seen.add(e.name)
                out.append(e.name)
    return out


def _gtk_setting(key: str, default: str = "") -> str:
    """Valore corrente di una chiave in ~/.config/gtk-3.0/settings.ini."""
    try:
        for ln in (HOME / ".config" / "gtk-3.0" / "settings.ini").read_text().splitlines():
            if ln.strip().startswith(key):
                return ln.split("=", 1)[1].strip()
    except (OSError, IndexError):
        pass
    return default


def _set_gtk_theme(name: str) -> None:
    """Applica il tema GTK a GTK3 e GTK2 (scrittura atomica: vedi model)."""
    from vesper.profiles import model as _m
    _m.gtk3_set("gtk-theme-name", name)          # settings.ini, con [Settings]
    _m._replace_line(HOME / ".gtkrc-2.0",
                     "gtk-theme-name", 'gtk-theme-name="%s"' % name)


def open_gtk_theme(_btn=None):
    """Tema GTK (aspetto interno delle app) e SET DI ICONE.

    Le icone possono seguire il preset — ogni preset indica i temi del proprio
    colore (Mint-Y e simili) e si usa il primo installato — oppure si può
    fissarne uno. Tutto si applica a caldo: le app GTK rileggono settings.ini
    da sole, senza riavviare la sessione.
    """
    from vesper.profiles import model as _m
    win, body = panel_window(_t("v.gtk.title"), 620, 620)

    intro = Gtk.Label(label=_t("v.gtk_intro"))
    intro.set_xalign(0)
    intro.set_line_wrap(True)
    intro.get_style_context().add_class("vesper-val")
    body.pack_start(intro, False, False, 0)

    # --- set di icone ---
    h1 = Gtk.Label(label=_t("v.gtk.icons"))
    h1.set_xalign(0)
    h1.get_style_context().add_class("vesper-section")
    body.pack_start(h1, False, False, 0)

    auto_label = _t("v.gtk.icons_auto") % _m.icon_theme_name()
    icon_combo = Gtk.ComboBoxText()
    icon_combo.append("auto", auto_label)
    themes = _m.available_icon_themes()
    for name in themes:
        icon_combo.append(name, name)
    icon_combo.set_active_id(_m.get_icon_choice() if _m.get_icon_choice() in
                             (["auto"] + themes) else "auto")
    body.pack_start(icon_combo, False, False, 0)

    icon_status = Gtk.Label(label="")
    icon_status.set_xalign(0)
    icon_status.get_style_context().add_class("vesper-val")
    body.pack_start(icon_status, False, False, 0)

    # anteprima: alcune icone comuni nel tema selezionato
    prev = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    prev.get_style_context().add_class("vesper-card")
    body.pack_start(prev, False, False, 0)

    def refresh_preview(theme_name):
        for ch in prev.get_children():
            prev.remove(ch)
        try:
            th = Gtk.IconTheme.new()
            th.set_custom_theme(theme_name)
        except Exception:                    # noqa: BLE001
            return
        for n in ("folder", "user-home", "text-x-generic", "applications-internet",
                  "utilities-terminal", "preferences-system"):
            try:
                pb = th.load_icon(n, 32, Gtk.IconLookupFlags.FORCE_SIZE)
                prev.pack_start(Gtk.Image.new_from_pixbuf(pb), False, False, 0)
            except Exception:                # noqa: BLE001
                continue
        prev.show_all()

    def icon_changed(combo):
        choice = combo.get_active_id() or "auto"
        applied = _m.set_icon_choice(choice)
        icon_status.set_text(_t("v.gtk.icons_set") % applied)
        refresh_preview(applied)
    refresh_preview(_m.icon_theme_name())
    icon_combo.connect("changed", icon_changed)   # connesso DOPO set_active_id

    # --- tema GTK ---
    h2 = Gtk.Label(label=_t("v.gtk.theme"))
    h2.set_xalign(0)
    h2.get_style_context().add_class("vesper-section")
    body.pack_start(h2, False, False, 0)

    gtk_combo = Gtk.ComboBoxText()
    gtk_themes = _gtk_themes()
    for name in gtk_themes:
        gtk_combo.append(name, name)
    cur_gtk = _gtk_setting("gtk-theme-name", "Adwaita")
    if cur_gtk in gtk_themes:
        gtk_combo.set_active_id(cur_gtk)
    body.pack_start(gtk_combo, False, False, 0)

    gtk_status = Gtk.Label(label="")
    gtk_status.set_xalign(0)
    gtk_status.get_style_context().add_class("vesper-val")
    body.pack_start(gtk_status, False, False, 0)

    def gtk_changed(combo):
        name = combo.get_active_id()
        if not name:
            return
        _set_gtk_theme(name)
        gtk_status.set_text(_t("v.gtk.theme_set") % name)
    gtk_combo.connect("changed", gtk_changed)     # connesso DOPO set_active_id

    note = Gtk.Label(label=_t("v.gtk.note"))
    note.set_xalign(0)
    note.set_line_wrap(True)
    note.get_style_context().add_class("vesper-val")
    body.pack_start(note, False, False, 0)

    # --- strumento esterno, se c'è ---
    btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    if have("lxappearance"):
        b_lx = icon_button(_t("v.gtk.lxappearance"), "preferences-desktop-theme")
        b_lx.connect("clicked", lambda _b: run_bg(["lxappearance"]))
        btns.pack_start(b_lx, False, False, 0)
    b_close = icon_button(_t("v.close"), "window-close")
    b_close.connect("clicked", lambda _b: win.destroy())
    btns.pack_end(b_close, False, False, 0)
    body.pack_end(btns, False, False, 0)

    win.show_all()


def open_wallpaper(_btn=None):
    """Selettore SFONDO con anteprime: sfondi abbinati alle skin del pannello +
    sfondi dei profili + file personale. E' una scelta SEPARATA e indipendente
    (voce a se': non cambia con profilo/skin) e persiste finche' non si preme
    «Torna allo sfondo del profilo». Applica via `vesper-wallpaper` (override)."""
    win, body = panel_window(_t("v.wallpaper.title"), 680, 600)
    from gi.repository import GdkPixbuf

    intro = Gtk.Label(label=_t("v.wall_intro"))
    intro.set_xalign(0); intro.set_line_wrap(True)
    intro.get_style_context().add_class("vesper-val")
    body.pack_start(intro, False, False, 0)

    status = Gtk.Label(label=""); status.set_xalign(0)
    status.get_style_context().add_class("vesper-val")

    def apply_wp(path):
        try:
            subprocess.run(["vesper-wallpaper", "set", str(path)])
            status.set_text(_t("v.wall_set") % os.path.basename(str(path)))
        except OSError:
            status.set_text(_t("v.wall_fail"))

    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    flow = Gtk.FlowBox()
    flow.set_selection_mode(Gtk.SelectionMode.NONE)
    flow.set_max_children_per_line(3)
    flow.set_homogeneous(True)
    flow.set_margin_top(6); flow.set_margin_bottom(6)
    scroll.add(flow)
    body.pack_start(scroll, True, True, 0)

    def add_thumb(path, label):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), 192, 108, False)
            img = Gtk.Image.new_from_pixbuf(pb)
        except Exception:                       # noqa: BLE001
            img = Gtk.Image.new_from_icon_name("image-x-generic", Gtk.IconSize.DIALOG)
        btn = Gtk.Button(); btn.add(img)
        btn.connect("clicked", lambda _b, p=path: apply_wp(p))
        card.pack_start(btn, False, False, 0)
        lab = Gtk.Label(label=label); lab.set_xalign(0.5)
        lab.get_style_context().add_class("vesper-val")
        card.pack_start(lab, False, False, 0)
        flow.add(card)

    from pathlib import Path as _P
    skin_dir = _P("/usr/share/vesper/wallpapers")
    if skin_dir.is_dir():
        for f in sorted(skin_dir.glob("skin-*.png")):
            add_thumb(f, _t("v.skin_prefix") + f.stem[5:])
    # Sfondi di serie: cartelle dati di Vesper (installate o dal repo)
    prof_dir = None
    try:
        from vesper import paths as _paths
        _dirs = _paths.data_dirs("backgrounds")
        prof_dir = _dirs[0] if _dirs else None
    except Exception:                    # noqa: BLE001
        prof_dir = None
    if prof_dir.is_dir():
        for f in sorted(prof_dir.glob("*.png")):
            add_thumb(f, _t("v.profile_prefix") + f.stem)

    body.pack_start(status, False, False, 0)

    btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    b_reset = icon_button(_t("v.wall_back_profile"), "view-refresh-symbolic")

    def do_reset(_b):
        try:
            subprocess.run(["vesper-wallpaper", "reset"])
            status.set_text(_t("v.wall_is_profile"))
        except OSError:
            pass
    b_reset.connect("clicked", do_reset)
    b_file = icon_button(_t("v.personal_file"), "document-open")

    def pick_file(_b):
        dlg = Gtk.FileChooserDialog(title=_t("v.choose_wall"),
                                    action=Gtk.FileChooserAction.OPEN, modal=True)
        dlg.add_button(_t("v.cancel"), Gtk.ResponseType.CANCEL)
        dlg.add_button(_t("v.set"), Gtk.ResponseType.ACCEPT)
        flt = Gtk.FileFilter(); flt.set_name(_t("v.images"))
        flt.add_mime_type("image/png"); flt.add_mime_type("image/jpeg")
        dlg.add_filter(flt)
        if prof_dir.is_dir():
            dlg.set_current_folder(str(prof_dir))
        if dlg.run() == Gtk.ResponseType.ACCEPT:
            apply_wp(dlg.get_filename())
        dlg.destroy()
    b_file.connect("clicked", pick_file)
    b_close = icon_button(_t("v.close"), "window-close")
    b_close.connect("clicked", lambda _b: win.destroy())
    btns.pack_start(b_reset, False, False, 0)
    btns.pack_start(b_file, False, False, 0)
    btns.pack_end(b_close, False, False, 0)
    body.pack_end(btns, False, False, 0)

    win.show_all()


# ---------------------------------------------------------------------------
# Tastiera
# ---------------------------------------------------------------------------
def open_keyboard(_btn=None):
    win, body = panel_window(_t("v.keyboard.title"), 480, 420)
    info = Gtk.Label(label=_t("v.kbd_desc"))
    info.set_xalign(0)
    info.get_style_context().add_class("vesper-val")
    body.pack_start(info, False, False, 0)

    def set_layout(name):
        if name == "it" and (HOME / ".Xmodmap-it").exists():
            subprocess.Popen(["xmodmap", str(HOME / ".Xmodmap-it")])
            info_dialog(_t("v.layout"), _t("v.kbd_set_it"), parent=win)
        else:
            subprocess.Popen(["sh", "-c", "setxkbmap us 2>/dev/null || true"])
            info_dialog(_t("v.layout"), _t("v.kbd_set_us"), parent=win)

    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    b_it = icon_button(_t("v.italian"), "preferences-desktop-locale")
    b_it.connect("clicked", lambda _b: set_layout("it"))
    b_us = icon_button("US", "preferences-desktop-keyboard")
    b_us.connect("clicked", lambda _b: set_layout("us"))
    row.pack_start(b_it, False, False, 0)
    row.pack_start(b_us, False, False, 0)
    body.pack_start(row, False, False, 0)

    # --- Prova tastiera: verifica caratteri e corrispondenze dei tasti -----
    frame = Gtk.Frame(label=_t("v.kbd_test"))
    fbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    fbox.set_margin_top(8); fbox.set_margin_bottom(8)
    fbox.set_margin_start(8); fbox.set_margin_end(8)
    frame.add(fbox)

    hint = Gtk.Label(
        label=_t("v.kbd_test_hint"))
    hint.set_xalign(0)
    fbox.pack_start(hint, False, False, 0)

    entry = Gtk.Entry()
    entry.set_placeholder_text(_t("v.kbd_test_ph"))
    fbox.pack_start(entry, False, False, 0)

    detail = Gtk.Label(label=_t("v.kbd_press"))
    detail.set_xalign(0)
    detail.set_selectable(True)
    detail.get_style_context().add_class("vesper-key")
    fbox.pack_start(detail, False, False, 0)

    def on_key(_w, ev):
        name = Gdk.keyval_name(ev.keyval) or "?"
        uni = Gdk.keyval_to_unicode(ev.keyval)
        ch = chr(uni) if uni and uni >= 32 else ""
        mods = []
        if ev.state & Gdk.ModifierType.CONTROL_MASK: mods.append("Ctrl")
        if ev.state & Gdk.ModifierType.MOD1_MASK:    mods.append("Alt")
        if ev.state & Gdk.ModifierType.SHIFT_MASK:   mods.append("Shift")
        if ev.state & Gdk.ModifierType.MOD4_MASK:    mods.append("Super")
        modstr = " + ".join(mods + [name]) if mods else name
        car = f"  carattere: '{ch}'" if ch else ""
        detail.set_text(
            f"tasto: {modstr}   keysym: {name}   keycode: {ev.hardware_keycode}{car}")
        return False  # lascia che l'entry riceva comunque il tasto

    entry.connect("key-press-event", on_key)
    body.pack_start(frame, True, True, 0)

    b_close = icon_button(_t("v.close"), "window-close")
    b_close.connect("clicked", lambda _b: win.destroy())
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    box.pack_end(b_close, False, False, 0)
    body.pack_end(box, False, False, 0)
    win.show_all()
    entry.grab_focus()


# ---------------------------------------------------------------------------
# Salvaschermo (vesper-screensaver + xautolock)
# ---------------------------------------------------------------------------
SS_CONF = HOME / ".config" / "vesper" / "screensaver.conf"


def _ss_styles():
    # Costruita a runtime (non a import-time): il demone caldo importa il modulo
    # una volta, quindi le etichette tradotte vanno risolte all'apertura vista.
    return [("nebula", _t("v.ss.nebula")),
            ("matrix", _t("v.ss.matrix")),
            ("starfield", _t("v.ss.stars")),
            ("aurora", _t("v.ss.aurora")),
            ("grid", _t("v.ss.synthwave")),
            ("hexpulse", _t("v.ss.honeycomb")),
            ("orbits", _t("v.ss.orbits")),
            ("logo", _t("v.ss.logo"))]


def _ss_read():
    cfg = {"enabled": "1", "timeout": "5", "style": "nebula", "lock": "0"}
    try:
        for line in SS_CONF.read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    except OSError:
        pass
    return cfg


def _ss_write(cfg):
    SS_CONF.parent.mkdir(parents=True, exist_ok=True)
    SS_CONF.write_text("enabled=%s\ntimeout=%s\nstyle=%s\nlock=%s\n" % (
        cfg.get("enabled", "1"), cfg.get("timeout", "5"),
        cfg.get("style", "nebula"), cfg.get("lock", "0")))


def open_screensaver(_btn=None):
    win, body = panel_window(_t("v.screensaver.title"), 540, 640)
    cfg = _ss_read()

    intro = Gtk.Label(label=_t("v.ss_intro"))
    intro.set_xalign(0); intro.set_line_wrap(True)
    intro.get_style_context().add_class("vesper-val")
    body.pack_start(intro, False, False, 0)

    # Attivazione
    row_en = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    lab_en = Gtk.Label(label=_t("v.ss_enable"))
    lab_en.set_xalign(0); lab_en.get_style_context().add_class("vesper-key")
    row_en.pack_start(lab_en, True, True, 0)
    sw = Gtk.Switch(); sw.set_valign(Gtk.Align.CENTER)
    sw.set_active(cfg.get("enabled", "1") != "0")
    row_en.pack_end(sw, False, False, 0)
    body.pack_start(row_en, False, False, 0)

    # Timeout
    row_to = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    lab_to = Gtk.Label(label=_t("v.ss_after"))
    lab_to.set_xalign(0); lab_to.get_style_context().add_class("vesper-key")
    row_to.pack_start(lab_to, True, True, 0)
    try:
        to_val = int(cfg.get("timeout", "5"))
    except ValueError:
        to_val = 5
    spin = Gtk.SpinButton.new_with_range(1, 120, 1)
    spin.set_value(max(1, min(120, to_val)))
    row_to.pack_end(spin, False, False, 0)
    body.pack_start(row_to, False, False, 0)

    # Stile
    row_st = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    lab_st = Gtk.Label(label=_t("v.style"))
    lab_st.set_xalign(0); lab_st.get_style_context().add_class("vesper-key")
    row_st.pack_start(lab_st, True, True, 0)
    combo = Gtk.ComboBoxText()
    _styles = _ss_styles()
    for key, desc in _styles:
        combo.append(key, desc)
    combo.set_active_id(cfg.get("style", "nebula")
                        if cfg.get("style", "nebula") in dict(_styles) else "nebula")
    row_st.pack_end(combo, False, False, 0)
    body.pack_start(row_st, False, False, 0)

    # --- Blocco schermo con password ---
    sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
    body.pack_start(sep, False, False, 4)
    lock_head = Gtk.Label(); lock_head.set_markup(_t("v.lock_hdr"))
    lock_head.set_xalign(0)
    body.pack_start(lock_head, False, False, 0)

    try:
        from vesper.screensaver import secret as _sssecret
    except Exception:                       # noqa: BLE001
        _sssecret = None

    row_lock = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    lab_lock = Gtk.Label(label=_t("v.lock_ask_pw"))
    lab_lock.set_xalign(0); lab_lock.get_style_context().add_class("vesper-key")
    row_lock.pack_start(lab_lock, True, True, 0)
    lock_sw = Gtk.Switch(); lock_sw.set_valign(Gtk.Align.CENTER)
    lock_sw.set_active(cfg.get("lock", "0") == "1")
    row_lock.pack_end(lock_sw, False, False, 0)
    body.pack_start(row_lock, False, False, 0)

    pw_state = Gtk.Label(); pw_state.set_xalign(0)
    pw_state.get_style_context().add_class("vesper-val")
    body.pack_start(pw_state, False, False, 0)

    def _refresh_pw_state():
        if _sssecret is None:
            pw_state.set_text(_t("v.pw_mod_na"))
        elif _sssecret.has_password():
            pw_state.set_text(_t("v.pw_set"))
        else:
            pw_state.set_text(_t("v.no_pw_set"))
    _refresh_pw_state()

    row_pw = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    pw_entry = Gtk.Entry(); pw_entry.set_visibility(False)
    pw_entry.set_placeholder_text(_t("v.new_password"))
    pw_entry.set_hexpand(True)
    pw_entry.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY,
                                     "view-reveal-symbolic")

    def _eye(entry, _pos, _ev):
        vis = not entry.get_visibility()
        entry.set_visibility(vis)
        entry.set_icon_from_icon_name(
            Gtk.EntryIconPosition.SECONDARY,
            "view-conceal-symbolic" if vis else "view-reveal-symbolic")
    pw_entry.connect("icon-press", _eye)
    row_pw.pack_start(pw_entry, True, True, 0)
    b_setpw = icon_button(_t("v.set"), "emblem-ok")
    b_delpw = icon_button(_t("v.remove"), "user-trash-symbolic")
    row_pw.pack_start(b_setpw, False, False, 0)
    row_pw.pack_start(b_delpw, False, False, 0)
    body.pack_start(row_pw, False, False, 0)

    def _do_setpw(_b=None):
        if _sssecret is None:
            return
        pw = pw_entry.get_text()
        if len(pw) < 4:
            pw_state.set_text(_t("v.pw_min4"))
            return
        _sssecret.set_password(pw)
        pw_entry.set_text("")
        _refresh_pw_state()
    b_setpw.connect("clicked", _do_setpw)

    def _do_delpw(_b=None):
        if _sssecret is None:
            return
        _sssecret.clear_password()
        lock_sw.set_active(False)
        _refresh_pw_state()
    b_delpw.connect("clicked", _do_delpw)

    status = Gtk.Label(label=""); status.set_xalign(0)
    status.get_style_context().add_class("vesper-val")
    body.pack_start(status, False, False, 0)

    def collect():
        want_lock = lock_sw.get_active()
        # non attivare il lock senza una password impostata
        if want_lock and (_sssecret is None or not _sssecret.has_password()):
            want_lock = False
            lock_sw.set_active(False)
            pw_state.set_text(_t("v.pw_first"))
        return {"enabled": "1" if sw.get_active() else "0",
                "timeout": str(int(spin.get_value())),
                "style": combo.get_active_id() or "nebula",
                "lock": "1" if want_lock else "0"}

    def do_save(_b=None):
        c = collect()
        _ss_write(c)
        run_bg(["vesper-screensaver-idle", "restart"])
        status.set_text(_t("v.settings_saved_applied"))

    # Pulsanti
    btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    b_try = icon_button(_t("v.try_now"), "media-playback-start")
    b_try.connect("clicked", lambda _b: run_bg(
        ["vesper-screensaver", combo.get_active_id() or "nebula"]))
    b_save = icon_button(_t("v.save_apply"), "emblem-ok", primary=True)
    b_save.connect("clicked", do_save)
    b_close = icon_button(_t("v.close"), "window-close")
    b_close.connect("clicked", lambda _b: win.destroy())
    btns.pack_start(b_try, False, False, 0)
    btns.pack_end(b_close, False, False, 0)
    btns.pack_end(b_save, False, False, 0)
    body.pack_end(btns, False, False, 0)

    win.show_all()



# ---------------------------------------------------------------------------
# Mouse e touchpad: taratura del doppio clic
# ---------------------------------------------------------------------------
# CAUSA A MONTE che questa vista risolve: GTK riconosce il doppio clic solo se
# i due clic arrivano entro un TEMPO e restano entro una DISTANZA. I default
# (400 ms, 5 px) sono tarati sul mouse, dove il puntatore non si sposta di un
# pixel fra i due clic. Col dito sul touchpad la distanza e' il vincolo che
# salta per primo, ed e' il motivo per cui un doppio tap VELOCE fallisce mentre
# uno lento - piu' deliberato, quindi piu' preciso - riesce.
#
# Il tempo NON va allungato a caso: piu' e' lungo, piu' il sistema ASPETTA
# prima di concludere che era un clic singolo, e i clic singoli sembrano lenti.
# Per questo qui si regolano entrambi, e c'e' una zona di prova per tararli.
def _dc_tempi():
    return [(_t("v.spd.vfast"), 300), (_t("v.spd.fast"), 450), (_t("v.spd.normal"), 600),
            (_t("v.spd.slow"), 800), (_t("v.spd.vslow"), 1000)]


def _dc_dist():
    return [(_t("v.tol.narrow"), 5), (_t("v.tol.medium"), 10), (_t("v.tol.wide"), 16),
            (_t("v.tol.vwide"), 24)]


def _dc_leggi():
    """Legge tempo e distanza correnti da settings.ini (default GTK se assenti)."""
    tempo, dist = 400, 5
    try:
        for riga in (HOME / ".config/gtk-3.0/settings.ini").read_text().splitlines():
            r = riga.strip()
            if r.startswith("gtk-double-click-time="):
                tempo = int(r.split("=", 1)[1])
            elif r.startswith("gtk-double-click-distance="):
                dist = int(r.split("=", 1)[1])
    except Exception:                            # noqa: BLE001
        pass
    return tempo, dist


def _dc_scrivi(tempo, dist):
    """Applica a GTK3 e GTK2. GTK sorveglia settings.ini: le finestre gia'
    aperte recepiscono il cambiamento subito, senza riavviare nulla."""
    from vesper.profiles.model import _replace_line     # scrittura ATOMICA
    _replace_line(HOME / ".config" / "gtk-3.0" / "settings.ini",
                  "gtk-double-click-time", "gtk-double-click-time=%d" % tempo)
    _replace_line(HOME / ".config" / "gtk-3.0" / "settings.ini",
                  "gtk-double-click-distance", "gtk-double-click-distance=%d" % dist)
    _replace_line(HOME / ".gtkrc-2.0",
                  "gtk-double-click-time", "gtk-double-click-time = %d" % tempo)
    _replace_line(HOME / ".gtkrc-2.0",
                  "gtk-double-click-distance", "gtk-double-click-distance = %d" % dist)
    try:
        st = Gtk.Settings.get_default()
        st.set_property("gtk-double-click-time", tempo)
        st.set_property("gtk-double-click-distance", dist)
    except Exception:                            # noqa: BLE001
        pass


def open_mouse(_btn=None):
    """Taratura del doppio clic, con zona di prova."""
    win, body = panel_window(_t("v.mouse.title"), 560, 520)
    tempo, dist = _dc_leggi()

    intro = Gtk.Label(label=(
        _t("v.mouse_intro")))
    intro.set_xalign(0); intro.set_line_wrap(True)
    intro.get_style_context().add_class("vesper-val")
    body.pack_start(intro, False, False, 0)

    def _riga(etichetta, presets, valore, nota):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lab = Gtk.Label(label=etichetta); lab.set_xalign(0)
        lab.get_style_context().add_class("vesper-key")
        lab.set_size_request(210, -1)
        box.pack_start(lab, False, False, 0)
        combo = Gtk.ComboBoxText()
        for nome, v in presets:
            combo.append(str(v), "%s  (%d)" % (nome, v))
        if not combo.set_active_id(str(valore)):
            combo.append(str(valore), _t("v.custom_n") % valore)
            combo.set_active_id(str(valore))
        box.pack_start(combo, True, True, 0)
        body.pack_start(box, False, False, 0)
        n = Gtk.Label(label=nota); n.set_xalign(0); n.set_line_wrap(True)
        n.get_style_context().add_class("vesper-val")
        body.pack_start(n, False, False, 0)
        return combo

    c_tempo = _riga(_t("v.dclick_speed"), _dc_tempi(), tempo,
                    _t("v.dclick_speed_help"))
    c_dist = _riga(_t("v.move_tol"), _dc_dist(), dist,
                   _t("v.move_tol_help"))

    # --- zona di prova ---------------------------------------------------
    sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
    sep.set_margin_top(10)
    body.pack_start(sep, False, False, 0)
    prova_lab = Gtk.Label(label=_t("v.dclick_try"))
    prova_lab.set_xalign(0)
    prova_lab.get_style_context().add_class("vesper-key")
    body.pack_start(prova_lab, False, False, 0)

    zona = Gtk.EventBox()
    zona.set_size_request(-1, 110)
    zona.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
    inner = Gtk.Label(label=_t("v.test_zone"))
    inner.get_style_context().add_class("vesper-val")
    zona.add(inner)
    body.pack_start(zona, False, False, 0)

    conta = {"singoli": 0, "doppi": 0}

    def on_click(_w, ev):
        if ev.type == Gdk.EventType._2BUTTON_PRESS:
            conta["doppi"] += 1
            inner.set_text(_t("v.dclick_ok")
                           % (conta["doppi"], conta["singoli"]))
        elif ev.type == Gdk.EventType.BUTTON_PRESS:
            conta["singoli"] += 1
            inner.set_text(_t("v.click_single")
                           % (conta["doppi"], conta["singoli"]))
        return False
    zona.connect("button-press-event", on_click)

    stato = Gtk.Label(label="")
    stato.set_xalign(0); stato.set_line_wrap(True)
    stato.get_style_context().add_class("vesper-val")
    body.pack_start(stato, False, False, 0)

    def applica(*_a):
        t = int(c_tempo.get_active_id() or 600)
        d = int(c_dist.get_active_id() or 16)
        _dc_scrivi(t, d)
        conta["singoli"] = conta["doppi"] = 0
        inner.set_text(_t("v.test_zone"))
        stato.set_text(_t("v.dclick_applied") % (t, d))
    c_tempo.connect("changed", applica)
    c_dist.connect("changed", applica)

    win.show_all()
    return win

# ---------------------------------------------------------------------------
# Gestione Bluetooth (stile blueman-manager) - backend vesper-bluetooth (BlueZ)
# ---------------------------------------------------------------------------
def _bt_parse_devices(raw: str):
    """Righe 'mac<TAB>nome<TAB>stato<TAB>trusted<TAB>icona' -> lista di dict."""
    devs = []
    for line in raw.splitlines():
        p = line.split("\t")
        if len(p) < 2 or not p[0].strip():
            continue
        devs.append({
            "mac": p[0], "name": p[1] or p[0],
            "state": p[2] if len(p) > 2 else "",
            "trusted": (len(p) > 3 and p[3] == "1"),
            "icon": p[4] if len(p) > 4 and p[4] else "bluetooth-symbolic",
        })
    order = {"conn": 0, "paired": 1, "": 2}
    devs.sort(key=lambda d: (order.get(d["state"], 2), d["name"].lower()))
    return devs


def _bt_device_info(mac: str):
    """Parsa 'vesper-bluetooth info MAC' in un dict key->value leggibile."""
    out = run_capture(["vesper-bluetooth", "info", mac], timeout=8)
    d = {}
    for line in out.splitlines():
        line = line.strip()
        if ":" in line:
            k, v = line.split(":", 1)
            d[k.strip()] = v.strip()
    return d


def open_bluetooth(_btn=None):
    win, body = panel_window(_t("v.bt.title"), 580, 580)

    # --- riga adattatore: nome + rinomina + accensione ---
    adapt = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    adapt.get_style_context().add_class("vesper-card")
    ada_ico = Gtk.Image.new_from_icon_name("bluetooth-symbolic",
                                           Gtk.IconSize.DND)
    adapt.pack_start(ada_ico, False, False, 0)
    ada_txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    ada_name = Gtk.Label(); ada_name.set_xalign(0)
    ada_name.get_style_context().add_class("vesper-key")
    ada_addr = Gtk.Label(); ada_addr.set_xalign(0)
    ada_addr.get_style_context().add_class("vesper-val")
    ada_txt.pack_start(ada_name, False, False, 0)
    ada_txt.pack_start(ada_addr, False, False, 0)
    adapt.pack_start(ada_txt, True, True, 0)
    ren_btn = icon_button(_t("v.rename"), "document-edit-symbolic")
    adapt.pack_end(ren_btn, False, False, 0)
    pw_sw = Gtk.Switch(); pw_sw.set_valign(Gtk.Align.CENTER)
    adapt.pack_end(pw_sw, False, False, 0)
    body.pack_start(adapt, False, False, 0)

    # riga _t("v.bt_visible")
    ctl = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    disc_lbl = Gtk.Label(label=_t("v.bt_make_visible"))
    disc_lbl.set_xalign(0); disc_lbl.get_style_context().add_class("vesper-val")
    ctl.pack_start(disc_lbl, True, True, 0)
    disc_sw = Gtk.Switch(); disc_sw.set_valign(Gtk.Align.CENTER)
    ctl.pack_end(disc_sw, False, False, 0)
    body.pack_start(ctl, False, False, 0)

    # riga _t("v.bt_recv") (OBEX): accende un server che salva i file
    # inviati da altri dispositivi nella cartella degli scaricati.
    rcv = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    rcv_lbl = Gtk.Label(label=_t("v.bt_recv_full"))
    rcv_lbl.set_xalign(0); rcv_lbl.get_style_context().add_class("vesper-val")
    rcv.pack_start(rcv_lbl, True, True, 0)
    rcv_sw = Gtk.Switch(); rcv_sw.set_valign(Gtk.Align.CENTER)
    rcv.pack_end(rcv_sw, False, False, 0)
    body.pack_start(rcv, False, False, 0)

    # riga scansione + stato
    scan_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    scan_btn = icon_button(_t("v.bt_scan"), "view-refresh", primary=True)
    spinner = Gtk.Spinner()
    scan_row.pack_start(scan_btn, False, False, 0)
    scan_row.pack_start(spinner, False, False, 0)
    status = Gtk.Label(); status.set_xalign(0)
    status.get_style_context().add_class("vesper-val")
    scan_row.pack_end(status, True, True, 0)
    body.pack_start(scan_row, False, False, 0)

    # --- lista dispositivi (scrollabile) ---
    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroller.set_vexpand(True)
    devbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    devbox.set_margin_top(4)
    scroller.add(devbox)
    body.pack_start(scroller, True, True, 0)

    st = {"busy": False}

    def set_status(msg):
        status.set_text(msg)

    def bt(*args, timeout=20):
        return run_capture(["vesper-bluetooth", *args], timeout=timeout)

    def _block(switch, active):
        h = getattr(switch, "_handler", None)
        if h is not None:
            switch.handler_block(h)
        switch.set_active(active)
        if h is not None:
            switch.handler_unblock(h)

    def refresh_adapter():
        def worker():
            raw = bt("adapter", timeout=8)
            GLib.idle_add(apply_adapter, raw)
        threading.Thread(target=worker, daemon=True).start()

    def apply_adapter(raw):
        p = (raw.strip("\n").split("\t") + ["", "", "", "", "", ""])[:6]
        name, alias, addr, powered, disc, _pair = p
        shown = alias or name or _t("v.bt_adapter")
        if not addr:
            ada_name.set_text(_t("v.bt_no_adapter"))
            ada_addr.set_text(_t("v.bt_vm_hint"))
            for w in (pw_sw, disc_sw, scan_btn, ren_btn):
                w.set_sensitive(False)
            return False
        ada_name.set_text(shown)
        ada_addr.set_text(addr)
        pw_sw.set_sensitive(True); ren_btn.set_sensitive(True)
        _block(pw_sw, powered == "1")
        disc_sw.set_sensitive(powered == "1")
        _block(disc_sw, disc == "1")
        return False

    def render(devs):
        for c in devbox.get_children():
            devbox.remove(c)
        if not devs:
            empty = Gtk.Label(label=_t("v.bt_none_scan"))
            empty.set_xalign(0); empty.get_style_context().add_class("vesper-val")
            empty.set_line_wrap(True)
            devbox.pack_start(empty, False, False, 0)
            devbox.show_all()
            return
        for d in devs:
            devbox.pack_start(_dev_row(d), False, False, 0)
        devbox.show_all()

    def _dev_row(d):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.get_style_context().add_class("vesper-tile")
        img = Gtk.Image.new_from_icon_name(d["icon"], Gtk.IconSize.DND)
        row.pack_start(img, False, False, 0)

        txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        name = Gtk.Label(label=d["name"]); name.set_xalign(0)
        name.get_style_context().add_class("vesper-key")
        sub = Gtk.Label(); sub.set_xalign(0)
        sub.get_style_context().add_class("vesper-val")
        tags = []
        if d["state"] == "conn":
            tags.append("connesso")
        elif d["state"] == "paired":
            tags.append("abbinato")
        if d["trusted"]:
            tags.append(_t("v.bt.trusted"))
        # Mostra SEMPRE il MAC (hex) come sottotitolo, insieme al nome in chiaro
        # (label 'name' sopra) e agli eventuali stati: cosi' ogni dispositivo ha
        # sia il nome leggibile sia l'indirizzo esadecimale, sempre visibili.
        sub.set_text("  •  ".join([d["mac"]] + tags))
        txt.pack_start(name, False, False, 0)
        txt.pack_start(sub, False, False, 0)
        row.pack_start(txt, True, True, 0)

        act = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        if d["state"] == "conn":
            b = icon_button(_t("v.bt_disconnect"), "network-offline-symbolic")
            b.connect("clicked", lambda _w, m=d["mac"], n=d["name"]:
                      do_action("disconnect", m, _t("v.bt_disconnecting") % n))
        else:
            b = icon_button(_t("v.bt_connect"), "network-transmit-receive-symbolic",
                            primary=True)
            b.connect("clicked", lambda _w, m=d["mac"], n=d["name"]:
                      do_action("connect", m, _t("v.bt_connecting") % n))
        act.pack_start(b, False, False, 0)
        if d["state"] == "":
            bp = icon_button(_t("v.bt_pair"), "emblem-synchronizing-symbolic")
            bp.connect("clicked", lambda _w, m=d["mac"], n=d["name"]:
                       do_action("pair", m, _t("v.bt_pairing") % n))
            act.pack_start(bp, False, False, 0)
        bt_lbl = _t("v.bt_untrust") if d["trusted"] else _t("v.bt_trust")
        bt_ico = ("security-medium-symbolic" if d["trusted"]
                  else "security-high-symbolic")
        btr = icon_button(bt_lbl, bt_ico)
        btr.connect("clicked", lambda _w, m=d["mac"], t=d["trusted"]:
                    do_action("untrust" if t else "trust", m,
                              _t("v.bt_trust_upd")))
        act.pack_start(btr, False, False, 0)
        bi = icon_button(_t("v.info"), "dialog-information-symbolic")
        bi.connect("clicked", lambda _w, m=d["mac"], n=d["name"]:
                   show_info(m, n))
        act.pack_start(bi, False, False, 0)
        # Invia file (OBEX) verso i device accoppiati/connessi.
        if d["state"] in ("conn", "paired"):
            bsend = icon_button(_t("v.bt_send_file"), "document-send-symbolic")
            bsend.connect("clicked", lambda _w, m=d["mac"], n=d["name"]:
                          send_file(m, n))
            act.pack_start(bsend, False, False, 0)
        brm = icon_button(_t("v.remove"), "user-trash-symbolic")
        brm.connect("clicked", lambda _w, m=d["mac"], n=d["name"]:
                    do_action("remove", m, _t("v.bt_removing") % n))
        act.pack_start(brm, False, False, 0)
        row.pack_end(act, False, False, 0)
        return row

    def reload_devices():
        def worker():
            devs = _bt_parse_devices(bt("devices", timeout=10))
            GLib.idle_add(lambda: render(devs))
        threading.Thread(target=worker, daemon=True).start()

    def do_action(action, mac, msg):
        if st["busy"]:
            return
        st["busy"] = True
        set_status(msg)
        def worker():
            # 70s: pair/connect attendono fino a 60s la conferma sul device.
            out = bt(action, mac, timeout=70)
            def done():
                st["busy"] = False
                low = out.lower()
                if action == "connect" and out.strip() and "successful" not in low:
                    set_status(_t("v.bt_conn_fail"))
                else:
                    set_status(_t("v.done_dot"))
                reload_devices(); refresh_adapter()
                return False
            GLib.idle_add(done)
        threading.Thread(target=worker, daemon=True).start()

    def send_file(mac, name):
        if st["busy"]:
            return
        dlg = Gtk.FileChooserDialog(
            title=_t("v.bt_send_to") % name, transient_for=win,
            action=Gtk.FileChooserAction.OPEN)
        dlg.add_button(_t("v.cancel"), Gtk.ResponseType.CANCEL)
        dlg.add_button(_t("v.send"), Gtk.ResponseType.OK)
        dlg.set_default_response(Gtk.ResponseType.OK)
        resp = dlg.run()
        path = dlg.get_filename() if resp == Gtk.ResponseType.OK else None
        dlg.destroy()
        if not path:
            return
        st["busy"] = True
        set_status(_t("v.bt_sending") % (os.path.basename(path), name))
        def worker():
            out = bt("send", mac, path, timeout=180).strip()
            def done():
                st["busy"] = False
                if out == "ok":
                    set_status(_t("v.bt_sent") % name)
                elif out == "err-noobex":
                    set_status(_t("v.bt_send_na"))
                elif out == "err-nofile":
                    set_status(_t("v.file_not_found"))
                elif out == "err-obexd":
                    set_status(_t("v.bt_send_fail_obexd"))
                else:
                    set_status(_t("v.bt_send_fail_check") % out)
                return False
            GLib.idle_add(done)
        threading.Thread(target=worker, daemon=True).start()

    def show_info(mac, name):
        def worker():
            d = _bt_device_info(mac)
            def show():
                fields = [(_t("v.bt.address"), mac)]
                for k_it, k_bz in ((_t("v.bt.name"), "Name"), ("Alias", "Alias"),
                                   (_t("v.bt.type"), "Icon"), (_t("v.bt.connected"), "Connected"),
                                   (_t("v.bt.paired"), "Paired"), (_t("v.bt.trusted"), "Trusted"),
                                   (_t("v.bt.battery"), "Battery Percentage"),
                                   (_t("v.bt.vendor"), "Modalias")):
                    if k_bz in d:
                        v = d[k_bz]
                        if k_bz in ("Connected", "Paired", "Trusted"):
                            v = _t("v.yes") if v == "yes" else _t("v.no")
                        fields.append((k_it, v))
                body_txt = "\n".join("%s: %s" % (k, v) for k, v in fields)
                info_dialog(_t("v.dev_label") % name, body_txt, parent=win)
                return False
            GLib.idle_add(show)
        threading.Thread(target=worker, daemon=True).start()

    def do_scan(_w=None):
        if st["busy"]:
            return
        st["busy"] = True
        spinner.start(); scan_btn.set_sensitive(False)
        set_status(_t("v.bt_scanning"))
        def worker():
            devs = _bt_parse_devices(bt("scan", "12", timeout=45))
            def done():
                st["busy"] = False
                spinner.stop(); scan_btn.set_sensitive(True)
                set_status(_t("v.bt_found") % len(devs) if devs
                           else _t("v.bt_none_found"))
                render(devs)
                return False
            GLib.idle_add(done)
        threading.Thread(target=worker, daemon=True).start()
    scan_btn.connect("clicked", do_scan)

    def do_rename(_w=None):
        dlg = Gtk.Dialog(title=_t("v.bt_rename_adapter"), transient_for=win,
                         modal=True)
        dlg.add_button(_t("v.cancel"), Gtk.ResponseType.CANCEL)
        dlg.add_button(_t("v.save"), Gtk.ResponseType.OK)
        dlg.set_default_response(Gtk.ResponseType.OK)
        ar = dlg.get_content_area(); ar.set_spacing(8); ar.set_border_width(12)
        ar.add(Gtk.Label(label=_t("v.bt_visible_name")))
        ent = Gtk.Entry(); ent.set_text(ada_name.get_text())
        ent.set_activates_default(True); ar.add(ent)
        dlg.show_all()
        if dlg.run() == Gtk.ResponseType.OK:
            newname = ent.get_text().strip()
            if newname:
                run_bg(["vesper-bluetooth", "alias", newname])
                GLib.timeout_add(800, lambda: (refresh_adapter(), False)[-1])
        dlg.destroy()
    ren_btn.connect("clicked", do_rename)

    def on_power(sw, state):
        run_bg(["vesper-bluetooth", "on" if state else "off"])
        disc_sw.set_sensitive(state)
        def after():
            refresh_adapter()
            if state:
                reload_devices()
            else:
                render([])
            return False
        GLib.timeout_add(1200, after)
        return False
    pw_sw._handler = pw_sw.connect("state-set", on_power)

    def on_disc(sw, state):
        run_bg(["vesper-bluetooth", "discoverable", "on" if state else "off"])
        return False
    disc_sw._handler = disc_sw.connect("state-set", on_disc)

    def on_recv(sw, state):
        def worker():
            out = bt("receive", "on" if state else "off", timeout=15).strip()
            def done():
                if not state:
                    set_status(_t("v.bt_recv_off"))
                elif out.startswith("on"):
                    set_status(_t("v.bt_recv_on"))
                elif out == "err-noobex":
                    set_status(_t("v.bt_recv_na"))
                else:
                    set_status(_t("v.bt_recv_notact") % out)
                return False
            GLib.idle_add(done)
        threading.Thread(target=worker, daemon=True).start()
        return False
    rcv_sw._handler = rcv_sw.connect("state-set", on_recv)
    # stato iniziale del server di ricezione
    def _init_recv():
        on = bt("receive", "status", timeout=6).strip() == "on"
        _block(rcv_sw, on)
        return False
    GLib.idle_add(_init_recv)

    btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    b_close = icon_button(_t("v.close"), "window-close")
    b_close.connect("clicked", lambda _b: win.destroy())
    btns.pack_end(b_close, False, False, 0)
    body.pack_end(btns, False, False, 0)

    refresh_adapter()
    reload_devices()
    win.show_all()


# ---------------------------------------------------------------------------
# Stile finestre (flat / vetro / telaio) - commutabile
# ---------------------------------------------------------------------------
_WSTYLES = [
    ("vetro",  _t("v.ws.glass_hud"),
     _t("v.ws.glass_desc")),
    ("flat",   _t("v.ws.flat_round"),
     _t("v.ws.flat_desc")),
    ("telaio", _t("v.ws.frame"),
     _t("v.ws.frame_desc")),
    ("aero",   _t("v.ws.real_glass"),
     _t("v.ws.real_desc")),
]


def open_window_style(_btn=None):
    win, body = panel_window(_t("v.ws.title"), 560, 460)
    try:
        from vesper.profiles import model as _wmodel
    except Exception:                       # noqa: BLE001
        _wmodel = None

    intro = Gtk.Label(label=_t("v.ws_intro"))
    intro.set_xalign(0); intro.set_line_wrap(True)
    intro.get_style_context().add_class("vesper-val")
    body.pack_start(intro, False, False, 0)

    current = _wmodel.get_window_style() if _wmodel else "vetro"
    group = None
    radios = {}
    for key, name, desc in _WSTYLES:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        card.get_style_context().add_class("vesper-card")
        rb = Gtk.RadioButton.new_with_label_from_widget(group, name)
        if group is None:
            group = rb
        rb.set_active(key == current)
        radios[key] = rb
        card.pack_start(rb, False, False, 0)
        d = Gtk.Label(label=desc); d.set_xalign(0); d.set_line_wrap(True)
        d.get_style_context().add_class("vesper-val")
        d.set_margin_start(24)
        card.pack_start(d, False, False, 0)
        body.pack_start(card, False, False, 0)

    status = Gtk.Label(label=""); status.set_xalign(0)
    status.get_style_context().add_class("vesper-val")
    body.pack_start(status, False, False, 0)

    def chosen():
        for k, rb in radios.items():
            if rb.get_active():
                return k
        return "vetro"

    def do_apply(_b=None):
        if _wmodel is None:
            status.set_text(_t("v.profiles_mod_na"))
            return
        style = chosen()
        _wmodel.set_window_style(style)
        # applica a caldo (lo stile riguarda le finestre, non la barra)
        try:
            from vesper.common import apply_window_style_live
            apply_window_style_live()
        except Exception:                   # noqa: BLE001
            pass
        status.set_text(_t("v.ws_applied") %
                        dict((k, n) for k, n, _ in _WSTYLES).get(style, style))
    # anteprima immediata anche solo cambiando la scelta
    for rb in radios.values():
        rb.connect("toggled", lambda w: w.get_active() and do_apply())

    btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    b_apply = icon_button(_t("v.apply"), "emblem-ok", primary=True)
    b_apply.connect("clicked", do_apply)
    b_close = icon_button(_t("v.close"), "window-close")
    b_close.connect("clicked", lambda _b: win.destroy())
    btns.pack_start(b_apply, False, False, 0)
    btns.pack_end(b_close, False, False, 0)
    body.pack_end(btns, False, False, 0)

    win.show_all()


_THEME_FAMILIES = [
    ("core",  _t("v.ac.core"),
     _t("v.ac.core_desc")),
    ("retro", _t("v.ac.retro"),
     _t("v.ac.retro_desc")),
    ("cards", _t("v.ac.cards"),
     _t("v.ac.cards_desc")),
    ("raw:Vesper-Arc-Dark", _t("v.ac.arc_dark"),
     _t("v.ac.arc_dark_desc")),
    ("raw:Vesper-Arc-Light", _t("v.ac.arc_light"),
     _t("v.ac.arc_light_desc")),
]
_PROMPT_STYLES = [
    ("default", _t("v.ac.prompt_one"),
     _t("v.ac.prompt_one_desc")),
    ("parrot",  _t("v.ac.prompt_parrot"),
     _t("v.ac.prompt_parrot_desc")),
    ("plain",   _t("v.ac.prompt_min"),
     _t("v.ac.prompt_min_desc")),
]


def open_appearance(_btn=None):
    """Aspetto COORDINATO col profilo: famiglia del tema finestre + stile del
    prompt del terminale. Le famiglie Retro/Cards seguono il colore del profilo
    attivo; il prompt e' commutabile e vale sui nuovi terminali."""
    win, body = panel_window(_t("v.ac.title"), 580, 600)
    try:
        from vesper.profiles import model as _m
    except Exception:                       # noqa: BLE001
        _m = None

    intro = Gtk.Label(label=_t("v.ac_intro"))
    intro.set_xalign(0); intro.set_line_wrap(True)
    intro.get_style_context().add_class("vesper-val")
    body.pack_start(intro, False, False, 0)

    # --- Tema finestre (famiglia coordinata) ---------------------------------
    h1 = Gtk.Label(label=_t("v.ac.window_theme")); h1.set_xalign(0)
    h1.get_style_context().add_class("vesper-section")
    body.pack_start(h1, False, False, 0)

    cur_fam = _m.theme_family() if _m else "core"
    fam_group = None; fam_radios = {}
    for key, name, desc in _THEME_FAMILIES:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        card.get_style_context().add_class("vesper-card")
        rb = Gtk.RadioButton.new_with_label_from_widget(fam_group, name)
        if fam_group is None:
            fam_group = rb
        rb.set_active(key == cur_fam)
        fam_radios[key] = rb
        card.pack_start(rb, False, False, 0)
        d = Gtk.Label(label=desc); d.set_xalign(0); d.set_line_wrap(True)
        d.get_style_context().add_class("vesper-val"); d.set_margin_start(24)
        card.pack_start(d, False, False, 0)
        body.pack_start(card, False, False, 0)

    fam_status = Gtk.Label(label=""); fam_status.set_xalign(0)
    fam_status.get_style_context().add_class("vesper-val")
    body.pack_start(fam_status, False, False, 0)

    def fam_chosen():
        for k, rb in fam_radios.items():
            if rb.get_active():
                return k
        return "core"

    def fam_apply(_b=None):
        if _m is None:
            fam_status.set_text(_t("v.profiles_mod_na"))
            return
        fam = fam_chosen()
        _m.set_theme_family(fam)          # salva + applica (openbox --reconfigure)
        fam_status.set_text(_t("v.ac.theme_applied") %
                            (fam, _m.resolve_ob_theme()))
    for rb in fam_radios.values():
        rb.connect("toggled", lambda w: w.get_active() and fam_apply())

    # --- Gestore finestre: Openbox o le decorazioni VERE di Mint -----------
    # Openbox non sa leggere i temi di Mint (formato metacity-1): per averli
    # davvero la sessione deve girare con marco o metacity. Qui si sceglie; la
    # scelta ha effetto al prossimo accesso.
    h_wm = Gtk.Label(label=_t("v.wm.title"))
    h_wm.set_xalign(0)
    h_wm.get_style_context().add_class("vesper-section")
    body.pack_start(h_wm, False, False, 0)

    wm_intro = Gtk.Label(label=_t("v.wm_intro"))
    wm_intro.set_xalign(0)
    wm_intro.set_line_wrap(True)
    wm_intro.get_style_context().add_class("vesper-val")
    body.pack_start(wm_intro, False, False, 0)

    wm_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    wm_row.get_style_context().add_class("vesper-card")
    wm_combo = Gtk.ComboBoxText()
    wm_labels = {"openbox": _t("v.wm.openbox"), "marco": _t("v.wm.marco"),
                 "metacity": _t("v.wm.metacity")}
    if _m is not None:
        for wm in _m.WM_SUPPORTED:
            etichetta = wm_labels.get(wm, wm)
            if not have(wm):
                etichetta += "  " + _t("v.wm.missing")
            wm_combo.append(wm, etichetta)
        wm_combo.set_active_id(_m.get_wm())
    wm_row.pack_start(wm_combo, True, True, 0)
    body.pack_start(wm_row, False, False, 0)

    wm_status = Gtk.Label(label="")
    wm_status.set_xalign(0)
    wm_status.set_line_wrap(True)
    wm_status.get_style_context().add_class("vesper-val")
    body.pack_start(wm_status, False, False, 0)

    def wm_changed(combo):
        if _m is None:
            return
        wm = combo.get_active_id()
        if not wm:
            return
        _m.set_wm(wm)
        if wm == "openbox":
            wm_status.set_text(_t("v.wm.set_openbox"))
        else:
            tema = _m.wm_theme_name() or "-"
            wm_status.set_text(_t("v.wm.set_mint") % (wm, tema))
    wm_combo.connect("changed", wm_changed)      # DOPO set_active_id

    # --- Oppure un tema FISSO fra tutti quelli installati -------------------
    # Qui compaiono anche i temi di terze parti inclusi in Vesper (i "1977" nei
    # vari colori) e qualunque tema che l'utente abbia messo in ~/.themes.
    fixed_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    fixed_row.get_style_context().add_class("vesper-card")
    fl = Gtk.Label(label=_t("v.ac.fixed_theme"))
    fl.set_xalign(0)
    fl.get_style_context().add_class("vesper-key")
    fixed_row.pack_start(fl, True, True, 0)
    fixed_combo = Gtk.ComboBoxText()
    installed = _ob_list_themes()
    for name in installed:
        fixed_combo.append("raw:" + name, name)
    if cur_fam.startswith("raw:") and cur_fam[4:] in installed:
        fixed_combo.set_active_id(cur_fam)
    fixed_row.pack_end(fixed_combo, False, False, 0)
    body.pack_start(fixed_row, False, False, 0)

    def fixed_changed(combo):
        key = combo.get_active_id()
        if not key or _m is None:
            return
        for rb in fam_radios.values():        # esce dalle famiglie coordinate
            rb.set_active(False)
        _m.set_theme_family(key)
        fam_status.set_text(_t("v.ac.theme_applied") % (key, _m.resolve_ob_theme()))
    fixed_combo.connect("changed", fixed_changed)   # DOPO set_active_id

    note = Gtk.Label(label=_t("v.ac_note"))
    note.set_xalign(0); note.set_line_wrap(True)
    note.get_style_context().add_class("vesper-val")
    body.pack_start(note, False, False, 0)

    # --- Tema pannello (skin barra + menu), indipendente dal preset ---------
    h_pt = Gtk.Label(label=_t("v.pt.title")); h_pt.set_xalign(0)
    h_pt.get_style_context().add_class("vesper-section")
    body.pack_start(h_pt, False, False, 0)

    pt_intro = Gtk.Label(label=_t("v.pt_intro"))
    pt_intro.set_xalign(0); pt_intro.set_line_wrap(True)
    pt_intro.get_style_context().add_class("vesper-val")
    body.pack_start(pt_intro, False, False, 0)

    try:
        from vesper import paneltheme as _pt
    except Exception:                       # noqa: BLE001
        _pt = None

    pt_ids = []
    pt_combo = Gtk.ComboBoxText()
    if _pt is not None:
        cur_pt = _pt.get_theme()
        for tid, name, src in _pt.list_themes():
            pt_combo.append_text(name if src == "builtin"
                                 else "%s — %s" % (name, src))
            pt_ids.append(tid)
        try:
            pt_combo.set_active(pt_ids.index(cur_pt))
        except ValueError:
            pt_combo.set_active(0)
    else:
        pt_combo.set_sensitive(False)

    row_pt = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    lab_pt = Gtk.Label(label=_t("v.skin_label")); lab_pt.set_xalign(0)
    lab_pt.get_style_context().add_class("vesper-val")
    row_pt.pack_start(lab_pt, False, False, 0)
    row_pt.pack_start(pt_combo, True, True, 0)
    body.pack_start(row_pt, False, False, 0)

    pt_status = Gtk.Label(label=""); pt_status.set_xalign(0)
    pt_status.get_style_context().add_class("vesper-val")
    body.pack_start(pt_status, False, False, 0)

    def pt_changed(_c=None):
        if _pt is None:
            return
        i = pt_combo.get_active()
        if i < 0 or i >= len(pt_ids):
            return
        tid = pt_ids[i]
        _pt.set_theme(tid)                 # il pannello si ricolora a caldo;
        try:                              # riavvio comunque per sicurezza.
            panelcfg.restart_panel()
        except Exception:                 # noqa: BLE001
            pass
        pt_status.set_text(_t("v.pt.applied") % tid)
    # collega DOPO set_active cosi' l'apertura della finestra non riavvia la barra
    pt_combo.connect("changed", pt_changed)

    # --- Prompt del terminale ------------------------------------------------
    h2 = Gtk.Label(label=_t("v.term_prompt")); h2.set_xalign(0)
    h2.get_style_context().add_class("vesper-section")
    body.pack_start(h2, False, False, 0)

    cur_pr = "default"
    try:
        cur_pr = (HOME / ".config" / "vesper" / "prompt").read_text().strip() or "default"
    except OSError:
        pass
    pr_group = None; pr_radios = {}
    for key, name, desc in _PROMPT_STYLES:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        card.get_style_context().add_class("vesper-card")
        rb = Gtk.RadioButton.new_with_label_from_widget(pr_group, name)
        if pr_group is None:
            pr_group = rb
        rb.set_active(key == cur_pr)
        pr_radios[key] = rb
        card.pack_start(rb, False, False, 0)
        d = Gtk.Label(label=desc); d.set_xalign(0); d.set_line_wrap(True)
        d.get_style_context().add_class("vesper-val"); d.set_margin_start(24)
        card.pack_start(d, False, False, 0)
        body.pack_start(card, False, False, 0)

    pr_status = Gtk.Label(label=""); pr_status.set_xalign(0)
    pr_status.get_style_context().add_class("vesper-val")
    body.pack_start(pr_status, False, False, 0)

    def pr_chosen():
        for k, rb in pr_radios.items():
            if rb.get_active():
                return k
        return "default"

    def pr_apply(_b=None):
        st = pr_chosen()
        try:
            subprocess.run(["vesper-prompt", "set", st])
        except OSError:
            pass
        pr_status.set_text(_t("v.prompt_set") % st)
    for rb in pr_radios.values():
        rb.connect("toggled", lambda w: w.get_active() and pr_apply())

    b_term = icon_button(_t("v.open_test_term"), "utilities-terminal")
    b_term.connect("clicked", lambda _b: run_bg(["vesper-terminal"]))
    body.pack_start(b_term, False, False, 0)

    btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    b_close = icon_button(_t("v.close"), "window-close")
    b_close.connect("clicked", lambda _b: win.destroy())
    btns.pack_end(b_close, False, False, 0)
    body.pack_end(btns, False, False, 0)

    win.show_all()


# ---------------------------------------------------------------------------
# Helper condivisi dalle viste che chiedono credenziali o privilegi
# ---------------------------------------------------------------------------
def _run_priv_term(inner: str, title: str = "Vesper"):
    """Esegue un comando privilegiato in un terminale (così doas/sudo può
    chiedere la password) e lascia la finestra aperta a fine comando.
    Il terminale lo scegle vesper-terminal: nessun emulatore fissato."""
    _ = title
    cmd = ("%s; echo; printf '%s'; read x" % (inner, _t("v.press_enter")))
    run_bg(["vesper-terminal", "-e", "sh", "-c", cmd])


def _eye_entry(placeholder=_t("v.password")):
    e = Gtk.Entry(); e.set_visibility(False); e.set_hexpand(True)
    e.set_placeholder_text(placeholder)
    e.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "view-reveal-symbolic")

    def _eye(entry, _p, _ev):
        v = not entry.get_visibility(); entry.set_visibility(v)
        entry.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY,
                                      "view-conceal-symbolic" if v else "view-reveal-symbolic")
    e.connect("icon-press", _eye)
    return e




def open_screens(_btn=None):
    """Gestione schermi: estendi/duplica o usa un solo monitor, risoluzione
    per output. Wrapper su vesper-screens (xrandr), come l'applet del pannello.
    Dopo ogni applicazione rilegge lo stato e riposiziona i pannelli (già
    gestito da vesper-screens -> _reposition_panels)."""
    win, body = panel_window(_t("v.screens.title"), 620, 640)
    intro = Gtk.Label(label=_t("v.screens_intro"))
    intro.set_xalign(0)
    intro.get_style_context().add_class("vesper-val")
    body.pack_start(intro, False, False, 0)

    # Comportamento AUTOMATICO: all'avvio e ogni volta che si collega/scollega
    # un monitor o si chiude il coperchio (lo applica vesper-screens-watch).
    # Prima non esisteva nulla del genere: un monitor collegato dopo l'avvio
    # restava spento e ci si vedeva solo la splash di boot.
    polbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    pol_lab = Gtk.Label(label=_t("v.screens_on_connect"))
    pol_lab.set_xalign(0)
    polbox.pack_start(pol_lab, False, False, 0)
    pol = Gtk.ComboBoxText()
    pol.append("mirror", _t("v.duplicate"))
    pol.append("extend", _t("v.extend"))
    _cur = (run_capture(["vesper-screens", "get-policy"]).strip() or "mirror")
    pol.set_active_id(_cur if _cur in ("mirror", "extend") else "mirror")
    # connesso DOPO set_active_id, altrimenti scatterebbe subito riapplicando.
    pol.connect("changed", lambda w: run_bg(
        ["vesper-screens", "set-policy", w.get_active_id() or "mirror"]))
    polbox.pack_start(pol, False, False, 0)
    body.pack_start(polbox, False, False, 0)

    outbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    body.pack_start(outbox, False, False, 0)

    def _rebuild():
        for c in outbox.get_children():
            outbox.remove(c)
        outs = []
        for line in run_capture(["vesper-screens", "outputs"]).splitlines():
            p = line.split("\t")
            if len(p) >= 4 and p[1] == "connected":
                outs.append((p[0], p[2], p[3]))       # nome, primary?, WxH
        if not outs:
            lbl = Gtk.Label(label=_t("v.no_screen"))
            lbl.set_xalign(0)
            outbox.pack_start(lbl, False, False, 0)
        else:
            if len(outs) >= 2:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                for lbl, act in ((_t("v.extend"), ["extend"]), (_t("v.duplicate"), ["mirror"])):
                    b = Gtk.Button(label=lbl)
                    b.get_style_context().add_class("vesper-menu-item")
                    b.connect("clicked", lambda _w, a=act: _apply(a))
                    row.pack_start(b, True, True, 0)
                outbox.pack_start(row, False, False, 0)
            for name, prim, res in outs:
                oc = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                oc.get_style_context().add_class("vesper-card")
                oc.set_margin_top(4)
                hdr = Gtk.Label()
                hdr.set_xalign(0)
                hdr.set_markup("<b>%s</b>%s  <small>%s</small>" % (
                    name, _t("v.primary_paren") if prim == "primary" else "", res))
                oc.pack_start(hdr, False, False, 0)
                r = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                combo = Gtk.ComboBoxText()
                modes = run_capture(["vesper-screens", "modes", name]).split()
                for m in modes:
                    combo.append_text(m)
                if modes:
                    cur = res.split("@")[0]
                    combo.set_active(modes.index(cur) if cur in modes else 0)
                r.pack_start(combo, True, True, 0)
                ba = Gtk.Button(label=_t("v.apply"))
                ba.get_style_context().add_class("vesper-menu-item")
                ba.connect("clicked", lambda _w, n=name, c=combo:
                           _apply(["mode", n, c.get_active_text() or ""]))
                r.pack_start(ba, False, False, 0)
                oc.pack_start(r, False, False, 0)

                # --- Orientamento: serve a chi monta il monitor in VERTICALE.
                #     Senza, lo schermo girato tornava orizzontale a ogni
                #     riapplicazione della disposizione.
                rr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                rl = Gtk.Label(label=_t("v.orientation"))
                rl.set_xalign(0)
                rl.get_style_context().add_class("vesper-key")
                rr.pack_start(rl, False, False, 0)
                rot_combo = Gtk.ComboBoxText()
                for rid, rlabel in (("normal", _t("v.rot.normal")),
                                    ("left", _t("v.rot.left")),
                                    ("right", _t("v.rot.right")),
                                    ("inverted", _t("v.rot.inverted"))):
                    rot_combo.append(rid, rlabel)
                cur_rot = (run_capture(["vesper-screens", "rotation", name])
                           or "normal").strip()
                rot_combo.set_active_id(cur_rot if cur_rot in
                                        ("normal", "left", "right", "inverted")
                                        else "normal")
                rr.pack_start(rot_combo, True, True, 0)
                br = Gtk.Button(label=_t("v.apply"))
                br.get_style_context().add_class("vesper-menu-item")
                br.connect("clicked", lambda _w, n=name, c=rot_combo:
                           _apply(["rotate", n, c.get_active_id() or "normal"]))
                rr.pack_start(br, False, False, 0)
                oc.pack_start(rr, False, False, 0)

                if len(outs) >= 2:
                    bo = Gtk.Button(label=_t("v.use_only_this"))
                    bo.get_style_context().add_class("vesper-menu-item")
                    bo.connect("clicked",
                               lambda _w, n=name: _apply(["only", n]))
                    oc.pack_start(bo, False, False, 0)
                outbox.pack_start(oc, False, False, 0)
        outbox.show_all()

    def _apply(args):
        if len(args) >= 4 and args[2] == "mode" and not args[3]:
            return
        run_bg(["vesper-screens"] + args)
        GLib.timeout_add(900, lambda: (_rebuild(), False)[1])

    _rebuild()
    win.show_all()
    return win


# ----- Assistente IA -------------------------------------------------------


# ----- Lingua dell'interfaccia -------------------------------------------
def open_language(_btn=None):
    """Selettore lingua nel Centro di Controllo (oltre all'applet e alla voce
    di menu del pannello). Applica con vesper-lang set."""
    import sys as _sys
    _sys.path.insert(0, "/usr/local/lib")
    try:
        from vesper import i18n
        langs = list(vesper.i18n.LANGS)
        names = vesper.i18n.LANG_NAMES
        cur = vesper.i18n.current_lang()
    except Exception:                          # noqa: BLE001
        langs = ["it", "en", "fr", "es", "de"]
        names = {"it": _t("v.italian"), "en": "English", "fr": "Français",
                 "es": "Español", "de": "Deutsch"}
        cur = "it"

    win, body = panel_window(_t("v.lang.title"), 460, 260)
    intro = Gtk.Label(label=_t("v.lang.desc"))
    intro.set_xalign(0); intro.set_line_wrap(True)
    intro.get_style_context().add_class("vesper-val")
    body.pack_start(intro, False, False, 0)

    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    row.get_style_context().add_class("vesper-card")
    lab = Gtk.Label(label=_t("v.lang.title")); lab.set_xalign(0)
    lab.get_style_context().add_class("vesper-key")
    row.pack_start(lab, True, True, 0)
    combo = Gtk.ComboBoxText()
    for c in langs:
        combo.append(c, names.get(c, c))
    combo.set_active_id(cur)
    row.pack_end(combo, False, False, 0)
    body.pack_start(row, False, False, 0)

    b_apply = icon_button(_t("v.apply"), "object-select-symbolic", primary=True)
    body.pack_start(b_apply, False, False, 0)

    def _apply(_b):
        code = combo.get_active_id()
        if code and code != cur:
            run_bg(["vesper-lang", "set", code])
            info_dialog(win, _t("v.lang.title"),
                        _t("v.lang.set_msg"))
    b_apply.connect("clicked", _apply)

    win.show_all()
    return win
