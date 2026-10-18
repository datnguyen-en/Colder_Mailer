"""Resume storage behind one small interface: a local folder in dev,
a private Supabase Storage bucket in prod."""

from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import httpx

from app.config import get_config


class Storage(Protocol):
    def save(self, key: str, data: bytes) -> None: ...
    def load(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError(f"Invalid storage key: {key}")
        return path

    def save(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def load(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class StorageError(Exception):
    pass


class SupabaseStorage:
    """A private bucket through Supabase's Storage REST API, using the server-only
    secret key (never sent to the browser)."""

    def __init__(self, url: str, secret_key: str, bucket: str, client: httpx.Client | None = None):
        self.base = f"{url.rstrip('/')}/storage/v1/object/{quote(bucket)}"
        headers = {"apikey": secret_key}
        if secret_key.startswith("eyJ"):  # legacy service_role JWT also goes in Authorization
            headers["Authorization"] = f"Bearer {secret_key}"
        self.client = client or httpx.Client(timeout=20)
        self.headers = headers

    def _url(self, key: str) -> str:
        if not key or key.startswith("/") or ".." in key.split("/"):
            raise ValueError(f"Invalid storage key: {key}")
        return f"{self.base}/{quote(key)}"

    def _check(self, res: httpx.Response, action: str, key: str) -> httpx.Response:
        if res.status_code >= 400:
            raise StorageError(f"Supabase Storage couldn't {action} {key} ({res.status_code}: {res.text[:200]})")
        return res

    def save(self, key: str, data: bytes) -> None:
        res = self.client.post(self._url(key), content=data, headers={
            **self.headers, "Content-Type": "application/pdf", "x-upsert": "true"})
        self._check(res, "save", key)

    def load(self, key: str) -> bytes:
        return self._check(self.client.get(self._url(key), headers=self.headers), "load", key).content

    def delete(self, key: str) -> None:
        res = self.client.delete(self._url(key), headers=self.headers)
        if res.status_code != 404:  # already gone is fine, like LocalStorage
            self._check(res, "delete", key)


def get_storage() -> Storage:
    config = get_config()
    if config.storage_backend == "supabase":
        return SupabaseStorage(config.supabase_url, config.supabase_secret_key, config.supabase_bucket)
    return LocalStorage(config.local_storage_dir)
