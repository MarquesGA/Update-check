from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from pathlib import Path


def command(args: list[str]) -> str:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=5, check=False)
        return proc.stdout if proc.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def detect() -> dict:
    cpu_out = command(["lscpu"])
    cpu = {key.strip(): value.strip() for line in cpu_out.splitlines() if ":" in line
           for key, value in [line.split(":", 1)]}
    cpuinfo = {}
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                cpuinfo.setdefault(key.strip(), value.strip())
    except OSError:
        pass
    model = (cpu.get("Model name") or cpu.get("Nome do modelo") or
             cpuinfo.get("model name") or cpuinfo.get("Model name") or
             platform.processor() or "Não identificado")
    cores = cpu.get("Core(s) per socket") or cpu.get("Núcleo(s) por soquete")
    if not cores:
        pairs = set()
        try:
            physical = core = None
            for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines() + [""]:
                if not line.strip():
                    if physical is not None and core is not None:
                        pairs.add((physical, core))
                    physical = core = None
                elif ":" in line:
                    key, value = (part.strip() for part in line.split(":", 1))
                    if key == "physical id": physical = value
                    elif key == "core id": core = value
            cores = str(len(pairs)) if pairs else ""
        except OSError:
            cores = ""
    os_info = {}
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                os_info[key] = value.strip().strip('"')
    except OSError:
        pass

    pci = command(["lspci", "-k", "-nn"])
    gpus, current = [], None
    for line in pci.splitlines():
        if re.search(r"VGA compatible controller|3D controller|Display controller", line, re.I):
            current = {"device": line.split(": ", 1)[-1], "driver": None}
            gpus.append(current)
        elif current and "Kernel driver in use:" in line:
            current["driver"] = line.split(":", 1)[1].strip()
        elif current and line and not line[0].isspace():
            current = None

    mem = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            mem[key] = int(value.strip().split()[0]) * 1024
    except (OSError, ValueError):
        pass
    try:
        fs = command(["findmnt", "-n", "-o", "FSTYPE", "/"]).strip()
    except Exception:
        fs = ""
    return {
        "cpu": model,
        "cores": cores or str(os.cpu_count() or ""),
        "threads": cpu.get("CPU(s)") or cpu.get("CPU(s) online") or str(os.cpu_count() or ""),
        "memory_bytes": mem.get("MemTotal"),
        "gpus": gpus,
        "kernel": platform.release(),
        "distribution": os_info.get("PRETTY_NAME", platform.system()),
        "desktop": os.environ.get("XDG_CURRENT_DESKTOP", "Não identificado"),
        "session": os.environ.get("XDG_SESSION_TYPE", "Não identificado"),
        "filesystem": fs or "Não identificado",
        "tools": {"lscpu": bool(shutil.which("lscpu")), "lspci": bool(shutil.which("lspci")),
                  "findmnt": bool(shutil.which("findmnt"))},
    }
