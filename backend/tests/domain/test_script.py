"""Scripts (ADR 0015): one beat per paragraph, episodes, framing cues kept for the director, Fountain."""

import pytest

from frameteller.domain import InvalidValueError
from frameteller.domain.script import ScriptFormat, parse_script, split_cues

ROOFTOP = """Night on a city rooftop. Lena feeds pigeons beside a humming air vent.

Wide shot. The skyline glitters behind her.

A paper kite drifts down and tangles in the antenna.

Close-up on Lena's hands as she frees it.
"""


def test_each_paragraph_is_one_beat_and_lines_inside_a_paragraph_join() -> None:
    script = parse_script("A rooftop at night.\nLena feeds pigeons.\n\nA kite drifts down.")
    [episode] = script.episodes
    assert [b.narration for b in episode.beats] == ["A rooftop at night. Lena feeds pigeons.", "A kite drifts down."]


def test_framing_cues_go_to_the_director_and_are_not_read_aloud() -> None:
    beats = parse_script(ROOFTOP).episodes[0].beats
    assert beats[1].narration == "The skyline glitters behind her."
    assert beats[1].direction == "Wide shot. The skyline glitters behind her."
    assert beats[3].narration == "Close-up on Lena's hands as she frees it."  # a long cue tells something: read
    assert len(beats) == 4


def test_cues_after_the_last_beat_direct_it() -> None:
    [beat] = parse_script("The kite rises.\n\nSlow push-in. Fade out.").episodes[0].beats
    assert beat.narration == "The kite rises."
    assert beat.direction == "The kite rises. Slow push-in. Fade out."


def test_a_paragraph_of_cues_alone_directs_the_next_beat() -> None:
    beats = parse_script("Wide shot.\n\nThe kite rises over the city.").episodes[0].beats
    assert [(b.narration, b.direction) for b in beats] == [
        ("The kite rises over the city.", "Wide shot. The kite rises over the city.")
    ]


@pytest.mark.parametrize(
    "cue",
    [
        "Wide shot.",
        "Close-up on the lamp.",
        "Close up.",
        "Extreme close-up.",
        "Medium shot.",
        "Over-the-shoulder.",
        "Low angle.",
        "Aerial shot.",
        "Establishing shot.",
        "POV.",
        "Cut to the street.",
        "Angle on the door.",
    ],
)
def test_framing_vocabulary(cue: str) -> None:
    assert split_cues(f"{cue} Lena laughs.") == ("Lena laughs.", cue)


def test_words_that_only_look_like_cues_are_read() -> None:
    assert split_cues("Wider than ever, the sky opens. Closer now, she waves.")[1] == ""


@pytest.mark.parametrize("heading", ["Episode 2", "EPISODE 2", "Ep. 2", "Ep 2", "episode 2: The Storm", "# Episode 2"])
def test_every_episode_heading_starts_a_new_episode(heading: str) -> None:
    script = parse_script(f"Lena climbs the stairs.\n\n{heading}\n\nThe storm arrives.", ScriptFormat.MARKDOWN)
    assert [(e.number, [b.narration for b in e.beats]) for e in script.episodes] == [
        (1, ["Lena climbs the stairs."]),
        (2, ["The storm arrives."]),
    ]


def test_a_script_that_starts_with_episode_one_has_no_empty_episode() -> None:
    script = parse_script("Episode 1\n\nLena wakes.\n\nEpisode 2\nThe kite returns.\n\nShe smiles.")
    assert [len(e.beats) for e in script.episodes] == [1, 2]
    assert [n for n, _ in script.beats] == [1, 2, 2]


def test_markdown_titles_lists_and_emphasis_are_cleaned() -> None:
    script = parse_script("# The Kite\n\n- **Lena** finds a *paper* kite.", ScriptFormat.MARKDOWN)
    assert [b.narration for b in script.episodes[0].beats] == ["Lena finds a paper kite."]


FOUNTAIN = """Title: The Kite
Author: Frameteller tests

EPISODE 1

INT. STAIRWELL - NIGHT

Lena climbs, two steps at a time. [[a note]]

LENA (V.O.)
(whispering)
Almost there.

CUT TO:

EXT. ROOFTOP - NIGHT

/* an old idea */
Wide shot. Pigeons scatter.

= a synopsis

# Act one

.TOWER ROOM

A kite flutters in.
"""


def test_fountain_scene_headings_direct_the_next_beat_and_noise_is_dropped() -> None:
    [episode] = parse_script(FOUNTAIN, ScriptFormat.FOUNTAIN).episodes
    assert [(b.narration, b.direction) for b in episode.beats] == [
        ("Lena climbs, two steps at a time.", "Scene: INT. STAIRWELL - NIGHT. Lena climbs, two steps at a time."),
        ("Lena says: Almost there.", 'Lena says: "Almost there."'),
        ("Pigeons scatter.", "Scene: EXT. ROOFTOP - NIGHT. Wide shot. Pigeons scatter."),
        ("A kite flutters in.", "Scene: TOWER ROOM. A kite flutters in."),
    ]


def test_fountain_episodes() -> None:
    script = parse_script("EPISODE 1\n\nLena waves.\n\nEPISODE 2\n\nEXT. PARK - DAY\n\nA kite.", ScriptFormat.FOUNTAIN)
    assert [len(e.beats) for e in script.episodes] == [1, 1]
    assert script.episodes[1].beats[0].direction == "Scene: EXT. PARK - DAY. A kite."


def test_an_empty_script_is_refused() -> None:
    with pytest.raises(InvalidValueError):
        parse_script("\n\n  \nEpisode 1\n\n")
