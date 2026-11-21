# ZenControl

CPU and GPU power control for the **ASUS Zenbook UX535QE** on Linux.

ZenControl switches the laptop between performance and power-saving modes with one click, or lets you set each limit by hand. It shows temperatures, clock speeds, power draw, fan speed and battery status live.

<p align="center">
  <img src="screenshots/overview.png" width="420" alt="Quick modes and live sensors">
  <img src="screenshots/controls.png" width="420" alt="Manual, GPU and advanced controls">
</p>

## Contents

- [Hardware](#hardware)
- [Modes](#modes)
- [Live monitoring](#live-monitoring)
- [Manual controls](#manual-controls)
- [NVIDIA GPU controls](#nvidia-gpu-controls)
- [Advanced controls](#advanced-controls)
- [Apps keeping the NVIDIA GPU awake](#apps-keeping-the-nvidia-gpu-awake)
- [Safety](#safety)
- [Installation](#installation)
- [Test results](#test-results)
- [Customizing modes](#customizing-modes)
- [Project layout](#project-layout)
- [Stability testing](#stability-testing)

---

## Hardware

| Component | Details |
|---|---|
| CPU | AMD Ryzen, 8 cores / 16 threads, 1.1–4.465 GHz, `amd-pstate-epp` driver |
| Integrated GPU | AMD Radeon (inside the CPU), used for the desktop and light work |
| Dedicated GPU | NVIDIA GeForce RTX 3050 Ti Laptop GPU, 4 GB, up to 2100 MHz |
| GPU power | 30 W on battery, 35 W on AC, up to 50 W on AC with Dynamic Boost |

The NVIDIA GPU powers off completely when no app is using it, and turns on automatically when a game or GPU app starts.

---

## Modes

Each button applies a full set of settings at once. The first change asks for your password (via polkit). It is remembered for a few minutes.

All changes reset on reboot.

### Summary

| | Max Performance | Performance | Balanced | Extreme Powersave |
|---|---|---|---|---|
| **CPU max frequency** | 4465 MHz | 3200 MHz | 2800 MHz | 1800 MHz |
| **CPU boost** | on | off | off | off |
| **CPU governor** | performance | performance | powersave | powersave |
| **Energy preference (EPP)** | performance | performance | balance_performance | power |
| **ASUS firmware profile** | performance | performance | balanced | quiet |
| **GPU max clock** | no cap (≈1770 MHz) | no cap (≈1770 MHz) | 1400 MHz | 900 MHz |
| **NVIDIA Dynamic Boost** | on | off | off | off |
| **GPU power under full load (AC)** | ≈40 W, limit 50 W | ≈35 W, limit 35 W | ≈28 W | ≈16 W |
| **CPU temp, all cores loaded** | — | 78 °C | 69 °C | 52 °C |

### Max Performance

All limits removed. These are the factory settings.

- **CPU:** boost enabled, up to **4465 MHz** on one or two cores for short bursts. With all cores busy it runs lower, depending on temperature and power.
- **Governor / EPP:** `performance` / `performance`. The CPU stays at high clocks and reacts instantly.
- **ASUS profile:** `performance`, the highest firmware power limits.
- **GPU:** no clock cap, with Dynamic Boost on. On AC the GPU may use up to **50 W**. Measured: 1770 MHz at ≈40 W under full compute load.

**Use for:** demanding games, rendering and compiling, on AC power.

**Note:** this is the highest power and heat configuration. Sudden restarts have been observed with these settings under heavy combined CPU and GPU load, so the app asks for confirmation before enabling it.

### Performance

Near full speed, without CPU boost or GPU Dynamic Boost.

- **CPU:** boost disabled, max **3200 MHz** on all cores. That's about 72 % of peak frequency, but power and heat drop much more than that, because the boost range needs much higher voltage.
- **Governor / EPP:** `performance` / `performance`.
- **ASUS profile:** `performance`.
- **GPU:** no clock cap, Dynamic Boost off. The GPU runs at full clock but within its base power limit: **35 W on AC**, 30 W on battery. Measured: 1770 MHz at ≈35 W.

**Use for:** gaming and heavy work when you want less heat and better stability than Max Performance. Measured 78 °C with all 16 threads loaded.

### Balanced

Moderate performance with lower power draw. Suitable on battery or AC.

- **CPU:** boost disabled, max **2800 MHz**.
- **Governor / EPP:** `powersave` / `balance_performance`. Despite its name, the `powersave` governor is not slow: it raises clocks when there is work and drops them when idle. `balance_performance` makes it ramp up quickly.
- **ASUS profile:** `balanced`.
- **GPU:** capped at **1400 MHz**, Dynamic Boost off. Measured: ≈28 W under full load, versus ≈35 W uncapped.

**Use for:** everyday work, browsing, video, light gaming. Measured 69 °C with all 16 threads loaded.

### Extreme Powersave

Maximum battery life, lowest heat and fan noise.

- **CPU:** boost disabled, max **1800 MHz**.
- **Governor / EPP:** `powersave` / `power`. The CPU prefers low clocks and only ramps up when necessary.
- **ASUS profile:** `quiet`, the lowest firmware power limits.
- **GPU:** capped at **900 MHz**, Dynamic Boost off. Measured: ≈16 W under full load, less than half of Performance.

**Use for:** reading, writing, video playback, and long sessions on battery. Measured 52 °C with all 16 threads loaded, and about 15 W CPU power.

### Stock

The first time any setting is changed, ZenControl saves the current values to `/var/lib/zencontrol/stock.json`. **Stock** restores exactly those values.

On the UX535QE the factory configuration matches Max Performance. A reboot also restores factory settings.

---

## Live monitoring

Updates every 2 seconds.

| Row | Shows |
|---|---|
| **CPU** | Temperature (Tctl), package power in watts, average clock across all threads |
| **Fans (zenfan)** | CPU and GPU fan speed in RPM, and the status reported by the separate `zenfan` fan daemon. ZenControl never changes fan settings. |
| **NVIDIA GPU** | `asleep (0 W)` when powered off. When awake: temperature, current power / power limit, and graphics clock. |
| **Battery** | Charge level. On AC: charging status and charge rate. On battery: current discharge in watts and estimated hours remaining. |

Below the rows, 16 bars show the current clock of each CPU thread. `off` means the thread is disabled (SMT off).

---

## Manual controls

Change any value and press **Apply**. Nothing is changed until then. **Discard changes** reloads the current system values.

| Control | Range | Description |
|---|---|---|
| **CPU boost** | on / off | Allows clocks above the 3.2 GHz base, up to 4465 MHz. Boost clocks need significantly higher voltage, so disabling boost is the most effective way to reduce CPU heat and power. |
| **Max CPU frequency** | 1100–4465 MHz | Upper clock limit for all cores. With boost off, the effective limit is 3200 MHz even if a higher value is set; the app shows a reminder. |
| **Governor** | performance / powersave | `performance` keeps clocks high at all times. `powersave` scales clocks to the workload, and how aggressively depends on the energy preference. |
| **Energy preference (EPP)** | performance, balance_performance, balance_power, power | Tells the CPU how much to favor speed over efficiency. Only adjustable with the `powersave` governor; with `performance` it is fixed to `performance`. |
| **ASUS firmware profile** | performance / balanced / quiet | The laptop's built-in power profile, which sets the firmware's power limits. Fan state is saved before the change and restored right after, so your fan control is unaffected. |

---

## NVIDIA GPU controls

Applying these briefly wakes the GPU if it is asleep. It powers off again once idle.

| Control | Range | Description |
|---|---|---|
| **Dynamic Boost** | on / off | Runs NVIDIA's `nvidia-powerd` service, which moves power from the CPU to the GPU when the CPU is lightly loaded. This raises the GPU limit from 35 W to up to **50 W**. The BIOS only allows it **on AC power**; on battery it has no effect. |
| **GPU power limit** | — | Not adjustable on the UX535QE (the driver reports it as unsupported), so it is disabled in the UI. Use the GPU max clock instead. |
| **GPU max clock** | 300–2100 MHz, 0 = no cap | Caps the graphics clock. This is the effective way to limit GPU power on this laptop. Measured under full load: 900 MHz ≈ 16 W, 1400 MHz ≈ 28 W, uncapped ≈ 35–41 W. |

---

## Advanced controls

| Control | Range | Description |
|---|---|---|
| **SMT** | on / off | Simultaneous multithreading: each of the 8 cores runs 2 threads, 16 in total. Turning it off leaves 8 threads, which slightly reduces power and heat but lowers multi-threaded performance. Applies immediately. Leave it on unless you have a specific reason. |
| **Battery charge limit** | 60–100 % | Stops charging at the chosen level. Keeping a lithium battery at 100 % for long periods speeds up wear, so **80 %** is a good choice if the laptop is usually plugged in. Set 100 % before you need full capacity. |

---

## Apps keeping the NVIDIA GPU awake

An idle but powered-on NVIDIA GPU uses about **6–8 W**, which costs a lot of battery time. It powers off automatically when no app holds it open.

This section lists the processes currently using the NVIDIA GPU:

- **gnome-shell** and **Xwayland** are part of the desktop and are normal.
- Other apps have a **Quit** button, which sends a normal close request (SIGTERM). Save your work in that app first.

The list only appears while the GPU is awake. "GPU is asleep" means nothing is keeping it on.

---

## Safety

- **No permanent changes.** Everything resets on reboot.
- **Limited scope.** It only changes CPU frequency, governor and EPP settings, the ASUS platform profile, NVIDIA clock limits, `nvidia-powerd`, SMT and the charge limit. It never changes fan curves, voltages, SMU/MSR registers, drivers or boot configuration.
- **Validated input.** Every value is checked against the limits the hardware reports. Invalid requests are rejected with an explanation.
- **Minimal privileges.** The GUI runs as your user. Only a small helper (`/usr/local/libexec/zencontrol-helper`) runs as root, through `pkexec`, after you authenticate.
- **No unnecessary GPU wake-ups.** Monitoring reads sensors directly and only calls `nvidia-smi` when the GPU is already awake.

---

## Installation

### Requirements

- Linux with the `amd-pstate` CPU driver (`amd-pstate-epp` for energy preference) and the `asus-wmi` platform profile
- Python 3, GTK 4, libadwaita 1.5+, PyGObject
- polkit (`pkexec`)
- NVIDIA proprietary driver (`nvidia-smi`, and `nvidia-powerd` for Dynamic Boost)

On Fedora:

```sh
sudo dnf install python3-gobject gtk4 libadwaita polkit
```

### Install

```sh
git clone https://github.com/Aliyov/ZenControl.git
cd ZenControl
./install.sh
```

This installs the root helper, the polkit policy and a desktop entry. Launch **ZenControl** from the app menu, or run:

```sh
python3 app/zencontrol.py
```

### Uninstall

```sh
./install.sh uninstall
```

Current settings remain active until the next reboot.

---

## Test results

Tested on a UX535QE on AC power. The GPU was loaded with a CUDA compute workload and the CPU with an AVX2 FMA stress test on all 16 threads, run separately.

| Mode | GPU clock | GPU power | GPU limit | CPU clock, all cores | CPU temp |
|---|---|---|---|---|---|
| Max Performance | 1770 MHz | 40 W | 50 W | 4424 MHz on one core | — |
| Performance | 1770 MHz | 35 W | 35 W | 3169 MHz | 78 °C |
| Balanced | 1395 MHz | 28 W | 35 W | 2795 MHz | 69 °C |
| Extreme Powersave | 900 MHz | 16 W | 35 W | 1777 MHz | 52 °C |

The stress test found no calculation errors in any mode. Max Performance was tested with a single CPU thread only.

Also verified: Dynamic Boost on/off, SMT on/off (16 ↔ 8 threads online), charge limit 80 % / 100 %, Stock restore, and rejection of invalid values.

---

## Customizing modes

Modes are defined in [`data/profiles.json`](data/profiles.json). Edit the values or add a new entry, and it appears as a new button. Available keys:

| Key | Values |
|---|---|
| `governor` | `"performance"`, `"powersave"` |
| `epp` | `"performance"`, `"balance_performance"`, `"balance_power"`, `"power"` |
| `boost` | `true`, `false` |
| `max_freq_mhz` | 1102–4465 |
| `platform_profile` | `"performance"`, `"balanced"`, `"quiet"` |
| `dynamic_boost` | `true`, `false` |
| `gpu_max_clock_mhz` | 300–2100, or `"default"` for no cap |
| `gpu_power_w` | watts, or `"default"` (only on GPUs that support it) |
| `smt` | `true`, `false` |
| `charge_limit` | 60–100 |

Keys that are left out are not changed.

---

## Project layout

```
app/zencontrol.py         GTK app
app/monitor.py            read-only sensor access
helper/zencontrol-helper  root helper, run via pkexec
data/                     polkit policy and mode definitions
diag/                     stress test and sensor logger
install.sh                installer
```

---

## Stability testing

```sh
gcc -O2 -mavx2 -mfma -pthread diag/stress.c -o diag/stress
./diag/stress fma 60 16             # AVX2 FMA load with result checking, 60 s, 16 threads
./diag/stress mem 60 16 256         # memory write/verify, 256 MB per thread
python3 diag/logger.py run.csv 95   # 1 Hz sensor log, stops the load if Tctl reaches 95 °C
```

The logger flushes every line to disk, so the data survives a hard reset.

---

## Disclaimer

Changing power settings is at your own risk. ZenControl is not affiliated with ASUS or NVIDIA.
