#!/usr/bin/env python3
"""usage: logger.py OUT.csv ABORT_TCTL_C"""
import glob
import os
import subprocess
import sys
import time

out, abort_t = sys.argv[1], float(sys.argv[2])


def rd(p, d=1):
    try:
        return int(open(p).read()) / d
    except Exception:
        return -1


hw = {open(h + "/name").read().strip(): h for h in glob.glob("/sys/class/hwmon/hwmon*")}
f = open(out, "a", buffering=1)
t0 = time.time()
f.write("t,Tctl,edge,PPT_W,BAT_W,fan_cpu,fan_gpu,"
        + ",".join(f"c{i}" for i in range(16))
        + ",gpuT,gpuW,gpuMHz,gpuThr\n")
while True:
    try:
        g = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=temperature.gpu,power.draw,clocks.gr,clocks_throttle_reasons.active",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2).stdout.strip().replace(", ", ",")
    except Exception:
        g = "-1,-1,-1,-1"
    T = rd(hw["k10temp"] + "/temp1_input", 1000)
    fr = [str(int(rd(f"/sys/devices/system/cpu/cpu{i}/cpufreq/cpuinfo_avg_freq", 1000)))
          for i in range(16)]
    f.write(f"{time.time()-t0:.0f},{T:.1f},{rd(hw['amdgpu']+'/temp1_input',1000):.0f},"
            f"{rd(hw['amdgpu']+'/power1_input',1e6):.1f},{rd(hw['BAT0']+'/power1_input',1e6):.1f},"
            f"{rd(hw['asus']+'/fan1_input'):.0f},{rd(hw['asus']+'/fan2_input'):.0f},"
            + ",".join(fr) + "," + g + "\n")
    os.fsync(f.fileno())
    if T >= abort_t:
        f.write(f"ABORT Tctl {T}\n")
        os.fsync(f.fileno())
        subprocess.run(["pkill", "-x", "stress"])
        subprocess.run(["pkill", "-x", "glxgears"])
    time.sleep(1)
