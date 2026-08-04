"""NOT-09 ManageTemplates - PUT /templates/{code}. Caller: Admin
(Muc 2 dac ta) -> yeu cau Bearer JWT role admin. Bat buoc If-Match tru
lan tao dau tien (xem domain/rules.py, application/commands/upsert_template.py)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header

from app.application.commands.upsert_template import upsert_template
from app.dependencies import get_template_repository
from app.repositories.interfaces import TemplateRepository
from app.schemas.requests import TemplateUpdate
from app.schemas.responses import TemplateResponse
from app.security.authentication import Principal, require_role
from app.security.authorization import ADMIN_ROLES

router = APIRouter(prefix="/templates", tags=["templates"])


@router.put("/{code}", response_model=TemplateResponse)
def replace_template(
    code: str,
    body: TemplateUpdate,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    if_match: str | None = Header(default=None, alias="If-Match"),
    repo: TemplateRepository = Depends(get_template_repository),
    _principal: Principal = Depends(require_role(*ADMIN_ROLES)),
):
    template = upsert_template(repo, code, body.subject, body.body, if_match)
    return TemplateResponse.from_entity(template)
