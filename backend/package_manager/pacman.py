from __future__ import annotations

import os
import re
import shutil
import subprocess


LINE = re.compile(r"^(?P<name>[A-Za-z0-9@._+:-]+)\s+(?P<old>\S+)\s*->\s*(?P<new>\S+)\s*$")
SIZE = re.compile(r"^(?P<amount>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>B|KiB|MiB|GiB)?$", re.I)


def parse_checkupdates(output: str) -> list[dict[str, str]]:
    result = []
    for line in output.splitlines():
        match = LINE.match(line.strip())
        if match:
            result.append({"name": match["name"], "installed_version": match["old"],
                           "available_version": match["new"], "repository": "official"})
    return result


def parse_download_sizes(output: str) -> dict[str, int]:
    sizes, package = {}, None
    units = {None: 1, "B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3}
    for line in output.splitlines():
        key, sep, value = line.partition(":")
        if not sep:
            continue
        if key.strip() == "Name":
            package = value.strip()
        elif key.strip() == "Download Size" and package:
            match = SIZE.match(value.strip())
            if match:
                unit = match["unit"]
                if unit:
                    unit = "B" if unit.lower() == "b" else unit[0].upper() + unit[1:]
                sizes.setdefault(package, int(float(match["amount"]) * units.get(unit, 1)))
    return sizes


def get_download_sizes(packages: list[str]) -> dict[str, int]:
    pacman = shutil.which("pacman")
    if not pacman or not packages:
        return {}
    try:
        proc = subprocess.run([pacman, "-Si", *packages], capture_output=True, text=True,
                              timeout=20, check=False, env={**os.environ, "LC_ALL": "C"})
    except (OSError, subprocess.TimeoutExpired):
        return {}
    return parse_download_sizes(proc.stdout)


def get_updates() -> tuple[list[dict[str, str]], str | None]:
    executable = shutil.which("checkupdates")
    packages: list[dict[str, str]] = []
    errors = []
    if executable:
        try:
            proc = subprocess.run([executable], capture_output=True, text=True, timeout=90, check=False)
            if proc.returncode in (0, 2):
                packages.extend(parse_checkupdates(proc.stdout))
            else:
                errors.append(proc.stderr.strip() or f"checkupdates encerrou com código {proc.returncode}")
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f"Falha ao consultar checkupdates: {exc}")
    else:
        errors.append("checkupdates não encontrado (instale pacman-contrib)")

    # paru/yay query mode: no sync, install, or privileged command is issued.
    helper = next(((name, shutil.which(name)) for name in ("paru", "yay") if shutil.which(name)), None)
    if helper:
        name, path = helper
        try:
            proc = subprocess.run([path, "-Qua"], capture_output=True, text=True, timeout=90, check=False)
            if proc.returncode == 0:
                for item in parse_checkupdates(proc.stdout):
                    item["repository"] = "AUR"
                    if all(existing["name"] != item["name"] for existing in packages):
                        packages.append(item)
            elif proc.returncode not in (1, 2):
                errors.append(proc.stderr.strip() or f"{name} encerrou com código {proc.returncode}")
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f"Falha ao consultar {name}: {exc}")
    sizes = get_download_sizes([p["name"] for p in packages if p["repository"] == "official"])
    for package in packages:
        package["download_size"] = sizes.get(package["name"])
    return packages, "; ".join(errors) if errors else None
