"""The creator's name and country over HTTP: submit, validation, edit and remove, the counter, filter and share page."""

from collections.abc import Callable

from tests.interface.conftest import Api
from tests.interface.test_gallery_routes import drawn


async def submit(api: Api, **creator: str | None) -> dict:  # type: ignore[type-arg]
    r = await api.client.post("/projects/p1/gallery", json={"consent": True, "audio": "none", **creator})
    assert r.status_code == 202, r.text
    await api.settle()
    return (await api.client.get("/projects/p1/gallery")).json()  # type: ignore[no-any-return]


async def share_page(api: Api) -> dict:  # type: ignore[type-arg]
    token = api.project().share_token
    return (await api.client.get(f"/shares/{token}")).json()  # type: ignore[no-any-return]


async def test_a_signed_entry_shows_its_name_and_country_on_the_card_and_the_share_page(
    make_api: Callable[..., Api],
) -> None:
    api = make_api()
    await drawn(api)
    mine = await submit(api, name="  Captain   Biscuit ", country="ke")
    assert mine["status"] == "published"
    assert mine["creator"] == {"name": "Captain Biscuit", "country": "KE", "official": False}

    page = (await api.client.get("/gallery")).json()
    assert page["entries"][0]["creator"] == {"name": "Captain Biscuit", "country": "KE", "official": False}
    assert page["countries"] == [{"code": "KE", "entries": 1}]
    assert len((await api.client.get("/gallery", params={"country": "KE"})).json()["entries"]) == 1
    assert (await api.client.get("/gallery", params={"country": "AE"})).json()["entries"] == []
    assert (await api.client.get("/gallery", params={"country": "ke"})).status_code == 422
    assert (await share_page(api))["creator"] == {"name": "Captain Biscuit", "country": "KE", "official": False}


async def test_an_unsigned_entry_is_anonymous_and_a_project_outside_the_gallery_has_no_byline(
    make_api: Callable[..., Api],
) -> None:
    api = make_api()
    await drawn(api)
    await api.client.post("/projects/p1/share", json={})
    assert (await share_page(api))["creator"] is None  # not in the gallery: nothing about the creator
    await submit(api)
    assert (await api.client.get("/gallery")).json()["entries"][0]["creator"] == {
        "name": "",
        "country": "",
        "official": False,
    }
    assert (await share_page(api))["creator"] == {
        "name": "",
        "country": "",
        "official": False,
    }  # "by an anonymous storyteller"
    assert (await api.client.get("/gallery")).json()["countries"] == []


async def test_names_over_40_characters_and_unknown_countries_are_refused(make_api: Callable[..., Api]) -> None:
    api = make_api()
    await drawn(api)
    for body in ({"name": "x" * 41}, {"country": "XX"}, {"country": "KEN"}):
        r = await api.client.post("/projects/p1/gallery", json={"consent": True, "audio": "none", **body})
        assert r.status_code == 422, body
    assert (await api.client.get("/projects/p1/gallery")).status_code == 404  # nothing was submitted


async def test_the_creator_edits_removes_and_still_withdraws(make_api: Callable[..., Api]) -> None:
    api = make_api()
    await drawn(api)
    await submit(api, name="Ama")

    r = await api.client.patch("/projects/p1/gallery", json={"name": "Ama K.", "country": "AE"})
    assert r.status_code == 200
    assert r.json()["status"] == "checking"  # a new name is checked before it shows
    assert (await api.client.get("/gallery")).json()["entries"] == []
    await api.settle()
    card = (await api.client.get("/gallery")).json()["entries"][0]
    assert card["creator"] == {"name": "Ama K.", "country": "AE", "official": False}

    r = await api.client.patch("/projects/p1/gallery", json={"name": None, "country": ""})
    assert r.json()["status"] == "published"  # removing shows at once
    assert (await api.client.get("/gallery")).json()["entries"][0]["creator"] == {
        "name": "",
        "country": "",
        "official": False,
    }

    assert (await api.client.patch("/projects/p1/gallery", json={"country": "ZZ"})).status_code == 422
    assert (await api.client.delete("/projects/p1/gallery")).status_code == 204
    assert (await api.client.patch("/projects/p1/gallery", json={"name": "Ama"})).status_code == 404


async def test_a_name_with_contact_details_goes_to_pending_and_the_admin_sees_it(make_api: Callable[..., Api]) -> None:
    admin = "admin-token-for-tests-0123456789abcdef"
    api = make_api(admin_token=admin)
    await drawn(api)
    mine = await submit(api, name="follow @amadraws")
    assert mine["status"] == "pending"
    assert "@amadraws" not in mine["note"]  # the creator gets the plain note, never the reviewer's words
    [entry] = (await api.client.get("/admin/gallery", headers={"Authorization": f"Bearer {admin}"})).json()
    assert entry["creator"]["name"] == "follow @amadraws"
    assert entry["note"] == "GAL-08: The name has a social handle."


async def test_countries_lists_every_code_and_only_suggests_one_from_the_request(make_api: Callable[..., Api]) -> None:
    api = make_api()
    r = (await api.client.get("/gallery/countries", headers={"Accept-Language": "en-KE,en;q=0.9"})).json()
    assert len(r["codes"]) == 249
    assert r["suggested"] == "KE"
    for header, expected in (("en", None), ("", None), ("fr-CA, en-US", "CA"), ("zh-Hant-TW", "TW"), ("en-XX", None)):
        got = (await api.client.get("/gallery/countries", headers={"Accept-Language": header})).json()
        assert got["suggested"] == expected, header


async def test_a_reserved_name_waits_with_a_clear_note_and_the_admin_makes_it_official(
    make_api: Callable[..., Api],
) -> None:
    admin = "admin-token-for-tests-0123456789abcdef"
    auth = {"Authorization": f"Bearer {admin}"}
    api = make_api(admin_token=admin)
    await drawn(api)
    mine = await submit(api, name="Frameteller  Team")
    assert mine["status"] == "pending"
    assert mine["note"] == "That name is reserved for official Frameteller entries, so a person will look at it first."
    assert not [r for r in api.fakes.reviewer.requests if "shown as the author" in r.subject]  # no moderation review
    assert (await api.client.get("/gallery")).json()["entries"] == []

    [entry] = (await api.client.get("/admin/gallery", headers=auth)).json()
    assert entry["note"].startswith("GAL-08: The name is reserved")
    assert (
        await api.client.patch(f"/admin/gallery/{entry['id']}", json={"name": "Frameteller team"})
    ).status_code == 401
    r = await api.client.patch(f"/admin/gallery/{entry['id']}", json={"name": "Frameteller team"}, headers=auth)
    assert r.json()["creator"] == {"name": "Frameteller team", "country": "", "official": True}
    assert r.json()["status"] == "pending"  # signing does not publish
    await api.client.post(f"/admin/gallery/{entry['id']}", json={"action": "publish"}, headers=auth)
    [card] = (await api.client.get("/gallery")).json()["entries"]
    assert card["creator"] == {"name": "Frameteller team", "country": "", "official": True}
    assert (await share_page(api))["creator"]["official"] is True
