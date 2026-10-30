"""Editing the story over HTTP: remove and merge beats, delete shots, and costumes on the cast and the shots."""

from dataclasses import replace

from frameteller.domain import MediaRef, Project, TranscriptTurn
from tests.builders import costume_project
from tests.fakes import PANEL_SIZE
from tests.interface.conftest import Api


async def recorded(api: Api) -> None:
    """Three beats of one recording ("rec"), one shot each, all drawn."""
    p = costume_project(looks=False)
    p.turns = [TranscriptTurn(f"rec-{i}", t.text, t.start_ms, t.end_ms) for i, t in enumerate(p.turns[:3])]
    p.shots = [replace(s, source_turn_ids=(f"rec-{i}",)) for i, s in enumerate(p.shots[:3])]
    for s in p.shots:
        p.panel(s.id).record_render(1, MediaRef(f"panels/{s.id}.webp"), f"resp_{s.id}", PANEL_SIZE)
    await api.fakes.repo.save(p)


async def test_removing_a_beat_takes_its_shot_out_and_renumbers(api: Api) -> None:
    await recorded(api)
    r = await api.client.delete("/projects/p1/turns/rec-1")
    assert r.status_code == 200
    body = r.json()
    assert [t["id"] for t in body["turns"]] == ["rec-0", "rec-2"]
    assert [(s["id"], s["number"]) for s in body["shots"]] == [("s1", 1), ("s3", 2)]
    r = await api.client.delete("/projects/p1/turns/rec-1")
    assert (r.status_code, r.json()["error"]["code"]) == (404, "beat_not_found")
    assert (await api.client.delete("/projects/p1/turns/bad%20id")).status_code == 422


async def test_merging_a_beat_with_the_previous_or_next_one(api: Api) -> None:
    await recorded(api)
    r = await api.client.post("/projects/p1/turns/rec-1/merge", json={"other": "previous"})
    assert r.status_code == 200
    turns = r.json()["turns"]
    assert [t["id"] for t in turns] == ["rec-0", "rec-2"]
    assert turns[0]["text"].endswith(
        "farmer costume: blue denim overalls over a white shirt, a red bandana around "
        "her neck and brown cowgirl boots. She looks in the mirror and grins."
    )
    r = await api.client.post("/projects/p1/turns/rec-2/merge", json={"other": "next"})
    assert (r.status_code, r.json()["error"]["code"]) == (422, "invalid_value")
    assert (await api.client.post("/projects/p1/turns/rec-0/merge", json={"other": "sideways"})).status_code == 422


async def test_deleting_a_shot_by_id(api: Api) -> None:
    await recorded(api)
    r = await api.client.delete("/projects/p1/shots/s2")
    assert r.status_code == 200
    assert [(s["id"], s["number"]) for s in r.json()["shots"]] == [("s1", 1), ("s3", 2)]
    assert len(r.json()["turns"]) == 3  # its words stay
    assert (await api.client.delete("/projects/p1/shots/s2")).json()["error"]["code"] == "shot_not_found"


async def test_the_cast_shows_each_look_and_the_shots_say_who_wears_it(api: Api) -> None:
    await api.fakes.repo.save(costume_project())
    body = (await api.client.get("/projects/p1")).json()
    wren = next(c for c in body["cast"]["characters"] if c["id"] == "wren")
    assert wren["looks"] == [
        {
            "id": "farmer_costume",
            "label": "Farmer costume",
            "clothes": "blue denim overalls over a white shirt, a red bandana around her neck, brown cowgirl boots",
            "reference_url": "/media/refs/wren-farmer.webp",
            "from_shots": [2, 3, 4, 5, 6],
            "sheet_error": None,
        }
    ]
    assert [s["looks"] for s in body["shots"]] == [{}, *[{"wren": "farmer_costume"}] * 5]


async def test_try_again_on_a_look_redraws_its_sheet(api: Api) -> None:
    p: Project = costume_project()
    await api.fakes.repo.save(p)
    r = await api.client.post("/projects/p1/cast/wren/looks/farmer_costume/regenerate")
    assert r.status_code == 202
    await api.settle()
    [sheet] = api.fakes.images.generated
    assert sheet.references == (MediaRef("refs/wren.webp"),)
    assert api.project().bible.get("wren").look("farmer_costume").reference == MediaRef(
        "projects/p1/characters/wren/looks/farmer_costume"
    )
    r = await api.client.post("/projects/p1/cast/wren/looks/witch/regenerate")
    assert (r.status_code, r.json()["error"]["code"]) == (404, "character_not_found")
