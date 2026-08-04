"""Use case: NOT-09 ManageTemplates - PUT /templates/{code}.

Neu template chua ton tai: tao moi (resource_version=1), khong can
If-Match. Neu da ton tai: BAT BUOC If-Match khop resource_version hien
tai (optimistic concurrency, giong ETag) - xem domain/rules.py."""
from __future__ import annotations

from app.domain.entities import Template
from app.domain.rules import ensure_template_version_matches
from app.repositories.interfaces import TemplateRepository


def upsert_template(
    template_repo: TemplateRepository,
    code: str,
    subject: str,
    body: str,
    if_match: str | None,
) -> Template:
    existing = template_repo.get(code)
    if existing is None:
        template = Template.create(code, subject, body)
    else:
        if if_match is not None:
            ensure_template_version_matches(existing, if_match)
        existing.replace(subject, body)
        template = existing
    template_repo.save(template)
    return template
