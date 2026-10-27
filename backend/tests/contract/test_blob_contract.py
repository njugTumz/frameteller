"""Blob adapters against the Azurite emulator (a service container in CI). No Azure account, no credits.

Locally:  docker run --rm -p 10000:10000 mcr.microsoft.com/azure-storage/azurite:3.37.0 azurite-blob --blobHost 0.0.0.0
"""

from __future__ import annotations

import asyncio
import os
import socket
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from azure.storage.blob import BlobServiceClient, ContainerClient

from frameteller.application.errors import ProjectNotFoundError
from frameteller.application.ports import UsageRecord
from frameteller.domain import MediaRef, Project
from frameteller.infrastructure.azure import AzureBlobMediaStorage, BlobProjectRepository, BlobSpendLedger, blob_service
from frameteller.infrastructure.config import Settings, load_settings
from tests.builders import project, turn

AZURITE = os.environ.get("AZURITE_CONNECTION_STRING", "UseDevelopmentStorage=true")  # the emulator's public account
AZURITE_API_VERSION = "2026-06-06"  # the newest Azurite 3.37 accepts; the SDK defaults to a newer one


def _azurite_up() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 10000), timeout=0.5):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _azurite_up(),
    reason="Azurite is not running on 127.0.0.1:10000. Start it with: docker run --rm -p 10000:10000 "
    "mcr.microsoft.com/azure-storage/azurite:3.37.0 azurite-blob --blobHost 0.0.0.0",
)


def blob_settings(**overrides: object) -> Settings:
    return load_settings(
        model_api_key="LLM_test_not_a_real_key_000000",
        storage_backend="blob",
        azure_storage_connection_string=AZURITE,
        azure_storage_api_version=AZURITE_API_VERSION,
        **overrides,
    )


@dataclass
class Containers:
    media: ContainerClient
    projects: ContainerClient


@pytest.fixture
def containers() -> Iterator[Containers]:
    service: BlobServiceClient = blob_service(blob_settings())
    run = uuid.uuid4().hex[:8]
    media = service.create_container(f"media{run}")
    projects = service.create_container(f"projects{run}")
    yield Containers(media, projects)
    media.delete_container()
    projects.delete_container()


@pytest.fixture
def repo(containers: Containers) -> BlobProjectRepository:
    return BlobProjectRepository(containers.projects)


async def test_media_round_trip_keeps_the_content_type(containers: Containers) -> None:
    storage = AzureBlobMediaStorage(containers.media)
    ref = await storage.put("projects/p1/panels/s1/r1/image", b"webp-bytes", "image/webp")
    assert ref == MediaRef("projects/p1/panels/s1/r1/image")
    assert await storage.get(ref) == b"webp-bytes"
    props = containers.media.get_blob_client(ref.key).get_blob_properties()
    assert props.content_settings.content_type == "image/webp"
    await storage.check_writable()
    with pytest.raises(ValueError, match="unsafe"):
        await storage.put("../escape", b"x", "image/webp")


async def test_projects_save_get_and_missing(repo: BlobProjectRepository) -> None:
    await repo.save(project())
    got = await repo.get("p1")
    assert [s.id for s in got.shots] == ["s1", "s2", "s3"]
    assert got.bible.is_approved
    with pytest.raises(ProjectNotFoundError):
        await repo.get("nope")
    with pytest.raises(ProjectNotFoundError):
        await repo.update("nope", lambda p: None)


async def test_concurrent_updates_from_two_replicas_both_land(containers: Containers) -> None:
    """Two repository instances stand in for two replicas: their locks are separate, only ETags protect."""
    a, b = BlobProjectRepository(containers.projects), BlobProjectRepository(containers.projects)
    await a.save(Project(id="p1", title="race"))
    attempts: list[str] = []

    def add(n: int):  # type: ignore[no-untyped-def]
        def change(p: Project) -> int:
            attempts.append(f"t{n}")
            p.add_turn(turn(n))
            return n

        return change

    results = await asyncio.gather(*(r.update("p1", add(n)) for n, r in enumerate([a, b, a, b, a, b], start=1)))

    assert sorted(results) == [1, 2, 3, 4, 5, 6]
    assert sorted(t.id for t in (await a.get("p1")).turns) == [f"t{n}" for n in range(1, 7)]
    assert len(attempts) >= 6  # conflicting writes were re-applied, not lost


async def test_spend_ledger_counts_charges_by_project_and_day(containers: Containers) -> None:
    ledger = BlobSpendLedger(containers.projects)
    await asyncio.gather(
        ledger.record("p1", "2026-10-27", 0.01, "image"),
        ledger.record("p1", "2026-10-27", 0.0025, "sam"),
        ledger.record("p2", "2026-10-28", 0.01, "image"),
    )
    assert await ledger.spent_by_project("p1") == pytest.approx(0.0125)
    assert await ledger.spent_on_day("2026-10-27") == pytest.approx(0.0125)
    assert await ledger.spent_by_project("p3") == 0
    usage = UsageRecord("sam-3.1", "segment_point", 4000, 0.0025, project_id="p1")
    await ledger.record_usage(usage, day="2026-10-27")
    assert await ledger.usage("2026-10-27") == [usage]
