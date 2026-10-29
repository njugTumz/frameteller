"""The admin API: bearer ADMIN_TOKEN, or nothing at all."""

from collections.abc import Callable

from tests.interface.conftest import Api

ADMIN = "admin-token-for-tests-0123456789abcdef"
AUTH = {"Authorization": f"Bearer {ADMIN}"}


async def test_the_overview_needs_the_admin_token(make_api: Callable[..., Api]) -> None:
    assert (await make_api().client.get("/admin/overview", headers=AUTH)).status_code == 404
    api = make_api(admin_token=ADMIN, budget_days_usd="")  # any day: the default cap
    assert (await api.client.get("/admin/overview")).status_code == 401
    assert (await api.client.get("/admin/overview", headers={"Authorization": "Bearer nope"})).status_code == 401
    r = await api.client.get("/admin/overview", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert [b["lane"] for b in body["budgets"]] == ["public", "judge"]
    assert body["budgets"][0]["cap_usd"] == 10
    assert {g["name"] for g in body["gates"]} == {"sessions", "images", "sam", "exports", "jobs"}
