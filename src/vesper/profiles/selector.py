# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Daniele Deplano (RedRider21). Parte di Vesper.
"""Selettore grafico dei preset di aspetto (GTK3).

Presenta i preset come schede, ognuna tinta col proprio colore d'accento e con
l'anteprima del suo sfondo. Applicando un preset cambiano subito accent,
sfondo, tema icone e stile finestre su tutto il desktop (i CSS generati sono
sorvegliati da vesper.common, che li ricarica a caldo).
"""
from __future__ import annotations

import subprocess
import sys

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GdkPixbuf  # noqa: E402

from . import model

try:
    from vesper.i18n import t as _t          # traduzioni (it/en/fr/es/de)
except Exception:                            # noqa: BLE001
    def _t(key, **kw):                       # fallback: non rompe mai la UI
        return key

try:
    from vesper.common import apply_css
except Exception:                            # noqa: BLE001
    def apply_css():
        pass

_EXTRA_CSS = b"""
.vesper-preset-card {
  background-color: #0a1422; border: 1px solid #1a3a52;
  border-radius: 4px; padding: 12px; margin: 6px; min-width: 210px;
}
.vesper-preset-card:hover { background-color: #0c1a2a; }
.vesper-preset-name { font-weight: bold; font-size: 13pt; }
.vesper-preset-desc { color: #5a8a9a; font-size: 9pt; }
.vesper-preset-accent { min-height: 5px; border-radius: 2px; margin-bottom: 8px; }
"""


def _hex_to_rgba(h: str, a: float) -> str:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        r, g, b = 0, 229, 255
    return "rgba(%d,%d,%d,%.2f)" % (r, g, b, a)


def _card_css(accent: str) -> bytes:
    # Hover/selezione: valgono per il BOTTONE (la scheda), quindi il provider
    # agganciato al contesto della scheda li colpisce correttamente.
    return (
        ".vesper-preset-card:hover { border-color: %s; }"
        ".vesper-preset-card.sel { border-color: %s; background-color: %s; }"
        % (accent, accent, _hex_to_rgba(accent, 0.12))
    ).encode()


def _accent_css(accent: str) -> bytes:
    # La barretta è un widget FIGLIO del bottone e in GTK3 un provider
    # agganciato a un widget NON vale per i figli: il colore va messo sulla
    # barretta stessa, altrimenti resta trasparente (gotcha noto).
    return (".vesper-preset-accent { background-color: %s; }" % accent).encode()


class Selector(Gtk.Window):
    def __init__(self):
        super().__init__(title=_t("sel.wtitle"))
        apply_css()
        prov = Gtk.CssProvider()
        prov.load_from_data(_EXTRA_CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.set_default_size(820, 680)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect("destroy", Gtk.main_quit)

        self._selected = model.current_preset()
        self._cards = {}

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(outer)

        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        header.get_style_context().add_class("vesper-headerbar")
        eb = Gtk.Label(label=_t("sel.eyebrow"))
        eb.set_xalign(0)
        eb.get_style_context().add_class("vesper-eyebrow")
        header.pack_start(eb, False, False, 0)
        t = Gtk.Label(label=_t("sel.title"))
        t.set_xalign(0)
        t.get_style_context().add_class("title")
        s = Gtk.Label(label=_t("sel.subtitle"))
        s.set_xalign(0)
        s.get_style_context().add_class("subtitle")
        header.pack_start(t, False, False, 0)
        header.pack_start(s, False, False, 0)
        outer.pack_start(header, False, False, 0)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        outer.pack_start(sw, True, True, 0)

        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_max_children_per_line(3)
        flow.set_min_children_per_line(1)
        flow.set_homogeneous(True)
        flow.set_margin_top(10)
        flow.set_margin_bottom(10)
        flow.set_margin_start(12)
        flow.set_margin_end(12)
        sw.add(flow)

        for key, d in model.presets().items():
            flow.add(self._make_card(key, d))

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.get_style_context().add_class("vesper-footer")
        self.hint = Gtk.Label(label="")
        self.hint.set_xalign(0)
        bar.pack_start(self.hint, True, True, 0)
        cancel = Gtk.Button(label=_t("v.cancel"))
        cancel.connect("clicked", lambda *_: self.destroy())
        bar.pack_start(cancel, False, False, 0)
        apply_btn = Gtk.Button(label=_t("sel.apply"))
        apply_btn.get_style_context().add_class("vesper-primary")
        apply_btn.connect("clicked", self._on_apply)
        bar.pack_start(apply_btn, False, False, 0)
        outer.pack_start(bar, False, False, 0)

        self._highlight(self._selected)

    def _thumb(self, key):
        """Anteprima dello sfondo del preset (o None se non c'è)."""
        p = None
        try:
            name = model.preset_data(key).get("wallpaper")
            if name:
                for d in model.wallpaper_dirs():
                    if (d / name).is_file():
                        p = d / name
                        break
        except Exception:                    # noqa: BLE001
            return None
        if p is None:
            return None
        try:
            pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(p), 190, 107, True)
            img = Gtk.Image.new_from_pixbuf(pix)
            img.set_tooltip_text(_t("sel.preview"))
            return img
        except Exception:                    # noqa: BLE001
            return None

    def _make_card(self, key, d):
        btn = Gtk.Button()
        btn.set_relief(Gtk.ReliefStyle.NONE)
        ctx = btn.get_style_context()
        ctx.add_class("vesper-preset-card")

        accent = d.get("accent", model.DEFAULT_ACCENT)
        prov = Gtk.CssProvider()
        prov.load_from_data(_card_css(accent))
        ctx.add_provider(prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        bar = Gtk.Box()
        bctx = bar.get_style_context()
        bctx.add_class("vesper-preset-accent")
        bprov = Gtk.CssProvider()
        bprov.load_from_data(_accent_css(accent))
        bctx.add_provider(bprov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        box.pack_start(bar, False, False, 0)

        thumb = self._thumb(key)
        if thumb is not None:
            box.pack_start(thumb, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        img = Gtk.Image.new_from_icon_name(d.get("icon", "vesper-logo-symbolic"),
                                           Gtk.IconSize.DND)
        row.pack_start(img, False, False, 0)
        name = Gtk.Label(label=d.get("name", key))
        name.set_xalign(0)
        name.get_style_context().add_class("vesper-preset-name")
        row.pack_start(name, True, True, 0)
        box.pack_start(row, False, False, 0)

        desc = Gtk.Label(label=d.get("desc", ""))
        desc.set_xalign(0)
        desc.set_line_wrap(True)
        desc.set_max_width_chars(28)
        desc.get_style_context().add_class("vesper-preset-desc")
        box.pack_start(desc, False, False, 0)

        btn.add(box)
        btn.connect("clicked", lambda *_: self._highlight(key))
        self._cards[key] = btn
        return btn

    def _highlight(self, key):
        self._selected = key
        for k, b in self._cards.items():
            ctx = b.get_style_context()
            if k == key:
                ctx.add_class("sel")
            else:
                ctx.remove_class("sel")
        d = model.preset_data(key)
        self.hint.set_text(_t("sel.preset_hint") % d.get("name", key))

    def _on_apply(self, _btn):
        model.activate_preset(self._selected)
        # Il pannello è un processo a sé: va riavviato perché rilegga l'accent e
        # il nome del preset. Il riavvio passa da vesper-panel-restart, il cui
        # argv NON contiene il pattern del pkill (altrimenti si autouccide).
        try:
            subprocess.Popen(["vesper-panel-restart"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        except OSError:
            pass
        self.destroy()


def run(argv=None) -> int:
    _ = argv
    apply_css()
    w = Selector()
    w.show_all()
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
