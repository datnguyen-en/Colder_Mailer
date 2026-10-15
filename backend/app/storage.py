"""Resume storage behind one small interface: a local folder in dev,
a private Supabase Storage bucket in prod (Phase 4)."""

from pathlib import Path
from typing import Protocol

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


def get_storage() -> Storage:
    config = get_config()
    if config.storage_backend == "local":
        return LocalStorage(config.local_storage_dir)
    raise NotImplementedError("Supabase storage arrives in Phase 4")
