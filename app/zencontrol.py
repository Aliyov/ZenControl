#!/usr/bin/env python3
"""ZenControl - CPU/GPU power control for the ASUS Zenbook UX535QE."""
import json
import os
import subprocess
import sys
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import monitor

HELPER = "/usr/local/libexec/zencontrol-helper"
PROFILES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "profiles.json")
GOVERNORS = ["performance", "powersave"]
EPPS = ["performance", "balance_performance", "balance_power", "power"]
PLATFORM = ["performance", "balanced", "quiet"]
NOMINAL_MHZ = 3201
LABELS = {"governor": "Governor", "epp": "Energy preference", "boost": "CPU boost",
          "max_freq_mhz": "Max frequency", "platform_profile": "ASUS profile",
          "dynamic_boost": "Dynamic Boost", "gpu_power_w": "GPU power limit",
          "gpu_max_clock_mhz": "GPU max clock", "smt": "SMT", "charge_limit": "Charge limit"}


def load_profiles():
    with open(PROFILES) as f:
        return json.load(f)


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="ZenControl")
        self.set_default_size(560, 900)
        self.profiles = load_profiles()
        self.dirty = set()
        self.loading = False
        self.gpu_info = None

        self.toasts = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        view.set_content(self.toasts)
        self.set_content(view)

        page = Adw.PreferencesPage()
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(page)
        self.toasts.set_child(scroll)

        self._build_presets(page)
        self._build_live(page)
        self._build_manual(page)
        self._build_gpu_holders(page)

        self.refresh(load_settings=True)
        GLib.timeout_add(2000, self.refresh)
        GLib.timeout_add(4000, self.refresh_gpu)

    def _build_presets(self, page):
        g = Adw.PreferencesGroup(title="Quick modes")
        box = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=5,
                          min_children_per_line=2, column_spacing=6, row_spacing=6)
        for name in list(self.profiles) + ["Stock"]:
            b = Gtk.Button(label=name)
            if name == "Max Performance":
                b.add_css_class("destructive-action")
            elif name == "Extreme Powersave":
                b.add_css_class("success")
            b.connect("clicked", self.on_preset, name)
            box.append(b)
        g.add(box)
        self.mode_label = Gtk.Label(xalign=0, wrap=True, css_classes=["dim-label"])
        g.add(self.mode_label)
        page.add(g)

    def _row(self, group, title):
        r = Adw.ActionRow(title=title)
        lbl = Gtk.Label(css_classes=["numeric"])
        r.add_suffix(lbl)
        group.add(r)
        return lbl

    def _build_live(self, page):
        g = Adw.PreferencesGroup(title="Live")
        self.l_cpu = self._row(g, "CPU")
        self.l_fan = self._row(g, "Fans (zenfan)")
        self.l_gpu = self._row(g, "NVIDIA GPU")
        self.l_bat = self._row(g, "Battery")

        grid = Gtk.Grid(column_spacing=8, row_spacing=4, margin_top=8, margin_bottom=8,
                        margin_start=12, margin_end=12)
        self.core_bars = []
        for i in range(os.cpu_count() or 16):
            lab = Gtk.Label(label=f"{i}", xalign=1, width_chars=2, css_classes=["dim-label", "caption"])
            bar = Gtk.LevelBar(min_value=0, max_value=4500, hexpand=True, valign=Gtk.Align.CENTER)
            bar.remove_offset_value("low")
            bar.remove_offset_value("high")
            bar.remove_offset_value("full")
            val = Gtk.Label(xalign=1, width_chars=5, css_classes=["numeric", "caption"])
            col = (i % 2) * 3
            grid.attach(lab, col, i // 2, 1, 1)
            grid.attach(bar, col + 1, i // 2, 1, 1)
            grid.attach(val, col + 2, i // 2, 1, 1)
            self.core_bars.append((bar, val))
        frame = Gtk.Frame(child=grid, margin_top=6)
        g.add(frame)
        page.add(g)

    def _combo(self, group, title, items, key, subtitle=None):
        r = Adw.ComboRow(title=title, model=Gtk.StringList.new(items))
        if subtitle:
            r.set_subtitle(subtitle)
        r.connect("notify::selected", self.on_change, key)
        group.add(r)
        return r

    def _spin(self, group, title, lo, hi, step, key, subtitle=None):
        r = Adw.SpinRow.new_with_range(lo, hi, step)
        r.set_title(title)
        if subtitle:
            r.set_subtitle(subtitle)
        r.connect("notify::value", self.on_change, key)
        group.add(r)
        return r

    def _switch(self, group, title, key, subtitle=None):
        r = Adw.SwitchRow(title=title)
        if subtitle:
            r.set_subtitle(subtitle)
        r.connect("notify::active", self.on_change, key)
        group.add(r)
        return r

    def _build_manual(self, page):
        g = Adw.PreferencesGroup(title="Manual", description="Changes are applied when you press Apply.")
        self.w_boost = self._switch(g, "CPU boost", "boost", "Clocks above 3.2 GHz (high voltage)")
        self.w_freq = self._spin(g, "Max CPU frequency (MHz)", 1100, 4465, 100, "max_freq_mhz")
        self.w_gov = self._combo(g, "Governor", GOVERNORS, "governor")
        self.w_epp = self._combo(g, "Energy preference", EPPS, "epp",
                                 "Only adjustable with the powersave governor")
        self.w_prof = self._combo(g, "ASUS firmware profile", PLATFORM, "platform_profile",
                                  "Firmware power limits. Fan state is preserved for zenfan.")
        page.add(g)

        gg = Adw.PreferencesGroup(title="NVIDIA GPU",
                                  description="Setting these wakes the GPU briefly.")
        self.w_dboost = self._switch(gg, "Dynamic Boost (nvidia-powerd)", "dynamic_boost",
                                     "Lets the GPU go above 35 W, up to 50 W")
        self.w_gpuw = self._spin(gg, "GPU power limit (W)", 10, 50, 1, "gpu_power_w")
        self.w_gpuclk = self._spin(gg, "GPU max clock (MHz, 0 = default)", 0, 2100, 50,
                                   "gpu_max_clock_mhz", "Fallback if the power limit is refused")
        page.add(gg)

        ag = Adw.PreferencesGroup(title="Advanced")
        self.w_smt = self._switch(ag, "SMT (2 threads per core)", "smt",
                                  "Off = 8 threads. Takes effect immediately.")
        self.w_charge = self._spin(ag, "Battery charge limit (%)", 60, 100, 5, "charge_limit")
        page.add(ag)

        bg = Adw.PreferencesGroup()
        box = Gtk.Box(spacing=12, halign=Gtk.Align.END)
        self.b_revert = Gtk.Button(label="Discard changes")
        self.b_revert.connect("clicked", lambda *_: self.refresh(load_settings=True))
        self.b_apply = Gtk.Button(label="Apply", css_classes=["suggested-action"])
        self.b_apply.connect("clicked", self.on_apply)
        box.append(self.b_revert)
        box.append(self.b_apply)
        bg.add(box)
        page.add(bg)

    def _build_gpu_holders(self, page):
        self.holders_group = Adw.PreferencesGroup(
            title="Apps keeping the NVIDIA GPU awake",
            description="The GPU sleeps on its own once nothing uses it (~6-8 W saved).")
        self.holder_rows = []
        page.add(self.holders_group)

    def refresh(self, load_settings=False):
        s = monitor.snapshot()
        fr = [f for f in s["freqs"] if f]
        avg = sum(fr) / len(fr) if fr else 0
        self.l_cpu.set_label(f"{s['tctl']:.0f} °C   {s['apu_w'] or 0:.0f} W   avg {avg:.0f} MHz")
        self.l_fan.set_label(f"{s['fan_cpu'] or 0:.0f} / {s['fan_gpu'] or 0:.0f} RPM   ·   {s['zenfan']}")
        if s["dgpu_awake"]:
            gi_ = self.gpu_info
            self.l_gpu.set_label(f"awake  {gi_['temp']:.0f} °C  {gi_['watts']:.0f}/{gi_['limit']:.0f} W  "
                                 f"{gi_['mhz']:.0f} MHz" if gi_ else "awake")
        else:
            self.l_gpu.set_label("asleep (0 W)")
        bw = s["bat_w"] or 0
        if s["ac"]:
            self.l_bat.set_label(f"{s['bat_pct']:.0f} %  AC, {s['bat_status'].lower()} {bw:.1f} W")
        else:
            left = f"  ~{s['bat_energy_wh'] / bw:.1f} h left" if bw > 0.5 and s["bat_energy_wh"] else ""
            self.l_bat.set_label(f"{s['bat_pct']:.0f} %  using {bw:.1f} W{left}")
        for (bar, val), f in zip(self.core_bars, s["freqs"]):
            bar.set_value(f or 0)
            val.set_label(f"{f:.0f}" if f else "off")

        self._refresh_holders()
        if load_settings:
            self._load_settings(s)
        return True

    def refresh_gpu(self):
        def work():
            info = monitor.gpu_query()
            GLib.idle_add(self._set_gpu_info, info)
        threading.Thread(target=work, daemon=True).start()
        return True

    def _set_gpu_info(self, info):
        self.gpu_info = info
        if info and "gpu_power_w" not in self.dirty:
            self.loading = True
            self.w_gpuw.set_value(info["limit"])
            self.loading = False

    def _refresh_holders(self):
        awake = monitor.dgpu_awake()
        holders = monitor.dgpu_holders() if awake else []
        for r in self.holder_rows:
            self.holders_group.remove(r)
        self.holder_rows = []
        if not holders:
            r = Adw.ActionRow(title="GPU is asleep" if not awake else "None found",
                              subtitle="Nothing to do" if not awake else "It should sleep shortly")
            self.holders_group.add(r)
            self.holder_rows.append(r)
            return
        for pid, name in holders:
            r = Adw.ActionRow(title=name, subtitle=f"PID {pid}")
            if name not in ("gnome-shell", "Xwayland"):
                b = Gtk.Button(label="Quit", valign=Gtk.Align.CENTER)
                b.connect("clicked", self.on_quit_holder, pid, name)
                r.add_suffix(b)
            else:
                r.set_subtitle(f"PID {pid} · desktop, normal")
            self.holders_group.add(r)
            self.holder_rows.append(r)

    def _load_settings(self, s):
        self.loading = True
        self.w_boost.set_active(s["boost"])
        self.w_freq.set_value(s["max_freq_mhz"] or 4465)
        self.w_gov.set_selected(GOVERNORS.index(s["governor"]) if s["governor"] in GOVERNORS else 0)
        self.w_epp.set_selected(EPPS.index(s["epp"]) if s["epp"] in EPPS else 0)
        self.w_prof.set_selected(PLATFORM.index(s["platform_profile"]) if s["platform_profile"] in PLATFORM else 0)
        self.w_dboost.set_active(s["dynamic_boost"])
        self.w_smt.set_active(s["smt"])
        if s["charge_limit"]:
            self.w_charge.set_value(s["charge_limit"])
        if self.gpu_info:
            self.w_gpuw.set_value(self.gpu_info["limit"])
        self._update_hints()
        self.loading = False
        self.dirty.clear()
        self._update_apply()

    def on_change(self, *args):
        key = args[-1]
        if self.loading:
            return
        self.dirty.add(key)
        self.mode_label.set_label("Mode: Custom (not applied yet)")
        self._update_hints()
        self._update_apply()

    def _update_hints(self):
        perf_gov = GOVERNORS[self.w_gov.get_selected()] == "performance"
        self.w_epp.set_sensitive(not perf_gov)
        if not self.w_boost.get_active() and self.w_freq.get_value() > NOMINAL_MHZ:
            self.w_freq.set_subtitle(f"Boost is off: the CPU stays at or below {NOMINAL_MHZ} MHz")
        else:
            self.w_freq.set_subtitle("")

    def _update_apply(self):
        self.b_apply.set_sensitive(bool(self.dirty))
        self.b_revert.set_sensitive(bool(self.dirty))

    def _manual_settings(self):
        values = {
            "boost": self.w_boost.get_active(),
            "max_freq_mhz": int(self.w_freq.get_value()),
            "governor": GOVERNORS[self.w_gov.get_selected()],
            "epp": EPPS[self.w_epp.get_selected()],
            "platform_profile": PLATFORM[self.w_prof.get_selected()],
            "dynamic_boost": self.w_dboost.get_active(),
            "gpu_power_w": int(self.w_gpuw.get_value()),
            "gpu_max_clock_mhz": int(self.w_gpuclk.get_value()) or "default",
            "smt": self.w_smt.get_active(),
            "charge_limit": int(self.w_charge.get_value()),
        }
        keys = set(self.dirty)
        if "governor" in keys and values["governor"] == "powersave":
            keys.add("epp")
        if values["governor"] == "performance":
            keys.discard("epp")
        if "boost" in keys:
            keys.add("max_freq_mhz")
        return {k: values[k] for k in keys}

    def on_apply(self, *_):
        self.run_helper(["apply", json.dumps(self._manual_settings())], "Custom")

    def on_preset(self, _btn, name):
        if name == "Stock":
            self.run_helper(["stock"], "Stock")
            return
        p = self.profiles[name]
        if name == "Max Performance":
            d = Adw.AlertDialog(heading="Max Performance?",
                                body="This removes all limits. It is the configuration in which the "
                                     "restarts happened. Fans stay under zenfan control.")
            d.add_response("cancel", "Cancel")
            d.add_response("ok", "Enable")
            d.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)
            d.connect("response", lambda _d, r: r == "ok" and self.run_helper(
                ["apply", json.dumps(p["settings"])], name))
            d.present(self)
            return
        self.run_helper(["apply", json.dumps(p["settings"])], name)

    def on_quit_holder(self, _b, pid, name):
        try:
            os.kill(pid, 15)
            self.toast(f"Asked {name} to quit")
        except OSError as e:
            self.toast(f"Could not stop {name}: {e.strerror}")

    def run_helper(self, args, mode):
        if not os.path.exists(HELPER):
            self.toast("Helper not installed. Run install.sh first.")
            return
        self.b_apply.set_sensitive(False)

        def work():
            r = subprocess.run(["pkexec", HELPER] + args, capture_output=True, text=True)
            GLib.idle_add(self._helper_done, r, mode)
        threading.Thread(target=work, daemon=True).start()

    def _helper_done(self, r, mode):
        if r.returncode in (126, 127) and not r.stdout:
            self.toast("Authorization cancelled")
            self._update_apply()
            return
        try:
            res = json.loads(r.stdout)
        except ValueError:
            self.toast(f"Helper error: {(r.stderr or r.stdout).strip()[:120]}")
            self._update_apply()
            return
        failed = {k: v["error"] for k, v in res.items() if not v.get("ok")}
        desc = self.profiles.get(mode, {}).get("note", "")
        self.mode_label.set_label(f"Mode: {mode}" + (f" · {desc}" if desc else ""))
        if failed:
            msg = "; ".join(f"{LABELS.get(k, k)}: {e}" for k, e in failed.items())
            self.toast(f"Applied with problems: {msg}", timeout=8)
        else:
            self.toast(f"{mode} applied")
        self.refresh(load_settings=True)
        return False

    def toast(self, text, timeout=3):
        self.toasts.add_toast(Adw.Toast(title=GLib.markup_escape_text(text), timeout=timeout))


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id="org.zencontrol.ZenControl")

    def do_activate(self):
        (self.props.active_window or Window(self)).present()


if __name__ == "__main__":
    App().run(sys.argv)
