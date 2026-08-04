"""Render noi dung email tu template - uu tien doc tu TemplateRepository
(DB, co the sua qua PUT /templates/{code} - NOT-09), fallback ve
template mac dinh (application/services/template_defaults.py) neu DB
chua co dong tuong ung."""
from __future__ import annotations

from app.application.services.template_defaults import DEFAULT_TEMPLATES
from app.repositories.interfaces import TemplateRepository


def render(template_repo: TemplateRepository, template_code: str, fields: dict[str, str]) -> tuple[str, str]:
    """Tra ve (subject, body) da dien du lieu."""
    template = template_repo.get(template_code)
    if template is not None:
        subject, body = template.subject, template.body
    else:
        subject, body = DEFAULT_TEMPLATES[template_code]
    return subject.format(**fields), body.format(**fields)
