"""The public-demo guardrails over HTTP: visitor and project limits, the full studio and the kill switch."""

from collections.abc import Callable

from tests.interface.conftest import Api, WsClient

CLICK = {"x": 10, "y": 10, "preview_width": 1920, "preview_height": 1280}


async def test_a_visitor_starts_three_stories_a_day(api: Api) -> None:
    me = {"X-Visitor-Id": "browser-0123456789abcdef"}
    for n in range(3):
        assert (await api.client.post("/projects", json={"title": f"Story {n}"}, headers=me)).status_code == 201

    r = await api.client.post("/projects", json={"title": "One more"}, headers=me)
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "limit_reached"
    assert "started 3 stories today" in r.json()["error"]["message"]

    other_browser = {"X-Visitor-Id": "browser-fedcba9876543210"}
    assert (await api.client.post("/projects", json={}, headers=other_browser)).status_code == 201


async def test_renders_and_edits_per_project(make_api: Callable[..., Api]) -> None:
    api = make_api(limit_renders_per_project=2)
    assert (await api.client.post("/projects/p1/shots/1/panel", json={})).status_code == 202
    await api.settle()
    edit = await api.client.post("/projects/p1/shots/1/panel/edit", json={"instruction": "her coat is red now"})
    assert edit.status_code == 202

    r = await api.client.post("/projects/p1/shots/2/panel", json={})
    assert r.status_code == 429
    assert r.json()["error"] == {
        "code": "limit_reached",
        "message": "This story has used its 2 drawings and edits for the public demo. "
        "Export the animatic or share it as it is.",
    }


async def test_exports_per_project(make_api: Callable[..., Api]) -> None:
    api = make_api(limit_exports_per_project=1)
    for n in (1, 2, 3):
        await api.client.post(f"/projects/p1/shots/{n}/panel", json={})
    await api.settle()
    assert (await api.client.post("/projects/p1/exports/animatic", json={})).status_code == 202
    await api.settle()

    r = await api.client.post("/projects/p1/exports/animatic", json={"subtitles": True})
    assert (r.status_code, r.json()["error"]["code"]) == (429, "limit_reached")


async def test_the_full_studio_still_opens_shared_storyboards(make_api: Callable[..., Api]) -> None:
    api = make_api(budget_per_day_usd=0.012)
    token = (await api.client.post("/projects/p1/share")).json()["token"]
    await api.client.post("/projects/p1/shots/1/panel", json={})
    await api.settle()  # one panel ($0.01) and pre-segmentation: the day's cap is reached

    r = await api.client.post("/projects/p1/shots/1/panel/select", json=CLICK)
    assert (r.status_code, r.json()["error"]) == (
        503,
        {"code": "studio_full", "message": "The studio is full for today. Come back tomorrow."},
    )
    status = (await api.client.get("/status")).json()
    assert (status["paused"], status["full"]) == (False, True)
    assert (await api.client.get(f"/shares/{token}")).status_code == 200


async def test_status_lists_the_limits(api: Api) -> None:
    assert (await api.client.get("/status")).json() == {
        "paused": False,
        "full": False,
        "limits": {
            "projects_per_visitor_per_day": 3,
            "narration_minutes_per_session": 3,
            "shots_per_episode": 12,
            "episodes_per_script": 3,
            "script_characters": 4000,
            "renders_per_project": 60,
            "exports_per_project": 3,
        },
    }


async def test_the_kill_switch_pauses_the_studio_but_not_shares_or_probes(make_api: Callable[..., Api]) -> None:
    token = (await make_api().client.post("/projects/p1/share")).json()["token"]
    api = make_api(demo_paused=True, allowed_origins="https://app.example")

    r = await api.client.post("/projects", json={})
    assert (r.status_code, r.json()["error"]["code"]) == (503, "paused")
    assert r.json()["error"]["message"] == "Frameteller is taking a short break. Back soon."
    assert (await api.client.get("/projects/p1")).status_code == 503
    preflight = await api.client.options(
        "/projects", headers={"Origin": "https://app.example", "Access-Control-Request-Method": "POST"}
    )
    assert preflight.headers["access-control-allow-origin"] == "https://app.example"  # the 503 stays readable

    for path in ("/healthz", "/readyz", f"/shares/{token}", f"/s/{token}"):
        assert (await api.client.get(path)).status_code == 200, path
    assert (await api.client.get("/status")).json()["paused"] is True

    ws = WsClient(api.app, "/ws/projects/p1/session")
    assert not await ws.connect()
    assert ws.close_code == 4503
    await ws.finish()
