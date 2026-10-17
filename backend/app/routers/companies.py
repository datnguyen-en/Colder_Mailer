from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import schemas
from app.db import get_db
from app.models import Company, Contact, Template

router = APIRouter(prefix="/companies", tags=["companies"])


def _with_counts(db: Session, companies: list[Company]) -> list[schemas.CompanyOut]:
    ids = [c.id for c in companies]
    status_counts: dict[int, dict[str, int]] = defaultdict(dict)
    last_contacted = {}
    for company_id, status, count, last_sent in db.execute(
        select(Contact.company_id, Contact.status, func.count(), func.max(Contact.sent_at))
        .where(Contact.company_id.in_(ids))
        .group_by(Contact.company_id, Contact.status)
    ):
        status_counts[company_id][status] = count
        if last_sent and (company_id not in last_contacted or last_sent > last_contacted[company_id]):
            last_contacted[company_id] = last_sent

    return [
        schemas.CompanyOut(
            id=company.id,
            name=company.name,
            domain=company.domain,
            notes=company.notes,
            template_id=company.template_id,
            aliases=sorted(a.domain for a in company.aliases),
            contact_count=sum(status_counts[company.id].values()),
            status_counts=status_counts[company.id],
            last_contacted_at=last_contacted.get(company.id),
            created_at=company.created_at,
        )
        for company in companies
    ]


@router.get("", response_model=list[schemas.CompanyOut])
def list_companies(db: Session = Depends(get_db)):
    companies = db.scalars(
        select(Company).options(selectinload(Company.aliases)).order_by(func.lower(Company.name))
    ).all()
    return _with_counts(db, list(companies))


@router.patch("/{company_id}", response_model=schemas.CompanyOut)
def update_company(company_id: int, req: schemas.CompanyUpdate, db: Session = Depends(get_db)):
    company = db.get(Company, company_id, options=[selectinload(Company.aliases)])
    if company is None:
        raise HTTPException(404, "Company not found")
    changes = req.model_dump(exclude_unset=True)
    if changes.get("template_id") is not None and db.get(Template, changes["template_id"]) is None:
        raise HTTPException(422, "Template not found")
    for field, value in changes.items():
        if field == "name" and not (value or "").strip():
            raise HTTPException(422, "Name can't be empty")
        setattr(company, field, value.strip() if isinstance(value, str) else value)
    db.commit()
    return _with_counts(db, [company])[0]
