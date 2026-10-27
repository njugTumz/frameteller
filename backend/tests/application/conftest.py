from dataclasses import dataclass

import pytest

from frameteller.domain import Project
from tests.builders import project
from tests.fakes import (
    FakeImageGeneration,
    FakeSegmentation,
    InMemoryJobQueue,
    InMemoryMediaStorage,
    InMemoryProjectRepository,
    RecordingBudget,
    SequentialIds,
)


@dataclass
class World:
    """Every fake a drawing use case needs, around one stored project."""

    repo: InMemoryProjectRepository
    images: FakeImageGeneration
    storage: InMemoryMediaStorage
    budget: RecordingBudget
    jobs: InMemoryJobQueue
    sam: FakeSegmentation
    ids: SequentialIds

    def project(self) -> Project:
        return self.repo.peek("p1")


def make_world(p: Project) -> World:
    storage = InMemoryMediaStorage()
    storage.files["refs/mira.webp"] = (b"mira-ref", "image/webp")
    storage.files["refs/cat.webp"] = (b"cat-ref", "image/webp")
    return World(
        InMemoryProjectRepository(p),
        FakeImageGeneration(),
        storage,
        RecordingBudget(),
        InMemoryJobQueue(),
        FakeSegmentation(),
        SequentialIds("obj"),
    )


@pytest.fixture
def world() -> World:
    return make_world(project())


@pytest.fixture
def draft_world() -> World:
    return make_world(project(approved=False))
