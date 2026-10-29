"""The continuity supervisor over HTTP: badges on the project, the feed, apply, accept and the setting."""

from frameteller.application.events import SupervisorNeedsUser
from frameteller.domain import Decision, Issue, Severity, Verdict
from frameteller.interface.dto import event_message
from tests.fakes import verdict
from tests.interface.conftest import Api

VEST = Issue("CONT-04", Severity.MAJOR, "Mira wears a blue vest that is not on her reference sheet")


def fix_vest(confidence: float = 0.9) -> Verdict:
    return verdict(
        Decision.FIX, VEST, confidence=confidence, fix="remove the blue vest", target="girl", parts=("vest",)
    )


async def test_a_draft_is_reviewed_fixed_and_shown_with_its_badge_and_feed(api: Api) -> None:
    api.fakes.reviewer.verdicts = [fix_vest(), verdict(model="muse-glimmer")]
    await api.client.post("/projects/p1/shots/1/panel", json={})
    await api.settle()

    body = (await api.client.get("/projects/p1")).json()
    review = body["shots"][0]["panel"]["review"]
    assert review["outcome"] == "fixed"
    assert review["summary"] == "Fixed: remove the blue vest"
    assert review["model"] == "muse-glimmer"
    assert review["fixes"] == 1
    assert body["shots"][0]["panel"]["revision"] == 2
    assert body["continuity_checks"] is True
    [entry] = body["supervisor"]
    assert entry["outcome"] == "fixed"
    assert entry["rule_ids"] == ["CONT-04"]
    assert entry["message"].endswith("Fixed in 1 try.")


async def test_needs_your_eye_then_apply_suggested_fix_or_accept_anyway(api: Api) -> None:
    api.fakes.reviewer.verdicts = [fix_vest(confidence=0.3)]  # unsure: ask
    await api.client.post("/projects/p1/shots/1/panel", json={})
    await api.settle()
    review = (await api.client.get("/projects/p1")).json()["shots"][0]["panel"]["review"]
    assert review["outcome"] == "needs_user"
    assert review["fix_instruction"] == "remove the blue vest"
    assert review["issues"] == [{"rule_id": "CONT-04", "severity": "major", "description": VEST.description}]

    accepted = await api.client.post("/projects/p1/shots/1/panel/review/accept")
    assert accepted.status_code == 200
    assert accepted.json()["shots"][0]["panel"]["review"]["outcome"] == "accepted"

    # Changed their mind: the suggestion still applies to this render.
    r = await api.client.post("/projects/p1/shots/1/panel/review/apply")
    assert r.status_code == 202
    assert r.json()["kind"] == "edit_panel"


async def test_apply_without_a_suggestion_is_refused(api: Api) -> None:
    await api.client.post("/projects/p1/shots/1/panel", json={})
    await api.settle()  # the fake reviewer passes it
    r = await api.client.post("/projects/p1/shots/1/panel/review/apply")
    assert r.status_code == 422
    assert (await api.client.post("/projects/p1/shots/1/panel/review/accept")).status_code == 422


async def test_continuity_checks_can_be_turned_off(api: Api) -> None:
    r = await api.client.patch("/projects/p1", json={"continuity_checks": False})
    assert r.status_code == 200
    assert r.json()["continuity_checks"] is False
    await api.client.post("/projects/p1/shots/1/panel", json={})
    await api.settle()
    assert api.fakes.reviewer.requests == []
    assert (await api.client.get("/projects/p1")).json()["shots"][0]["panel"]["review"] is None


async def test_supervisor_events_go_to_the_client(api: Api) -> None:
    api.fakes.reviewer.verdicts = [verdict(Decision.ASK, VEST)]
    await api.client.post("/projects/p1/shots/1/panel", json={})
    await api.settle()
    p = api.project()
    assert p.panel("s1").review is not None
    message = event_message(SupervisorNeedsUser(p.supervisor_log[-1], (VEST,), "", 1))
    assert message["type"] == "supervisor.needs_user"
    assert message["entry"]["shot_id"] == "s1"
    assert message["issues"][0]["rule_id"] == "CONT-04"
    assert message["revision"] == 1
