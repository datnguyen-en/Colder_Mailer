from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import richtext, schemas, services
from app.db import get_db
from app.models import Template
from app.routers.contacts import get_contact

router = APIRouter(prefix="/templates", tags=["templates"])


def _save(db: Session, template: Template, req: schemas.TemplateIn) -> Template:
    current_default = services.default_template(db)  # query before touching the row
    template.name, template.subject = req.name, req.subject
    template.body = richtext.sanitize(req.body)
    db.add(template)
    # There is always exactly one default; it only moves when another is made default.
    if req.is_default or current_default in (None, template):
        db.execute(update(Template).where(Template.is_default).values(is_default=False))
        db.flush()
        template.is_default = True
    db.commit()
    return template


@router.get("", response_model=list[schemas.TemplateOut])
def list_templates(db: Session = Depends(get_db)):
    return db.scalars(select(Template).order_by(Template.is_default.desc(), Template.name)).all()


@router.post("", response_model=schemas.TemplateOut, status_code=201)
def create_template(req: schemas.TemplateIn, db: Session = Depends(get_db)):
    return _save(db, Template(), req)


@router.put("/{template_id}", response_model=schemas.TemplateOut)
def update_template(template_id: int, req: schemas.TemplateIn, db: Session = Depends(get_db)):
    template = db.get(Template, template_id)
    if template is None:
        raise HTTPException(404, "Template not found")
    return _save(db, template, req)


@router.post("/preview", response_model=schemas.EmailPreview)
def preview_template(req: schemas.TemplatePreviewRequest, db: Session = Depends(get_db)):
    """Render unsaved editor text against a contact, for the live preview."""
    contact = get_contact(db, req.contact_id)
    draft = SimpleNamespace(subject=req.subject, body=req.body)
    return services.preview_email(db, draft, contact)
