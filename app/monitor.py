"""Read-only sensor access."""
import glob
import os
import subprocess

CPU = "/sys/devices/system/cpu"
DGPU = "/sys/bus/pci/devices/0000:01:00.0"


def read(path, default=None):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def num(path, div=1, default=None):
    v = read(path)
    try:
        return int(v) / div
    except (TypeError, ValueError):
        return default


def _hwmons():
    out = {}
    for d in glob.glob("/sys/class/hwmon/hwmon*"):
        n = read(f"{d}/name")
        if n:
            out.setdefault(n, d)
    return out


HW = _hwmons()


def ncpus():
    return len(glob.glob(f"{CPU}/cpu[0-9]*/cpufreq"))


def cpu_freqs_mhz():
    res = []
    for i in range(os.cpu_count() or 16):
        f = num(f"{CPU}/cpu{i}/cpufreq/cpuinfo_avg_freq", 1000)
        if f is None:
            f = num(f"{CPU}/cpu{i}/cpufreq/scaling_cur_freq", 1000)
        res.append(f)
    return res


def dgpu_awake():
    return read(f"{DGPU}/power/runtime_status") == "active"


def dgpu_holders():
    found = []
    for fd_dir in glob.glob("/proc/[0-9]*/fd"):
        try:
            for fd in os.listdir(fd_dir):
                t = os.readlink(f"{fd_dir}/{fd}")
                if t.startswith("/dev/nvidia") and t[11:].isdigit():
                    pid = int(fd_dir.split("/")[2])
                    found.append((pid, read(f"/proc/{pid}/comm", "?")))
                    break
        except OSError:
            continue
    return found


def gpu_query():
    if not dgpu_awake():
        return None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu,power.draw,clocks.gr,power.limit",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3).stdout.strip()
        t, w, c, lim = (x.strip() for x in out.split(","))
        return {"temp": float(t), "watts": float(w), "mhz": float(c), "limit": float(lim)}
    except Exception:
        return None


def snapshot():
    bat = "/sys/class/power_supply/BAT0"
    p0 = f"{CPU}/cpufreq/policy0"
    return {
        "tctl": num(f"{HW.get('k10temp')}/temp1_input", 1000),
        "apu_w": num(f"{HW.get('amdgpu')}/power1_input", 1e6),
        "fan_cpu": num(f"{HW.get('asus')}/fan1_input"),
        "fan_gpu": num(f"{HW.get('asus')}/fan2_input"),
        "bat_status": read(f"{bat}/status"),
        "bat_pct": num(f"{bat}/capacity"),
        "bat_w": num(f"{bat}/power1_input", 1e6) if os.path.exists(f"{bat}/power1_input")
                 else num(f"{HW.get('BAT0')}/power1_input", 1e6),
        "bat_energy_wh": num(f"{bat}/energy_now", 1e6),
        "ac": read("/sys/class/power_supply/AC0/online") == "1",
        "freqs": cpu_freqs_mhz(),
        "dgpu_awake": dgpu_awake(),
        "zenfan": read("/run/zenfan/boost", "not running"),
        "zenfan_conf": read("/etc/zenfan/boost.conf", ""),
        "governor": read(f"{p0}/scaling_governor"),
        "epp": read(f"{p0}/energy_performance_preference"),
        "boost": read(f"{CPU}/cpufreq/boost") == "1",
        "max_freq_mhz": num(f"{p0}/scaling_max_freq", 1000),
        "hw_max_mhz": num(f"{p0}/cpuinfo_max_freq", 1000),
        "hw_floor_mhz": num(f"{p0}/amd_pstate_lowest_nonlinear_freq", 1000),
        "platform_profile": read("/sys/firmware/acpi/platform_profile"),
        "smt": read(f"{CPU}/smt/control") == "on",
        "charge_limit": num(f"{bat}/charge_control_end_threshold"),
        "dynamic_boost": subprocess.run(["systemctl", "is-active", "--quiet", "nvidia-powerd"]).returncode == 0,
    }
