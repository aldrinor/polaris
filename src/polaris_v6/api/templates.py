"""GET /templates and /templates/{id} — expose v6 template registry over HTTP.

Lets the frontend dashboard render the template selector from the
authoritative `config/v6_templates/*.json` files instead of hardcoding.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from polaris_v6.templates.registry import (
    TemplateContent,
    list_template_ids,
    load_template,
)

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=list[TemplateContent])
def list_all() -> list[TemplateContent]:
    """Return all loadable v6 templates from the registry.

    Templates that fail to load are silently skipped so one malformed file
    does not break the whole selector.
    """
    out: list[TemplateContent] = []
    for tid in list_template_ids():
        try:
            out.append(load_template(tid))
        except Exception:
            continue
    return out


@router.get("/{template_id}", response_model=TemplateContent)
def get_one(template_id: str) -> TemplateContent:
    """Return one template by id.

    Raises HTTPException 404 when no template with `template_id` exists.
    """
    try:
        return load_template(template_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
