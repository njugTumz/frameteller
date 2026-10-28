from collections.abc import Sequence

import pytest

from frameteller.application.errors import ShareNotFoundError
from frameteller.application.use_cases import GeneratePanel, OpenShare, RevokeShare, SharePreview, ShareProject
from tests.application.conftest import World
from tests.fakes import InMemoryShareIndex


class RecordingPreview:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[bytes]]] = []

    async def contact_sheet(self, title: str, panels: Sequence[bytes]) -> bytes:
        self.calls.append((title, list(panels)))
        return b"png"


async def test_share_is_stable_until_revoked_and_then_gone(world: World) -> None:
    index = InMemoryShareIndex()
    share, revoke, open_share = (
        ShareProject(world.repo, index, world.ids),
        RevokeShare(world.repo, index),
        OpenShare(world.repo, index),
    )

    token = await share.execute("p1")
    assert await share.execute("p1") == token  # the same link people already have
    assert index.tokens == {token: "p1"}
    assert (await open_share.execute(token)).id == "p1"

    await revoke.execute("p1")
    assert index.tokens == {}
    with pytest.raises(ShareNotFoundError):
        await open_share.execute(token)
    assert await share.execute("p1") != token  # sharing again makes a new link


async def test_a_lingering_index_entry_does_not_reopen_a_revoked_link(world: World) -> None:
    index = InMemoryShareIndex()
    token = await ShareProject(world.repo, index, world.ids).execute("p1")
    p = world.project()
    p.unshare()
    await world.repo.save(p)
    with pytest.raises(ShareNotFoundError):
        await OpenShare(world.repo, index).execute(token)
    with pytest.raises(ShareNotFoundError):
        await OpenShare(world.repo, index).execute("nope")


async def test_preview_uses_the_drawn_panels_in_order(world: World) -> None:
    index = InMemoryShareIndex()
    for shot_id in ("s3", "s1"):
        await GeneratePanel(world.repo, world.images, world.budget, world.jobs).execute("p1", shot_id, revision=1)
    token = await ShareProject(world.repo, index, world.ids).execute("p1")
    preview = RecordingPreview()

    assert await SharePreview(OpenShare(world.repo, index), world.storage, preview).execute(token) == b"png"

    [(title, panels)] = preview.calls
    assert title == "The Lantern Cat"
    assert len(panels) == 2
    assert panels[0] == world.storage.files["projects/p1/panels/s1/r1/image"][0]
