"""The teleprompter finds where a paragraph's reading ends, tolerating what the transcriber gets wrong."""

# ruff: noqa: RUF001  (full-width punctuation and curly quotes are the text under test)
from frameteller.application.teleprompter import normalise, paragraph_end

KITE = "A paper kite drifts down and tangles in the old antenna."


def heard(text: str) -> list[str]:
    return normalise(text)


def test_read_exactly_ends_at_the_last_word() -> None:
    words = heard("A paper kite drifts down and tangles in the old antenna")
    assert paragraph_end(KITE, words) == len(words) - 1


def test_misheard_and_dropped_words_still_line_up() -> None:
    words = heard("a paper kite drifts down and tangle in the ole antena")
    assert paragraph_end(KITE, words) == len(words) - 1


def test_a_misheard_last_word_stays_with_its_paragraph() -> None:
    words = heard("a paper kite drifts down and tangles in the old antimony lena reaches up")
    assert paragraph_end(KITE, words) == 10  # "antimony", not "old"


def test_a_missing_last_word_is_tolerated_when_the_rest_of_the_tail_is_there() -> None:
    words = heard("a paper kite drifts down and tangles in the old")
    assert paragraph_end(KITE, words) == len(words) - 1


def test_not_finished_yet() -> None:
    assert paragraph_end(KITE, heard("a paper kite drifts down and")) is None


def test_the_tail_words_said_too_early_do_not_count() -> None:
    # "the old antenna" alone, before most of the paragraph was read
    assert paragraph_end(KITE, heard("the old antenna")) is None


def test_reading_on_into_the_next_paragraph_cuts_at_the_end_of_this_one() -> None:
    words = heard("a paper kite drifts down and tangles in the old antenna Lena reaches up to free it")
    assert paragraph_end(KITE, words) == 10  # "antenna"


def test_numbers_and_accents_match_either_way() -> None:
    assert paragraph_end("She counts 3 pigeons on the café roof.", heard("she counts three pigeons on the cafe roof"))


def test_a_short_paragraph() -> None:
    assert paragraph_end("Night falls.", heard("night falls")) == 1
    assert paragraph_end("Night falls.", heard("night")) is None


def test_tail_words_that_turn_up_by_chance_in_another_reading_do_not_count() -> None:
    # Measured on staging: the Mira recording read against the lighthouse script matched this tail by chance.
    paragraph = "A tiny lighthouse on a rock in the middle of a stormy sea. Waves crash all around it."
    words = heard(
        "Scene one night a narrow alley in the rain Mira a girl in a yellow raincoat with a red scarf walks home "
        "alone she hears a tiny sound under a wooden crate Mira walks out of the alley with the cat on her "
        "shoulder the rain stops close up on the cat it looks back at the alley"
    )
    assert paragraph_end(paragraph, words) is None


def test_japanese_and_chinese_match_by_characters() -> None:
    assert normalise("リナは「紙の凧」を拾った。") == ["リ", "ナ", "は", "紙", "の", "凧", "を", "拾", "っ", "た"]
    assert normalise("Lenaは3匹") == ["lena", "は", "three", "匹"]
    paragraph = "夜の屋上で、リナは紙の凧を拾った。"
    heard = normalise("夜の屋上でリナは紙の凧を拾った次の段落")
    assert paragraph_end(paragraph, heard) == heard.index("た")
    assert paragraph_end(paragraph, normalise("夜の屋上でリナは紙の")) is None  # not at the end yet
    misheard = normalise("夜の屋上でリナは紙の旅を広った")  # two characters misheard
    assert paragraph_end(paragraph, misheard) == len(misheard) - 1
    zh = "夜幕降临，丽娜接住了一只纸风筝。"
    assert paragraph_end(zh, normalise("夜幕降临丽娜接住了一只纸风筝")) == 13


def test_korean_hindi_and_arabic_keep_their_words() -> None:
    assert normalise("밤이 오면, 리나는.") == ["밤이", "오면", "리나는"]
    assert normalise("अपनी कहानी सुनाएँ।") == ["अपनी", "कहानी", "सुनाएँ"]  # vowel signs stay
    assert normalise("احكِ قصتك!") == ["احكِ", "قصتك"]
    assert paragraph_end("밤이 오면 리나는 연을 잡는다.", normalise("밤이 오면 리나는 연을 잡는다")) == 4
