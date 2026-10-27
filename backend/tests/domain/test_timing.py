import pytest

from frameteller.domain import MIN_SHOT_MS, split_duration


@pytest.mark.parametrize(
    ("total", "words"),
    [(29920, [12, 8, 9, 15, 11]), (10000, [10, 5, 5]), (9840, [9]), (7001, [1, 1, 1]), (4000, [50, 1, 1])],
)
def test_parts_always_add_up_to_the_turn(total: int, words: list[int]) -> None:
    assert sum(split_duration(total, words)) == total


def test_split_follows_word_counts() -> None:
    assert split_duration(10000, [10, 5, 5]) == [5000, 2500, 2500]
    assert split_duration(9840, [9]) == [9840]
    assert split_duration(1000, []) == []


def test_every_shot_gets_at_least_one_and_a_half_seconds() -> None:
    parts = split_duration(10000, [60, 1, 1])
    assert parts[1:] == [MIN_SHOT_MS, MIN_SHOT_MS]
    assert parts[0] == 10000 - 2 * MIN_SHOT_MS
    assert split_duration(10000, [0, 0]) == [5000, 5000]  # no words still counts as one


def test_a_turn_too_short_for_the_minimum_is_split_evenly() -> None:
    assert split_duration(4000, [50, 1, 1]) == [1334, 1333, 1333]
    assert split_duration(2, [1, 1, 1]) == [1, 1, 1]  # never a zero-length shot
