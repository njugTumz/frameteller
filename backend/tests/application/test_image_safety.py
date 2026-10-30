"""What reaches Muse Image (ADR 0019): no exact ages, family relationships or body words, one plainer retry after
a refusal, and a concrete suggestion (not the same request again) after a second one."""

from dataclasses import replace

import pytest

from frameteller.application.errors import ModelContentFilteredError, RefusedUnchangedError
from frameteller.application.image_safety import (
    SafeImages,
    appearance_only,
    plainer,
    sanitize,
    suggest_clothes,
    suggest_description,
)
from frameteller.application.ports import EditRequest, ImageRequest
from frameteller.application.use_cases import (
    ApproveCast,
    GenerateCastReferences,
    GenerateCharacterReference,
    GeneratePanel,
    RequestCastReferences,
)
from frameteller.application.use_cases.generate_character_reference import SheetFailedError
from frameteller.domain import MediaRef, Project, SheetRefusal
from tests.builders import COSTUME, FARMER, costume_project
from tests.fakes import (
    FakeImageGeneration,
    InMemoryJobQueue,
    InMemoryMediaStorage,
    InMemoryProjectRepository,
    RecordingBudget,
    RecordingPublisher,
    SequentialIds,
)

REFUSED = ModelContentFilteredError("muse-image-1.0", "HTTP 400 content filter")

# The three descriptions production refused on Oct 30 (first tries at their sheets).
PRODUCTION_REFUSED = [
    "human female with average build and expressive face",
    "adult human female with round face and dark hair tied back",
    "adult human man of average build with a plain face and short dark hair",
]


@pytest.mark.parametrize(
    ("text", "clean"),
    [
        ("my 6-year-old daughter Wren, small build, curly brown hair", "the child Wren, curly brown hair"),
        ("Wren runs downstairs to show her dad, who claps.", "Wren runs downstairs to show the man, who claps."),
        ("My son Kito, aged 7, in a green shirt", "The child Kito, young, in a green shirt"),
        ("human female with average build and expressive face", "human female with expressive face"),
        ("adult human man of average build with a plain face", "adult human man with a plain face"),
        ("a 40-year-old baker with a full-body apron", "an adult baker with an apron"),
        ("large tiger with orange fur, muscular build, feline face", "large tiger with orange fur, feline face"),
        ("Two years later, Wren grins.", "Two years later, Wren grins."),  # not an age
        ("small orange fox", "small orange fox"),
    ],
)
def test_prompts_lose_exact_ages_family_relationships_and_body_words(text: str, clean: str) -> None:
    assert sanitize(text) == clean


def test_the_plainer_wordings_keep_only_the_look() -> None:
    assert appearance_only("human 12-year-old girl, small build, round face, orange headscarf") == (
        "round face, orange headscarf"
    )
    assert suggest_description("my 6-year-old daughter, small build, curly brown hair, purple pyjamas") == (
        "cheerful young storybook character with curly brown hair, purple pyjamas"
    )
    assert suggest_description(PRODUCTION_REFUSED[2]) == (
        "friendly storybook character with a plain face and short dark hair"
    )
    assert (
        suggest_description("small orange fox with a white-tipped tail") == "small orange fox with a white-tipped tail"
    )
    assert suggest_clothes(FARMER.clothes) == FARMER.clothes
    assert plainer("Edit the little girl's coat: make it red.") == "Edit the character's coat: make it red."


@pytest.mark.parametrize("description", PRODUCTION_REFUSED)
def test_the_production_refusals_are_now_asked_as_fully_clothed_storybook_characters(description: str) -> None:
    from frameteller.application.prompts import reference_prompt
    from frameteller.domain import Character

    prompt = sanitize(reference_prompt(Character("x", "X", description)))
    assert "full body" not in prompt
    assert "build" not in prompt
    assert "fully clothed, friendly standing pose" in prompt


async def test_every_prompt_is_cleaned_and_a_refusal_gets_one_plainer_try() -> None:
    fake = FakeImageGeneration(InMemoryMediaStorage())
    images = SafeImages(fake)
    await images.generate(ImageRequest("Draw my daughter, 6 years old, small build", "low", "panel"), "a")
    assert fake.generated[-1].prompt == "Draw the child, young"

    fake.refuse = [REFUSED]
    await images.generate(ImageRequest("first wording", "low", "panel", fallback_prompt="her 5-year-old son"), "b")
    assert [r.prompt for r in fake.generated[-2:]] == ["first wording", "the child"]

    fake.refuse = [REFUSED, REFUSED]
    with pytest.raises(ModelContentFilteredError):
        await images.generate(ImageRequest("again", "low", "panel"), "c")
    assert len(fake.generated) == 5  # one retry only


async def test_an_edit_is_cleaned_too() -> None:
    fake = FakeImageGeneration(InMemoryMediaStorage())
    await SafeImages(fake).edit(EditRequest(MediaRef("p.webp"), "Make my daughter's coat red", "high"), "e")
    assert fake.edits[0].prompt == "Make the child's coat red"


def told_by_a_parent() -> Project:
    """The costume story as a parent tells it: "my daughter", her age, her build; costume from shot 2."""
    p = costume_project()
    wren = p.bible.get("wren")
    p.upsert_character(replace(wren, canonical_description="my 6-year-old daughter, small build, curly brown hair"))
    p.bible.set_reference("wren", MediaRef("refs/wren.webp"))
    p.bible.set_look_reference("wren", FARMER.id, MediaRef("refs/wren-farmer.webp"))
    p.shots = [
        replace(s, action=COSTUME[s.number - 1].replace("Wren", "my daughter", 1).replace("her dad", "her daddy"))
        for s in p.shots
    ]
    p.bible.approve()
    return p


async def test_the_parents_costume_story_reaches_muse_image_without_age_family_or_body_words() -> None:
    fake = FakeImageGeneration(InMemoryMediaStorage())
    repo, budget = InMemoryProjectRepository(told_by_a_parent()), RecordingBudget()
    images = SafeImages(fake)
    for target in ("wren", "wren/farmer_costume"):
        await GenerateCastReferences(
            GenerateCharacterReference(repo, images, budget), RecordingPublisher(), repo
        ).execute("p1", [target])
    await ApproveCast(repo, InMemoryJobQueue(), SequentialIds("j")).execute("p1")
    for s in repo.peek("p1").shots:
        await GeneratePanel(repo, images, budget, InMemoryJobQueue()).execute("p1", s.id, 1)

    prompts = [r.prompt for r in fake.generated]
    assert len(prompts) == 8  # two sheets, six panels
    for prompt in prompts:
        for word in ("daughter", "daddy", "6-year-old", "build", "full body"):
            assert word not in prompt, (word, prompt)
    assert "a storybook illustration of a cheerful young character, with curly brown hair" in prompts[0]
    assert "fully clothed, friendly standing pose" in prompts[0]
    assert all("wears the farmer costume: blue denim overalls" in p for p in prompts[3:])
    assert repo.peek("p1").bible.get("wren").canonical_description.startswith("my 6-year-old daughter")  # as told


async def test_a_sheet_refused_twice_offers_a_suggestion_and_blocks_the_same_try_again() -> None:
    fake = FakeImageGeneration(InMemoryMediaStorage())
    fake.refuse = [REFUSED, REFUSED]
    repo, jobs = InMemoryProjectRepository(told_by_a_parent()), InMemoryJobQueue()
    with pytest.raises(SheetFailedError, match="twice"):
        await GenerateCharacterReference(repo, SafeImages(fake), RecordingBudget()).execute("p1", "wren")
    told = "my 6-year-old daughter, small build, curly brown hair"
    assert repo.peek("p1").sheet_refusals["wren"] == SheetRefusal(
        told, "cheerful young storybook character with curly brown hair"
    )
    assert "all-ages family story" in fake.generated[1].prompt  # the retry was by look only

    request = RequestCastReferences(repo, jobs, SequentialIds("c"))
    with pytest.raises(RefusedUnchangedError):
        await request.execute("p1", ["wren"], again=True)
    assert (await request.execute("p1", ["wren"])).enqueued  # the director's own queueing is never blocked

    # Use this description: the cast approval redraws with it, and a drawn sheet clears the refusal.
    await ApproveCast(repo, jobs, SequentialIds("j")).execute(
        "p1", {"wren": "cheerful young storybook character with curly brown hair"}
    )
    assert (await request.execute("p1", ["wren"], again=True)).enqueued
    await GenerateCharacterReference(repo, SafeImages(fake), RecordingBudget()).execute("p1", "wren")
    assert repo.peek("p1").sheet_refusals == {}


async def test_a_refused_outfit_suggests_plain_clothes() -> None:
    fake = FakeImageGeneration(InMemoryMediaStorage())
    fake.refuse = [REFUSED, REFUSED]
    repo = InMemoryProjectRepository(told_by_a_parent())
    with pytest.raises(SheetFailedError, match="Farmer costume"):
        await GenerateCharacterReference(repo, SafeImages(fake), RecordingBudget()).execute(
            "p1", "wren", look_id=FARMER.id
        )
    assert repo.peek("p1").sheet_refusals["wren/farmer_costume"].suggestion == FARMER.clothes
