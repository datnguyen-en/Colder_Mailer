import httpx
import pytest

from app.storage import LocalStorage, StorageError, SupabaseStorage

PDF = b"%PDF-1.7 resume"


def supabase(handler, key="sb_secret_abc"):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return SupabaseStorage("https://proj.supabase.co/", key, "resumes", client=client)


def test_supabase_save_load_delete_hit_the_private_bucket():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.method, str(req.url), req.headers.get("apikey"),
                     req.headers.get("authorization"), req.headers.get("x-upsert")))
        if req.method == "GET":
            return httpx.Response(200, content=PDF)
        return httpx.Response(200, json={"Key": "resumes/resume/r.pdf"})

    store = supabase(handler)
    store.save("resume/r.pdf", PDF)
    assert store.load("resume/r.pdf") == PDF
    store.delete("resume/r.pdf")

    url = "https://proj.supabase.co/storage/v1/object/resumes/resume/r.pdf"
    assert seen == [
        ("POST", url, "sb_secret_abc", None, "true"),  # upsert, so a re-upload replaces it
        ("GET", url, "sb_secret_abc", None, None),
        ("DELETE", url, "sb_secret_abc", None, None),
    ]


def test_legacy_service_role_jwt_is_also_sent_as_bearer():
    headers = {}

    def handler(req):
        headers.update(req.headers)
        return httpx.Response(200, content=PDF)

    supabase(handler, key="eyJhbGciOi.legacy").load("resume/r.pdf")
    assert headers["authorization"] == "Bearer eyJhbGciOi.legacy"


def test_supabase_errors_are_raised_but_missing_delete_is_fine():
    store = supabase(lambda req: httpx.Response(404 if req.method == "DELETE" else 403, text="denied"))
    with pytest.raises(StorageError, match="403"):
        store.load("resume/r.pdf")
    with pytest.raises(StorageError, match="403"):
        store.save("resume/r.pdf", PDF)
    store.delete("resume/r.pdf")  # 404: already gone


@pytest.mark.parametrize("key", ["", "/etc/passwd", "resume/../../x.pdf"])
def test_bad_keys_are_rejected(key, tmp_path):
    with pytest.raises(ValueError):
        supabase(lambda req: httpx.Response(200))._url(key)
    if key:
        with pytest.raises(ValueError):
            LocalStorage(tmp_path)._path(key)
