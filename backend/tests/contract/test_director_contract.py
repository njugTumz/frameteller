import json
from collections.abc import Callable
from typing import Any

import httpx2
import pytest
from openai import AsyncOpenAI

from frameteller.application.errors import InvalidModelOutputError
from frameteller.application.ports import LookChange
from frameteller.domain import Framing, Project, TranscriptTurn
from frameteller.infrastructure.config import Settings
from frameteller.infrastructure.meta.director import SYSTEM_PROMPT, MetaSparkDirectorAdapter
from frameteller.infrastructure.resilience import ModelCaller
from tests.builders import FARMER, costume_project, costume_turn, project
from tests.contract.conftest import FAKE_KEY
from tests.fakes import InMemorySpendLedger
from tests.fixtures import load, replay

TURN_4 = TranscriptTurn("t4", "Mira smiles and holds out her hand. The cat steps into the light.", 21600, 26800)

Client = Callable[[httpx2.MockTransport], AsyncOpenAI]


def story() -> Project:
    p = project(approved=True, shots=0)
    p.add_turn(TURN_4)
    return p


def body(request: httpx2.Request) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(request.content)
    return data


def with_content(content: str) -> dict[str, Any]:
    """The recorded exchange with a different model answer, for the validation-retry path."""
    ex = load("director_turn")[0]
    b = json.loads(ex["body"])
    b["choices"][0]["message"]["content"] = content
    return {**ex, "body": json.dumps(b)}


async def test_turn_becomes_shots_timed_by_the_turn(
    client_for: Client, caller: ModelCaller, settings: Settings, ledger: InMemorySpendLedger
) -> None:
    transport, seen = replay("director_turn")
    director = MetaSparkDirectorAdapter(client_for(transport), caller, settings)

    out = await director.direct_turn(TURN_4, story())

    assert out.new_characters == ()
    assert out.shots
    assert all(s.source_turn_ids == ("t4",) for s in out.shots)
    assert {c for s in out.shots for c in s.character_ids} <= {"mira", "cat"}
    assert sum(s.duration_ms for s in out.shots) == pytest.approx(TURN_4.duration_ms, abs=len(out.shots))
    assert all(isinstance(s.framing, Framing) for s in out.shots)

    request = seen[0]
    assert request.url.path == "/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
    sent = body(request)
    assert sent["model"] == "muse-spark-1.3-contributor"
    assert sent["reasoning_effort"] == "minimal"
    assert sent["response_format"]["type"] == "json_schema"
    assert sent["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert sent["messages"][1]["content"].startswith("Character bible:\n")

    [usage] = ledger.usage
    assert usage.model == "muse-spark-1.3-contributor"
    assert usage.ok
    assert (usage.input_tokens, usage.output_tokens, usage.cached_tokens) == (714, 253, 0)
    assert 0 < usage.cost_usd < 0.001


async def test_stable_prefix_is_identical_across_turns(
    client_for: Client, caller: ModelCaller, settings: Settings
) -> None:
    recorded = json.loads(json.loads(load("director_turn")[0]["body"])["choices"][0]["message"]["content"])
    for s in recorded["shots"]:
        s["source_turn_ids"] = ["t5"]
    transport, seen = replay([*load("director_turn"), with_content(json.dumps(recorded))])
    director = MetaSparkDirectorAdapter(client_for(transport), caller, settings)
    p = story()
    p.add_turn(TranscriptTurn("t5", "Wide shot. The rain stops.", 26800, 30000))

    await director.direct_turn(TURN_4, p)
    await director.direct_turn(p.turns[-1], p)

    first, second = (body(r)["messages"] for r in seen)
    assert first[:2] == second[:2]  # system prompt + bible: the cacheable prefix
    assert first[2] != second[2]


async def test_invalid_answer_is_retried_once_with_the_error(
    client_for: Client, caller: ModelCaller, settings: Settings
) -> None:
    bad = json.dumps(
        {
            "new_characters": [],
            "shots": [
                {
                    "framing": "wide",
                    "character_ids": ["ghost"],
                    "setting": "alley",
                    "action": "a ghost",
                    "dialogue": "",
                    "source_turn_ids": ["t4"],
                }
            ],
        }
    )
    transport, seen = replay([with_content(bad), *load("director_turn")])
    director = MetaSparkDirectorAdapter(client_for(transport), caller, settings)

    out = await director.direct_turn(TURN_4, story())

    assert out.shots
    retry = body(seen[1])["messages"]
    assert retry[-2]["role"] == "assistant"
    assert "ghost" in retry[-1]["content"]
    assert "failed validation" in retry[-1]["content"]


async def test_gives_up_after_two_invalid_answers(client_for: Client, caller: ModelCaller, settings: Settings) -> None:
    transport, _ = replay([with_content("not json"), with_content("{}")])
    director = MetaSparkDirectorAdapter(client_for(transport), caller, settings)

    with pytest.raises(InvalidModelOutputError):
        await director.direct_turn(TURN_4, story())


async def test_edit_instruction_is_routed_to_target_parts_and_change(
    client_for: Client, caller: ModelCaller, settings: Settings
) -> None:
    transport, seen = replay("director_edit")
    director = MetaSparkDirectorAdapter(client_for(transport), caller, settings)
    p = project(approved=True, shots=2)

    intent = await director.interpret_edit("her coat is red now", p.shot("s1"), [p.bible.get("mira")])

    assert intent.target == "girl in the yellow raincoat"
    assert intent.parts == ("raincoat", "hood", "sleeves")
    assert intent.change == "make it red"
    sent = body(seen[0])
    assert sent["reasoning_effort"] == "minimal"
    assert sent["messages"][2]["content"].endswith("Instruction: her coat is red now")
    assert "mira" in sent["messages"][1]["content"]


async def test_a_reveal_revises_one_of_the_last_three_shots(
    client_for: Client, caller: ModelCaller, settings: Settings
) -> None:
    p = project(approved=True, shots=4)  # shots 2-4 are revisable, shot 1 is not
    turn = TranscriptTurn("t5", "It was the cat all along.", 16000, 20000)
    p.add_turn(turn)

    def answer(number: int) -> dict[str, Any]:
        return with_content(
            json.dumps(
                {
                    "new_characters": [],
                    "shots": [
                        {
                            "framing": "medium",
                            "character_ids": ["cat"],
                            "setting": "alley",
                            "action": "The cat purrs",
                            "dialogue": "",
                            "source_turn_ids": ["t5"],
                        }
                    ],
                    "updated_shots": [{"number": number, "character_ids": ["cat"], "action": "The cat hides"}],
                }
            )
        )

    transport, seen = replay([answer(1), answer(3)])
    out = await MetaSparkDirectorAdapter(client_for(transport), caller, settings).direct_turn(turn, p)

    assert len(seen) == 2  # shot 1 is too old: retried with the error
    assert "shot 1 is not one of the last shots [2, 3, 4]" in seen[1].content.decode()
    assert [(r.shot_id, r.character_ids, r.action) for r in out.revisions] == [("s3", ("cat",), "The cat hides")]
    assert "updated_shots" in body(seen[0])["response_format"]["json_schema"]["schema"]["properties"]


async def test_older_answers_without_updated_shots_still_parse(
    client_for: Client, caller: ModelCaller, settings: Settings
) -> None:
    transport, _ = replay("director_turn")
    out = await MetaSparkDirectorAdapter(client_for(transport), caller, settings).direct_turn(TURN_4, story())
    assert out.revisions == ()


async def test_a_real_person_or_a_franchise_character_is_refused_with_a_reason(
    client_for: Client, caller: ModelCaller, settings: Settings
) -> None:
    no = "Frameteller draws original characters only. Who would you like in this scene instead?"
    transport, seen = replay([with_content(json.dumps({"new_characters": [], "shots": [], "refusal": f" {no} "}))])

    out = await MetaSparkDirectorAdapter(client_for(transport), caller, settings).direct_turn(TURN_4, story())

    assert (out.shots, out.new_characters, out.refusal) == ((), (), no)
    assert "original" in body(seen[0])["messages"][0]["content"]  # the rule is in the stable system prompt


def costume_answer(from_shot: int, turn_id: str = "t2") -> dict[str, Any]:
    return with_content(
        json.dumps(
            {
                "new_characters": [],
                "shots": [
                    {
                        "framing": "medium",
                        "character_ids": ["wren"],
                        "setting": "her bedroom",
                        "action": "Wren puts on her farmer costume and grins at the mirror",
                        "dialogue": "",
                        "source_turn_ids": [turn_id],
                    }
                ],
                "outfit_changes": [
                    {
                        "character_id": "wren",
                        "look_id": "farmer_costume",
                        "label": "Farmer costume",
                        "clothes": FARMER.clothes,
                        "from_shot": from_shot,
                    }
                ],
            }
        )
    )


def costume_story() -> Project:
    p = costume_project(looks=False)
    p.shots, p.turns = p.shots[:1], p.turns[:1]
    p.add_turn(costume_turn(2))
    return p


async def test_a_costume_is_recorded_from_the_shot_that_shows_it(
    client_for: Client, caller: ModelCaller, settings: Settings
) -> None:
    transport, seen = replay([costume_answer(9), costume_answer(2)])
    out = await MetaSparkDirectorAdapter(client_for(transport), caller, settings).direct_turn(
        costume_turn(2), costume_story()
    )

    assert len(seen) == 2  # shot 9 does not exist: retried with the error
    assert "outfit_changes: from_shot 9 is not one of [1, 2]" in seen[1].content.decode()
    assert out.looks == (LookChange("wren", "farmer_costume", "Farmer costume", FARMER.clothes, 2),)
    sent = body(seen[0])
    assert "outfit_changes" in sent["response_format"]["json_schema"]["schema"]["properties"]
    assert "outfit_changes" in sent["messages"][0]["content"]


async def test_the_director_sees_each_characters_looks_and_who_wears_what(
    client_for: Client, caller: ModelCaller, settings: Settings
) -> None:
    transport, seen = replay([costume_answer(7, "t7")])  # the new shot (7) stays in the costume
    p = costume_project()
    p.add_turn(TranscriptTurn("t7", "Wren takes a bow.", 48000, 52000))
    await MetaSparkDirectorAdapter(client_for(transport), caller, settings).direct_turn(p.turns[-1], p)

    messages = body(seen[0])["messages"]
    bible = json.loads(messages[1]["content"].removeprefix("Character bible:\n"))
    assert bible[1]["looks"] == [{"look_id": "farmer_costume", "label": "Farmer costume", "clothes": FARMER.clothes}]
    assert "looks" not in bible[0]  # Dad has only his everyday clothes
    shots = json.loads(messages[2]["content"].split("Shots so far:\n")[1].split("\n\nDirect")[0])
    assert [s.get("looks") for s in shots] == [None, *[{"wren": "farmer_costume"}] * 5]
