"""The admin's Errors tab over HTTP: what is recorded, failed jobs with Retry, and "Report a problem"."""

from collections.abc import Callable
from typing import Any

from tests.interface.conftest import Api

ADMIN = "admin-token-for-tests-0123456789abcdef"
AUTH = {"Authorization": f"Bearer {ADMIN}"}


async def errors(api: Api) -> dict[str, Any]:
    r = await api.client.get("/admin/errors", headers=AUTH)
    assert r.status_code == 200
    body: dict[str, Any] = r.json()
    return body


async def test_the_tab_needs_the_admin_token(make_api: Callable[..., Api]) -> None:
    assert (await make_api().client.get("/admin/errors", headers=AUTH)).status_code == 404
    api = make_api(admin_token=ADMIN)
    assert (await api.client.get("/admin/errors")).status_code == 401
    assert (await api.client.post("/admin/jobs/retry", json={"key": "k"})).status_code == 401
    assert await errors(api) == {"recent": [], "counts_24h": {}, "health": [], "failed_jobs": [], "reports": []}


async def test_an_invalid_request_is_recorded_and_keeps_its_422_body(make_api: Callable[..., Api]) -> None:
    api = make_api(admin_token=ADMIN)
    r = await api.client.post("/projects", json={"style": "oil"})
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == ["body", "style"]  # FastAPI's own shape, unchanged

    (error,) = (await errors(api))["recent"]
    assert (error["component"], error["code"]) == ("api", "invalid_request")
    assert error["message"].startswith("POST /projects: body.style")
    assert len(error["visitor"]) == 12
    assert "127.0.0.1" not in str(error)
    assert (await errors(api))["counts_24h"] == {"invalid_request": 1}


async def test_not_found_and_admin_mistakes_are_not_recorded(make_api: Callable[..., Api]) -> None:
    api = make_api(admin_token=ADMIN)
    assert (await api.client.get("/projects/nope")).status_code == 404
    assert (await api.client.get("/admin/errors", headers={"Authorization": "Bearer nope"})).status_code == 401
    assert (await errors(api))["recent"] == []


async def test_a_job_that_gave_up_is_listed_then_retried(make_api: Callable[..., Api]) -> None:
    api = make_api(admin_token=ADMIN)
    api.fakes.images.fail_next = True
    key = (await api.client.post("/projects/p1/shots/1/panel", json={})).json()["key"]
    await api.settle()

    tab = await errors(api)
    (job,) = tab["failed_jobs"]
    assert (job["key"], job["kind"], job["component"], job["project_id"]) == (key, "generate_panel", "image", "p1")
    assert "payload" not in job
    assert any(e["code"].startswith("job_failed") and e["project_id"] == "p1" for e in tab["recent"])

    r = await api.client.post("/admin/jobs/retry", json={"key": key}, headers=AUTH)
    assert r.status_code == 202
    assert r.json()["key"] == key
    await api.settle()
    assert api.project().panel("s1").status.value == "ready"
    assert (await errors(api))["failed_jobs"] == []

    r = await api.client.post("/admin/jobs/retry", json={"key": key}, headers=AUTH)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "retry_refused")


async def test_a_retry_is_refused_while_the_studio_is_full(make_api: Callable[..., Api]) -> None:
    api = make_api(admin_token=ADMIN, budget_per_day_usd=0.012)
    api.fakes.images.fail_next = True
    failed = (await api.client.post("/projects/p1/shots/1/panel", json={})).json()["key"]
    await api.settle()  # the failed panel was charged ($0.01): another would pass the day's cap

    r = await api.client.post("/admin/jobs/retry", json={"key": failed}, headers=AUTH)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "retry_refused")
    assert [j["key"] for j in (await errors(api))["failed_jobs"]] == [failed]  # still there for later


async def test_report_a_problem(make_api: Callable[..., Api]) -> None:
    api = make_api(admin_token=ADMIN)
    r = await api.client.post("/projects/p1/problems", json={"text": "The cat vanished in shot 2."})
    assert r.status_code == 201
    assert (await api.client.post("/projects/p1/problems", json={})).status_code == 201  # words are optional

    reports = (await errors(api))["reports"]
    assert [(p["project_id"], p["text"]) for p in reports] == [("p1", ""), ("p1", "The cat vanished in shot 2.")]
    assert len(reports[0]["visitor"]) == 12

    assert (await api.client.post("/projects/p1/problems", json={"text": "x" * 501})).status_code == 422
    assert (await api.client.post("/projects/nope/problems", json={})).status_code == 404
    for _ in range(3):
        assert (await api.client.post("/projects/p1/problems", json={})).status_code == 201
    r = await api.client.post("/projects/p1/problems", json={"text": "one more"})
    assert (r.status_code, r.json()["error"]["code"]) == (429, "limit_reached")
