from frameteller.application.use_cases import MergeCharacters, RemoveCharacter, RenameCharacter
from frameteller.domain import MediaRef, Size
from tests.builders import project
from tests.fakes import InMemoryJobQueue, InMemoryProjectRepository


def drawn_repo(*, approved: bool = True) -> InMemoryProjectRepository:
    p = project(approved=approved)
    for s in p.shots:
        p.panel(s.id).record_render(1, MediaRef(f"projects/p1/panels/{s.id}/r1/image"), "resp", Size(1920, 1280))
    return InMemoryProjectRepository(p)


async def test_merge_redraws_the_changed_panels_as_drafts() -> None:
    repo, jobs = drawn_repo(), InMemoryJobQueue()
    merged = await MergeCharacters(repo, jobs).execute("p1", "cat", "mira")
    assert merged.project.shot("s2").character_ids == ("mira",)
    assert [(j.payload["shot_id"], j.payload["revision"], j.payload["quality"]) for j in jobs.jobs] == [
        ("s2", "2", "low")
    ]
    assert [t.shot_id for t in merged.redrawing] == ["s2"]
    assert "cat" not in repo.peek("p1").bible


async def test_merge_before_approval_redraws_nothing() -> None:
    repo, jobs = drawn_repo(approved=False), InMemoryJobQueue()
    await MergeCharacters(repo, jobs).execute("p1", "cat", "mira")
    assert jobs.jobs == []


async def test_rename_and_remove_are_saved() -> None:
    repo = drawn_repo()
    await RenameCharacter(repo).execute("p1", "cat", "Pip")
    assert repo.peek("p1").bible.get("cat").name == "Pip"
    await RemoveCharacter(repo).execute("p1", "cat")
    assert repo.peek("p1").panels["s2"].outdated
