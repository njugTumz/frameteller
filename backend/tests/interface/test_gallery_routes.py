"""The gallery over HTTP: submit with consent, the public listing and media, hearts, reports, withdraw, admin."""

from collections.abc import Callable

from tests.interface.conftest import Api

ADMIN = "admin-token-for-tests-0123456789abcdef"
AUTH = {"Authorization": f"Bearer {ADMIN}"}
BROWSER = {"X-Visitor-Id": "browser-0001"}


async def drawn(api: Api) -> None:
    for n in (1, 2, 3):
        await api.client.post(f"/projects/p1/shots/{n}/panel", json={})
    await api.settle()


async def test_submit_publish_heart_report_and_withdraw(make_api: Callable[..., Api]) -> None:
    api = make_api(admin_token=ADMIN, public_app_url="https://app.example")
    await drawn(api)
    refused = await api.client.post("/projects/p1/gallery", json={"consent": False, "audio": "none"})
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "gallery_submission"

    r = await api.client.post("/projects/p1/gallery", json={"consent": True, "audio": "none"})
    assert r.status_code == 202
    assert r.json()["status"] == "checking"
    await api.settle()
    mine = (await api.client.get("/projects/p1/gallery")).json()
    assert mine["status"] == "published"

    page = (await api.client.get("/gallery", headers=BROWSER)).json()["entries"]
    assert len(page) == 1
    card = page[0]
    assert card["title"] == "The Lantern Cat"
    assert card["share_url"].startswith("https://app.example/s/")
    assert not card["hearted"]
    video = await api.client.get(card["video_url"], headers={"Range": "bytes=0-3"})
    assert video.status_code == 206
    assert (await api.client.get(card["cover_url"])).status_code == 200

    for _ in range(2):
        hearts = (await api.client.post(f"/gallery/{card['id']}/heart", headers=BROWSER)).json()
        assert hearts == {"hearts": 1, "hearted": True}
    assert (await api.client.get("/gallery", headers=BROWSER)).json()["entries"][0]["hearted"]

    sitemap = await api.client.get("/gallery/sitemap.xml")
    assert card["share_url"] in sitemap.text
    assert "https://app.example/gallery" in sitemap.text

    reported = await api.client.post(f"/gallery/{card['id']}/report", json={"reason": "not original"})
    assert reported.status_code == 204
    entries = (await api.client.get("/admin/gallery", headers=AUTH)).json()
    assert entries[0]["reports"][0]["reason"] == "not original"

    assert (await api.client.delete("/projects/p1/gallery")).status_code == 204
    assert (await api.client.get("/gallery")).json()["entries"] == []
    assert (await api.client.get(card["video_url"])).status_code == 404
    assert (await api.client.get("/projects/p1/gallery")).status_code == 404


async def test_the_admin_publishes_a_pending_entry_and_can_hide_feature_and_remove(
    make_api: Callable[..., Api],
) -> None:
    from frameteller.domain import Decision
    from tests.fakes import verdict

    api = make_api(admin_token=ADMIN)
    api.fakes.reviewer.verdicts = [verdict(Decision.ASK, confidence=0.9)]
    await drawn(api)
    await api.client.post("/projects/p1/gallery", json={"consent": True, "audio": "none"})
    await api.settle()
    mine = (await api.client.get("/projects/p1/gallery")).json()
    assert mine["status"] == "pending"
    assert mine["note"] == "A person will look at it before it appears in the gallery."
    assert (await api.client.get("/gallery")).json()["entries"] == []

    assert (await api.client.get("/admin/gallery")).status_code == 401
    [entry] = (await api.client.get("/admin/gallery", headers=AUTH)).json()
    assert entry["status"] == "pending"
    watch = await api.client.get(f"/admin/gallery/{entry['id']}/video.mp4", headers=AUTH)
    assert watch.status_code == 200
    for action in ("publish", "feature"):
        r = await api.client.post(f"/admin/gallery/{entry['id']}", json={"action": action}, headers=AUTH)
        assert r.status_code == 200
    featured = (await api.client.get("/gallery", params={"view": "featured"})).json()["entries"]
    assert [c["id"] for c in featured] == [entry["id"]]
    await api.client.post(f"/admin/gallery/{entry['id']}", json={"action": "hide"}, headers=AUTH)
    assert (await api.client.get("/gallery")).json()["entries"] == []
    assert (await api.client.delete(f"/admin/gallery/{entry['id']}", headers=AUTH)).status_code == 204
    assert (await api.client.get("/admin/gallery", headers=AUTH)).json() == []
