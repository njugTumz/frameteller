"""The judge pass: the private link's token becomes a signed cookie; judges skip visitor caps and the public cap."""

import hashlib
import hmac
from collections.abc import Callable
from datetime import UTC, datetime

import httpx2

from frameteller.interface.judge import COOKIE, _key, issue, pass_id, valid
from tests.interface.conftest import Api

TOKEN = "judge-token-for-tests-0123456789abcdef"
ME = {"X-Visitor-Id": "browser-0123456789abcdef"}
ADMIN = "admin-token-for-tests-0123456789abcdef"


async def test_the_link_token_sets_a_cookie_and_status_shows_the_badge(make_api: Callable[..., Api]) -> None:
    api = make_api(judge_token=TOKEN)
    assert (await api.client.get("/status")).json()["judge"] is False

    r = await api.client.post("/judge", json={"token": TOKEN})
    assert r.status_code == 200
    assert r.json()["judge"] is True
    cookie = r.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE}=v2.")
    assert "HttpOnly" in cookie
    assert TOKEN not in cookie
    assert (await api.client.get("/status")).json()["judge"] is True

    assert (await api.client.delete("/judge")).status_code == 204
    assert (await api.client.get("/status")).json()["judge"] is False


async def test_a_wrong_token_is_refused_and_no_pass_without_a_token(make_api: Callable[..., Api]) -> None:
    api = make_api(judge_token=TOKEN)
    r = await api.client.post("/judge", json={"token": TOKEN[:-1] + "x"})
    assert r.status_code == 403
    assert "set-cookie" not in r.headers
    assert (await make_api().client.post("/judge", json={"token": TOKEN})).status_code == 404


async def test_a_forged_or_rotated_cookie_is_public(make_api: Callable[..., Api]) -> None:
    api = make_api(judge_token=TOKEN)
    old, _ = issue("the-previous-judge-token-0123456789abcdef", 21)
    api.client.cookies.set(COOKIE, old)
    assert (await api.client.get("/status")).json()["judge"] is False
    api.client.cookies.set(COOKIE, "v1.99999999999.0000")
    assert (await api.client.get("/status")).json()["judge"] is False


def test_passes_run_out() -> None:
    value, expires = issue(TOKEN, 1, now=lambda: 1000.0)
    assert valid(TOKEN, value, now=lambda: expires - 1)
    assert not valid(TOKEN, value, now=lambda: expires + 1)
    assert not valid(None, value)


async def test_judges_skip_the_per_visitor_story_limit(make_api: Callable[..., Api]) -> None:
    api = make_api(judge_token=TOKEN)
    await api.client.post("/judge", json={"token": TOKEN})
    for n in range(5):
        r = await api.client.post("/projects", json={"title": f"Judge story {n}"}, headers=ME)
        assert r.status_code == 201


async def test_judges_spend_from_their_own_pool_when_the_public_cap_is_spent(make_api: Callable[..., Api]) -> None:
    api = make_api(judge_token=TOKEN, budget_per_day_usd=0.05, budget_days_usd="", judge_budget_per_day_usd=1)
    day = api.container.settings.budget_calendar.day(datetime.now(UTC))  # the day is UTC+4
    api.fakes.ledger.by_day[day] = 0.05  # the public cap is spent
    assert (await api.client.get("/status")).json()["full"] is True
    public = await api.client.post("/projects/p1/shots/1/panel", json={})
    assert public.status_code == 202
    await api.settle()
    assert api.fakes.ledger.by_day[day] == 0.05  # the public render was refused: the studio is full

    await api.client.post("/judge", json={"token": TOKEN})
    assert (await api.client.get("/status")).json()["full"] is False
    assert (await api.client.post("/projects/p1/shots/2/panel", json={})).status_code == 202
    await api.settle()
    assert api.fakes.ledger.by_day[f"{day}.judge"] > 0
    assert api.fakes.ledger.by_day[day] == 0.05


def browser(api: Api) -> httpx2.AsyncClient:
    """Another browser: its own cookie jar against the same studio."""
    return httpx2.AsyncClient(transport=httpx2.ASGITransport(app=api.app), base_url="http://test")


async def test_one_link_serves_any_number_of_judges_each_with_a_pass_of_their_own(
    make_api: Callable[..., Api],
) -> None:
    api = make_api(judge_token=TOKEN)
    judges = [browser(api) for _ in range(4)]
    passes = []
    for j in judges:
        r = await j.post("/judge", json={"token": TOKEN})  # the token is never used up
        assert r.status_code == 200
        passes.append(pass_id(TOKEN, j.cookies[COOKIE]))
    assert None not in passes
    assert len(set(passes)) == 4  # a pass per browser
    for j in judges:
        assert (await j.get("/status")).json()["judge"] is True
    assert (await api.client.get("/status")).json()["judge"] is False  # a browser without the link is public
    for j in judges:
        await j.aclose()


def test_passes_issued_before_ids_stay_valid_until_they_run_out() -> None:
    expires = 5000
    signed = f"v1.{expires}"
    old = f"{signed}.{hmac.new(_key(TOKEN), signed.encode(), hashlib.sha256).hexdigest()}"
    assert pass_id(TOKEN, old, now=lambda: 4000) is not None
    assert pass_id(TOKEN, old, now=lambda: 6000) is None


async def test_each_pass_has_its_own_daily_story_limit_with_a_friendly_message(make_api: Callable[..., Api]) -> None:
    api = make_api(judge_token=TOKEN, judge_stories_per_pass_per_day=2)
    first, second = browser(api), browser(api)
    for j in (first, second):
        await j.post("/judge", json={"token": TOKEN})
    for n in range(2):
        assert (await first.post("/projects", json={"title": f"Story {n}"}, headers=ME)).status_code == 201
    r = await first.post("/projects", json={"title": "One more"}, headers=ME)
    assert r.status_code == 429
    assert "This judge pass has started 2 stories today" in r.json()["error"]["message"]
    assert "saved" in r.json()["error"]["message"]
    # Another judge, from the same link, still has their own stories.
    assert (await second.post("/projects", json={"title": "Mine"}, headers=ME)).status_code == 201
    for j in (first, second):
        await j.aclose()


async def test_the_admin_overview_lists_passes_and_can_lower_the_reserve(make_api: Callable[..., Api]) -> None:
    api = make_api(judge_token=TOKEN, admin_token=ADMIN, judge_budget_per_day_usd=15, judge_budget_days_usd="")
    admin = {"Authorization": f"Bearer {ADMIN}"}
    judge = browser(api)
    await judge.post("/judge", json={"token": TOKEN})
    assert (await judge.post("/projects", json={"title": "A judge's story"}, headers=ME)).status_code == 201
    assert (await judge.post("/projects/p1/shots/1/panel", json={})).status_code == 202
    await api.settle()

    overview = (await api.client.get("/admin/overview", headers=admin)).json()
    [seen] = overview["judge_passes"]
    assert seen["pass_id"] == pass_id(TOKEN, judge.cookies[COOKIE])
    assert seen["stories_today"] == 1
    assert seen["spent_today_usd"] > 0  # the render, counted for this pass
    assert overview["judge_reserve"] == {"calendar_usd": 15, "override_usd": None, "stories_per_pass_per_day": 15}

    lowered = await api.client.put("/admin/judge/reserve", json={"usd": 0.001}, headers=admin)
    assert lowered.json()["override_usd"] == 0.001
    judges = next(
        b for b in (await api.client.get("/admin/overview", headers=admin)).json()["budgets"] if b["lane"] == "judge"
    )
    assert judges["cap_usd"] == 0.001
    assert (await judge.get("/status")).json()["full"] is True  # judges are held at once, no redeploy
    # It only lowers: an override above the calendar's reserve leaves the calendar's.
    await api.client.put("/admin/judge/reserve", json={"usd": 100}, headers=admin)
    assert (await judge.get("/status")).json()["full"] is False
    assert (await api.client.put("/admin/judge/reserve", json={"usd": 1}, headers={})).status_code == 401
    await judge.aclose()
