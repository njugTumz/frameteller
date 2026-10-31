"""Redraw over HTTP (ADR 0022): what should change, the versions on the project and Keep previous."""

from frameteller.application.errors import ModelContentFilteredError
from tests.interface.conftest import Api

REFUSED = ModelContentFilteredError("muse-image-1.0", "HTTP 400 content filter")


async def test_redraw_with_a_change_then_keep_previous(api: Api) -> None:
    await api.client.post("/projects/p1/shots/1/panel", json={})
    await api.settle()
    first = (await api.client.get("/projects/p1")).json()["shots"][0]["panel"]

    r = await api.client.post("/projects/p1/shots/1/panel", json={"redraw": True, "change": "make it night"})
    assert r.status_code == 202
    assert r.json()["revision"] == 2
    await api.settle()
    assert "The director asks for this change: make it night." in api.fakes.images.generated[-1].prompt

    panel = (await api.client.get("/projects/p1")).json()["shots"][0]["panel"]
    assert panel["shown_revision"] == 2
    assert [(v["revision"], v["image_url"]) for v in panel["versions"]] == [(1, first["image_url"])]

    kept = await api.client.post("/projects/p1/shots/1/panel/versions/1")
    assert kept.status_code == 200
    panel = kept.json()["shots"][0]["panel"]
    assert (panel["shown_revision"], panel["image_url"]) == (3, first["image_url"])
    assert [v["revision"] for v in panel["versions"]] == [2]  # and back again, if they change their mind


async def test_unknown_version_and_a_long_change_are_refused_plainly(api: Api) -> None:
    await api.client.post("/projects/p1/shots/1/panel", json={})
    await api.settle()
    missing = await api.client.post("/projects/p1/shots/1/panel/versions/9")
    assert missing.status_code == 404
    long = await api.client.post("/projects/p1/shots/1/panel", json={"redraw": True, "change": "x" * 301})
    assert long.status_code == 422


async def test_a_refused_redraw_says_what_to_change_and_offers_a_suggestion(api: Api) -> None:
    await api.client.post("/projects/p1/shots/1/panel", json={})
    await api.settle()
    api.fakes.images.refuse = [REFUSED, REFUSED]  # the plainer retry is refused too
    await api.client.post("/projects/p1/shots/1/panel", json={"surprise": True})
    await api.settle()

    panel = (await api.client.get("/projects/p1")).json()["shots"][0]["panel"]
    assert panel["status"] == "ready"
    assert panel["shown_revision"] == 1
    assert panel["suggested_change"].startswith("keep it calm and friendly: ")
