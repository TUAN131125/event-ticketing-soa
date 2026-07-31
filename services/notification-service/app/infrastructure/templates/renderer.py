"""Doc va dien du lieu vao mau HTML trong app/templates/.

Tach rieng khoi application/commands: doc file la chi tiet ha tang
(infrastructure), khong phai logic nghiep vu - use case chi goi
render(template_name, **fields) ma khong biet file nam o dau.
"""
from __future__ import annotations

from pathlib import Path

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"


def render(template_name: str, **fields: str) -> str:
    path = _TEMPLATES_DIR / template_name
    with path.open(encoding="utf-8") as f:
        return f.read().format(**fields)
