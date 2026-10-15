from dataclasses import asdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import parser, schemas, services
from app.db import get_db
from app.models import Contact

router = APIRouter(tags=["parse"])


@router.post("/parse", response_model=list[schemas.PreviewRow])
def parse(req: schemas.ParseRequest, db: Session = Depends(get_db)):
    """Preview rows for pasted text or a CSV export. Writes nothing."""
    aliases, companies = services.CompanyIndex(db).name_maps()
    parse_fn = parser.parse_csv if req.format == "csv" else parser.parse
    rows = parse_fn(req.text, aliases, companies)

    statuses = dict(db.execute(
        select(Contact.email, Contact.status).where(Contact.email.in_([r.email for r in rows]))
    ).all())
    for row in rows:
        status = statuses.get(row.email)
        if status == "new":
            row.flags.append("already_imported")
        elif status:
            row.flags.append("already_contacted")
    return [schemas.PreviewRow(**asdict(r)) for r in rows]
