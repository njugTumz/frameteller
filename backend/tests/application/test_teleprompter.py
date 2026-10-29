"""The teleprompter finds where a paragraph's reading ends, tolerating what the transcriber gets wrong."""

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
