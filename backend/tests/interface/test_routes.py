from collections.abc import Callable

import httpx2

from frameteller.application.ports import Segment
from frameteller.domain import MediaRef
from frameteller.interface.routes.shares import preview_description
from tests.builders import bitmap, project
from tests.interface.conftest import Api

MIRA = Segment(bitmap(100, 100, 300, 400).box, bitmap(100, 100, 300, 400), "Mira", MediaRef("projects/p1/cut.png"))


async def test_create_and_get_a_project(api: Api) -> None:
    created = await api.client.post("/projects", json={"title": "The Lantern Cat"})
    assert created.status_code == 201
    body = created.json()
    assert body["title"] == "The Lantern Cat"
    assert body["cast"] == {"status": "draft", "characters": []}
    assert body["style"] == "pencil"

    got = await api.client.get(f"/projects/{body['id']}")
    assert got.status_code == 200
    assert got.json() == body


async def test_a_project_keeps_its_style(api: Api) -> None:
    created = await api.client.post("/projects", json={"title": "Paper", "style": "paper_cutout"})
    assert created.json()["style"] == "paper_cutout"
    assert (await api.client.get(f"/projects/{created.json()['id']}")).json()["style"] == "paper_cutout"
    assert (await api.client.post("/projects", json={"style": "oil"})).status_code == 422


async def test_unknown_project_is_404_with_a_user_message(api: Api) -> None:
    r = await api.client.get("/projects/nope")
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "project_not_found", "message": "We couldn't find that project."}}
    assert (await api.client.get("/projects/bad%20id")).status_code == 422


async def test_project_shows_cast_shots_and_media_urls(api: Api) -> None:
    body = (await api.client.get("/projects/p1")).json()
    assert body["cast"]["status"] == "approved"
    assert {c["id"]: c["reference_url"] for c in body["cast"]["characters"]} == {
        "mira": "/media/refs/mira.webp",
        "cat": "/media/refs/cat.webp",
    }
    assert [s["number"] for s in body["shots"]] == [1, 2, 3]
    assert body["shots"][0]["panel"] is None


async def test_render_is_queued_then_shows_on_the_project_and_in_media(api: Api) -> None:
    r = await api.client.post("/projects/p1/shots/2/panel", json={"quality": "final"})
    assert r.status_code == 202
    assert r.json() == {
        "kind": "generate_panel",
        "key": "generate_panel:p1:s2:r1",
        "enqueued": True,
        "shot_id": "s2",
        "revision": 1,
    }
    await api.settle()
    assert api.fakes.images.generated[0].quality == "high"

    panel = (await api.client.get("/projects/p1")).json()["shots"][1]["panel"]
    assert (panel["revision"], panel["status"], panel["width"], panel["height"]) == (1, "ready", 1920, 1280)
    media = await api.client.get(panel["image_url"])
    assert media.status_code == 200
    assert media.content == b"image-1"
    assert media.headers["cache-control"] == "private, max-age=31536000, immutable"
    again = await api.client.get(panel["image_url"], headers={"If-None-Match": media.headers["etag"]})
    assert again.status_code == 304


async def test_render_errors_map_to_http(api: Api) -> None:
    assert (await api.client.post("/projects/p1/shots/9/panel", json={})).json()["error"]["code"] == "shot_not_found"
    p = project(approved=False)
    await api.fakes.repo.save(p)
    r = await api.client.post("/projects/p1/shots/1/panel", json={})
    assert r.status_code == 409
    assert "approve the cast" in r.json()["error"]["message"]
    assert (await api.client.post("/projects/p1/shots/1/panel", json={"quality": "best"})).status_code == 422


async def test_edit_is_routed_and_rendered_in_the_background(api: Api) -> None:
    assert (
        await api.client.post("/projects/p1/shots/1/panel/edit", json={"instruction": "red coat"})
    ).status_code == 409
    await api.client.post("/projects/p1/shots/1/panel", json={})
    await api.settle()

    r = await api.client.post("/projects/p1/shots/1/panel/edit", json={"instruction": "her coat is red now"})
    assert r.status_code == 202
    assert r.json()["kind"] == "edit_panel"
    await api.settle()
    assert api.project().panel("s1").revision == 2
    assert api.fakes.director.calls == ["interpret_edit:her coat is red now"]
    assert (await api.client.post("/projects/p1/shots/1/panel/edit", json={"instruction": ""})).status_code == 422


async def test_select_hits_the_pre_segmented_mask_without_calling_sam(api: Api) -> None:
    api.fakes.sam.by_concept = {"8-year-old girl": MIRA}
    await api.client.post("/projects/p1/shots/1/panel", json={})
    await api.settle()  # render, then pre-segmentation (ADR 0006)

    # (75, 100) on a 960x640 preview is (150, 200) on the 1920x1280 panel: inside Mira.
    r = await api.client.post(
        "/projects/p1/shots/1/panel/select", json={"x": 75, "y": 100, "preview_width": 960, "preview_height": 640}
    )
    assert r.status_code == 200
    assert r.json() == {
        "cached": True,
        "mask": {
            "id": "character:mira",
            "label": "Mira",
            "character_id": "mira",
            "box": {"left": 100, "top": 100, "right": 300, "bottom": 400},
            "cutout_url": "/media/projects/p1/cut.png",
        },
    }
    assert api.fakes.sam.point_calls == []


async def test_select_on_nothing_and_over_budget(make_api: Callable[..., Api]) -> None:
    api = make_api(budget_per_project_usd=0.012)  # one panel ($0.01), then too little for SAM twice
    await api.client.post("/projects/p1/shots/2/panel", json={})
    await api.settle()  # pre-segmentation: SAM finds nothing (no concepts set) but is charged twice
    click = {"x": 10, "y": 10, "preview_width": 1920, "preview_height": 1280}

    r = await api.client.post("/projects/p1/shots/2/panel/select", json=click)
    assert r.status_code == 402
    assert r.json()["error"]["code"] == "budget_exceeded"

    api = make_api()
    await api.client.post("/projects/p1/shots/1/panel", json={})
    await api.settle()
    r = await api.client.post("/projects/p1/shots/1/panel/select", json=click)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "nothing_to_select"


async def test_reorder(api: Api) -> None:
    r = await api.client.post("/projects/p1/shots/reorder", json={"shot_ids": ["s3", "s1", "s2"]})
    assert r.status_code == 200
    assert [(s["id"], s["number"]) for s in r.json()["shots"]] == [("s3", 1), ("s1", 2), ("s2", 3)]
    assert (await api.client.post("/projects/p1/shots/reorder", json={"shot_ids": ["s3"]})).status_code == 409


async def test_cast_corrections_redraw_then_approve(api: Api) -> None:
    await api.fakes.repo.save(project(approved=False))
    r = await api.client.post("/projects/p1/cast/approve", json={})
    assert r.status_code == 409  # no sheets yet

    r = await api.client.post("/projects/p1/cast/approve", json={"descriptions": {"mira": "Mira in a green coat"}})
    assert r.json() == {"approved": False, "redrawing": ["mira"], "job_key": "generate_cast:p1:mira:id1"}
    await api.settle()
    assert api.project().bible.get("mira").reference is not None

    r = await api.client.post("/projects/p1/cast/cat/regenerate")
    assert r.status_code == 202
    await api.settle()
    assert (await api.client.post("/projects/p1/cast/approve", json={})).json()["approved"] is True
    assert (await api.client.post("/projects/p1/cast/dragon/regenerate")).status_code == 404


async def test_media_refuses_keys_outside_projects_and_missing_files(api: Api) -> None:
    assert (await api.client.get("/media/refs/mira.webp")).status_code == 404
    assert (await api.client.get("/media/projects/p1/none.webp")).status_code == 404


async def test_health_and_readiness(api: Api) -> None:
    assert (await api.client.get("/healthz")).json() == {"status": "ok"}
    r = await api.client.get("/readyz")
    assert r.json() == {"status": "ready", "checks": {"settings": "ok", "storage": "ok"}}
    api.fakes.ready = False
    r = await api.client.get("/readyz")
    assert r.status_code == 503
    assert r.json()["checks"]["storage"] == "failed"


async def test_unexpected_errors_are_json_500s(api: Api) -> None:
    async def broken(*_: object) -> None:
        raise RuntimeError("disk on fire")

    api.fakes.repo.get = broken  # type: ignore[method-assign,assignment]
    client = httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=api.app, raise_app_exceptions=False), base_url="http://t"
    )
    r = await client.get("/projects/p1")
    assert r.status_code == 500
    assert r.json() == {"error": {"code": "error", "message": "Something went wrong. Please try again."}}
    assert "disk on fire" not in r.text


async def test_rename_remove_and_merge_characters(api: Api) -> None:
    renamed = await api.client.patch("/projects/p1/cast/cat", json={"name": "Pip"})
    assert renamed.status_code == 200
    assert {c["id"]: c["name"] for c in renamed.json()["cast"]["characters"]}["cat"] == "Pip"

    await api.client.post("/projects/p1/shots/2/panel", json={"quality": "draft"})
    await api.settle()
    merged = await api.client.post("/projects/p1/cast/cat/merge", json={"into": "mira"})
    assert merged.status_code == 200
    body = merged.json()
    assert [c["id"] for c in body["cast"]["characters"]] == ["mira"]
    assert body["shots"][1]["character_ids"] == ["mira"]
    assert body["shots"][1]["panel"]["outdated"] is True
    await api.settle()
    assert api.project().panels["s2"].revision == 2  # redrawn as a draft
    assert not api.project().panels["s2"].outdated

    assert (await api.client.post("/projects/p1/cast/mira/merge", json={"into": "mira"})).status_code == 422
    assert (await api.client.post("/projects/p1/cast/mira/merge", json={"into": "owl"})).status_code == 404
    removed = await api.client.delete("/projects/p1/cast/mira")
    assert removed.status_code == 200
    assert removed.json()["cast"] == {"status": "draft", "characters": []}
    assert all(s["character_ids"] == [] for s in removed.json()["shots"])
    assert (await api.client.delete("/projects/p1/cast/mira")).status_code == 404


async def test_delete_my_recording(api: Api) -> None:
    from frameteller.domain import Narration

    p = api.project()
    p.keep_narration(Narration("s1", MediaRef("projects/p1/narration/s1.wav"), 5000))
    await api.fakes.repo.save(p)
    api.fakes.storage.files["projects/p1/narration/s1.wav"] = (b"RIFF\x00\x00\x00\x00WAVE", "audio/wav")
    body = (await api.client.get("/projects/p1")).json()
    assert body["narrations"] == [{"session": "s1", "duration_ms": 5000, "url": "/media/projects/p1/narration/s1.wav"}]
    assert (await api.client.get(body["narrations"][0]["url"])).headers["content-type"] == "audio/wav"

    deleted = await api.client.delete("/projects/p1/narration")
    assert deleted.status_code == 200
    assert deleted.json()["narrations"] == []
    assert "projects/p1/narration/s1.wav" not in api.fakes.storage.files


async def test_moving_an_object_saves_a_layer_and_shows_the_composite(api: Api) -> None:
    api.fakes.sam.by_concept = {"8-year-old girl": MIRA}
    api.fakes.storage.files["projects/p1/cut.png"] = (b"mira-cut", "image/png")
    await api.client.post("/projects/p1/shots/1/panel", json={})
    await api.settle()

    r = await api.client.post(
        "/projects/p1/shots/1/panel/layers", json={"object_id": "character:mira", "dx": 30, "dy": 5, "scale": 1.25}
    )
    assert r.status_code == 202
    assert r.json()["kind"] == "compose_panel"
    await api.settle()  # clean plate, then the composite

    panel = (await api.client.get("/projects/p1")).json()["shots"][0]["panel"]
    assert panel["revision"] == 1
    assert panel["shown_revision"] == 2
    assert panel["base_image_url"] == "/media/projects/p1/panels/s1/r1/image"
    assert "/composites/" in panel["image_url"]
    assert panel["layers"] == [{"object_id": "character:mira", "dx": 30, "dy": 5, "scale": 1.25, "deleted": False}]
    assert (await api.client.get(panel["image_url"])).status_code == 200
    [(_, prompt)] = api.fakes.images.edits
    assert prompt.startswith("Remove the 8-year-old girl")


async def test_layers_need_a_known_object_and_a_sane_scale(api: Api) -> None:
    await api.client.post("/projects/p1/shots/1/panel", json={})
    await api.settle()
    unknown = await api.client.post("/projects/p1/shots/1/panel/layers", json={"object_id": "character:ghost"})
    assert unknown.status_code in (404, 422)
    huge = await api.client.post("/projects/p1/shots/1/panel/layers", json={"object_id": "x", "scale": 9})
    assert huge.status_code == 422


async def test_job_status_is_the_fallback_for_missed_job_updates(api: Api) -> None:
    for n in (1, 2, 3):
        await api.client.post(f"/projects/p1/shots/{n}/panel", json={})
    await api.settle()
    key = (await api.client.post("/projects/p1/exports/animatic", json={})).json()["key"]
    await api.settle()
    assert (await api.client.get(f"/projects/p1/jobs/{key}")).json() == {
        "key": key,
        "status": "succeeded",
        "message": None,
    }
    # A job this server never saw (it ran on a replaced revision), and another project's key.
    lost = "export_animatic:p1:0123456789ab"
    assert (await api.client.get(f"/projects/p1/jobs/{lost}")).json()["status"] == "unknown"
    other = key.replace(":p1:", ":p2:")
    assert (await api.client.get(f"/projects/p1/jobs/{other}")).json()["status"] == "unknown"
    assert (await api.client.get(f"/projects/p2/jobs/{key}")).json()["status"] == "unknown"


async def test_export_animatic_then_play_seek_and_download_it(api: Api) -> None:
    refused = await api.client.post("/projects/p1/exports/animatic", json={})
    assert refused.status_code == 409  # no panels yet
    for n in (1, 2, 3):
        await api.client.post(f"/projects/p1/shots/{n}/panel", json={})
    await api.settle()

    r = await api.client.post("/projects/p1/exports/animatic", json={"subtitles": True})
    assert r.status_code == 202
    assert r.json()["kind"] == "export_animatic"
    await api.settle()

    animatic = (await api.client.get("/projects/p1")).json()["animatic"]
    assert animatic["duration_ms"] == 12000
    assert animatic["subtitles"] is True
    assert animatic["voiced"] is False
    whole = await api.client.get(animatic["url"])
    assert whole.headers["content-type"] == "video/mp4"
    assert whole.headers["accept-ranges"] == "bytes"
    part = await api.client.get(animatic["url"], headers={"Range": "bytes=4-7"})
    assert part.status_code == 206
    assert part.content == b"ftyp"
    assert part.headers["content-range"] == f"bytes 4-7/{len(whole.content)}"
    tail = await api.client.get(animatic["url"], headers={"Range": "bytes=-4"})
    assert tail.content == whole.content[-4:]
    beyond = await api.client.get(animatic["url"], headers={"Range": "bytes=999-"})
    assert beyond.status_code == 416
    download = await api.client.get(animatic["url"] + "?download=1")
    assert download.headers["content-disposition"].startswith('attachment; filename="animatic-')


async def test_storyboard_pdf_downloads(api: Api) -> None:
    r = await api.client.get("/projects/p1/exports/storyboard.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"] == 'attachment; filename="storyboard.pdf"'
    assert r.content.startswith(b"%PDF")


async def test_share_link_previews_on_x_and_shows_a_read_only_storyboard(make_api: Callable[..., Api]) -> None:
    api = make_api(allowed_origins="https://studio.example,http://localhost:5173")
    await api.client.post("/projects/p1/shots/1/panel", json={})
    await api.settle()

    shared = await api.client.post("/projects/p1/share")
    assert shared.status_code == 200
    link = shared.json()
    token = link["token"]
    assert link["url"].endswith(f"/s/{token}")
    assert link["page_url"] == f"https://studio.example/s/{token}"
    assert (await api.client.get("/projects/p1")).json()["share_token"] == token

    stub = await api.client.get(f"/s/{token}")
    assert stub.status_code == 200
    assert '<meta property="og:title" content="The Lantern Cat">' in stub.text
    assert (
        '<meta property="og:description" content="A 3-shot storyboard, told out loud with Frameteller.">' in stub.text
    )
    assert f'/shares/{token}/og.png"' in stub.text
    assert f'content="0;url=https://studio.example/s/{token}"' in stub.text
    assert "p1" not in stub.text.replace(f"/s/{token}", "")  # never the project id

    page = (await api.client.get(f"/shares/{token}")).json()
    assert page["title"] == "The Lantern Cat"
    assert [s["image_url"] for s in page["shots"]] == [f"/shares/{token}/panels/1", None, None]
    assert page["animatic"] is None
    assert "p1" not in str(page)
    assert (await api.client.get(f"/shares/{token}/panels/1")).status_code == 200
    assert (await api.client.get(f"/shares/{token}/panels/2")).status_code == 404
    og = await api.client.get(f"/shares/{token}/og.png")
    assert og.headers["content-type"] == "image/png"

    assert (await api.client.delete("/projects/p1/share")).status_code == 204
    assert (await api.client.get(f"/shares/{token}")).status_code == 404
    gone = await api.client.get(f"/s/{token}")
    assert gone.status_code == 404
    assert "url=https://studio.example/s/" in gone.text  # the share page explains


async def test_a_share_link_is_unlisted_until_the_owner_makes_it_public(api: Api) -> None:
    await api.client.post("/projects/p1/shots/1/panel", json={})
    await api.settle()
    link = (await api.client.post("/projects/p1/share")).json()
    token = link["token"]
    assert link["public"] is False
    assert (await api.client.get("/projects/p1")).json()["share_public"] is False
    stub = await api.client.get(f"/s/{token}")
    assert '<meta name="robots" content="noindex, nofollow">' in stub.text
    for path in (f"/s/{token}", f"/shares/{token}", f"/shares/{token}/panels/1", f"/shares/{token}/og.png"):
        assert (await api.client.get(path)).headers["x-robots-tag"] == "noindex, nofollow", path
    assert (await api.client.get(f"/shares/{token}")).json()["public"] is False

    public = (await api.client.post("/projects/p1/share", json={"public": True})).json()
    assert public == {**link, "public": True}  # the same link, now listed
    stub = await api.client.get(f"/s/{token}")
    assert 'name="robots"' not in stub.text
    assert "x-robots-tag" not in stub.headers
    assert "x-robots-tag" not in (await api.client.get(f"/shares/{token}/panels/1")).headers
    assert (await api.client.get(f"/shares/{token}")).json()["public"] is True

    await api.client.post("/projects/p1/share", json={"public": False})
    assert (await api.client.get(f"/shares/{token}")).headers["x-robots-tag"] == "noindex, nofollow"
    await api.client.delete("/projects/p1/share")
    gone = await api.client.get(f"/s/{token}")
    assert gone.headers["x-robots-tag"] == "noindex, nofollow"


def test_share_preview_wording() -> None:
    assert preview_description(6, True) == "A 6-shot storyboard and animatic, told out loud with Frameteller."
    assert preview_description(1, False) == "A 1-shot storyboard, told out loud with Frameteller."
    assert preview_description(0, False) == "A storyboard, told out loud with Frameteller."
