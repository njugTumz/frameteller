"""Words in any script: Japanese and Chinese split by characters, other scripts by spaces."""

# ruff: noqa: RUF001  (full-width punctuation and curly quotes are the text under test)
from frameteller.domain import is_cjk, join, tokens, units

JA = "夜の屋上で、リナは「紙の凧」を拾った。"
ZH = "夜幕降临，丽娜接住了一只纸风筝。"
KO = "밤이 오면 리나는 연을 잡는다."
HI = "अपनी कहानी सुनाएँ frameteller.com पर"
AR = "احكِ قصتك على frameteller.com"


def test_japanese_and_chinese_split_into_characters_with_their_punctuation() -> None:
    assert tokens(JA)[:6] == ["夜", "の", "屋", "上", "で、", "リ"]
    assert "「紙" in tokens(JA)
    assert tokens(JA)[-1] == "た。"
    assert tokens(ZH)[3] == "临，"
    assert tokens("ラーメン") == ["ラー", "メ", "ン"]  # the prolonged sound mark stays with its kana


def test_spaced_scripts_split_into_words() -> None:
    assert tokens("Lena’s kite, “up” high…") == ["Lena’s", "kite,", "“up”", "high…"]
    assert tokens(KO) == ["밤이", "오면", "리나는", "연을", "잡는다."]
    assert tokens(HI) == ["अपनी", "कहानी", "सुनाएँ", "frameteller.com", "पर"]
    assert tokens(AR) == ["احكِ", "قصتك", "على", "frameteller.com"]


def test_join_puts_every_script_back_as_written() -> None:
    for text in (JA, ZH, KO, HI, AR, "Lena’s kite, “up” high…", "ラーメンを食べた。Lenaは笑った。"):
        assert join(tokens(text)) == text
    assert join(["Hello", "there."]) == "Hello there."
    assert join(["猫", "Lena", "は"]) == "猫Lenaは"


def test_units_count_words_or_characters() -> None:
    assert units("A paper kite drifts down.") == 5
    assert units(JA) == 15  # characters, punctuation left out
    assert units(KO) == 12
    assert units(HI) == 5
    assert (is_cjk(JA), is_cjk(ZH), is_cjk(KO), is_cjk(HI), is_cjk(AR)) == (True, True, True, False, False)
