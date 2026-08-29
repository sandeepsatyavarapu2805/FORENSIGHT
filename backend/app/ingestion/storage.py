import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.config import settings

CHUNK_SIZE = 1024 * 1024


class UploadTooLargeError(Exception):
    pass


@dataclass(frozen=True)
class StoredUpload:
    storage_key: str
    original_filename: str
    size: int
    sha256: str
    path: Path


class LocalFileStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    async def save(self, upload: UploadFile, maximum_bytes: int) -> StoredUpload:
        original_name = Path((upload.filename or "").replace("\\", "/")).name
        if not original_name or original_name in {".", ".."}:
            raise ValueError("A valid source filename is required")

        self.root.mkdir(parents=True, exist_ok=True)
        storage_key = f"{uuid.uuid4().hex}.source"
        destination = (self.root / storage_key).resolve()
        if destination.parent != self.root:
            raise ValueError("Invalid storage destination")

        digest = hashlib.sha256()
        size = 0
        try:
            with destination.open("xb") as target:
                while chunk := await upload.read(CHUNK_SIZE):
                    size += len(chunk)
                    if size > maximum_bytes:
                        raise UploadTooLargeError
                    digest.update(chunk)
                    target.write(chunk)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()

        return StoredUpload(
            storage_key=storage_key,
            original_filename=original_name,
            size=size,
            sha256=digest.hexdigest(),
            path=destination,
        )

    def path_for(self, storage_key: str) -> Path:
        path = (self.root / storage_key).resolve()
        if path.parent != self.root:
            raise ValueError("Invalid storage key")
        return path

    def delete(self, storage_key: str) -> None:
        self.path_for(storage_key).unlink(missing_ok=True)


def get_file_storage() -> LocalFileStorage:
    return LocalFileStorage(settings.upload_storage_path)
