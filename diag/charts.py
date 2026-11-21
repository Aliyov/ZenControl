#!/usr/bin/env python3
"""usage: charts.py RESULTS_DIR"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

D = sys.argv[1]
MODES = ["Extreme Powersave", "Balanced", "Performance", "Max Performance"]
COLORS = ["#9ec5f4", "#5598e7", "#256abf", "#104281"]
INK, INK2, GRID, BG = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
plt.rcParams.update({"font.family": "sans-serif", "font.size": 10, "text.color": INK, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK, "axes.edgecolor": GRID, "figure.facecolor": BG,
                     "axes.facecolor": BG, "savefig.facecolor": BG})

R, T = {}, {}
for line in open(os.path.join(D, "results.jsonl")):
    r = json.loads(line)
    if "error" not in r and "aborted" not in r:
        R[(r["mode"], r["test"])] = r
    if r["duration"] > 3 and r["test"] != "gaming":
        T[(r["mode"], r["test"])] = r

TESTS = [  # key, label, metric, higher_is_better
    ("python", "Python single-thread", "seconds", False),
    ("sha256_1t", "SHA-256, 1 thread", "MB_s", True),
    ("sha256_16t", "SHA-256, 16 threads", "MB_s", True),
    ("aes_16t", "AES-256-GCM, 16 threads", "MB_s", True),
    ("7zip", "7-Zip, 16 threads", "MIPS", True),
    ("ffmpeg", "x264 1080p encode", "fps", True),
    ("sustained", "Sustained AVX2, 3 min", "iterations", True),
    ("glmark2", "glmark2 OpenGL", "score", True),
    ("gaming_gl", "Gaming-like (GPU + 4 CPU threads)", "score", True),
    ("hashcat_md5", "hashcat MD5", "GH_s", True),
    ("hashcat_sha256", "hashcat SHA-256", "GH_s", True),
    ("cuda", "CUDA compute", "GFLOPS", True),
]
TESTS = [t for t in TESTS if any((m, t[0]) in R for m in MODES)]


def style(ax):
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def legend(fig, ax):
    h = [plt.Rectangle((0, 0), 1, 1, color=c) for c in COLORS]
    fig.legend(h, MODES, loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 0.985))


def relative():
    tests = [t for t in TESTS if ("Max Performance", t[0]) in R]
    n = len(tests)
    fig, ax = plt.subplots(figsize=(9, 0.62 * n + 1.4))
    bh = 0.19
    for i, (key, label, metric, hib) in enumerate(tests):
        ref = R.get(("Max Performance", key))
        for j, m in enumerate(MODES):
            r = R.get((m, key))
            if not r or not ref:
                continue
            v, rv = r[metric], ref[metric]
            pct = 100 * (v / rv if hib else rv / v)
            y = i + (j - 1.5) * (bh + 0.02)
            ax.barh(y, pct, height=bh, color=COLORS[j], linewidth=0)
            ax.text(pct + 1, y, f"{pct:.0f}%", va="center", fontsize=7.5, color=INK2)
    ax.set_yticks(range(n), [t[1] for t in tests])
    ax.invert_yaxis()
    ax.set_xlim(0, 118)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xlabel("Speed relative to Max Performance (100% = Max Performance)")
    style(ax)
    legend(fig, ax)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(os.path.join(D, "relative.png"), dpi=140)


def temps():
    keys = [t for t in TESTS if t[0] not in ("python", "sha256_1t")]
    fig, axes = plt.subplots(1, 2, figsize=(10, 0.5 * len(keys) + 1.6), sharey=True)
    for ax, (field, title) in zip(axes, (("cpu_temp_max", "Max CPU temperature (°C)"),
                                         ("gpu_temp_max", "Max GPU temperature (°C)"))):
        for i, (key, label, *_ ) in enumerate(keys):
            for j, m in enumerate(MODES):
                r = T.get((m, key))
                if r and field in r["sensors"]:
                    ax.plot(r["sensors"][field], i, "o", color=COLORS[j], markersize=8,
                            markeredgecolor=BG, markeredgewidth=2)
        ax.set_title(title, fontsize=10, color=INK, loc="left")
        ax.set_yticks(range(len(keys)), [k[1] for k in keys])
        ax.invert_yaxis() if ax is axes[0] else None
        style(ax)
        ax.grid(axis="y", color=GRID, linewidth=0.5)
    axes[0].set_xlim(45, 100)
    axes[0].axvline(95, color="#e34948", linewidth=1, linestyle="--")
    axes[0].text(95.5, len(keys) - 0.6, "95 °C\nstop", fontsize=7.5, color=INK2, va="bottom")
    axes[1].set_xlim(45, 80)
    legend(fig, axes[0])
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(os.path.join(D, "temperatures.png"), dpi=140)


def efficiency():
    rows = [("sha256_16t", "SHA-256 16 threads\n(MB/s per CPU watt)", "MB_s", "cpu_w_avg"),
            ("7zip", "7-Zip\n(MIPS per CPU watt)", "MIPS", "cpu_w_avg"),
            ("cuda", "CUDA\n(GFLOPS per GPU watt)", "GFLOPS", "gpu_w_avg"),
            ("hashcat_md5", "hashcat MD5\n(MH/s per GPU watt)", "GH_s", "gpu_w_avg")]
    fig, axes = plt.subplots(1, 4, figsize=(11, 3.4))
    for ax, (key, title, metric, watt) in zip(axes, rows):
        vals = []
        for m in MODES:
            r = R.get((m, key))
            vals.append(r[metric] * (1000 if metric == "GH_s" else 1) / r["sensors"][watt] if r else 0)
        ax.bar(range(4), vals, color=COLORS, width=0.7, linewidth=0)
        for x, v in enumerate(vals):
            ax.text(x, v, f"{v:.0f}", ha="center", va="bottom", fontsize=8, color=INK2)
        ax.set_title(title, fontsize=9, color=INK)
        ax.set_xticks([])
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.set_yticks([])
    legend(fig, axes[0])
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    fig.savefig(os.path.join(D, "efficiency.png"), dpi=140)


relative()
temps()
efficiency()
print("charts written")
