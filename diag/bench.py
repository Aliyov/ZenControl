#!/usr/bin/env python3
"""usage: bench.py OUT_DIR BIN_DIR [MODE ...]"""
import json
import os
import re
import statistics
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))
import monitor

OUT, BIN = sys.argv[1], sys.argv[2]
MODES = sys.argv[3:] or ["Extreme Powersave", "Balanced", "Performance", "Max Performance"]
HELPER = "/usr/local/libexec/zencontrol-helper"
PROFILES = json.load(open(os.path.join(ROOT, "data", "profiles.json")))
NV = {**os.environ, "__NV_PRIME_RENDER_OFFLOAD": "1", "__GLX_VENDOR_LIBRARY_NAME": "nvidia",
      "vblank_mode": "0", "__GL_SYNC_TO_VBLANK": "0"}
VK_DEV = "5d0e40cef77df5af6f9c57eeaf41849b"
ABORT_CPU, ABORT_GPU = 95, 87
os.makedirs(OUT, exist_ok=True)
RESULTS = os.path.join(OUT, "results.jsonl")
LOG = open(os.path.join(OUT, "sensors.csv"), "a", buffering=1)


class Sampler(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.samples = []
        self.aborted = None

    def run(self):
        LOG.write("t,tctl,cpu_w,cpu_mhz,gpu_t,gpu_w,gpu_mhz,fan_cpu,fan_gpu\n")
        while True:
            s = monitor.snapshot()
            g = monitor.gpu_query() or {}
            f = [x for x in s["freqs"] if x]
            row = (time.time(), s["tctl"], s["apu_w"], sum(f) / len(f), g.get("temp"), g.get("watts"),
                   g.get("mhz"), s["fan_cpu"], s["fan_gpu"])
            self.samples.append(row)
            LOG.write(",".join("" if v is None else f"{v:.2f}" for v in row) + "\n")
            os.fsync(LOG.fileno())
            if (s["tctl"] or 0) >= ABORT_CPU or (g.get("temp") or 0) >= ABORT_GPU:
                self.aborted = f"Tctl {s['tctl']} / GPU {g.get('temp')}"
                for p in ("stress", "gpuburn", "glmark2", "vkmark", "hashcat", "7z", "ffmpeg", "openssl"):
                    subprocess.run(["pkill", "-x", p])
            time.sleep(1)

    def stats(self, t0, t1):
        rows = [r for r in self.samples if t0 <= r[0] <= t1]

        def agg(i, name):
            v = [r[i] for r in rows if r[i] is not None]
            return {f"{name}_avg": round(statistics.mean(v), 1), f"{name}_max": round(max(v), 1)} if v else {}
        out = {}
        for i, n in ((1, "cpu_temp"), (2, "cpu_w"), (3, "cpu_mhz"), (4, "gpu_temp"), (5, "gpu_w"),
                     (6, "gpu_mhz"), (7, "fan_cpu"), (8, "fan_gpu")):
            out.update(agg(i, n))
        return out


SAMPLER = Sampler()


def helper(*args):
    return json.loads(subprocess.run(["pkexec", HELPER, *args], capture_output=True, text=True).stdout)


def gpu_temp():
    g = monitor.gpu_query()
    return g["temp"] if g else 0


def cooldown(cpu=55, gpu=50, limit=240):
    t = time.time()
    while time.time() - t < limit:
        if (monitor.snapshot()["tctl"] or 0) <= cpu and gpu_temp() <= gpu:
            break
        time.sleep(3)
    time.sleep(5)


def sh(cmd, env=None, timeout=900):
    return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout)


def last_k(out, prefix):
    for line in reversed(out.splitlines()):
        if line.lower().startswith(prefix.lower()):
            return float(line.split()[-1].rstrip("k")) / 1000
    raise ValueError(f"no {prefix} line")


def t_python():
    code = "import hashlib\nx=b'z'\nfor i in range(9_000_000): x=hashlib.md5(x).digest()\ns=0\nfor i in range(60_000_000): s+=i*i%7"
    t = time.time()
    sh([sys.executable, "-c", code])
    return {"seconds": round(time.time() - t, 2)}


def t_sha256_1t():
    return {"MB_s": round(last_k(sh(["openssl", "speed", "-seconds", "30", "-bytes", "16384", "sha256"]).stdout, "sha256"), 1)}


def t_sha256_16t():
    r = sh(["openssl", "speed", "-multi", "16", "-seconds", "45", "-bytes", "16384", "sha256"])
    return {"MB_s": round(last_k(r.stdout, "sha256"), 1)}


def t_aes_16t():
    r = sh(["openssl", "speed", "-multi", "16", "-seconds", "45", "-bytes", "16384", "-evp", "aes-256-gcm"])
    return {"MB_s": round(last_k(r.stdout, "AES-256-GCM"), 1)}


def t_7zip():
    out = sh(["7z", "b", "8", "-mmt16"]).stdout
    tot = next(l for l in out.splitlines() if l.startswith("Tot:")).split()
    return {"MIPS": int(tot[-1])}


def t_ffmpeg():
    frames = 3000
    t = time.time()
    r = sh(["ffmpeg", "-hide_banner", "-nostdin", "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=60",
            "-frames:v", str(frames), "-c:v", "libx264", "-preset", "medium", "-f", "null", "-"])
    dt = time.time() - t
    if r.returncode:
        raise RuntimeError(r.stderr[-200:])
    return {"seconds": round(dt, 1), "fps": round(frames / dt, 1)}


def t_glmark2():
    scenes = ["build:use-vbo=true", "texture", "shading:shading=phong", "bump:bump-render=normals",
              "effect2d", "jellyfish", "terrain", "refract"]
    cmd = ["glmark2", "--off-screen", "-s", "1920x1080"]
    for s in scenes:
        cmd += ["-b", f"{s}:duration=15"]
    out = sh(cmd, env=NV).stdout
    fps = {m.group(1): int(m.group(2)) for m in re.finditer(r"\[(\w+)\].*?FPS: (\d+)", out)}
    return {"score": int(re.search(r"Score: (\d+)", out).group(1)), "scene_fps": fps}


def vkmark(scenes, duration):
    cmd = ["vkmark", "-D", VK_DEV, "-s", "1920x1080", "-p", "mailbox"]
    for s in scenes:
        cmd += ["-b", f"{s}:duration={duration}"]
    out = sh(cmd).stdout
    fps = {m.group(1): int(m.group(2)) for m in re.finditer(r"\[(\w+)\].*?FPS: (\d+)", out)}
    return {"score": int(re.search(r"Score: (\d+)", out).group(1)), "scene_fps": fps}


def t_vkmark():
    return vkmark(["vertex", "texture", "shading", "cube", "effect2d", "desktop"], 20)


def hashcat(m, target):
    out = sh(["hashcat", "-m", str(m), "-a", "3", "-D", "2", "-w", "3", "--potfile-disable", "--quiet",
              "--status", "--status-json", "--status-timer", "5", "--runtime", "90", target,
              "?a?a?a?a?a?a?a?a?a"]).stdout
    speeds = [sum(d["speed"] for d in j["devices"]) for j in
              (json.loads(l) for l in out.splitlines() if l.startswith("{"))]
    steady = speeds[3:] or speeds
    return {"GH_s": round(statistics.mean(steady) / 1e9, 3), "GH_s_first": round(speeds[0] / 1e9, 3)}


def t_hashcat_md5():
    return hashcat(0, "5d41402abc4b2a76b9719d911017c592")


def t_hashcat_sha256():
    return hashcat(1400, "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824")


def t_cuda():
    out = sh([f"{BIN}/gpuburn", "90"]).stdout
    return {"GFLOPS": float(re.search(r"GFLOPS ([\d.]+)", out).group(1))}


def t_gaming():
    load = subprocess.Popen([f"{BIN}/stress", "fma", "200", "8"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        return vkmark(["shading", "cube", "texture"], 45)
    finally:
        load.kill()
        load.wait()


def t_sustained():
    t0 = time.time()
    out = sh([f"{BIN}/stress", "fma", "180", "16"]).stdout
    rows = [r for r in SAMPLER.samples if r[0] >= t0]
    first = [r[3] for r in rows if r[0] - t0 <= 15]
    last = [r[3] for r in rows if r[0] - t0 >= 150]
    m = re.search(r"iters=(\d+) errors=(\d+)", out)
    return {"iterations": int(m.group(1)), "errors": int(m.group(2)),
            "mhz_first_15s": round(statistics.mean(first)), "mhz_last_30s": round(statistics.mean(last))}


def t_gaming_gl():
    load = subprocess.Popen([f"{BIN}/stress", "fma", "200", "4"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        cmd = ["glmark2", "--off-screen", "-s", "1920x1080"]
        for sc in ("terrain", "jellyfish", "refract", "shading:shading=phong"):
            cmd += ["-b", f"{sc}:duration=30"]
        out = sh(cmd, env=NV).stdout
        fps = {m.group(1): int(m.group(2)) for m in re.finditer(r"\[(\w+)\].*?FPS: (\d+)", out)}
        return {"score": int(re.search(r"Score: (\d+)", out).group(1)), "scene_fps": fps}
    finally:
        load.kill()
        load.wait()


def t_idle():
    time.sleep(25)
    return {}


TESTS = [
    ("idle", "Idle (25 s)", t_idle),
    ("python", "Python single-thread", t_python),
    ("sha256_1t", "OpenSSL SHA-256, 1 thread", t_sha256_1t),
    ("sha256_16t", "OpenSSL SHA-256, 16 threads", t_sha256_16t),
    ("aes_16t", "OpenSSL AES-256-GCM, 16 threads", t_aes_16t),
    ("7zip", "7-Zip benchmark, 16 threads", t_7zip),
    ("ffmpeg", "ffmpeg x264 1080p encode", t_ffmpeg),
    ("sustained", "Sustained AVX2 load, 16 threads, 3 min", t_sustained),
    ("glmark2", "glmark2 OpenGL 1080p", t_glmark2),
    ("hashcat_md5", "hashcat MD5 (GPU)", t_hashcat_md5),
    ("hashcat_sha256", "hashcat SHA-256 (GPU)", t_hashcat_sha256),
    ("cuda", "CUDA FMA compute", t_cuda),
    ("gaming_gl", "Gaming-like: glmark2 heavy scenes + 4-thread CPU load", t_gaming_gl),
]


def record(entry):
    with open(RESULTS, "a") as f:
        f.write(json.dumps(entry) + "\n")
        f.flush()
        os.fsync(f.fileno())


def main():
    only = os.environ.get("BENCH_TESTS")
    tests = [t for t in TESTS if not only or t[0] in only.split(",")]
    SAMPLER.start()
    ac = monitor.snapshot()["ac"]
    print(f"AC: {ac}", flush=True)
    for mode in MODES:
        res = helper("apply", json.dumps(PROFILES[mode]["settings"]))
        bad = {k: v["error"] for k, v in res.items() if not v["ok"]}
        print(f"\n=== {mode}  {'apply OK' if not bad else bad}", flush=True)
        for key, name, fn in tests:
            cooldown()
            if SAMPLER.aborted:
                print("aborted earlier, stopping", flush=True)
                return
            t0 = time.time()
            try:
                metrics, err = fn(), None
            except Exception as e:
                metrics, err = {}, str(e)[:200]
            t1 = time.time()
            entry = {"mode": mode, "ac": ac, "test": key, "name": name, "duration": round(t1 - t0, 1),
                     **metrics, "sensors": SAMPLER.stats(t0, t1)}
            if err:
                entry["error"] = err
            if SAMPLER.aborted:
                entry["aborted"] = SAMPLER.aborted
            record(entry)
            print(f"{name:42s} {json.dumps({k: v for k, v in entry.items() if k not in ('sensors', 'mode', 'ac', 'test', 'name')})}"
                  f"  cpu {entry['sensors'].get('cpu_temp_avg')}/{entry['sensors'].get('cpu_temp_max')}°C"
                  f"  gpu {entry['sensors'].get('gpu_temp_avg')}/{entry['sensors'].get('gpu_temp_max')}°C", flush=True)
    helper("apply", json.dumps(PROFILES["Balanced"]["settings"]))
    print("\nDONE, back on Balanced", flush=True)


if __name__ == "__main__":
    main()
