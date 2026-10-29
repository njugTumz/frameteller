"""Azure Blob Storage adapters: media, project documents and the spend ledger (CLAUDE.md section 7).

Auth is DefaultAzureCredential: the Container App's managed identity in Azure, `az login` locally. A connection
string is accepted only for the Azurite emulator. The SDK's async clients need aiohttp, so the sync clients run in
worker threads; they are thread-safe, and azure-core retries transient failures with exponential backoff.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from azure.core import MatchConditions
from azure.core.exceptions import ResourceExistsError, ResourceModifiedError, ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContainerClient, ContentSettings

from frameteller.application.errors import ProjectNotFoundError
from frameteller.application.ports import UsageRecord
from frameteller.domain import MediaRef, Project
from frameteller.infrastructure.config import Settings
from frameteller.infrastructure.local.serialization import project_from_dict, project_to_dict
from frameteller.infrastructure.storage_keys import check_key

MAX_UPDATE_ATTEMPTS = 8  # optimistic retries when another writer changed the project in between


class ProjectConflictError(RuntimeError):
    """The project kept changing under us; nothing was written."""


def blob_service(settings: Settings) -> BlobServiceClient:
    options: dict[str, Any] = {
        "retry_total": settings.retry_attempts,
        "connection_timeout": 10,
        "read_timeout": settings.text_timeout_s,
    }
    if settings.azure_storage_api_version:
        options["api_version"] = settings.azure_storage_api_version  # Azurite lags the SDK's newest version
    if settings.azure_storage_connection_string is not None:
        conn = settings.azure_storage_connection_string.get_secret_value()
        return BlobServiceClient.from_connection_string(conn, **options)
    url = f"https://{settings.azure_storage_account}.blob.core.windows.net"
    return BlobServiceClient(url, credential=DefaultAzureCredential(), **options)


class AzureBlobMediaStorage:
    """MediaStoragePort on a private blob container. The backend streams media; no public or SAS URLs yet."""

    def __init__(self, container: ContainerClient) -> None:
        self._container = container

    async def put(self, key: str, data: bytes, content_type: str) -> MediaRef:
        blob = self._container.get_blob_client(check_key(key))
        settings = ContentSettings(content_type=content_type)
        await asyncio.to_thread(blob.upload_blob, data, overwrite=True, content_settings=settings)
        return MediaRef(key)

    async def get(self, ref: MediaRef) -> bytes:
        blob = self._container.get_blob_client(check_key(ref.key))

        def download() -> bytes:
            return blob.download_blob().readall()

        return await asyncio.to_thread(download)

    async def delete(self, ref: MediaRef) -> None:
        blob = self._container.get_blob_client(check_key(ref.key))

        def remove() -> None:
            with contextlib.suppress(ResourceNotFoundError):
                blob.delete_blob()

        await asyncio.to_thread(remove)

    async def check_writable(self) -> None:
        """Readiness probe: write and delete a tiny blob. Raises if the identity or network cannot."""
        blob = self._container.get_blob_client(".ready")

        def probe() -> None:
            blob.upload_blob(b"ok", overwrite=True)
            blob.delete_blob()

        await asyncio.to_thread(probe)


class BlobShareIndex:
    """ShareIndex as one tiny blob per token next to the project documents (shares/<token>)."""

    def __init__(self, container: ContainerClient) -> None:
        self._container = container

    def _blob(self, token: str) -> Any:
        return self._container.get_blob_client(check_key(f"shares/{token}"))

    async def put(self, token: str, project_id: str) -> None:
        await asyncio.to_thread(self._blob(token).upload_blob, project_id.encode(), overwrite=True)

    async def find(self, token: str) -> str | None:
        try:
            blob = self._blob(token)
        except ValueError:
            return None

        def read() -> bytes:
            return bytes(blob.download_blob().readall())

        try:
            return (await asyncio.to_thread(read)).decode()
        except ResourceNotFoundError:
            return None

    async def delete(self, token: str) -> None:
        def remove() -> None:
            with contextlib.suppress(ResourceNotFoundError):
                self._blob(token).delete_blob()

        await asyncio.to_thread(remove)


class BlobProjectRepository:
    """ProjectRepository as one JSON blob per project, with ETag optimistic concurrency.

    update() re-reads and re-applies the change when another writer saved in between, so replicas never lose
    each other's updates. A per-project lock avoids pointless conflicts inside this process.
    """

    def __init__(self, container: ContainerClient) -> None:
        self._container = container
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def _blob_name(self, project_id: str) -> str:
        return check_key(f"projects/{project_id}.json")

    async def _load(self, project_id: str) -> tuple[Project, str]:
        blob = self._container.get_blob_client(self._blob_name(project_id))

        def download() -> tuple[bytes, str]:
            stream = blob.download_blob()
            return stream.readall(), str(stream.properties.etag)

        try:
            data, etag = await asyncio.to_thread(download)
        except ResourceNotFoundError:
            raise ProjectNotFoundError(project_id) from None
        return project_from_dict(json.loads(data)), etag

    async def get(self, project_id: str) -> Project:
        project, _ = await self._load(project_id)
        return project

    async def save(self, project: Project) -> None:
        async with self._locks[project.id]:
            await self._write(project, etag=None)

    async def update[T](self, project_id: str, change: Callable[[Project], T]) -> T:
        async with self._locks[project_id]:
            for _ in range(MAX_UPDATE_ATTEMPTS):
                project, etag = await self._load(project_id)
                result = change(project)
                try:
                    await self._write(project, etag=etag)
                    return result
                except ResourceModifiedError:
                    continue  # someone else saved first: apply the change again to their version
            raise ProjectConflictError(f"project {project_id} kept changing; gave up after {MAX_UPDATE_ATTEMPTS} tries")

    async def _write(self, project: Project, *, etag: str | None) -> None:
        blob = self._container.get_blob_client(self._blob_name(project.id))
        data = json.dumps(project_to_dict(project), ensure_ascii=False).encode()
        settings = ContentSettings(content_type="application/json")
        if etag is None:
            await asyncio.to_thread(blob.upload_blob, data, overwrite=True, content_settings=settings)
        else:
            await asyncio.to_thread(
                blob.upload_blob,
                data,
                overwrite=True,
                content_settings=settings,
                etag=etag,
                match_condition=MatchConditions.IfNotModified,
            )


class BlobSpendLedger:
    """SpendLedger as append blobs: charges per project and per day (for budgets), usage per day (metrics).

    Each row is one append block, which Blob Storage applies atomically, so concurrent writers are safe.
    """

    def __init__(self, container: ContainerClient) -> None:
        self._container = container

    async def spent_by_project(self, project_id: str) -> float:
        return sum(float(r["cost_usd"]) for r in await self._rows(f"spend/projects/{project_id}.jsonl"))

    async def spent_on_day(self, day: str) -> float:
        return sum(float(r["cost_usd"]) for r in await self._rows(f"spend/days/{day}.jsonl"))

    async def record(self, project_id: str, day: str, cost_usd: float, what: str) -> None:
        row = {"type": "charge", "project_id": project_id, "day": day, "cost_usd": cost_usd, "what": what}
        await asyncio.gather(
            self._append(f"spend/projects/{project_id}.jsonl", row), self._append(f"spend/days/{day}.jsonl", row)
        )

    async def record_usage(self, usage: UsageRecord, day: str | None = None) -> None:
        day = day or datetime.now(UTC).date().isoformat()
        await self._append(f"spend/usage/{day}.jsonl", {"type": "usage", **dataclasses.asdict(usage)})

    async def usage(self, day: str) -> list[UsageRecord]:
        rows = await self._rows(f"spend/usage/{day}.jsonl")
        return [UsageRecord(**{k: v for k, v in r.items() if k != "type"}) for r in rows]

    async def _rows(self, name: str) -> list[dict[str, Any]]:
        return await read_rows(self._container, name)

    async def _append(self, name: str, row: dict[str, Any]) -> None:
        await append_row(self._container, name, row)


async def read_rows(container: ContainerClient, name: str) -> list[dict[str, Any]]:
    """The JSON lines of an append blob; none when it does not exist yet."""
    blob = container.get_blob_client(check_key(name))

    def read() -> bytes:
        try:
            return blob.download_blob().readall()
        except ResourceNotFoundError:
            return b""

    text = (await asyncio.to_thread(read)).decode()
    return [json.loads(line) for line in text.splitlines() if line.strip()]


async def append_row(container: ContainerClient, name: str, row: dict[str, Any]) -> None:
    """One JSON line as one append block, which Blob Storage applies atomically."""
    blob = container.get_blob_client(check_key(name))
    data = (json.dumps(row) + "\n").encode()

    def append() -> None:
        # Create it only if it does not exist yet, so a racing writer never truncates it.
        with contextlib.suppress(ResourceExistsError, ResourceModifiedError):
            blob.create_append_blob(match_condition=MatchConditions.IfMissing)
        blob.append_block(data)

    await asyncio.to_thread(append)


class BlobVisitorQuota:
    """VisitorQuota as one append blob per day, visitor and kind (quotas/<day>/<kind>/<visitor>.jsonl).

    Visitors are hashes, never raw IPs. The media lifecycle rule does not cover this container, but each row
    is tiny and a day's blobs are never read again after that day.
    """

    def __init__(self, container: ContainerClient) -> None:
        self._container = container

    async def used(self, visitor: str, day: str, kind: str) -> int:
        return len(await read_rows(self._container, f"quotas/{day}/{kind}/{visitor}.jsonl"))

    async def add(self, visitor: str, day: str, kind: str) -> None:
        await append_row(self._container, f"quotas/{day}/{kind}/{visitor}.jsonl", {"kind": kind})
