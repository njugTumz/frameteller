"""The judge pass: the private link's token becomes a signed cookie; judges skip visitor caps and the public cap."""

from collections.abc import Callable
from datetime import UTC, datetime

from frameteller.interface.judge import COOKIE, issue, valid
from tests.interface.conftest import Api

TOKEN = "judge-token-for-tests-0123456789abcdef"
ME = {"X-Visitor-Id": "browser-0123456789abcdef"}


async def test_the_link_token_sets_a_cookie_and_status_shows_the_badge(make_api: Callable[..., Api]) -> None:
    api = make_api(judge_token=TOKEN)
    assert (await api.client.get("/status")).json()["judge"] is False

    r = await api.client.post("/judge", json={"token": TOKEN})
    assert r.status_code == 200
    assert r.json()["judge"] is True
    cookie = r.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE}=v1.")
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
