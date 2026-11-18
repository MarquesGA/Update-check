from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

CATEGORIES = {
    "kernel": ("linux", "kernel", "initramfs", "boot"),
    "gpu": ("mesa", "vulkan", "opengl", "nvidia", "amd", "amdgpu", "intel graphics"),
    "desktop": ("plasma", "kde", "wayland", "xorg", "kwin"),
    "audio": ("pipewire", "wireplumber", "alsa", "audio"),
    "network": ("networkmanager", "wifi", "bluetooth"),
    "security": ("security", "vulnerability", "cve-"),
}


def _is_recent(value: str) -> bool:
    if not value:
        return False
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            stamp = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return False
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp >= datetime.now(timezone.utc) - timedelta(days=180)


def correlate(package: str, publications: list[dict]) -> dict:
    pkg = package.lower()
    related = []
    for item in publications:
        text = (item.get("title", "") + " " + item.get("content", "")).lower()
        if re.search(r"(?<![a-z0-9@._+:-])" + re.escape(pkg) + r"(?![a-z0-9@._+:-])", text):
            related.append(item)
    resolved = [item for item in related if item.get("resolution") == "fixed"]
    unresolved = [item for item in related if item.get("resolution") != "fixed"]
    if not related:
        return {"risk": "normal", "report_count": 0,
                "summary": "Nenhum relato correlacionado no histórico coletado; isso não garante ausência de problemas.",
                "resolved_count": 0, "resolved_publications": [], "publications": []}
    if not unresolved:
        return {"risk": "normal", "report_count": 0, "resolved_count": len(resolved),
                "summary": f"Os {len(resolved)} relato(s) correlacionado(s) estão marcados como concluídos no GitHub. Confira a correção e a versão mencionada na fonte original antes de atualizar.",
                "resolved_publications": resolved, "publications": []}
    recent = sum(1 for item in unresolved if _is_recent(item.get("published_at") or ""))
    source_count = len({item.get("source_id") for item in unresolved if item.get("source_id") is not None})
    if len(unresolved) >= 5 and recent >= 3 and source_count >= 2:
        risk = "critical"
    elif len(unresolved) >= 3 or recent >= 2:
        risk = "attention"
    else:
        risk = "informative"
    topics = sorted({cat for cat, terms in CATEGORIES.items()
                     if any(term in (item.get("title", "") + " " + item.get("content", "")).lower()
                            for item in unresolved for term in terms)})
    summary = f"{len(unresolved)} relato(s) sem correção confirmada menciona(m) exatamente {package}."
    if resolved:
        summary += f" {len(resolved)} relato(s) foi/foram marcado(s) como concluído(s) no GitHub; confira a versão corretiva na fonte."
    if topics:
        summary += " Temas relacionados: " + ", ".join(topics) + "."
    return {"risk": risk, "report_count": len(unresolved), "resolved_count": len(resolved),
            "summary": summary, "publications": unresolved,
            "resolved_publications": resolved, "categories": topics}
