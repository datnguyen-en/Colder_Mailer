from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import require_user
from app.config import get_config
from app.routers import companies, contacts, parse, settings, stats, templates

config = get_config()  # fails fast on bad config (e.g. AUTH_DISABLED in prod)

app = FastAPI(title="Cold Email Tracker API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)

for module in (parse, contacts, companies, templates, settings, stats):
    app.include_router(module.router, dependencies=[Depends(require_user)])


@app.get("/health")
def health():
    return {"ok": True}
